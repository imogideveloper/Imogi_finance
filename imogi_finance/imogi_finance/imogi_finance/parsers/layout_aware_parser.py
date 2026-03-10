# -*- coding: utf-8 -*-
# Copyright (c) 2026, Imogi Finance and contributors
# For license information, please see license.txt

"""
Layout-Aware OCR Parser for Indonesian Tax Invoices (Faktur Pajak).

Uses coordinate-based extraction from Google Vision API bounding boxes to
accurately map label → value pairs by spatial position, preventing the
field-swap bug where PPN gets stored in DPP.

Key Principle:
    Instead of relying on regex-only text matching (which confuses labels
    that appear close together), this parser:
    1. Extracts all tokens with their (x, y) bounding boxes
    2. Finds label tokens by pattern matching
    3. Finds value tokens by spatial position (same row, rightward column)
    4. Auto-detects the value column range from token distribution
    5. Validates that extracted values are internally consistent

Indonesian Tax Invoice Layout (normalized 0.0–1.0 coordinates):
    ┌─────────────────────────────────────────────────────────────────┐
    │                         Faktur Pajak                           │
    │                                                                │
    │  Label Column (x ≈ 0.05–0.55)     Value Column (x ≈ 0.55–0.95)│
    │                                                                │
    │  Harga Jual / Penggantian               4.953.154,00          │ y≈0.58
    │  Dikurangi Potongan Harga                 247.658,00          │ y≈0.60
    │  Dikurangi Uang Muka...                          -            │ y≈0.62
    │  Dasar Pengenaan Pajak                  4.313.371,00          │ y≈0.64 ⭐
    │  Jumlah PPN (Pajak...)                    517.605,00          │ y≈0.66 ⭐
    │  Jumlah PPnBM (Pajak...)                        0,00          │ y≈0.68
    └─────────────────────────────────────────────────────────────────┘
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Any

import frappe
from frappe import _

from .normalization import parse_indonesian_currency
from .vision_helpers import _resolve_full_text_annotation


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class BoundingBox:
    """
    Represents an OCR bounding box with utility methods.

    Google Vision API returns normalized coordinates (0.0 to 1.0) where:
      - (0, 0) is the top-left corner of the page
      - (1, 1) is the bottom-right corner
      - X increases left → right
      - Y increases top → bottom

    Attributes:
        x_min: Left edge X coordinate (0.0–1.0)
        y_min: Top edge Y coordinate (0.0–1.0)
        x_max: Right edge X coordinate (0.0–1.0)
        y_max: Bottom edge Y coordinate (0.0–1.0)
    """

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def center_x(self) -> float:
        """Horizontal center of the bounding box."""
        return (self.x_min + self.x_max) / 2.0

    @property
    def center_y(self) -> float:
        """Vertical center of the bounding box."""
        return (self.y_min + self.y_max) / 2.0

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    def is_same_row(self, other: "BoundingBox", tolerance: float = 0.012) -> bool:
        """
        Check if two bounding boxes are on the same visual row.

        Uses center-Y comparison with configurable tolerance.
        Default tolerance 0.012 corresponds to ~1.2% of page height,
        roughly one text line in a standard A4 invoice.

        Args:
            other: Another bounding box to compare with.
            tolerance: Maximum allowed Y-center distance (normalized).

        Returns:
            True if boxes are on the same horizontal row.
        """
        return abs(self.center_y - other.center_y) <= tolerance

    def is_right_of(self, other: "BoundingBox", gap: float = 0.01) -> bool:
        """
        Check if this box is to the right of another box.

        Args:
            other: The reference bounding box.
            gap: Minimum horizontal gap (default 1% page width).

        Returns:
            True if this box starts to the right of the other box.
        """
        return self.x_min > (other.x_max - gap)

    def is_below(self, other: "BoundingBox", max_distance: float = 0.04) -> bool:
        """
        Check if this box is directly below another, within max_distance.

        Args:
            other: The reference bounding box.
            max_distance: Maximum vertical gap (normalized).

        Returns:
            True if this box is below the other within the distance limit.
        """
        return 0 < (self.center_y - other.center_y) <= max_distance

    def vertical_overlap(self, other: "BoundingBox") -> float:
        """Return the overlap ratio along the Y-axis (0.0–1.0)."""
        overlap_top = max(self.y_min, other.y_min)
        overlap_bot = min(self.y_max, other.y_max)
        overlap = max(0.0, overlap_bot - overlap_top)
        min_height = min(self.height, other.height)
        if min_height <= 0:
            return 0.0
        return overlap / min_height


@dataclass
class OCRToken:
    """
    A single word/token from OCR output with its spatial position.

    Attributes:
        text: The recognized text content.
        bbox: The bounding box in normalized page coordinates.
        confidence: OCR recognition confidence (0.0–1.0), if available.
        page: Page number (1-based).
    """

    text: str
    bbox: BoundingBox
    confidence: float = 1.0
    page: int = 1

    def __repr__(self):
        return (
            f"OCRToken('{self.text}', "
            f"x=[{self.bbox.x_min:.3f}–{self.bbox.x_max:.3f}], "
            f"y=[{self.bbox.y_min:.3f}–{self.bbox.y_max:.3f}], "
            f"conf={self.confidence:.2f})"
        )

    @property
    def is_numeric(self) -> bool:
        """True if text looks like a number (digits, dots, commas)."""
        cleaned = self.text.replace(".", "").replace(",", "").replace("-", "").strip()
        return bool(cleaned) and cleaned.isdigit()

    @property
    def is_currency_value(self) -> bool:
        """True if text looks like an Indonesian currency amount."""
        return bool(re.match(r"^\d[\d.,]*$", self.text.strip()))


# =============================================================================
# LABEL PATTERNS — ordered by specificity (most specific first)
# =============================================================================
# Each entry is (field_name, list_of_regex_patterns).
# Patterns are tried in order; the first match wins.
# More specific patterns come first to avoid false positives.

SUMMARY_LABEL_PATTERNS: List[Tuple[str, List[re.Pattern]]] = [
    (
        "harga_jual",
        [
            re.compile(r"Harga\s+Jual\s*/\s*Penggantian\s*/\s*Uang\s+Muka\s*/\s*Termin", re.I),
            re.compile(r"Harga\s+Jual\s*/\s*Penggantian\s*/\s*Uang\s+Muka", re.I),
            re.compile(r"Harga\s+Jual\s*/\s*Penggantian", re.I),
            re.compile(r"Harga\s+Jual", re.I),
        ],
    ),
    (
        "potongan_harga",
        [
            re.compile(r"Dikurangi\s+Potongan\s+Harga", re.I),
            re.compile(r"Potongan\s+Harga", re.I),
        ],
    ),
    (
        "uang_muka",
        [
            re.compile(r"Dikurangi\s+Uang\s+Muka\s+yang\s+telah\s+diterima", re.I),
            re.compile(r"Dikurangi\s+Uang\s+Muka", re.I),
        ],
    ),
    (
        "dpp",
        [
            re.compile(r"Dasar\s+Pengenaan\s+Pajak", re.I),
            re.compile(r"DPP\b", re.I),
        ],
    ),
    (
        "ppn",
        [
            re.compile(r"Jumlah\s+PPN\s*\([^)]*\)", re.I),
            re.compile(r"Jumlah\s+PPN\b(?!\s*BM)", re.I),
        ],
    ),
    (
        "ppnbm",
        [
            re.compile(r"Jumlah\s+PPnBM\s*\([^)]*\)", re.I),
            re.compile(r"Jumlah\s+PPnBM", re.I),
            re.compile(r"PPnBM", re.I),
        ],
    ),
]


# =============================================================================
# LAYOUT-AWARE PARSER
# =============================================================================

class LayoutAwareParser:
    """
    Coordinate-based parser for Indonesian tax invoice summary sections.

    Rather than relying purely on text-regex (which can confuse adjacent
    fields like DPP and PPN), this parser:

    1. Converts the Google Vision API response into ``OCRToken`` objects
       that carry bounding-box coordinates.
    2. Reconstructs logical text lines by grouping tokens that share the
       same Y-coordinate row.
    3. Identifies label tokens via regex pattern matching.
    4. Finds the corresponding value in the *same row* (or the row
       directly below) within an auto-detected value column.
    5. Parses the value as Indonesian Rupiah currency.
    6. Validates the full set of extracted amounts for consistency.

    Usage::

        parser = LayoutAwareParser(vision_json=ocr_raw_json)
        result = parser.parse_summary_section()
        # result == {
        #     'harga_jual': 4953154.0,
        #     'dpp': 4313371.0,
        #     'ppn': 517605.0,
        #     ...
        # }
    """

    # Row grouping tolerance — 1.2 % of page height
    ROW_TOLERANCE: float = 0.012

    # Default value column range (overridden by auto-detection)
    DEFAULT_VALUE_COL_X_MIN: float = 0.55
    DEFAULT_VALUE_COL_X_MAX: float = 0.98

    # Summary section usually lives in the bottom 60% of the page
    SUMMARY_Y_MIN: float = 0.40
    SUMMARY_Y_MAX: float = 0.95

    def __init__(
        self,
        vision_json: Optional[Dict[str, Any]] = None,
        tokens: Optional[List[OCRToken]] = None,
        use_normalized_coords: bool = True,
    ):
        """
        Initialize the parser.

        Accepts *either* a raw Google Vision API JSON response *or*
        a pre-built list of ``OCRToken`` objects.

        Args:
            vision_json: Full Google Vision API response dict.
                         Expected structure (with double-nested responses):
                         ``{"responses": [{"responses": [{"fullTextAnnotation": ...}]}]}``
                         or the simpler ``{"fullTextAnnotation": ...}``.
            tokens: Pre-built list of OCRToken objects (skips extraction).
            use_normalized_coords: If True (default), bbox coords are in
                                   0.0–1.0. If False, raw pixel coords are
                                   used and value-column defaults shift.
        """
        self._logger = frappe.logger()
        self._use_normalized = use_normalized_coords

        if tokens is not None:
            self.tokens: List[OCRToken] = tokens
        elif vision_json is not None:
            self.tokens = self._extract_tokens(vision_json)
        else:
            self.tokens = []

        # Build row groups and auto-detect value column
        self._rows: List[Tuple[float, List[OCRToken]]] = []
        self._value_col_range: Tuple[float, float] = (
            self.DEFAULT_VALUE_COL_X_MIN,
            self.DEFAULT_VALUE_COL_X_MAX,
        )
        self._full_text: str = ""

        if self.tokens:
            self._rows = self._group_tokens_by_row()
            self._value_col_range = self._detect_value_column()
            self._full_text = self._reconstruct_full_text()

        self._logger.debug(
            f"[LayoutParser] Initialized with {len(self.tokens)} tokens, "
            f"{len(self._rows)} rows, "
            f"value column x=[{self._value_col_range[0]:.3f}–{self._value_col_range[1]:.3f}]"
        )

    # =========================================================================
    # TOKEN EXTRACTION FROM GOOGLE VISION JSON
    # =========================================================================

    def _extract_tokens(self, vision_json: Dict[str, Any]) -> List[OCRToken]:
        """
        Convert Google Vision API JSON into a list of ``OCRToken`` objects.

        Handles multiple nesting variants:
          - ``{"responses": [{"responses": [{"fullTextAnnotation": ...}]}]}``
          - ``{"responses": [{"fullTextAnnotation": ...}]}``
          - ``{"fullTextAnnotation": ...}``

        For each word, symbols are concatenated into ``text``, and the
        word-level bounding box is extracted from either
        ``normalizedVertices`` (preferred) or ``vertices``.

        Args:
            vision_json: Raw JSON from Google Vision API.

        Returns:
            List of OCRToken with bounding boxes.
        """
        tokens: List[OCRToken] = []

        # --- Unwrap nested responses to reach fullTextAnnotation ---
        # 🔥 FIX: Use shared unwrapper from multirow_parser
        fta = _resolve_full_text_annotation(vision_json)
        if fta is None:
            self._logger.warning("[LayoutParser] No fullTextAnnotation found in OCR JSON")
            return tokens

        # Store the raw combined text for fallback regex matching
        self._raw_full_text = fta.get("text", "")

        pages = fta.get("pages", [])
        if not pages:
            self._logger.warning("[LayoutParser] No pages in fullTextAnnotation")
            return tokens

        for page_idx, page in enumerate(pages):
            page_no = page_idx + 1
            page_width = page.get("width", 1)
            page_height = page.get("height", 1)

            for block in page.get("blocks", []):
                for paragraph in block.get("paragraphs", []):
                    for word in paragraph.get("words", []):
                        symbols = word.get("symbols", [])
                        if not symbols:
                            continue

                        word_text = "".join(
                            sym.get("text", "") for sym in symbols
                        )
                        if not word_text.strip():
                            continue

                        bbox = self._extract_bbox(
                            word, page_width, page_height
                        )
                        if bbox is None:
                            continue

                        # Confidence: word → paragraph → block fallback
                        conf = (
                            word.get("confidence")
                            or paragraph.get("confidence")
                            or block.get("confidence")
                            or 0.0
                        )

                        tokens.append(
                            OCRToken(
                                text=word_text.strip(),
                                bbox=bbox,
                                confidence=float(conf) if conf else 0.0,
                                page=page_no,
                            )
                        )

        self._logger.info(
            f"[LayoutParser] Extracted {len(tokens)} tokens from "
            f"{len(pages)} page(s)"
        )
        return tokens
    def _extract_bbox(
        self,
        word: Dict[str, Any],
        page_width: int,
        page_height: int,
    ) -> Optional[BoundingBox]:
        """
        Extract a ``BoundingBox`` from a Vision API word object.

        Prefers ``normalizedVertices`` (already 0–1). Falls back to
        ``vertices`` and normalizes by page dimensions.
        """
        bb = word.get("boundingBox", {})

        # Try normalizedVertices first
        nverts = bb.get("normalizedVertices", [])
        if len(nverts) >= 4:
            xs = [v.get("x", 0.0) for v in nverts]
            ys = [v.get("y", 0.0) for v in nverts]
            return BoundingBox(
                x_min=min(xs), y_min=min(ys),
                x_max=max(xs), y_max=max(ys),
            )

        # Fallback: raw vertices → normalize
        verts = bb.get("vertices", [])
        if len(verts) >= 4:
            xs = [v.get("x", 0) for v in verts]
            ys = [v.get("y", 0) for v in verts]
            pw = page_width if page_width > 0 else 1
            ph = page_height if page_height > 0 else 1
            if self._use_normalized:
                return BoundingBox(
                    x_min=min(xs) / pw, y_min=min(ys) / ph,
                    x_max=max(xs) / pw, y_max=max(ys) / ph,
                )
            else:
                return BoundingBox(
                    x_min=float(min(xs)), y_min=float(min(ys)),
                    x_max=float(max(xs)), y_max=float(max(ys)),
                )

        return None

    # =========================================================================
    # ROW CLUSTERING
    # =========================================================================

    def _group_tokens_by_row(self) -> List[Tuple[float, List[OCRToken]]]:
        """
        Group tokens into logical rows by Y-coordinate proximity.

        Algorithm:
          1. Sort tokens by center_y.
          2. Walk through sorted list; if the gap to the current row's
             average Y exceeds ``ROW_TOLERANCE``, start a new row.
          3. Within each row, sort tokens left-to-right by center_x.

        Returns:
            Sorted list of ``(row_center_y, [tokens…])`` tuples.
        """
        if not self.tokens:
            return []

        sorted_tokens = sorted(self.tokens, key=lambda t: t.bbox.center_y)

        rows: List[List[OCRToken]] = []
        current_row: List[OCRToken] = [sorted_tokens[0]]
        current_y_sum = sorted_tokens[0].bbox.center_y
        current_y_count = 1

        for tok in sorted_tokens[1:]:
            avg_y = current_y_sum / current_y_count
            if abs(tok.bbox.center_y - avg_y) <= self.ROW_TOLERANCE:
                current_row.append(tok)
                current_y_sum += tok.bbox.center_y
                current_y_count += 1
            else:
                rows.append(current_row)
                current_row = [tok]
                current_y_sum = tok.bbox.center_y
                current_y_count = 1

        if current_row:
            rows.append(current_row)

        # Sort tokens within each row by x, compute row center_y
        result: List[Tuple[float, List[OCRToken]]] = []
        for row_tokens in rows:
            row_tokens.sort(key=lambda t: t.bbox.center_x)
            avg_y = sum(t.bbox.center_y for t in row_tokens) / len(row_tokens)
            result.append((avg_y, row_tokens))

        return result

    def _reconstruct_full_text(self) -> str:
        """Reconstruct full text from rows (for fallback regex)."""
        lines = []
        for _, row_tokens in self._rows:
            line = " ".join(t.text for t in row_tokens)
            lines.append(line)
        return "\n".join(lines)

    # =========================================================================
    # VALUE COLUMN AUTO-DETECTION
    # =========================================================================

    def _detect_value_column(self) -> Tuple[float, float]:
        """
        Auto-detect the value column X-range from token distribution.

        Strategy:
          - Collect center_x of all tokens that look like currency values
            (digits with dots/commas) in the summary region (lower page).
          - If enough currency tokens exist, the value column spans from
            (min_x − padding) to (max_x + padding).
          - Otherwise, fall back to the default range.

        Returns:
            Tuple ``(x_min, x_max)`` for the value column.
        """
        currency_xs: List[float] = []

        for _, row_tokens in self._rows:
            for tok in row_tokens:
                # Only consider tokens in the lower portion of the page
                if tok.bbox.center_y < self.SUMMARY_Y_MIN:
                    continue
                if tok.is_currency_value:
                    currency_xs.append(tok.bbox.center_x)

        if len(currency_xs) < 3:
            self._logger.debug(
                "[LayoutParser] Too few currency tokens for column detection; "
                "using defaults"
            )
            return (self.DEFAULT_VALUE_COL_X_MIN, self.DEFAULT_VALUE_COL_X_MAX)

        # Use the interquartile range to avoid outliers
        currency_xs.sort()
        q1_idx = len(currency_xs) // 4
        q3_idx = 3 * len(currency_xs) // 4
        trimmed = currency_xs[q1_idx: q3_idx + 1] if q3_idx > q1_idx else currency_xs

        x_min = min(trimmed) - 0.05  # 5% left padding
        x_max = max(trimmed) + 0.05  # 5% right padding

        # Clamp to page bounds
        x_min = max(0.0, x_min)
        x_max = min(1.0, x_max)

        # Sanity: value column should be in the right half
        if x_min < 0.35:
            x_min = 0.35

        self._logger.debug(
            f"[LayoutParser] Auto-detected value column: "
            f"x=[{x_min:.3f}–{x_max:.3f}] from {len(currency_xs)} currency tokens"
        )
        return (x_min, x_max)

    # =========================================================================
    # LABEL FINDING
    # =========================================================================

    def _build_row_text_index(self) -> List[Tuple[float, str, List[OCRToken]]]:
        """
        Build an index of (row_y, concatenated_text, tokens) for fast
        label searching.
        """
        index = []
        for row_y, row_tokens in self._rows:
            text = " ".join(t.text for t in row_tokens)
            index.append((row_y, text, row_tokens))
        return index

    def find_label_token(
        self,
        patterns: List[re.Pattern],
        field_name: str = "",
    ) -> Optional[Tuple[int, OCRToken, float]]:
        """
        Find the row containing a label that matches one of the patterns.

        🔧 FIX: Searches BOTTOM-UP (reverse row order) so that summary
        section labels at the bottom of the page are matched before the
        identically-worded table column headers near the top.
        E.g., "Harga Jual / Penggantian / Uang Muka / Termin" appears
        both as a column header and as the summary total label — we want
        the summary copy.

        Args:
            patterns: Compiled regex patterns, ordered most-specific first.
            field_name: For logging purposes.

        Returns:
            Tuple of ``(row_index, first_label_token, row_center_y)``
            or ``None`` if no match.
        """
        row_index = self._build_row_text_index()

        for pattern in patterns:
            # 🔧 Iterate rows bottom-up so summary labels win over table headers
            for idx in range(len(row_index) - 1, -1, -1):
                row_y, row_text, row_tokens = row_index[idx]
                if pattern.search(row_text):
                    # Return the leftmost token in the matched row as the
                    # label anchor (tokens are already sorted left→right)
                    label_tok = row_tokens[0]
                    self._logger.debug(
                        f"[LayoutParser] Found label '{field_name}' "
                        f"at row {idx} (y={row_y:.3f}): \"{row_text}\""
                    )
                    return (idx, label_tok, row_y)

        return None

    # =========================================================================
    # VALUE EXTRACTION BY POSITION
    # =========================================================================

    def find_value_in_row(
        self,
        row_index: int,
        value_col_x_min: Optional[float] = None,
        value_col_x_max: Optional[float] = None,
    ) -> Optional[str]:
        """
        Find a currency value token in the given row that lies within the
        value column.

        Tokens are scanned right-to-left (rightmost value wins, as the
        value is typically right-aligned in the column).

        If the value is split across multiple adjacent tokens (e.g.
        ``"4.313.371"`` and ``",00"``), they are merged.

        Args:
            row_index: Index into ``self._rows``.
            value_col_x_min: Override for value column left bound.
            value_col_x_max: Override for value column right bound.

        Returns:
            Merged currency string, or ``None`` if nothing found.
        """
        if row_index < 0 or row_index >= len(self._rows):
            return None

        col_min = value_col_x_min if value_col_x_min is not None else self._value_col_range[0]
        col_max = value_col_x_max if value_col_x_max is not None else self._value_col_range[1]

        _, row_tokens = self._rows[row_index]

        # Collect tokens in the value column
        value_tokens: List[OCRToken] = []
        for tok in row_tokens:
            if col_min <= tok.bbox.center_x <= col_max:
                value_tokens.append(tok)

        if not value_tokens:
            return None

        # Sort right-to-left for priority, but merge left-to-right
        value_tokens.sort(key=lambda t: t.bbox.x_min)

        # Merge adjacent numeric fragments (e.g. "4.313.371" + ",00")
        merged = self._merge_numeric_tokens(value_tokens)
        return merged

    def find_value_below_label(
        self,
        label_row_index: int,
        max_rows_below: int = 2,
        value_col_x_min: Optional[float] = None,
        value_col_x_max: Optional[float] = None,
    ) -> Optional[str]:
        """
        Find a value in the rows immediately below the label row.

        Some invoice layouts place the value on the next line directly
        beneath the label. This method checks up to ``max_rows_below``
        rows below the label.

        Args:
            label_row_index: Row index where the label was found.
            max_rows_below: How many rows below to search (default 2).
            value_col_x_min: Override for value column left bound.
            value_col_x_max: Override for value column right bound.

        Returns:
            Merged currency string, or ``None``.
        """
        for offset in range(1, max_rows_below + 1):
            below_idx = label_row_index + offset
            if below_idx >= len(self._rows):
                break

            # Check that the row below is close enough vertically
            label_y = self._rows[label_row_index][0]
            below_y = self._rows[below_idx][0]
            if (below_y - label_y) > 0.05:
                # Too far below — unlikely to be the value row
                break

            val = self.find_value_in_row(
                below_idx, value_col_x_min, value_col_x_max
            )
            if val is not None:
                return val

        return None

    def _merge_numeric_tokens(self, tokens: List[OCRToken]) -> Optional[str]:
        """
        Merge adjacent tokens that form a single currency amount.

        Handles cases where OCR splits ``"4.313.371,00"`` into
        ``["4.313.371", ",00"]`` or ``["4", ".", "313", ".", "371", ",", "00"]``.

        Only merges tokens where the gap between consecutive tokens is
        small (< 3% page width) and tokens contain numeric characters,
        dots, or commas.

        Returns the merged string, or ``None`` if no numeric content found.
        """
        if not tokens:
            return None

        # Filter to tokens that contain at least one digit or are punctuation
        # fragments (comma, dot) that could be part of a number
        numeric_or_punct = []
        for tok in tokens:
            stripped = tok.text.strip()
            if re.match(r"^[\d.,\-]+$", stripped):
                numeric_or_punct.append(tok)

        if not numeric_or_punct:
            return None

        # Merge tokens with small horizontal gaps
        numeric_or_punct.sort(key=lambda t: t.bbox.x_min)
        merged_parts: List[str] = [numeric_or_punct[0].text.strip()]

        for i in range(1, len(numeric_or_punct)):
            prev = numeric_or_punct[i - 1]
            curr = numeric_or_punct[i]
            gap = curr.bbox.x_min - prev.bbox.x_max
            if gap < 0.03:
                # Close enough to be part of the same number
                merged_parts.append(curr.text.strip())
            else:
                # Gap too wide — take what we have so far or start new
                break

        merged = "".join(merged_parts)

        # Validate it looks numeric
        if not re.search(r"\d", merged):
            return None

        return merged

    # =========================================================================
    # CURRENCY PARSING
    # =========================================================================

    def _parse_currency(self, text: str) -> Optional[float]:
        """
        Parse Indonesian currency text into a float.

        Delegates to ``parse_indonesian_currency`` from normalization module,
        but returns ``None`` instead of 0.0 for truly invalid input.

        Args:
            text: Currency string, e.g. ``"4.313.371,00"`` or ``"Rp 517.605,00"``

        Returns:
            Parsed float, or ``None`` if unparseable.
        """
        if not text:
            return None

        value = parse_indonesian_currency(text)

        # parse_indonesian_currency returns 0.0 for invalid input.
        # Distinguish real zero ("0,00") from parse failure.
        if value == 0.0:
            # If the text actually contains "0" it's a real zero
            if re.search(r"0", text):
                return 0.0
            return None

        return value

    # =========================================================================
    # HIGH-LEVEL: EXTRACT A SINGLE FIELD
    # =========================================================================

    def extract_currency_value(
        self,
        patterns: List[re.Pattern],
        field_name: str = "",
        value_col_x_min: Optional[float] = None,
        value_col_x_max: Optional[float] = None,
    ) -> Optional[float]:
        """
        Extract a currency value for a labelled field using position.

        Steps:
          1. Find the label row via pattern matching.
          2. Look for a value token in the **same row** within the value
             column.
          3. If not found, look in the **next row below** the label.
          4. Parse the value as Indonesian currency.

        Args:
            patterns: Regex patterns for the label text.
            field_name: Human-readable name for logging.
            value_col_x_min: Override value column left bound.
            value_col_x_max: Override value column right bound.

        Returns:
            Parsed float value, or ``None`` if not found.
        """
        match = self.find_label_token(patterns, field_name)
        if match is None:
            self._logger.debug(
                f"[LayoutParser] Label not found for '{field_name}'"
            )
            return None

        row_idx, label_tok, row_y = match

        # Strategy 1: value in the same row
        raw_value = self.find_value_in_row(
            row_idx, value_col_x_min, value_col_x_max
        )
        if raw_value is not None:
            parsed = self._parse_currency(raw_value)
            if parsed is not None:
                self._logger.debug(
                    f"[LayoutParser] {field_name} = {parsed:,.2f} "
                    f"(same-row at y={row_y:.3f})"
                )
                return parsed

        # Strategy 2: value in the next row below the label
        raw_value = self.find_value_below_label(
            row_idx, max_rows_below=2,
            value_col_x_min=value_col_x_min,
            value_col_x_max=value_col_x_max,
        )
        if raw_value is not None:
            parsed = self._parse_currency(raw_value)
            if parsed is not None:
                self._logger.debug(
                    f"[LayoutParser] {field_name} = {parsed:,.2f} "
                    f"(below-label at row after y={row_y:.3f})"
                )
                return parsed

        self._logger.warning(
            f"[LayoutParser] Could not extract value for '{field_name}' "
            f"(label found at y={row_y:.3f})"
        )
        return None

    # =========================================================================
    # MAIN ENTRY POINT: PARSE SUMMARY SECTION
    # =========================================================================

    def parse_summary_section(self) -> Dict[str, Optional[float]]:
        """
        Extract all summary fields from the invoice using spatial/bbox-aware parsing.

        🔥 NOTE: This is a sophisticated bbox-aware parser. For simpler text-block
        based parsing, use parse_summary_section_from_blocks() from multirow_parser.

        Two-pass approach:
          **Pass 1** — Find all label rows first, so we know which rows
          contain labels and must not be "stolen" as value rows.
          **Pass 2** — For each label, look for a value in the same row
          then in the row below, skipping rows that belong to other labels.

        Returns:
            Dictionary with keys: ``harga_jual``, ``potongan_harga``,
            ``uang_muka``, ``dpp``, ``ppn``, ``ppnbm``.
            Values are ``float`` or ``0.0`` (if not found).
        """
        result: Dict[str, Optional[float]] = {}

        # === PASS 1: discover all label rows ===
        label_info: Dict[str, Optional[Tuple[int, OCRToken, float]]] = {}
        label_row_indices: set = set()  # rows that ARE labels

        for field_name, patterns in SUMMARY_LABEL_PATTERNS:
            match = self.find_label_token(patterns, field_name)
            label_info[field_name] = match
            if match is not None:
                label_row_indices.add(match[0])

        # === PASS 2: extract values, respecting label ownership ===
        used_value_rows: set = set()  # rows already consumed as values

        for field_name, patterns in SUMMARY_LABEL_PATTERNS:
            match = label_info[field_name]
            if match is None:
                result[field_name] = None
                continue

            row_idx, label_tok, row_y = match

            value = None
            source_row = None

            # Strategy A: value in the same row as the label
            raw = self.find_value_in_row(row_idx)
            if raw is not None:
                parsed = self._parse_currency(raw)
                if parsed is not None:
                    value = parsed
                    source_row = row_idx

            # Strategy B: value in row(s) below the label
            if value is None:
                for offset in range(1, 3):
                    below_idx = row_idx + offset
                    if below_idx >= len(self._rows):
                        break
                    label_y_current = self._rows[row_idx][0]
                    below_y = self._rows[below_idx][0]
                    if (below_y - label_y_current) > 0.05:
                        break

                    # Skip rows that ARE labels for other fields
                    if below_idx in label_row_indices and below_idx != row_idx:
                        continue

                    # Skip rows already consumed as value rows
                    if below_idx in used_value_rows:
                        continue

                    raw = self.find_value_in_row(below_idx)
                    if raw is not None:
                        parsed = self._parse_currency(raw)
                        if parsed is not None:
                            value = parsed
                            source_row = below_idx
                            break

            if source_row is not None:
                used_value_rows.add(source_row)

            result[field_name] = value if value is not None else 0.0

        # Replace None with 0.0 for consistency
        for k in result:
            if result[k] is None:
                result[k] = 0.0

        # =================================================================
        # POST-EXTRACTION PLAUSIBILITY CHECK
        # =================================================================
        # Validate that DPP is consistent with Harga Jual under standard
        # Indonesian tax rules. If not, the extraction likely mixed up
        # line-item values with summary totals — invalidate to trigger
        # the text-based fallback in process_with_layout_parser().
        #
        # Rules checked:
        #   - 2025 "Nilai Lain" (040): DPP ≈ Harga Jual × 11/12
        #   - Classic (010/other):     DPP ≈ Harga Jual − Potongan − Uang Muka
        # =================================================================
        hj = result.get("harga_jual", 0.0)
        pot = result.get("potongan_harga", 0.0)
        um = result.get("uang_muka", 0.0)
        dpp_val = result.get("dpp", 0.0)
        ppn_val = result.get("ppn", 0.0)

        if hj > 0 and dpp_val > 0 and ppn_val > 0:
            # Expected DPP under 2025 "Nilai Lain" rule
            expected_dpp_new = hj * 11.0 / 12.0
            # Expected DPP under classic rule
            expected_dpp_classic = hj - pot - um

            tol = 0.20  # 20 % tolerance

            dpp_ok_new = (
                expected_dpp_new > 0
                and abs(dpp_val - expected_dpp_new) <= expected_dpp_new * tol
            )
            dpp_ok_classic = (
                expected_dpp_classic > 0
                and abs(dpp_val - expected_dpp_classic) <= expected_dpp_classic * tol
            )

            if not dpp_ok_new and not dpp_ok_classic:
                self._logger.warning(
                    f"[LayoutParser] PLAUSIBILITY FAIL: "
                    f"DPP ({dpp_val:,.0f}) doesn't match Harga Jual ({hj:,.0f}) "
                    f"under new rules (expected ~{expected_dpp_new:,.0f}) "
                    f"or classic rules (expected ~{expected_dpp_classic:,.0f}). "
                    f"Invalidating coordinate extraction to trigger text fallback."
                )
                for k in result:
                    result[k] = 0.0

        self._logger.info(
            f"[LayoutParser] Summary extracted: "
            + ", ".join(f"{k}={v:,.2f}" for k, v in result.items())
        )

        return result

    # =========================================================================
    # FALLBACK: TEXT-BASED EXTRACTION
    # =========================================================================

    def parse_summary_from_text(self, ocr_text: str) -> Dict[str, float]:
        """
        Fallback text-only extraction (no coordinates).

        Delegates to the existing ``extract_summary_values`` from
        normalization.py. Use this when no bounding-box data is available.

        Args:
            ocr_text: Plain OCR text.

        Returns:
            Summary dict with float values.
        """
        from .normalization import extract_summary_values
        return extract_summary_values(ocr_text)


# =============================================================================
# VALIDATION
# =============================================================================

def validate_summary_amounts(
    summary: Dict[str, Optional[float]],
    tax_rate: float = 0.11,
) -> Dict[str, Any]:
    """
    Validate extracted summary values for internal consistency.

    Returns a structured report with errors, warnings, and confidence
    score (0–100).

    Critical Errors (confidence → 0):
      - Missing DPP or PPN
      - PPN > DPP  (field-swap indicator!)
      - DPP > Harga Jual (impossible)

    Warnings (reduce confidence):
      - PPN differs from DPP × tax_rate by > 2 %
      - DPP ≠ Harga Jual − Potongan − Uang Muka

    Bug-Pattern Detection:
      - If Harga Jual ≈ DPP + PPN and PPN > DPP, the parser probably
        wrote the PPN value into the DPP field.

    Args:
        summary: Dict from ``parse_summary_section()``.
        tax_rate: Expected PPN rate (default 0.11 = 11 %).

    Returns:
        Dict with keys:
          - ``is_valid``: bool
          - ``errors``: list of critical error messages
          - ``warnings``: list of warnings
          - ``confidence``: float 0–100
    """
    logger = frappe.logger()

    harga_jual = summary.get("harga_jual") or 0.0
    potongan = summary.get("potongan_harga") or 0.0
    uang_muka = summary.get("uang_muka") or 0.0
    dpp = summary.get("dpp") or 0.0
    ppn = summary.get("ppn") or 0.0
    ppnbm = summary.get("ppnbm") or 0.0

    errors: List[str] = []
    warnings: List[str] = []
    confidence = 100.0

    # ---- Critical: required fields ----
    if dpp <= 0:
        errors.append("DPP (Dasar Pengenaan Pajak) is missing or zero")
        confidence = 0.0
    if ppn <= 0:
        errors.append("PPN (Pajak Pertambahan Nilai) is missing or zero")
        confidence = 0.0

    # ---- Critical: field-swap detection ----
    if ppn > 0 and dpp > 0 and ppn > dpp:
        errors.append(
            f"FIELD SWAP DETECTED: PPN ({ppn:,.0f}) > DPP ({dpp:,.0f}). "
            f"PPN should always be smaller than DPP."
        )
        confidence = 0.0

    # ---- Critical: DPP > Harga Jual ----
    if harga_jual > 0 and dpp > harga_jual * 1.01:
        errors.append(
            f"DPP ({dpp:,.0f}) exceeds Harga Jual ({harga_jual:,.0f}). "
            f"This is normally impossible."
        )
        confidence = 0.0

    # ---- Bug pattern: Harga Jual ≈ alleged-DPP + alleged-PPN ----
    if (
        harga_jual > 0
        and dpp > 0
        and ppn > 0
        and ppn > dpp
    ):
        # If harga_jual ≈ dpp + ppn, the "dpp" value is actually ppn
        if abs(harga_jual - (dpp + ppn)) <= 1.0:
            errors.append(
                f"BUG PATTERN: Harga Jual ({harga_jual:,.0f}) ≈ "
                f"alleged DPP ({dpp:,.0f}) + alleged PPN ({ppn:,.0f}). "
                f"DPP and PPN values are likely swapped."
            )
            confidence = 0.0

    # ---- Warning: PPN vs expected ----
    if dpp > 0 and ppn > 0 and confidence > 0:
        expected_ppn = dpp * tax_rate
        pct_diff = abs(ppn - expected_ppn) / expected_ppn if expected_ppn else 0
        if pct_diff > 0.02:
            warnings.append(
                f"PPN ({ppn:,.0f}) differs {pct_diff:.1%} from "
                f"expected DPP × {tax_rate:.0%} = {expected_ppn:,.0f}"
            )
            confidence -= min(pct_diff * 100, 15.0)

    # ---- Warning: DPP vs Harga Jual − discounts ----
    if harga_jual > 0 and dpp > 0 and confidence > 0:
        expected_dpp = harga_jual - potongan - uang_muka
        if expected_dpp > 0:
            dpp_diff_pct = abs(dpp - expected_dpp) / expected_dpp
            if dpp_diff_pct > 0.01:
                warnings.append(
                    f"DPP ({dpp:,.0f}) differs {dpp_diff_pct:.1%} from "
                    f"Harga Jual − Potongan − Uang Muka = {expected_dpp:,.0f} "
                    f"(may use alternative tax base calculation)"
                )
                confidence -= min(dpp_diff_pct * 50, 10.0)

    # ---- Warning: negative values ----
    for name, val in [
        ("harga_jual", harga_jual),
        ("dpp", dpp),
        ("ppn", ppn),
        ("ppnbm", ppnbm),
    ]:
        if val < 0:
            warnings.append(f"{name} is negative ({val:,.0f})")
            confidence -= 5.0

    # Clamp confidence
    confidence = max(0.0, min(100.0, confidence))

    is_valid = len(errors) == 0

    logger.info(
        f"[Validation] valid={is_valid}, confidence={confidence:.1f}, "
        f"errors={len(errors)}, warnings={len(warnings)}"
    )

    return {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "confidence": round(confidence, 1),
    }


# =============================================================================
# INTEGRATED PROCESSING FUNCTION
# =============================================================================

def process_with_layout_parser(
    vision_json: Dict[str, Any],
    faktur_no: str = "",
    faktur_type: str = "",
    ocr_text: str = "",
) -> Dict[str, Any]:
    """
    Process a tax invoice using the layout-aware parser with full
    validation pipeline.

    This is the recommended entry point. It:
      1. Creates a ``LayoutAwareParser`` from the Vision JSON.
      2. Extracts summary values using coordinate-based logic.
      3. Falls back to text-regex extraction if coordinate extraction
         yields insufficient data.
      4. Detects the tax rate from DPP/PPN ratio and faktur type.
      5. Validates all values.
      6. Returns a complete result dict ready for DocType field mapping.

    Args:
        vision_json: Google Vision API JSON (stored in ``ocr_raw_json``).
        faktur_no: Invoice number, e.g. ``"040.002-26.50406870"``.
        faktur_type: Invoice type prefix, e.g. ``"040"``.
        ocr_text: Optional plain OCR text (fallback).

    Returns:
        Dict with fields: ``harga_jual``, ``dpp``, ``ppn``, ``ppnbm``,
        ``potongan_harga``, ``uang_muka``, ``detected_tax_rate``,
        ``parse_status``, ``is_valid``, ``validation_issues``,
        ``confidence_score``, ``extraction_method``.
    """
    logger = frappe.logger()
    logger.info(
        f"[LayoutParser] Processing invoice: {faktur_no} (type: {faktur_type})"
    )

    extraction_method = "layout_aware"

    # --- Step 1: coordinate-based extraction ---
    parser = LayoutAwareParser(vision_json=vision_json)
    summary = parser.parse_summary_section()

    # Check if critical fields were found
    dpp = summary.get("dpp", 0.0)
    ppn = summary.get("ppn", 0.0)

    # Resolve fallback text: use caller-supplied text, or the raw text
    # embedded inside the Vision JSON (so the text fallback works even when
    # the caller passes ocr_text="").
    _fallback_text = ocr_text or getattr(parser, "_raw_full_text", "") or parser._full_text

    if dpp <= 0 or ppn <= 0:
        # --- Fallback: text-based extraction ---
        if _fallback_text:
            logger.warning(
                "[LayoutParser] Coordinate extraction incomplete; "
                "falling back to text-based extraction"
            )
            extraction_method = "text_fallback"
            text_summary = parser.parse_summary_from_text(_fallback_text)
            # Merge: prefer layout values where found, fill gaps from text
            for key in text_summary:
                if summary.get(key, 0.0) == 0.0 and text_summary[key] > 0:
                    summary[key] = text_summary[key]
            dpp = summary.get("dpp", 0.0)
            ppn = summary.get("ppn", 0.0)

    # -----------------------------------------------------------------
    # Cross-validate: even when coordinate extraction returned values,
    # also run text extraction.  If text-based values are significantly
    # larger AND internally consistent, prefer them — summary totals
    # are always larger than individual line-item amounts, so "larger
    # but consistent" is a strong signal of correct extraction.
    # -----------------------------------------------------------------
    if dpp > 0 and ppn > 0 and _fallback_text and extraction_method == "layout_aware":
        text_summary = parser.parse_summary_from_text(_fallback_text)
        text_dpp = text_summary.get("dpp", 0.0)
        text_ppn = text_summary.get("ppn", 0.0)
        text_hj = text_summary.get("harga_jual", 0.0)

        # If text extraction gives values ≥2× larger, check consistency
        if text_dpp > dpp * 2 and text_ppn > ppn * 2 and text_dpp > 0 and text_ppn > 0:
            text_ratio = text_ppn / text_dpp if text_dpp > 0 else 0
            if 0.08 <= text_ratio <= 0.15:
                logger.warning(
                    f"[LayoutParser] Cross-validation override: "
                    f"text extraction gives larger, consistent values. "
                    f"DPP {dpp:,.0f} → {text_dpp:,.0f}, "
                    f"PPN {ppn:,.0f} → {text_ppn:,.0f}"
                )
                for key in text_summary:
                    if text_summary[key] > 0:
                        summary[key] = text_summary[key]
                dpp = summary.get("dpp", 0.0)
                ppn = summary.get("ppn", 0.0)
                extraction_method = "text_cross_validated"

    harga_jual = summary.get("harga_jual", 0.0)
    potongan_harga = summary.get("potongan_harga", 0.0)
    uang_muka = summary.get("uang_muka", 0.0)
    ppnbm = summary.get("ppnbm", 0.0)

    # --- Step 2: tax rate detection ---
    from .normalization import detect_tax_rate

    detected_rate = detect_tax_rate(dpp, ppn, faktur_type)

    # --- Step 3: validation ---
    validation = validate_summary_amounts(summary, tax_rate=detected_rate)

    # --- Step 4: determine parse status ---
    parse_status = "Draft"
    confidence_score = validation["confidence"] / 100.0

    has_minimum = dpp > 0 and ppn > 0

    if not has_minimum:
        parse_status = "Draft"
        confidence_score = 0.0
    elif validation["is_valid"] and not validation["warnings"]:
        parse_status = "Approved"
    elif validation["is_valid"]:
        parse_status = "Needs Review"
        confidence_score = max(confidence_score, 0.5)
    else:
        parse_status = "Needs Review"
        confidence_score = max(confidence_score, 0.1)

    result = {
        "harga_jual": harga_jual,
        "potongan_harga": potongan_harga,
        "uang_muka": uang_muka,
        "dpp": dpp,
        "ppn": ppn,
        "ppnbm": ppnbm,
        "detected_tax_rate": detected_rate,
        "tax_rate_percentage": detected_rate * 100,
        "parse_status": parse_status,
        "is_valid": validation["is_valid"],
        "validation_issues": validation["errors"] + validation["warnings"],
        "validation_errors": validation["errors"],
        "validation_warnings": validation["warnings"],
        "confidence_score": confidence_score,
        "extraction_method": extraction_method,
        "faktur_no": faktur_no,
        "faktur_type": faktur_type,
    }

    logger.info(
        f"[LayoutParser] Done: status={parse_status}, "
        f"confidence={confidence_score:.1%}, "
        f"method={extraction_method}, "
        f"DPP={dpp:,.0f}, PPN={ppn:,.0f}"
    )

    return result
