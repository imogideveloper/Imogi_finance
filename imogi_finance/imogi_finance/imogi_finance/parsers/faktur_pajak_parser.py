# -*- coding: utf-8 -*-
# Copyright (c) 2026, Imogi Finance and contributors
# For license information, please see license.txt

"""
PyMuPDF-based layout-aware parser for Indonesian Tax Invoices (Faktur Pajak).

This module extracts line items from PDF tax invoices using token positions
to accurately map Harga Jual, DPP, and PPN columns, solving multi-line item
extraction bugs.

🔥 FRAPPE CLOUD SAFE: Uses bytes-based PDF reading via Frappe File API.
   Works with local files, S3, and remote storage.
"""

import logging
import re
from typing import Dict, List, Tuple, Optional, Any

import frappe

# Import Vision JSON unwrapping helper
from .vision_helpers import _resolve_full_text_annotation

_logger = logging.getLogger(__name__)
try:
    _logger = frappe.logger()
except Exception:
    pass

# Try importing PyMuPDF (fitz)
try:
	import fitz  # PyMuPDF
	PYMUPDF_AVAILABLE = True
except ImportError:
	PYMUPDF_AVAILABLE = False
	frappe.log_error(
		title="PyMuPDF Not Available",
		message="PyMuPDF (fitz) is not installed. PDF text extraction will fall back to OCR. "
		        "Install with: pip install PyMuPDF>=1.23.0"
	)

# =============================================================================
# 🔥 SIGNATURE/FOOTER STOP KEYWORDS - Single Source of Truth
# =============================================================================
# These keywords indicate footer/signature section that should STOP table parsing
# and should NEVER be treated as line items.
SIGNATURE_STOP_KEYWORDS = {
	"ditandatangani secara elektronik",
	"sesuai dengan ketentuan",
	"direktorat jenderal pajak",
	"tidak diperlukan tanda tangan basah",
	"referensi: invoice",
	"(referensi:",
}


class Token:
	"""
	Unified token model for text with bounding box coordinates.

	Supports both PyMuPDF text-layer extraction and Google Vision OCR results.
	Tracks page number for multi-page documents and OCR confidence for quality monitoring.
	"""

	def __init__(
		self,
		text: str,
		x0: float,
		y0: float,
		x1: float,
		y1: float,
		page_no: int = 1,
		confidence: Optional[float] = None,
		source: str = "pymupdf"
	):
		self.text = text.strip()
		self.x0 = x0
		self.y0 = y0
		self.x1 = x1
		self.y1 = y1
		self.x_mid = (x0 + x1) / 2
		self.y_mid = (y0 + y1) / 2
		self.width = x1 - x0
		self.height = y1 - y0
		self.page_no = page_no  # Track page number for multi-page PDFs
		self.confidence = confidence  # OCR confidence (0.0-1.0), None for text-layer PDFs
		self.source = source  # "pymupdf" or "vision_ocr"

	def __repr__(self):
		conf_str = f", conf={self.confidence:.2f}" if self.confidence is not None else ""
		return f"Token('{self.text}', x={self.x0:.1f}, y={self.y0:.1f}, page={self.page_no}{conf_str})"

	def to_dict(self) -> Dict:
		"""Convert to dictionary for JSON serialization."""
		result = {
			"text": self.text,
			"bbox": [self.x0, self.y0, self.x1, self.y1],
			"x_mid": self.x_mid,
			"y_mid": self.y_mid,
			"page_no": self.page_no,
			"source": self.source
		}
		if self.confidence is not None:
			result["confidence"] = self.confidence
		return result


class ColumnRange:
	"""Represents X-coordinate range for a table column."""

	def __init__(self, name: str, x_min: float, x_max: float):
		self.name = name
		self.x_min = x_min
		self.x_max = x_max
		self.width = x_max - x_min

	def expand(self, pixels: float = None, percentage: float = None):
		"""Expand range to handle column shifts."""
		if pixels is None and percentage is None:
			# Default: max(10px, 5% of width)
			expansion = max(10, self.width * 0.05)
		elif pixels is not None:
			expansion = pixels
		else:
			expansion = self.width * percentage

		self.x_min -= expansion
		self.x_max += expansion
		self.width = self.x_max - self.x_min

	def contains(self, token: Token, min_overlap: float = 0.1) -> bool:
		"""Check if token overlaps with column range."""
		overlap_start = max(self.x_min, token.x0)
		overlap_end = min(self.x_max, token.x1)
		overlap = max(0, overlap_end - overlap_start)

		if overlap <= 0:
			return False

		# Check if overlap ratio is sufficient
		overlap_ratio = overlap / token.width if token.width > 0 else 0
		return overlap_ratio >= min_overlap

	def to_dict(self) -> Dict:
		"""Convert to dictionary for JSON serialization."""
		return {
			"name": self.name,
			"x_min": self.x_min,
			"x_max": self.x_max,
			"width": self.width
		}


# =============================================================================
# 🔥 FRAPPE CLOUD SAFE PDF HANDLING
# =============================================================================

def _get_pdf_bytes(file_url_or_name: str) -> bytes:
	"""
	Get PDF file content as bytes via Frappe File API.

	🔥 FRAPPE CLOUD SAFE: Works with local files, S3, and remote storage.
	This is the recommended way to read files in Frappe Cloud environments
	where get_local_path() may return non-existent paths.

	Args:
		file_url_or_name: Can be:
			- File URL: /private/files/xxx.pdf or /files/xxx.pdf
			- File doctype name
			- Absolute path (fallback for backward compatibility)

	Returns:
		PDF content as bytes

	Raises:
		ValueError: If file not found, empty, or not a valid PDF
	"""
	import os

	if not file_url_or_name:
		raise ValueError("File URL/name is empty or None")

	frappe.logger().info(f"[PDF] Getting bytes for: {file_url_or_name}")

	file_doc = None
	content = None

	# Strategy 1: Try as File doctype name
	try:
		if frappe.db.exists("File", file_url_or_name):
			file_doc = frappe.get_doc("File", file_url_or_name)
			frappe.logger().info(f"[PDF] Found File doc by name: {file_doc.name}")
	except Exception as e:
		frappe.logger().debug(f"[PDF] Not a File doc name: {e}")

	# Strategy 2: Try as file_url
	if not file_doc:
		try:
			file_doc_name = frappe.db.get_value("File", {"file_url": file_url_or_name}, "name")
			if file_doc_name:
				file_doc = frappe.get_doc("File", file_doc_name)
				frappe.logger().info(f"[PDF] Found File doc by file_url: {file_doc.name}")
		except Exception as e:
			frappe.logger().debug(f"[PDF] Could not find by file_url: {e}")

	# Strategy 3: Try with normalized URL (strip leading /)
	if not file_doc and file_url_or_name.startswith("/"):
		try:
			normalized_url = file_url_or_name.lstrip("/")
			file_doc_name = frappe.db.get_value(
				"File",
				{"file_url": ["like", f"%{normalized_url}"]},
				"name"
			)
			if file_doc_name:
				file_doc = frappe.get_doc("File", file_doc_name)
				frappe.logger().info(f"[PDF] Found File doc by normalized URL: {file_doc.name}")
		except Exception as e:
			frappe.logger().debug(f"[PDF] Could not find by normalized URL: {e}")

	# Get content from File doc
	if file_doc:
		try:
			content = file_doc.get_content()
			frappe.logger().info(
				f"[PDF] Got content via File API: {len(content) if content else 0} bytes"
			)
		except Exception as e:
			frappe.logger().warning(f"[PDF] File.get_content() failed: {e}")
			content = None

	# Strategy 4: Fallback to direct file read (for absolute paths)
	if not content and os.path.isabs(file_url_or_name) and os.path.exists(file_url_or_name):
		try:
			with open(file_url_or_name, "rb") as f:
				content = f.read()
			frappe.logger().info(f"[PDF] Read from absolute path: {len(content)} bytes")
		except Exception as e:
			frappe.logger().warning(f"[PDF] Direct file read failed: {e}")

	# Strategy 5: Fallback to site_path resolution
	if not content:
		try:
			from frappe.utils import get_site_path
			site_path = get_site_path(file_url_or_name.strip("/"))
			if os.path.exists(site_path):
				with open(site_path, "rb") as f:
					content = f.read()
				frappe.logger().info(f"[PDF] Read from site_path: {len(content)} bytes")
		except Exception as e:
			frappe.logger().warning(f"[PDF] Site path resolution failed: {e}")

	# Validate content
	if not content:
		raise ValueError(
			f"Could not read PDF file: {file_url_or_name}. "
			"File may not exist or is in remote storage that is not accessible."
		)

	if len(content) == 0:
		raise ValueError(f"PDF file is empty (0 bytes): {file_url_or_name}")

	# Validate PDF header (allow some whitespace before %PDF)
	header_check = content[:20].lstrip()
	if not header_check.startswith(b"%PDF"):
		# Check if it might be gzipped or otherwise compressed
		if content[:2] == b"\x1f\x8b":
			raise ValueError(
				f"File appears to be gzipped, not a PDF: {file_url_or_name}"
			)
		raise ValueError(
			f"File is not a valid PDF (missing %PDF header): {file_url_or_name}. "
			f"First bytes: {content[:20]!r}"
		)

	frappe.logger().info(
		f"[PDF] Successfully loaded {len(content)} bytes from {file_url_or_name}"
	)
	return content


def extract_text_with_bbox_from_bytes(pdf_bytes: bytes, source_name: str = "bytes") -> List[Token]:
	"""
	Extract text with bounding boxes from PDF bytes using PyMuPDF.

	🔥 FRAPPE CLOUD SAFE: Opens PDF from bytes, not file path.
	This avoids issues with S3/remote storage where local paths don't exist.

	Args:
		pdf_bytes: PDF content as bytes
		source_name: Name for logging (e.g., file URL)

	Returns:
		List of Token objects with text, coordinates, and page_no

	Raises:
		ValueError: If PyMuPDF not available, PDF encrypted, or corrupted
	"""
	if not PYMUPDF_AVAILABLE:
		frappe.log_error(
			title="PyMuPDF Not Installed",
			message=(
				"PyMuPDF is required for Tax Invoice OCR line item parsing. "
				"Add 'PyMuPDF>=1.23.0' to imogi_finance/requirements.txt and redeploy."
			)
		)
		return []

	if not pdf_bytes:
		raise ValueError("PDF bytes is empty or None")

	if len(pdf_bytes) < 100:
		frappe.logger().warning(
			f"[PyMuPDF] PDF suspiciously small ({len(pdf_bytes)} bytes): {source_name}"
		)

	tokens = []
	doc = None

	try:
		# 🔥 Open from bytes, not path - this is the key fix!
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")

		# Defensive check: verify document is actually open
		if doc.is_closed:
			raise ValueError(f"PDF document closed immediately after open (corrupted): {source_name}")

		# Check for encrypted PDFs
		if doc.is_encrypted:
			if not doc.authenticate(""):  # Try empty password
				raise ValueError(f"PDF is encrypted and requires password: {source_name}")
			frappe.logger().info(f"[PyMuPDF] PDF encrypted but opened with empty password: {source_name}")

		if len(doc) == 0:
			raise ValueError(f"PDF has no pages: {source_name}")

		page_count = len(doc)

		# Process ALL pages
		for page_index in range(page_count):
			page_no = page_index + 1  # 1-based page numbering
			page = doc[page_index]

			# Extract text as dictionary with position info
			text_dict = page.get_text("dict")

			# Parse blocks -> lines -> spans
			for block in text_dict.get("blocks", []):
				if block.get("type") != 0:  # 0 = text block
					continue

				for line in block.get("lines", []):
					for span in line.get("spans", []):
						text = span.get("text", "").strip()
						if not text:
							continue

						bbox = span.get("bbox")  # (x0, y0, x1, y1)
						if bbox and len(bbox) == 4:
							token = Token(
								text=text,
								x0=bbox[0],
								y0=bbox[1],
								x1=bbox[2],
								y1=bbox[3],
								page_no=page_no,
								source="pymupdf"
							)
							tokens.append(token)

		frappe.logger().info(
			f"[PyMuPDF] Extracted {len(tokens)} tokens from {page_count} page(s): {source_name}"
		)

		if len(tokens) == 0:
			frappe.logger().warning(
				f"[PyMuPDF] No text tokens extracted: {source_name}. PDF may be scanned image."
			)

		return tokens

	except fitz.FileDataError as e:
		raise ValueError(f"PDF file is corrupted or invalid: {source_name}. Error: {e}")
	except Exception as e:
		error_str = str(e).lower()
		if "encrypted" in error_str:
			raise ValueError(f"PDF is encrypted: {source_name}")
		if "closed" in error_str or "invalid" in error_str:
			raise ValueError(f"PDF corrupted or closed unexpectedly: {source_name}. Error: {e}")
		frappe.log_error(
			title="PyMuPDF Text Extraction Failed",
			message=f"Error extracting text from {source_name}: {e}\n{frappe.get_traceback()}"
		)
		raise

	finally:
		# Always close the document to prevent resource leaks
		if doc is not None and not doc.is_closed:
			try:
				doc.close()
			except Exception:
				pass


def extract_text_with_bbox(file_url_or_path: str) -> List[Token]:
	"""
	Extract text with bounding boxes from PDF using PyMuPDF.

	🔥 FRAPPE CLOUD SAFE: Now uses bytes-based extraction internally.
	Accepts file URLs, File doc names, or absolute paths.

	Args:
		file_url_or_path: File URL (/private/files/xxx.pdf), File name, or path

	Returns:
		List of Token objects with text, coordinates, and page_no
		Empty list if PyMuPDF not available

	Raises:
		ValueError: If file not found, empty, encrypted, or corrupted
	"""
	if not PYMUPDF_AVAILABLE:
		frappe.log_error(
			title="PyMuPDF Not Installed",
			message="PyMuPDF is required for Tax Invoice OCR line item parsing."
		)
		return []

	# Get PDF bytes via Cloud-safe method
	pdf_bytes = _get_pdf_bytes(file_url_or_path)

	# Extract using bytes-based method
	return extract_text_with_bbox_from_bytes(pdf_bytes, source_name=file_url_or_path)


def vision_to_tokens(vision_json: Dict[str, Any]) -> List[Token]:
	"""
	Convert Google Vision OCR JSON result to unified Token list.

	Reads fullTextAnnotation.pages[].blocks[].paragraphs[].words[]
	and creates Token objects with page_no, confidence, and bounding boxes.

	Vision API coordinate system:
	- Origin (0,0) is top-left
	- boundingBox.vertices = [{x, y}, {x, y}, {x, y}, {x, y}]
	  (4 corners: top-left, top-right, bottom-right, bottom-left)

	Handles multiple Vision JSON nesting variants:
	- {"responses": [{"responses": [{"fullTextAnnotation": ...}]}]}
	- {"responses": [{"fullTextAnnotation": ...}]}
	- {"fullTextAnnotation": ...}

	Args:
		vision_json: Parsed JSON from Google Vision API response

	Returns:
		List of Token objects with page_no and confidence
	"""
	tokens = []

	# 🔥 FIX: Unwrap nested responses to reach fullTextAnnotation
	full_text = _resolve_full_text_annotation(vision_json)
	if not full_text:
		frappe.logger().warning("No fullTextAnnotation found in Vision JSON (after unwrapping)")
		return tokens
	pages = full_text.get("pages", [])

	if not pages:
		frappe.logger().warning("No pages found in Vision OCR result")
		return tokens

	for page_index, page in enumerate(pages):
		page_no = page_index + 1  # 1-based page numbering

		blocks = page.get("blocks", [])
		for block in blocks:
			paragraphs = block.get("paragraphs", [])
			for paragraph in paragraphs:
				words = paragraph.get("words", [])
				for word in words:
					# Construct word text from symbols
					symbols = word.get("symbols", [])
					if not symbols:
						continue

					word_text = "".join([sym.get("text", "") for sym in symbols])
					if not word_text.strip():
						continue

					# Extract bounding box (4 vertices -> x0,y0,x1,y1)
					bbox = word.get("boundingBox", {})
					vertices = bbox.get("vertices", [])

					if len(vertices) < 4:
						continue

					# Convert vertices to (x_min, y_min, x_max, y_max)
					x_coords = [v.get("x", 0) for v in vertices if "x" in v]
					y_coords = [v.get("y", 0) for v in vertices if "y" in v]

					if not x_coords or not y_coords:
						continue

					x0 = min(x_coords)
					y0 = min(y_coords)
					x1 = max(x_coords)
					y1 = max(y_coords)

					# Extract confidence (optional, word-level or paragraph-level)
					confidence = word.get("confidence")
					if confidence is None:
						confidence = paragraph.get("confidence")
					if confidence is None:
						confidence = block.get("confidence")

					# Create Token
					token = Token(
						text=word_text,
						x0=float(x0),
						y0=float(y0),
						x1=float(x1),
						y1=float(y1),
						page_no=page_no,
						confidence=float(confidence) if confidence is not None else None,
						source="vision_ocr"
					)
					tokens.append(token)

	frappe.logger().info(
		f"Converted {len(tokens)} tokens from Vision OCR ({len(pages)} page(s))"
	)

	return tokens


def extract_tokens(
	file_url_or_path: Optional[str] = None,
	vision_json: Optional[Dict] = None,
	pdf_bytes: Optional[bytes] = None
) -> List[Token]:
	"""
	Unified token extraction with automatic fallback.

	🔥 FRAPPE CLOUD SAFE: Now accepts file URLs for bytes-based extraction.

	Pure extraction layer - does not perform any parsing logic.
	Returns unified Token list regardless of source.

	Extraction Priority (automatic fallback):
		1. Vision JSON (if provided) - Best for scanned PDFs
		2. PDF bytes (if provided) - Direct bytes extraction
		3. PyMuPDF via file URL (if file_url_or_path provided) - Best for text-layer PDFs
		4. Raise ValueError if all fail or none provided

	Args:
		file_url_or_path: File URL (/private/files/xxx.pdf), File name, or path
		vision_json: Google Vision OCR JSON result (for scanned PDFs)
		pdf_bytes: Direct PDF bytes (optional, for pre-loaded content)

	Returns:
		List of Token objects

	Raises:
		ValueError if no input provided or all extraction methods fail
	"""
	if not file_url_or_path and not vision_json and not pdf_bytes:
		raise ValueError("At least one of file_url_or_path, vision_json, or pdf_bytes must be provided")

	# Track errors for final error message
	vision_error = None
	pymupdf_error = None

	# STEP 1: Try vision_json first (preferred for scanned PDFs)
	if vision_json:
		try:
			tokens = vision_to_tokens(vision_json)
			if tokens:
				frappe.logger().info(f"Extracted {len(tokens)} tokens from Vision OCR JSON")
				return tokens
			else:
				vision_error = "returned 0 tokens (empty or invalid JSON structure)"
				frappe.logger().warning(f"Vision JSON provided but {vision_error} - falling back to PyMuPDF")
		except Exception as e:
			vision_error = str(e)
			frappe.logger().warning(f"Vision OCR extraction failed: {vision_error} - falling back to PyMuPDF")

	# STEP 2: Try direct bytes if provided
	if pdf_bytes:
		try:
			tokens = extract_text_with_bbox_from_bytes(pdf_bytes, source_name="direct_bytes")
			if tokens:
				frappe.logger().info(f"Extracted {len(tokens)} tokens from PDF bytes")
				return tokens
			else:
				pymupdf_error = "returned 0 tokens (PDF may be scanned image without text layer)"
		except ValueError as e:
			pymupdf_error = str(e)
		except Exception as e:
			pymupdf_error = f"unexpected error - {str(e)}"

	# STEP 3: Try file URL/path via Cloud-safe method
	# NOTE: Always try if file_url_or_path is provided, even if Step 2 failed
	# (Step 2 might fail with direct bytes, but Step 3 could work with file lookup)
	if file_url_or_path:
		try:
			# Get bytes first, then extract - Cloud safe!
			file_bytes = _get_pdf_bytes(file_url_or_path)
			tokens = extract_text_with_bbox_from_bytes(file_bytes, source_name=file_url_or_path)
			if tokens:
				frappe.logger().info(f"Extracted {len(tokens)} tokens from PyMuPDF (text layer)")
				return tokens
			else:
				# Use 'or' to preserve error from Step 2 if it had more context
				pymupdf_error = pymupdf_error or "returned 0 tokens (PDF may be scanned image without text layer)"
		except ValueError as e:
			pymupdf_error = pymupdf_error or str(e)
		except Exception as e:
			error_str = str(e).lower()
			if "closed" in error_str or "invalid" in error_str or "corrupt" in error_str:
				pymupdf_error = pymupdf_error or f"document corrupted - {str(e)}"
			elif "not found" in error_str or "could not read" in error_str:
				pymupdf_error = pymupdf_error or f"file access error - {str(e)}"
			else:
				pymupdf_error = pymupdf_error or str(e)

	# Build clear error message
	vision_status = "not provided" if not vision_json else f"failed ({vision_error})" if vision_error else "failed"
	pymupdf_status = "not attempted" if not file_url_or_path and not pdf_bytes else pymupdf_error or "unknown error"

	raise ValueError(
		f"Both extraction methods failed. "
		f"Vision OCR: {vision_status}. "
		f"PyMuPDF: {pymupdf_status}"
	)


def detect_table_header(tokens: List[Token]) -> Tuple[Optional[float], Dict[str, ColumnRange], str]:
	"""
	Detect table header row and extract column ranges.

	Supports two Faktur Pajak formats:
	1. Multi-column: Separate Harga Jual, DPP, PPN columns per line item
	2. Single-column: Only Harga Jual per line, DPP/PPN in summary section

	Args:
		tokens: List of Token objects

	Returns:
		Tuple of (header_y_position, column_ranges_dict, format_type)
		format_type is either "multi_column" or "single_column"
	"""
	# Group tokens by Y coordinate (rows)
	rows = cluster_tokens_by_row(tokens, y_tolerance=5)

	# Keywords to identify header row - Multi-column format
	# More variations to handle OCR errors, spacing variations, and partial matches
	multi_col_keywords = {
		"harga_jual": [
			"harga jual", "harga", "jual", "hrg jual", "hrg", 
			"selling price", "price", "nilai", "jumlah",
			"hargajual",  # No space variant
			"(rp)", "rp", "rupiah"  # Amount column indicators
		],
		"dpp": [
			"dpp", "dasar pengenaan", "dasar", "pengenaan",
			"dpP", "dPp", "d.p.p", "d.p.p.",  # OCR variations
			"dasarpengenaan", "dasarpengeneanpajak",  # No space variants
			"base", "tax base"
		],
		"ppn": [
			"ppn", "pajak pertambahan", "pajak", "pertambahan",
			"pPn", "PpN", "p.p.n", "p.p.n.",  # OCR variations
			"pajakpertambahan", "pjkpertambahan",  # No space variants
			"vat", "value added tax"
		]
	}

	# Keywords for single-column format header
	# Standard DJP format: "Harga Jual / Penggantian / Uang Muka / Termin"
	# Extended with more format variations
	single_col_keywords = [
		"harga jual / penggantian",
		"harga jual/penggantian",
		"hargajual/penggantian",  # No space
		"harga jual penggantian",  # No slash
		"uang muka / termin",
		"uang muka/termin",
		"uangmuka/termin",  # No space
		"uang muka termin",  # No slash
		"penggantian",
		"termin",
		"harga jual",
		"hargajual",  # No space
		"nilai barang",
		"uraian",  # Description column often near value column
		"nama barang",
		"jumlah harga"  # Alternative phrasing
	]

	column_ranges = {}
	header_y = None
	format_type = None

	for y_pos, row_tokens in rows:
		# Combine tokens in row for keyword matching
		# Also create a version with minimal spaces for better OCR error tolerance
		row_text = " ".join([t.text.lower() for t in row_tokens])
		row_text_compact = row_text.replace(" ", "")  # For no-space variants

		# First, check for multi-column format (all 3 separate columns)
		found_columns = {}
		for col_name, keywords in multi_col_keywords.items():
			for keyword in keywords:
				# Check both normal and compact text
				if keyword in row_text or keyword.replace(" ", "") in row_text_compact:
					# Find matching tokens (look for any part of keyword)
					keyword_parts = keyword.split()
					matching_tokens = [
						t for t in row_tokens 
						if any(part in t.text.lower() for part in keyword_parts) or
						   keyword.replace(" ", "") in t.text.lower().replace(" ", "")
					]
					if matching_tokens:
						x_min = min(t.x0 for t in matching_tokens)
						x_max = max(t.x1 for t in matching_tokens)
						found_columns[col_name] = (x_min, x_max)
						break

		# If we found at least 2 columns, this is likely multi-column format
		# We can infer the missing column position from the found ones
		if len(found_columns) >= 2:
			header_y = y_pos
			format_type = "multi_column"

			# Create ColumnRange objects for found columns
			for col_name, (x_min, x_max) in found_columns.items():
				col_range = ColumnRange(col_name, x_min, x_max)
				col_range.expand()
				column_ranges[col_name] = col_range

			# 🔧 FIX: If only 2 columns found, try to infer the third
			if len(found_columns) == 2:
				_infer_missing_column(column_ranges, row_tokens, found_columns)

			frappe.logger().info(
				f"Found MULTI-COLUMN header at Y={header_y:.1f} with columns: "
				f"{list(column_ranges.keys())}"
			)
			break

		# Check for single-column format (Harga Jual only)
		for keyword in single_col_keywords:
			if keyword in row_text or keyword.replace(" ", "") in row_text_compact:
				# Find tokens that might be part of the header
				# Look for keywords or currency indicators or numeric patterns
				keyword_parts = keyword.split()
				matching_tokens = [
					t for t in row_tokens 
					if any(kw in t.text.lower() for kw in 
						   ["harga", "jual", "termin", "penggantian", "(rp)", "rp", "nilai", "jumlah"]) or
					   any(part in t.text.lower() for part in keyword_parts)
				]
				if matching_tokens:
					# Find rightmost numeric/value column
					# Look for tokens on right side that could be value columns
					value_tokens = [t for t in row_tokens if t.x0 > 300]  # Heuristic: value columns usually on right
					if value_tokens:
						rightmost = max(value_tokens, key=lambda t: t.x1)
						x_min = rightmost.x0
						x_max = rightmost.x1
					else:
						# Fallback to rightmost matching token
						rightmost = max(matching_tokens, key=lambda t: t.x1)
						x_min = rightmost.x0
						x_max = rightmost.x1

					header_y = y_pos
					format_type = "single_column"

					# Only create harga_jual column - DPP/PPN will be calculated from summary
					col_range = ColumnRange("harga_jual", x_min, x_max)
					col_range.expand(pixels=30)  # Wider expansion for single column
					column_ranges["harga_jual"] = col_range

					frappe.logger().info(
						f"Found SINGLE-COLUMN header at Y={header_y:.1f}. "
						f"DPP/PPN will be extracted from summary section."
					)
					break

		if format_type:
			break

	if not column_ranges:
		# Try fallback: look for rightmost numeric columns
		header_y, column_ranges = _fallback_column_detection(rows)
		if column_ranges:
			format_type = "multi_column"  # Fallback assumes multi-column
			frappe.logger().warning(
				"Used fallback column detection. "
				"This may be less accurate than keyword-based detection."
			)
		else:
			# Log diagnostic information to help troubleshoot
			_log_header_detection_failure(rows, tokens)
			frappe.log_error(
				title="Table Header Not Found",
				message="Could not detect table header row with Harga Jual/DPP/PPN columns"
			)

	return header_y, column_ranges, format_type


def _fallback_column_detection(rows: List[Tuple[float, List[Token]]]) -> Tuple[Optional[float], Dict[str, ColumnRange]]:
	"""
	Fallback column detection when header keywords not found.

	Strategy:
	1. Look for rows with 3+ well-separated numeric columns (multi-column format)
	2. Look for rows with 1 numeric column on right (single-column format)
	3. Analyze column alignment across multiple rows

	Args:
		rows: List of (y_position, tokens) tuples

	Returns:
		Tuple of (header_y, column_ranges) or (None, {})
	"""
	numeric_pattern = re.compile(r'^[\d\.\,]+$')  # Strict: ONLY numeric
	amount_pattern = re.compile(r'[\d\.]{1,}\,\d{2}$')  # Indonesian currency format

	# Strategy 1: Look for clear multi-column headers
	for y_pos, row_tokens in rows[:20]:  # Check first 20 rows only
		# Find tokens that look like currency amounts (more specific than just numeric)
		amount_tokens = [t for t in row_tokens if amount_pattern.search(t.text.strip())]
		
		if len(amount_tokens) >= 3:
			# Check if they're well-separated (proper columns)
			amount_tokens.sort(key=lambda t: t.x0)
			
			# Calculate gaps between tokens
			gaps = []
			for i in range(len(amount_tokens) - 1):
				gaps.append(amount_tokens[i+1].x0 - amount_tokens[i].x1)
			
			# If we have reasonable gaps (at least 20 pixels), likely columns
			if all(gap > 20 for gap in gaps[:3]):
				rightmost_3 = amount_tokens[-3:]
				
				# Assume order: Harga Jual, DPP, PPN
				column_ranges = {
					"harga_jual": ColumnRange("harga_jual", rightmost_3[0].x0, rightmost_3[0].x1),
					"dpp": ColumnRange("dpp", rightmost_3[1].x0, rightmost_3[1].x1),
					"ppn": ColumnRange("ppn", rightmost_3[2].x0, rightmost_3[2].x1)
				}
				
				# Expand ranges
				for col in column_ranges.values():
					col.expand()
				
				frappe.logger().warning(
					f"Fallback multi-column detection at Y={y_pos:.1f} "
					f"(found {len(amount_tokens)} amount tokens)"
				)
				
				return y_pos, column_ranges

	# Strategy 2: Single-column format - find rightmost amount column
	for y_pos, row_tokens in rows[:20]:
		# Look for tokens on the right side that could be amounts
		right_tokens = [t for t in row_tokens if t.x0 > 350]  # Right half of page
		amount_tokens = [t for t in right_tokens if amount_pattern.search(t.text.strip())]
		
		if amount_tokens:
			# Use rightmost amount token as the value column
			rightmost = max(amount_tokens, key=lambda t: t.x1)
			
			column_ranges = {
				"harga_jual": ColumnRange("harga_jual", rightmost.x0, rightmost.x1)
			}
			column_ranges["harga_jual"].expand(pixels=40)
			
			frappe.logger().warning(
				f"Fallback single-column detection at Y={y_pos:.1f}"
			)
			
			return y_pos, column_ranges

	return None, {}


def _infer_missing_column(
	column_ranges: Dict[str, ColumnRange],
	row_tokens: List[Token],
	found_columns: Dict[str, Tuple[float, float]]
) -> None:
	"""
	Try to infer the position of a missing third column when only 2 are found.
	
	Args:
		column_ranges: Dict to update with inferred column
		row_tokens: Tokens in the header row
		found_columns: Dict of found column positions
	"""
	# Determine which column is missing
	all_cols = {"harga_jual", "dpp", "ppn"}
	missing_col = (all_cols - set(found_columns.keys())).pop()
	
	# Get rightmost numeric tokens that aren't already assigned
	assigned_x_ranges = [(x0, x1) for x0, x1 in found_columns.values()]
	
	# Find tokens that might be the missing column
	# Look for numeric-like tokens that are well-separated from found columns
	numeric_pattern = re.compile(r'[\d\.\,\(\)]')
	candidate_tokens = [
		t for t in row_tokens
		if numeric_pattern.search(t.text) and
		not any(x0 - 10 <= t.x0 <= x1 + 10 for x0, x1 in assigned_x_ranges)
	]
	
	if candidate_tokens:
		# Use rightmost unassigned numeric token
		rightmost = max(candidate_tokens, key=lambda t: t.x1)
		col_range = ColumnRange(missing_col, rightmost.x0, rightmost.x1)
		col_range.expand()
		column_ranges[missing_col] = col_range
		
		frappe.logger().info(
			f"Inferred missing column '{missing_col}' at X={rightmost.x0:.1f}"
		)


def _log_header_detection_failure(rows: List[Tuple[float, List[Token]]], tokens: List[Token]) -> None:
	"""
	Log diagnostic information when header detection fails.
	Helps troubleshooting by showing what text was actually found.
	
	Args:
		rows: Grouped tokens by row
		tokens: All tokens
	"""
	try:
		# Log first 10 rows of text to see what's in the document
		sample_rows = []
		for i, (y_pos, row_tokens) in enumerate(rows[:10]):
			row_text = " ".join(t.text for t in row_tokens)
			sample_rows.append(f"Row {i+1} (Y={y_pos:.1f}): {row_text[:100]}")
		
		diagnostic_msg = (
			"Failed to detect table header. First 10 rows:\n" +
			"\n".join(sample_rows) +
			f"\n\nTotal tokens: {len(tokens)}, Total rows: {len(rows)}"
		)
		
		frappe.logger().error(diagnostic_msg)
		
	except Exception as e:
		frappe.logger().error(f"Error logging header detection failure: {str(e)}")


def find_table_end(tokens: List[Token], header_y: float) -> Optional[float]:
	"""
	Find Y-position where table ends (totals/summary section).

	Looks for keywords: "Jumlah", "Total", "Grand Total", "Dasar Pengenaan Pajak"

	Args:
		tokens: List of Token objects
		header_y: Y-position of header row (to search below it)

	Returns:
		Y-position of table end, or None if not found
	"""
	# Keywords that indicate end of line items table
	stop_keywords = [
		"jumlah", "total", "grand total", "subtotal",
		"dasar pengenaan pajak", "harga jual / penggantian",
		# 🔥 FIX: Include signature/footer keywords to stop before footer section
		*SIGNATURE_STOP_KEYWORDS,
	]

	# Filter tokens below header
	below_header = [t for t in tokens if t.y0 > header_y]

	# Group by Y coordinate
	rows = cluster_tokens_by_row(below_header, y_tolerance=5)

	for y_pos, row_tokens in rows:
		row_text = " ".join([t.text.lower() for t in row_tokens])

		for keyword in stop_keywords:
			if keyword in row_text:
				frappe.logger().info(
					f"Found table end keyword '{keyword}' at Y={y_pos:.1f}"
				)
				return y_pos

	# If not found, return None (will use all tokens below header)
	return None


def cluster_tokens_by_row(tokens: List[Token], y_tolerance: float = 3) -> List[Tuple[float, List[Token]]]:
	"""
	Group tokens into rows based on Y-coordinate clustering.

	Args:
		tokens: List of Token objects
		y_tolerance: Maximum Y-distance to consider same row

	Returns:
		List of (y_position, tokens_in_row) tuples, sorted by Y
	"""
	if not tokens:
		return []

	# Sort tokens by Y position
	sorted_tokens = sorted(tokens, key=lambda t: t.y_mid)

	rows = []
	current_row = [sorted_tokens[0]]
	current_y = sorted_tokens[0].y_mid

	for token in sorted_tokens[1:]:
		if abs(token.y_mid - current_y) <= y_tolerance:
			# Same row
			current_row.append(token)
			current_y = sum(t.y_mid for t in current_row) / len(current_row)
		else:
			# New row
			rows.append((current_y, current_row))
			current_row = [token]
			current_y = token.y_mid

	# Add last row
	if current_row:
		rows.append((current_y, current_row))

	return rows


def assign_tokens_to_columns(
	row_tokens: List[Token],
	column_ranges: Dict[str, ColumnRange]
) -> Dict[str, List[Token]]:
	"""
	Assign tokens in a row to appropriate columns based on X-overlap.

	IMPORTANT: Only assigns tokens that overlap with defined column ranges.
	Tokens outside all column ranges (e.g., in description area) are excluded.

	Args:
		row_tokens: Tokens in this row
		column_ranges: Dictionary of column name -> ColumnRange

	Returns:
		Dictionary of column name -> tokens in that column
	"""
	assignments = {col_name: [] for col_name in column_ranges.keys()}

	# Sort column ranges by X position to determine leftmost boundary
	sorted_cols = sorted(column_ranges.values(), key=lambda c: c.x_min)
	leftmost_numeric_col = sorted_cols[0].x_min if sorted_cols else float('inf')

	for token in row_tokens:
		# Critical guard: Skip tokens that are clearly in description area
		# (left of the leftmost numeric column)
		if token.x1 < leftmost_numeric_col * 0.9:  # 10% tolerance
			continue

		assigned = False
		for col_name, col_range in column_ranges.items():
			if col_range.contains(token):
				assignments[col_name].append(token)
				assigned = True
				break  # Assign to first matching column only

		# Log warning if numeric token wasn't assigned (potential data loss)
		if not assigned and re.search(r'[\d\.,]+', token.text):
			frappe.logger().debug(
				f"Numeric token '{token.text}' at X={token.x0:.1f} not assigned to any column. "
				f"This is expected for amounts in description."
			)

	return assignments


def get_rightmost_value(tokens: List[Token]) -> Optional[str]:
	"""
	Get the rightmost token's text from a list (for numeric columns).

	Args:
		tokens: List of tokens in a column

	Returns:
		Text of rightmost token, or None if empty
	"""
	if not tokens:
		return None

	rightmost = max(tokens, key=lambda t: t.x1)
	return rightmost.text


def merge_description_wraparounds(rows: List[Dict]) -> List[Dict]:
	"""
	Merge multi-row OCR items into single items.

	🔧 REWRITTEN: Uses a three-pass strategy to handle the multi-line
	item format in Indonesian Faktur Pajak where each item spans 4-5
	visual rows in the OCR output.

	Pass 1 (forward): Merge any row WITHOUT column values into the
	         previous row. Rows with harga_jual/dpp/ppn values stay separate.
	Pass 2 (backward): Merge leading no-value rows INTO the next value
	         row below them (handles description preceding its value).
	Pass 3 (dedup): When consecutive rows share the same harga_jual
	         from fallback extraction, keep only the last one (the one
	         with the real column-assigned value) and merge descriptions.

	Args:
		rows: List of parsed row dictionaries

	Returns:
		List of merged row dictionaries
	"""
	if not rows:
		return []

	# === Pass 1: Forward merge — no-value rows merge into preceding row ===
	pass1 = []
	current_row = None

	for row in rows:
		has_numbers = any([
			row.get("harga_jual"),
			row.get("dpp"),
			row.get("ppn")
		])

		if has_numbers or current_row is None:
			# Data row or very first row
			if current_row:
				pass1.append(current_row)
			current_row = dict(row)  # shallow copy
		else:
			# No column values → merge into current_row as description continuation
			if current_row and row.get("description"):
				prev_desc = current_row.get("description", "")
				new_desc = row.get("description", "")
				current_row["description"] = f"{prev_desc} {new_desc}".strip()
				_logger.debug(
					f"Merge P1 (fwd): '{new_desc[:50]}' into previous row"
				)

	if current_row:
		pass1.append(current_row)

	# === Pass 2: Backward merge — leading no-value rows merge forward ===
	# If the first N rows have no value but the (N+1)th does, merge them
	# into the (N+1)th row. This handles: desc row → desc row → value row.
	pass2 = []
	pending_no_value: List[Dict] = []

	for row in pass1:
		has_numbers = any([
			row.get("harga_jual"),
			row.get("dpp"),
			row.get("ppn")
		])

		if not has_numbers:
			pending_no_value.append(row)
		else:
			# Merge any pending no-value rows into this value row
			if pending_no_value:
				combined_desc = " ".join(
					r.get("description", "") for r in pending_no_value
					if r.get("description")
				)
				if combined_desc:
					row_desc = row.get("description", "")
					row["description"] = f"{combined_desc} {row_desc}".strip()
					_logger.debug(
						f"Merge P2 (bwd): {len(pending_no_value)} no-value rows "
						f"merged into value row"
					)
				pending_no_value = []

			pass2.append(row)

	# If there are trailing no-value rows after the last value row,
	# append them to the last value row (or keep them as-is if no value rows exist)
	if pending_no_value:
		if pass2:
			last_row = pass2[-1]
			for nv_row in pending_no_value:
				if nv_row.get("description"):
					prev_desc = last_row.get("description", "")
					last_row["description"] = f"{prev_desc} {nv_row['description']}".strip()
		else:
			# All rows are no-value → just return them as-is
			pass2 = pending_no_value

	# === Pass 3: Deduplication — merge consecutive rows with same harga_jual ===
	# The single-column fallback sometimes extracts the same price from the
	# description text AND the column token, creating duplicate value rows.
	if len(pass2) <= 1:
		return pass2

	pass3 = [pass2[0]]
	for row in pass2[1:]:
		prev = pass3[-1]
		prev_hj = str(prev.get("harga_jual", "") or "").strip()
		curr_hj = str(row.get("harga_jual", "") or "").strip()

		if prev_hj and curr_hj and prev_hj == curr_hj:
			# Same harga_jual → merge descriptions, keep later row's value
			prev_desc = prev.get("description", "")
			curr_desc = row.get("description", "")
			row["description"] = f"{prev_desc} {curr_desc}".strip()
			pass3[-1] = row  # replace with merged
			_logger.debug(
				f"Merge P3 (dedup): rows with same harga_jual={curr_hj}"
			)
		else:
			pass3.append(row)

	return pass3


def parse_invoice(
	file_url_or_path: Optional[str] = None,
	vision_json: Optional[Dict] = None,
	tax_rate: float = 0.11,
	pdf_path: Optional[str] = None  # Backward compatibility alias
) -> Dict[str, Any]:
	"""
	🆕 LINE ITEM PARSER - Token+Bounding Box Based

	🔥 FRAPPE CLOUD SAFE: Now uses bytes-based PDF reading.

	Scope:
		Extracts LINE ITEMS (individual rows) from Faktur Pajak using spatial coordinates.
		Does NOT extract header/totals (use parse_faktur_pajak_text() for that).

	Extracted Per Line Item:
		- line_no (sequential)
		- description (item description, multi-line merged)
		- harga_jual (price per item)
		- dpp (taxable base per item)
		- ppn (tax amount per item)
		- page_no (for multi-page PDFs)
		- row_confidence (OCR quality score)

	Used By:
		- Tax Invoice OCR Upload.parse_line_items()
		- auto_parse_line_items() background job

	Extraction Strategy (Automatic Fallback):
		1. Try Vision JSON (if ocr_raw_json exists) → Best for scanned PDFs
		2. Fallback: PyMuPDF text layer → Best for digital PDFs
		3. If both fail: Set status "Needs Review"

	Token Sources:
		- PyMuPDF: extract_text_with_bbox() → Native text layer
		- Vision OCR: vision_to_tokens() → Google Vision API response

	Parsing Architecture:
		1. extract_tokens() → Unified Token list (source-agnostic)
		2. detect_table_header() → Find "Harga Jual", "DPP", "PPN" columns
		3. _parse_multipage() → Handle multi-page PDFs with sticky columns
		4. assign_tokens_to_columns() → Map tokens to columns by X-coordinate
		5. merge_description_wraparounds() → Combine multi-line descriptions
		6. normalize_all_items() → Parse Indonesian amounts
		7. validate_all_line_items() → Business rule validation

	Multi-Page Support:
		✅ Handles 1-N page PDFs
		✅ Sticky column detection (reuse header from page 1)
		✅ Strong totals detection on last page only
		✅ Global line numbering across pages

	Why Token-Based?
		- Accurate column mapping (X/Y coordinates)
		- Handles multi-line item descriptions
		- Solves regex parsing limitations for tabular data
		- Multi-page support out of the box

	⚠️ DO NOT USE FOR HEADERS
		For header/totals extraction, use:
		from imogi_finance.tax_invoice_ocr import parse_faktur_pajak_text

	Args:
		file_url_or_path: File URL (/private/files/xxx.pdf), File name, or path (🔥 Cloud-safe)
		vision_json: Google Vision OCR JSON result (for scanned PDFs)
		tax_rate: PPN tax rate for validation (default 11%)
		pdf_path: DEPRECATED - use file_url_or_path instead (backward compatibility)

	Returns:
		Dictionary with:
			- items: List of line item dictionaries (empty if parsing failed)
			- debug_info: Debug metadata (source, token_count, page_count, tokens)
			- success: Boolean (True if parsing succeeded)
			- errors: List of error messages (empty if success)

	Example:
		>>> from imogi_finance.imogi_finance.parsers.faktur_pajak_parser import parse_invoice
		>>> result = parse_invoice(file_url_or_path="/private/files/faktur.pdf", tax_rate=0.11)
		>>> if result["success"]:
		...     for item in result["items"]:
		...         print(f"Line {item['line_no']}: {item['description']} - Rp {item['harga_jual']}")
		>>> else:
		...     print(f"Parsing failed: {result['errors']}")
	"""
	# Backward compatibility: pdf_path -> file_url_or_path
	if pdf_path and not file_url_or_path:
		file_url_or_path = pdf_path

	result = {
		"items": [],
		"debug_info": {},
		"success": False,
		"errors": []
	}

	try:
		# Step 1: Extract tokens (source-specific, Cloud-safe)
		tokens = extract_tokens(file_url_or_path=file_url_or_path, vision_json=vision_json)

		if not tokens:
			result["errors"].append("No text extracted from source")
			return result

		# Step 2: Parse tokens (source-agnostic)
		result = parse_tokens(tokens, tax_rate)

	except ValueError as e:
		# Handle invalid inputs
		result["errors"].append(str(e))
		frappe.logger().error(f"Invalid input: {str(e)}")
	except Exception as e:
		error_msg = f"Parsing failed: {str(e)}"
		result["errors"].append(error_msg)
		frappe.log_error(
			title="Tax Invoice Parsing Error",
			message=f"Error: {str(e)}\n{frappe.get_traceback()}"
		)

	return result


def _parse_multipage(tokens: List[Token], tax_rate: float) -> Dict[str, Any]:
	"""
	Parse multi-page invoice with per-page column detection and sticky columns.

	Works with BOTH PyMuPDF and Vision OCR tokens.
	Used for ALL invoices regardless of page count (including page_count=1).

	Key features:
	- Per-page header detection with sticky columns
	- Header keyword skipping on subsequent pages
	- Strong totals detection (last page only)
	- Global line numbering across all pages
	- Per-page debug summary

	Args:
		tokens: All tokens from all pages (any source)
		tax_rate: PPN tax rate

	Returns:
		Dictionary with items and debug_info
	"""
	# Determine page count
	page_count = max(t.page_no for t in tokens) if tokens else 1

	result = {
		"items": [],
		"debug_info": {
			"page_count": page_count,
			"pages": []
		}
	}

	# State carried across pages
	previous_column_ranges = None
	previous_format_type = None
	global_line_no = 1

	# Header keywords to skip on continuation pages
	HEADER_SKIP_KEYWORDS = [
		"harga jual", "dasar pengenaan", "dpp", "ppn",
		"nama barang", "kode barang", "no.", "no"
	]

	# Strong totals keywords (need 2+ to trigger table end)
	# 🔥 FIX: Include signature keywords as hard-stop (single keyword sufficient)
	TOTALS_KEYWORDS = [
		"jumlah", "total", "grand total", "subtotal",
		"dasar pengenaan pajak", "dikurangi potongan",
		# Signature markers - single occurrence should stop parsing
		*SIGNATURE_STOP_KEYWORDS,
	]

	# 🔥 Summary row keywords - rows containing these are NEVER valid line items
	# This is the LAST LINE OF DEFENSE against summary rows leaking into items
	# Uses SIGNATURE_STOP_KEYWORDS as single source of truth
	SUMMARY_ROW_KEYWORDS = {
		"harga jual / pengganti",
		"harga jual/pengganti",
		"harga jual / pengganti / uang muka",
		"harga jual/pengganti/uang muka",
		"dasar pengenaan pajak",
		"jumlah ppn",
		"jumlah ppnbm",
		"ppn = ",
		"ppnbm = ",
		"grand total",
		# 🔧 FIX: Removed "potongan harga" — it appears inside multi-row item
		#   details (e.g., "Potongan Harga = Rp 0,00") and was causing valid line
		#   items to be filtered out. Summary-level "Dikurangi Potongan Harga"
		#   is caught by SUMMARY_START_KEYWORDS instead.
		"uang muka yang telah diterima",
		"nilai lain",
		# 🔥 FIX: Include signature/footer patterns
		*SIGNATURE_STOP_KEYWORDS,
	}

	for page_no in range(1, page_count + 1):
		frappe.logger().debug(f"Processing page {page_no}/{page_count}")

		page_result = _parse_page(
			tokens=tokens,
			page_no=page_no,
			tax_rate=tax_rate,
			previous_column_ranges=previous_column_ranges,
			previous_format_type=previous_format_type,
			global_line_no=global_line_no,
			header_skip_keywords=HEADER_SKIP_KEYWORDS,
			totals_keywords=TOTALS_KEYWORDS,
			is_last_page=(page_no == page_count)
		)

		# Accumulate items
		result["items"].extend(page_result["items"])

		# Update state for next page
		previous_column_ranges = page_result.get("column_ranges")
		previous_format_type = page_result.get("format_type")
		global_line_no += len(page_result["items"])

		# Store per-page debug info
		page_debug = {
			"page_no": page_no,
			"items_count": len(page_result["items"]),
			"format_type": page_result.get("format_type"),
			"used_sticky_columns": page_result.get("used_sticky_columns", False),
			"table_end_y": page_result.get("table_end_y")
		}

		# Add column ranges to debug (only if detected)
		if page_result.get("column_ranges"):
			page_debug["column_ranges"] = {
				k: v.to_dict() for k, v in page_result.get("column_ranges", {}).items()
			}

		# 🔥 OBSERVABILITY: Add filter stats to page debug
		if page_result.get("filter_stats"):
			page_debug["filter_stats"] = page_result["filter_stats"]

		result["debug_info"]["pages"].append(page_debug)

	# Set format_type at document level (use first page's type)
	if result["debug_info"]["pages"]:
		result["debug_info"]["format_type"] = result["debug_info"]["pages"][0]["format_type"]

	# 🔥 OBSERVABILITY: Aggregate filter stats across all pages
	total_filter_stats = {
		"raw_rows_count": 0,
		"filtered_summary_count": 0,
		"filtered_header_count": 0,
		"filtered_zero_suspect_count": 0,
		"final_items_count": len(result["items"]),
		"first_10_filtered_descriptions": []
	}

	for page_debug in result["debug_info"]["pages"]:
		if "filter_stats" in page_debug:
			ps = page_debug["filter_stats"]
			total_filter_stats["raw_rows_count"] += ps.get("raw_rows_count", 0)
			total_filter_stats["filtered_summary_count"] += ps.get("filtered_summary_count", 0)
			total_filter_stats["filtered_header_count"] += ps.get("filtered_header_count", 0)
			total_filter_stats["filtered_zero_suspect_count"] += ps.get("filtered_zero_suspect_count", 0)
			# Collect first 10 filtered descriptions across all pages
			for desc in ps.get("first_10_filtered_descriptions", []):
				if len(total_filter_stats["first_10_filtered_descriptions"]) < 10:
					total_filter_stats["first_10_filtered_descriptions"].append(desc)

	result["debug_info"]["filter_stats"] = total_filter_stats

	return result


def _parse_page(
	tokens: List[Token],
	page_no: int,
	tax_rate: float,
	previous_column_ranges: Optional[Dict[str, ColumnRange]],
	previous_format_type: Optional[str],
	global_line_no: int,
	header_skip_keywords: List[str],
	totals_keywords: List[str],
	is_last_page: bool
) -> Dict[str, Any]:
	"""Parse a single page from multi-page document."""
	page_result = {
		"items": [],
		"column_ranges": None,
		"format_type": None,
		"table_end_y": None,
		"used_sticky_columns": False
	}

	# Filter tokens for this page
	page_tokens = [t for t in tokens if t.page_no == page_no]

	if not page_tokens:
		frappe.logger().warning(f"No tokens on page {page_no}")
		return page_result

	# Try detect header
	header_y, column_ranges, format_type = detect_table_header(page_tokens)

	# Sticky columns: reuse from previous page if not found
	if (not column_ranges or not header_y) and previous_column_ranges and page_no > 1:
		frappe.logger().info(f"Page {page_no}: Using sticky columns from previous page")
		column_ranges = previous_column_ranges
		format_type = previous_format_type
		header_y = _find_first_non_header_row(page_tokens, header_skip_keywords)
		page_result["used_sticky_columns"] = True

		# 🔧 FIX: On continuation pages with sticky columns, check if the page
		# actually has table content. If it's just the signature/footer section
		# (which is common for page 2 of Faktur Pajak), skip parsing entirely.
		page_text = " ".join(t.text.lower() for t in page_tokens)
		has_signature = any(kw in page_text for kw in SIGNATURE_STOP_KEYWORDS)
		# Count tokens that look like IDR amounts (at least 5 digits with separators)
		import re as _re_page
		amount_token_count = sum(
			1 for t in page_tokens
			if _re_page.match(r'^[\d\.]{5,}[,]\d{2}$', t.text.strip())
		)
		if has_signature and amount_token_count < 3:
			frappe.logger().info(
				f"Page {page_no}: Sticky columns but signature detected with "
				f"only {amount_token_count} amount tokens — skipping page"
			)
			return page_result

	if not column_ranges:
		frappe.logger().warning(f"Page {page_no}: No columns detected, skipping page")
		return page_result

	page_result["column_ranges"] = column_ranges
	page_result["format_type"] = format_type

	# Find table end (strong detection on last page only)
	if is_last_page:
		table_end_y = _find_table_end_strong(page_tokens, header_y, totals_keywords, min_keywords=2)
	else:
		# On continuation pages, parse until end of page (no early stop)
		table_end_y = None

	page_result["table_end_y"] = table_end_y

	# Filter table tokens
	table_tokens = [t for t in page_tokens if t.y0 > header_y]
	if table_end_y:
		table_tokens = [t for t in table_tokens if t.y0 < table_end_y]

	# Cluster into rows
	rows = cluster_tokens_by_row(table_tokens, y_tolerance=3)

	# Parse each row
	parsed_rows = []
	for y_pos, row_tokens in rows:
		column_assignments = assign_tokens_to_columns(row_tokens, column_ranges)

		if format_type == "multi_column":
			row_data = {
				"row_y": y_pos,
				"page_no": page_no,
				"harga_jual": get_rightmost_value(column_assignments.get("harga_jual", [])),
				"dpp": get_rightmost_value(column_assignments.get("dpp", [])),
				"ppn": get_rightmost_value(column_assignments.get("ppn", [])),
			}
		else:
			# Single-column format
			harga_jual_raw = get_rightmost_value(column_assignments.get("harga_jual", []))

			row_data = {
				"row_y": y_pos,
				"page_no": page_no,
				"harga_jual": harga_jual_raw,
				"dpp": None,
				"ppn": None,
			}

		# Get description
		desc_tokens = [t for t in row_tokens
		               if not any(t in col_list for col_list in column_assignments.values())]
		row_data["description"] = " ".join([t.text for t in desc_tokens]) if desc_tokens else ""

		# 🔥 FIX: Fallback harga_jual extraction for single-column format
		# If harga_jual is empty/junk, extract last valid amount from description
		# 🔧 TIGHTENED: Skip extraction for rows that are clearly price-detail
		# continuation lines (contain "x 1,00", "x 1.00", "Lainnya",
		# "Potongan Harga", "PPnBM"). These describe item pricing breakdown,
		# not standalone line-item values.
		if format_type != "multi_column":
			hj_value = row_data.get("harga_jual")
			# Check if harga_jual is missing or junk (like "(Rp)" or empty)
			is_junk = not hj_value or hj_value in {"(Rp)", "Rp", "-", "0", "0,00"}

			if is_junk and row_data.get("description"):
				desc_text = row_data["description"]
				desc_lower = desc_text.lower()

				# 🔧 FIX: Don't extract from price-detail/continuation lines
				# These contain the per-unit amount which will be duplicated
				is_price_detail = any(marker in desc_lower for marker in [
					" x 1,", " x 1.", " x 2,", " x 2.", " x 3,", " x 3.", " x 4,", " x 4.",
					" x 5,", " x 5.",
					"lainnya", "potongan harga", "ppnbm",
				])

				if not is_price_detail:
					# Extract amounts with thousand separator (to avoid qty like "1,00")
					# Pattern: 1-3 digits, then groups of .XXX, optionally ending with ,XX
					amount_pattern = re.compile(r'(\d{1,3}(?:\.\d{3})+(?:,\d{2})?)')
					amount_matches = amount_pattern.findall(desc_text)

					if amount_matches:
						# Take the LAST amount (usually the total for the line)
						last_amount_str = amount_matches[-1]
						# Parse Indonesian format: 360.500,00 -> 360500.00
						try:
							parsed_amount = float(
								last_amount_str.replace(".", "").replace(",", ".")
							)
							# 🔥 ENHANCED VALIDATION: Prevent qty extraction
							# - Must be >= 10,000 IDR (valid item price)
							# - Must NOT look like qty (1.000, 2.000, 100.000, etc.)
							# - Must have reasonable decimal part (not .000,00 which suggests qty×1000)
							is_valid_price = (
								parsed_amount >= 10000 and  # Minimum reasonable price
								not (parsed_amount % 1000 == 0 and parsed_amount < 1_000_000)  # Avoid 1000, 2000, etc.
							)

							if is_valid_price:
								row_data["harga_jual"] = last_amount_str
								frappe.logger().debug(
									f"Single-column fallback: extracted harga_jual={last_amount_str} "
									f"(parsed: {parsed_amount:,.0f}) from description"
								)
							else:
								frappe.logger().warning(
									f"Single-column fallback: rejected amount {last_amount_str} "
									f"(parsed: {parsed_amount:,.0f}) - looks like qty, not price"
								)
						except (ValueError, TypeError):
							pass

		parsed_rows.append(row_data)

	# Merge wraparounds
	merged_rows = merge_description_wraparounds(parsed_rows)

	# 🔥 CRITICAL FIX: Filter out summary/header rows that leaked past table_end detection
	# Summary section rows (e.g., "Harga Jual / Pengganti", "Dasar Pengenaan Pajak")
	# and header rows (e.g., "No. Barang / Nama Barang") are NEVER valid line items

	# Keywords that indicate a summary/totals row (case-insensitive contains match)
	# 🔥 FIX: Uses SIGNATURE_STOP_KEYWORDS for consistency (single source of truth)
	SUMMARY_ROW_KEYWORDS = {
		"harga jual / pengganti",
		"harga jual/pengganti",
		"harga jual / pengganti / uang muka",
		"harga jual/pengganti/uang muka",
		"dasar pengenaan pajak",
		"jumlah ppn",
		"jumlah ppnbm",
		"ppn = ",
		"ppn =",
		"ppnbm = ",
		"ppnbm =",
		"grand total",
		# 🔧 FIX: Removed "potongan harga" — it appears inside multi-row item details
		#   (e.g., "Potongan Harga = Rp 0,00") and was causing valid line items to be
		#   filtered out. Summary-level "Dikurangi Potongan Harga" is caught separately.
		"uang muka yang telah diterima",
		"nilai lain",
		"total harga",
		"sub total",
		"subtotal",
		# 🔥 FIX: Include signature/footer patterns from single source of truth
		*SIGNATURE_STOP_KEYWORDS,
	}

	# 🔧 FIX: Keywords that must START the description to be considered summary rows.
	# These distinguish summary-level labels from item detail text containing the
	# same words (e.g., "Potongan Harga = Rp 0,00" inside an item vs
	# "Dikurangi Potongan Harga" as a standalone summary label).
	# CRITICAL: "potongan harga" removed because it appears in item details as
	# "Potongan Harga = Rp 0,00" which should NOT be filtered!
	SUMMARY_START_KEYWORDS = [
		"dikurangi potongan harga",  # Summary-level discount row (KEEP)
		# "potongan harga",  # ❌ REMOVED - conflicts with item details
		"harga jual",
		"dasar pengenaan",
		"jumlah ppn",
		"jumlah ppnbm",
	]

	# Keywords that indicate a header row (not a data row)
	HEADER_ROW_KEYWORDS = {
		"no. barang",
		"nama barang",
		"no. barang / nama barang",
		"kode barang",
		"harga satuan",
		"jumlah barang",
		# 🔧 FIX: Catch wrapped header text from "Nama Barang / Jasa Kena Pajak"
		"jasa kena pajak",
		"barang kena pajak",
	}

	# Keywords for the extra zero-value rule
	# If DPP==0 AND PPN==0 AND description contains any of these, it's a summary row
	ZERO_VALUE_SUSPECT_KEYWORDS = {
		"ppn",
		"dpp",
		"dasar",
		"harga jual",
		"pengganti",
		"total",
		"jumlah",
	}

	def _is_summary_row(row: Dict[str, Any]) -> Tuple[bool, str, str]:
		"""
		Check if row is a summary/header row that should be filtered out.

		🔧 SMART FILTER: Distinguishes between:
		  - Summary labels: "Dikurangi Potongan Harga" (standalone) → FILTER
		  - Item detail text: "...Potongan Harga = Rp 0,00..." (embedded) → KEEP

		Detection strategy:
		  1. Substring match against SUMMARY_ROW_KEYWORDS (broad match)
		  2. Start-of-description match against SUMMARY_START_KEYWORDS (precise)
		  3. Item number pattern override: if description starts with ``\\d+ \\d{6}``
		     (e.g., "1 000000"), it's ALWAYS a line item, never a summary row.

		Whitespace normalization: Collapses multiple spaces, strips, lowercases
		before matching keywords.

		Returns:
			Tuple of (is_filtered, reason, filter_type)
			filter_type is one of: "summary", "header", "zero_suspect", ""
		"""
		description = row.get("description", "")
		if not description:
			return False, "", ""

		# 🔥 Whitespace normalization: collapse multiple spaces, strip, lowercase
		import re as _re
		text_lower = _re.sub(r'\s+', ' ', description.lower().strip())

		# 🔧 FIX: If description starts with an item number pattern (e.g., "1 000000"),
		# it's a line item — never filter it, regardless of embedded keywords.
		if _re.match(r'^\d+\s+\d{4,6}', text_lower):
			return False, "", ""

		# Check summary keywords (broad substring match).
		# These keywords should NOT appear in normal item descriptions.
		for kw in SUMMARY_ROW_KEYWORDS:
			if kw in text_lower:
				return True, f"summary keyword '{kw}'", "summary"

		# 🔧 FIX: Check start-of-description keywords for summary labels that
		# might also appear embedded in item details (like "Potongan Harga").
		# Only match if the description STARTS with the summary label.
		for kw in SUMMARY_START_KEYWORDS:
			if text_lower.startswith(kw):
				# Extra safety: if it has a valid harga_jual value, it might be
				# a real item with an unfortunate name — don't filter
				raw_hj = row.get("harga_jual", "")
				if raw_hj and str(raw_hj).strip():
					frappe.logger().debug(
						f"[FILTER] Row starts with summary keyword '{kw}' but has "
						f"harga_jual='{raw_hj}' — keeping as line item"
					)
					continue
				return True, f"summary start keyword '{kw}'", "summary"

		# Check header keywords
		for kw in HEADER_ROW_KEYWORDS:
			if kw in text_lower:
				return True, f"header keyword '{kw}'", "header"

		# Extra rule: DPP==0 AND PPN==0 with suspect keywords
		# This catches rows like "Harga Jual / Pengganti" with amount but no DPP/PPN
		raw_dpp = row.get("dpp") or row.get("raw_dpp") or ""
		raw_ppn = row.get("ppn") or row.get("raw_ppn") or ""

		# Parse numeric values (handle string or float)
		try:
			if isinstance(raw_dpp, str):
				dpp_val = float(raw_dpp.replace(".", "").replace(",", ".")) if raw_dpp.strip() else 0
			else:
				dpp_val = float(raw_dpp) if raw_dpp else 0
		except (ValueError, TypeError):
			dpp_val = 0

		try:
			if isinstance(raw_ppn, str):
				ppn_val = float(raw_ppn.replace(".", "").replace(",", ".")) if raw_ppn.strip() else 0
			else:
				ppn_val = float(raw_ppn) if raw_ppn else 0
		except (ValueError, TypeError):
			ppn_val = 0

		# If DPP and PPN are both zero/empty and description has suspect keywords
		# 🔧 FIX: Skip this check if the row has a valid harga_jual — that means
		# it's a real item (e.g., merged multi-row item with "PPnBM" in description)
		raw_hj_check = row.get("harga_jual", "")
		has_harga_jual = bool(raw_hj_check and str(raw_hj_check).strip())

		if dpp_val == 0 and ppn_val == 0 and not has_harga_jual:
			for kw in ZERO_VALUE_SUSPECT_KEYWORDS:
				if kw in text_lower:
					return True, f"zero DPP/PPN with suspect keyword '{kw}'", "zero_suspect"

		return False, "", ""

	# 🔥 OBSERVABILITY: Track filtering statistics for debug_info
	filter_stats = {
		"raw_rows_count": len(merged_rows),
		"filtered_summary_count": 0,
		"filtered_header_count": 0,
		"filtered_zero_suspect_count": 0,
		"first_10_filtered_descriptions": []
	}

	filtered_rows = []

	for row in merged_rows:
		is_filtered, reason, filter_type = _is_summary_row(row)
		if is_filtered:
			desc = row.get("description", "")[:60]

			# Track by type
			if filter_type == "summary":
				filter_stats["filtered_summary_count"] += 1
			elif filter_type == "header":
				filter_stats["filtered_header_count"] += 1
			elif filter_type == "zero_suspect":
				filter_stats["filtered_zero_suspect_count"] += 1

			# Store first 10 descriptions for debugging
			if len(filter_stats["first_10_filtered_descriptions"]) < 10:
				filter_stats["first_10_filtered_descriptions"].append(f"'{desc}' ({reason})")

			continue
		filtered_rows.append(row)

	# 🔧 FIX: Second-pass garbage filter — remove footer/signature rows that
	# leak through when table_end_y detection fails (e.g., page 2 content).
	# These are: bare years ("2025"), single names ("APRIANI"), rows with only
	# tiny junk values (< 100 IDR) and no description.
	clean_rows = []
	import re as _re2
	for row in filtered_rows:
		desc = (row.get("description", "") or "").strip()
		hj_raw = str(row.get("harga_jual", "") or "").strip()

		# Filter: bare 4-digit year with no meaningful value
		if _re2.match(r'^(19|20)\d{2}$', desc) and not hj_raw:
			filter_stats["filtered_summary_count"] += 1
			if len(filter_stats["first_10_filtered_descriptions"]) < 10:
				filter_stats["first_10_filtered_descriptions"].append(
					f"'{desc}' (bare year)"
				)
			continue

		# Filter: empty description with tiny junk values (< 100 IDR)
		if not desc and hj_raw:
			try:
				hj_val = float(hj_raw.replace(".", "").replace(",", "."))
				if hj_val < 100:
					filter_stats["filtered_summary_count"] += 1
					if len(filter_stats["first_10_filtered_descriptions"]) < 10:
						filter_stats["first_10_filtered_descriptions"].append(
							f"'(empty desc, hj={hj_raw})' (junk value)"
						)
					continue
			except (ValueError, TypeError):
				pass

		# Filter: single short word (≤12 chars), no values — likely signer name
		if desc and len(desc) <= 12 and " " not in desc and not hj_raw:
			# Only filter if it's ALL CAPS or titlecase (name-like), not an item code
			if desc.isupper() or desc.istitle():
				# Extra: don't filter if it looks like an item code (digits/special chars)
				if not _re2.search(r'\d', desc):
					filter_stats["filtered_summary_count"] += 1
					if len(filter_stats["first_10_filtered_descriptions"]) < 10:
						filter_stats["first_10_filtered_descriptions"].append(
							f"'{desc}' (signer name)"
						)
					continue

		clean_rows.append(row)

	filtered_rows = clean_rows
	filter_stats["final_items_count"] = len(filtered_rows)

	# Store filter stats in page_result for aggregation
	page_result["filter_stats"] = filter_stats

	# Log filtered rows (debug level to avoid noise)
	filtered_count = len(merged_rows) - len(filtered_rows)
	if filtered_count > 0:
		frappe.logger().debug(
			f"[PARSE] Page {page_no}: Filtered {filtered_count} row(s) - "
			f"summary={filter_stats['filtered_summary_count']}, "
			f"header={filter_stats['filtered_header_count']}, "
			f"zero_suspect={filter_stats['filtered_zero_suspect_count']}"
		)

	# 🔥 MULTIROW GROUPING: Detect and merge multirow items
	# Pattern: Items spanning multiple rows in format:
	#   Row 1: "1 000000" (item number + code)
	#   Row 2: "HYDRO CARBON TREATMENT" (description)
	#   Row 3: "Rp 360.500,00 x 1,00 Lainnya" (price × qty)
	#   Row 4: "Potongan Harga = Rp 0,00" (discount detail)
	#   Row 5: "PPnBM (0,00%) = Rp 0,00" (luxury tax detail)
	#   Row 6: Final amount with harga_jual value
	
	# Detect multirow pattern by checking for characteristic markers
	import re as _re_multirow
	
	has_multirow_pattern = False
	item_number_pattern = _re_multirow.compile(r'^\d+\s+\d{4,6}')
	
	for row in filtered_rows:
		desc = (row.get("description", "") or "").lower()
		# Check for multirow markers
		if (item_number_pattern.match(row.get("description", "")) or
		    "potongan harga =" in desc or 
		    "ppnbm (" in desc or
		    (_re_multirow.search(r'rp\s*[\d.,]+\s*x\s*[\d.,]+', desc))):
			has_multirow_pattern = True
			break
	
	if has_multirow_pattern and len(filtered_rows) > 1:
		frappe.logger().info(
			f"[MULTIROW] Page {page_no}: Detected multirow pattern, merging rows"
		)
		
		grouped_items = []
		current_item = None
		item_start_index = -1
		
		for idx, row in enumerate(filtered_rows):
			desc = row.get("description", "") or ""
			desc_lower = desc.lower()
			
			# Check if this row starts a new item (has item number pattern)
			is_item_start = bool(item_number_pattern.match(desc))
			
			# Check if this is a continuation row (detail lines)
			is_continuation = (
				"potongan harga =" in desc_lower or
				"ppnbm (" in desc_lower or
				_re_multirow.search(r'rp\s*[\d.,]+\s*x\s*[\d.,]+', desc_lower) or
				(not row.get("harga_jual") and not row.get("dpp") and 
				 not is_item_start and current_item is not None)
			)
			
			if is_item_start:
				# Save previous item if exists
				if current_item:
					grouped_items.append(current_item)
				
				# Start new item
				current_item = {
					'descriptions': [desc],
					'rows': [row],
					'start_index': idx,
					'has_values': bool(row.get("harga_jual") or row.get("dpp") or row.get("ppn"))
				}
				item_start_index = idx
				
			elif is_continuation and current_item is not None:
				# Add to current item as continuation
				current_item['descriptions'].append(desc)
				current_item['rows'].append(row)
				# Update has_values if this row has them
				if row.get("harga_jual") or row.get("dpp") or row.get("ppn"):
					current_item['has_values'] = True
					
			elif current_item is None:
				# No current item, treat as standalone (shouldn't happen after filtering)
				grouped_items.append({
					'descriptions': [desc],
					'rows': [row],
					'start_index': idx,
					'has_values': bool(row.get("harga_jual") or row.get("dpp") or row.get("ppn"))
				})
			else:
				# Next item without clear marker - save current and start new
				if current_item:
					grouped_items.append(current_item)
				
				current_item = {
					'descriptions': [desc],
					'rows': [row],
					'start_index': idx,
					'has_values': bool(row.get("harga_jual") or row.get("dpp") or row.get("ppn"))
				}
		
		# Don't forget last item
		if current_item:
			grouped_items.append(current_item)
		
		frappe.logger().info(
			f"[MULTIROW] Grouped {len(filtered_rows)} rows into {len(grouped_items)} items"
		)
		
		# Merge each group into single item
		merged_items = []
		for group in grouped_items:
			# Find row with actual values (harga_jual/dpp/ppn)
			value_row = None
			for row in group['rows']:
				if row.get("harga_jual") or row.get("dpp") or row.get("ppn"):
					value_row = row
					break
			
			# Use first row as base if no value row found
			if not value_row:
				value_row = group['rows'][0] if group['rows'] else {}
			
			# Build merged description
			# Remove item number from description if it's there
			clean_descriptions = []
			for desc in group['descriptions']:
				# Remove item number pattern from start
				clean_desc = item_number_pattern.sub('', desc).strip()
				# Skip empty or pure detail lines
				if clean_desc and not clean_desc.lower().startswith(('potongan harga =', 'ppnbm (')):
					# Also skip price x qty lines
					if not _re_multirow.match(r'^\s*rp\s*[\d.,]+\s*x\s*[\d.,]+', clean_desc, _re_multirow.IGNORECASE):
						clean_descriptions.append(clean_desc)
			
			# Merge into single description
			merged_desc = ' '.join(clean_descriptions) if clean_descriptions else group['descriptions'][0]
			
			# Create merged item
			merged_item = {
				**value_row,
				'description': merged_desc,
				'line_no': group['start_index'] + 1,  # Will be reassigned later
			}
			
			merged_items.append(merged_item)
		
		filtered_rows = merged_items
		filter_stats["final_items_count"] = len(filtered_rows)
		
		frappe.logger().info(
			f"[MULTIROW] Merged into {len(merged_items)} final items"
		)

	# Assign global line numbers
	for row in filtered_rows:
		if 'line_no' not in row or row.get('line_no', 0) <= 0:
			row["line_no"] = global_line_no
		row["raw_harga_jual"] = row.get("raw_harga_jual", "") or row.get("harga_jual", "") or ""
		row["raw_dpp"] = row.get("raw_dpp", "") or row.get("dpp", "") or ""
		row["raw_ppn"] = row.get("raw_ppn", "") or row.get("ppn", "") or ""
		global_line_no += 1

	page_result["items"] = filtered_rows
	return page_result


def _find_first_non_header_row(tokens: List[Token], skip_keywords: List[str]) -> float:
	"""Find first row without header keywords (for continuation pages)."""
	rows = cluster_tokens_by_row(tokens, y_tolerance=5)

	for y_pos, row_tokens in rows:
		row_text = " ".join([t.text.lower() for t in row_tokens])
		has_header = any(kw.lower() in row_text for kw in skip_keywords)

		if not has_header:
			return y_pos

	return rows[0][0] if rows else 0.0


def _find_table_end_strong(
	tokens: List[Token],
	header_y: float,
	totals_keywords: List[str],
	min_keywords: int = 2
) -> Optional[float]:
	"""
	Find table end with strong detection (requires 2+ keywords).

	Prevents early termination on ambiguous single keywords like "Total" in descriptions.

	🔧 FIX: Added single-keyword strong signals for summary section labels
	that unambiguously mark the end of the line-item table:
	- "Harga Jual / Penggantian" (start of summary totals)
	- "Dikurangi Potongan Harga" (only appears in summary section)
	- "Dasar Pengenaan Pajak" (already existed)
	"""
	below_header = [t for t in tokens if t.y0 > header_y]
	rows = cluster_tokens_by_row(below_header, y_tolerance=5)

	for y_pos, row_tokens in rows:
		row_text = " ".join([t.text.lower() for t in row_tokens])

		keyword_count = sum(1 for kw in totals_keywords if kw in row_text)

		if keyword_count >= min_keywords:
			frappe.logger().info(f"Strong totals block at Y={y_pos:.1f} ({keyword_count} keywords)")
			return y_pos

		# Special case: single phrases that unambiguously end the item table
		if "dasar pengenaan pajak" in row_text:
			return y_pos
		if "harga jual / penggantian" in row_text or "harga jual/penggantian" in row_text:
			# Only if this is NOT the table column header (which is at header_y).
			# Since we already filter `t.y0 > header_y`, any "Harga Jual / Penggantian"
			# row here is the summary label, not the column header.
			frappe.logger().info(
				f"Summary 'Harga Jual / Penggantian' row at Y={y_pos:.1f} → table end"
			)
			return y_pos
		if "dikurangi potongan harga" in row_text:
			frappe.logger().info(
				f"Summary 'Dikurangi Potongan Harga' row at Y={y_pos:.1f} → table end"
			)
			return y_pos

	return None


def parse_tokens(tokens: List[Token], tax_rate: float = 0.11) -> Dict[str, Any]:
	"""
	Pure parsing function: convert tokens to structured line items.

	Parser layer - only accepts Token list, agnostic to source (PyMuPDF or Vision OCR).
	Always uses multi-page parser for consistency (works for page_count=1 too).

	Args:
		tokens: List of Token objects from any source
		tax_rate: PPN tax rate for validation (default 11%)

	Returns:
		Dictionary with:
			- items: List of line item dictionaries
			- debug_info: Debug metadata
			- success: Boolean
			- errors: List of error messages
	"""
	result = {
		"items": [],
		"debug_info": {},
		"success": False,
		"errors": []
	}

	try:
		if not tokens:
			result["errors"].append("No tokens provided")
			return result

		# Determine source and page count
		page_count = max(t.page_no for t in tokens) if tokens else 1
		source = tokens[0].source if tokens else "unknown"

		result["debug_info"]["source"] = source
		result["debug_info"]["token_count"] = len(tokens)
		result["debug_info"]["page_count"] = page_count

		# Store tokens in debug info (truncate if too large)
		MAX_DEBUG_TOKENS = 500
		if len(tokens) <= MAX_DEBUG_TOKENS:
			result["debug_info"]["tokens"] = [t.to_dict() for t in tokens]
		else:
			result["debug_info"]["tokens"] = (
				[t.to_dict() for t in tokens[:100]] +
				[{"text": f"... {len(tokens) - 200} tokens truncated ...", "bbox": [0, 0, 0, 0], "page_no": 0}] +
				[t.to_dict() for t in tokens[-100:]]
			)
			result["debug_info"]["tokens_truncated"] = True

		# ALWAYS use multi-page parser (works for page_count=1 too)
		# No separate single-page legacy path
		multi_result = _parse_multipage(tokens, tax_rate)
		result.update(multi_result)

		result["success"] = True
		frappe.logger().info(
			f"Successfully parsed {len(result['items'])} line items from {page_count} page(s) ({source})"
		)

	except Exception as e:
		error_msg = f"Parsing failed: {str(e)}"
		result["errors"].append(error_msg)
		frappe.log_error(
			title="Tax Invoice Parsing Error",
			message=f"Error: {str(e)}\n{frappe.get_traceback()}"
		)

	return result
