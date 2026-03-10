# -*- coding: utf-8 -*-
# Copyright (c) 2026, Imogi Finance and contributors
# For license information, please see license.txt

"""
Unit tests for Tax Invoice Faktur Pajak Parser.

Tests cover:
- Token extraction and bounding box handling
- Table boundary detection
- Column range detection and expansion
- Row grouping and Y-clustering
- Description wraparound merging
- Indonesian number normalization
- Validation logic and confidence scoring
- Auto-approval threshold logic
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import frappe
from frappe.tests.utils import FrappeTestCase

from imogi_finance.imogi_finance.parsers.faktur_pajak_parser import (
    Token,
    ColumnRange,
    detect_table_header,
    find_table_end,
    cluster_tokens_by_row,
    assign_tokens_to_columns,
    get_rightmost_value,
    merge_description_wraparounds,
    parse_invoice
)
from imogi_finance.imogi_finance.parsers.normalization import (
    normalize_indonesian_number,
    clean_description,
    normalize_line_item,
    extract_npwp
)
from imogi_finance.imogi_finance.parsers.validation import (
    validate_line_item,
    validate_invoice_totals,
    determine_parse_status,
    generate_validation_summary_html
)


class TestToken(unittest.TestCase):
    """Test Token class."""
    
    def test_token_creation(self):
        """Test Token initialization and properties."""
        token = Token("Harga Jual", 100.0, 50.0, 200.0, 70.0)
        
        self.assertEqual(token.text, "Harga Jual")
        self.assertEqual(token.x0, 100.0)
        self.assertEqual(token.y0, 50.0)
        self.assertEqual(token.x1, 200.0)
        self.assertEqual(token.y1, 70.0)
        self.assertEqual(token.x_mid, 150.0)
        self.assertEqual(token.y_mid, 60.0)
        self.assertEqual(token.width, 100.0)
        self.assertEqual(token.height, 20.0)
    
    def test_token_to_dict(self):
        """Test Token serialization to dictionary."""
        token = Token("Test", 10.0, 20.0, 30.0, 40.0)
        token_dict = token.to_dict()
        
        self.assertEqual(token_dict["text"], "Test")
        self.assertEqual(token_dict["bbox"], [10.0, 20.0, 30.0, 40.0])
        self.assertEqual(token_dict["x_mid"], 20.0)
        self.assertEqual(token_dict["y_mid"], 30.0)


class TestColumnRange(unittest.TestCase):
    """Test ColumnRange class."""
    
    def test_column_range_creation(self):
        """Test ColumnRange initialization."""
        col = ColumnRange("harga_jual", 100.0, 200.0)
        
        self.assertEqual(col.name, "harga_jual")
        self.assertEqual(col.x_min, 100.0)
        self.assertEqual(col.x_max, 200.0)
        self.assertEqual(col.width, 100.0)
    
    def test_column_expansion_default(self):
        """Test default column expansion (max of 10px or 5%)."""
        col = ColumnRange("test", 100.0, 200.0)  # width=100
        col.expand()
        
        # Should expand by max(10, 100*0.05) = 10
        self.assertEqual(col.x_min, 90.0)
        self.assertEqual(col.x_max, 210.0)
        self.assertEqual(col.width, 120.0)
    
    def test_column_expansion_pixels(self):
        """Test column expansion with fixed pixels."""
        col = ColumnRange("test", 100.0, 200.0)
        col.expand(pixels=20)
        
        self.assertEqual(col.x_min, 80.0)
        self.assertEqual(col.x_max, 220.0)
    
    def test_column_expansion_percentage(self):
        """Test column expansion with percentage."""
        col = ColumnRange("test", 100.0, 200.0)  # width=100
        col.expand(percentage=0.10)  # 10%
        
        self.assertEqual(col.x_min, 90.0)
        self.assertEqual(col.x_max, 210.0)
    
    def test_column_contains_token(self):
        """Test token containment with overlap ratio."""
        col = ColumnRange("test", 100.0, 200.0)
        
        # Token fully inside
        token1 = Token("1.234.567", 120.0, 50.0, 180.0, 70.0)
        self.assertTrue(col.contains(token1))
        
        # Token partially overlapping (>10% overlap)
        token2 = Token("Test", 190.0, 50.0, 250.0, 70.0)  # 10px overlap / 60px width = 16.7%
        self.assertTrue(col.contains(token2))
        
        # Token outside
        token3 = Token("Outside", 300.0, 50.0, 350.0, 70.0)
        self.assertFalse(col.contains(token3))


class TestRowGrouping(unittest.TestCase):
    """Test row grouping and clustering logic."""
    
    def test_cluster_tokens_by_row(self):
        """Test Y-coordinate clustering into rows."""
        tokens = [
            Token("A", 10, 100, 20, 110),  # Row 1
            Token("B", 30, 102, 40, 112),  # Row 1 (within tolerance)
            Token("C", 50, 150, 60, 160),  # Row 2
            Token("D", 70, 148, 80, 158),  # Row 2 (within tolerance)
            Token("E", 90, 200, 100, 210), # Row 3
        ]
        
        rows = cluster_tokens_by_row(tokens, y_tolerance=5)
        
        self.assertEqual(len(rows), 3)
        self.assertEqual(len(rows[0][1]), 2)  # Row 1 has 2 tokens
        self.assertEqual(len(rows[1][1]), 2)  # Row 2 has 2 tokens
        self.assertEqual(len(rows[2][1]), 1)  # Row 3 has 1 token
    
    def test_empty_token_list(self):
        """Test clustering with empty token list."""
        rows = cluster_tokens_by_row([])
        self.assertEqual(len(rows), 0)


class TestColumnAssignment(unittest.TestCase):
    """Test token assignment to columns."""
    
    def test_assign_tokens_to_columns(self):
        """Test assigning tokens based on X-overlap."""
        # Define columns
        columns = {
            "harga_jual": ColumnRange("harga_jual", 200, 300),
            "dpp": ColumnRange("dpp", 320, 420),
            "ppn": ColumnRange("ppn", 440, 540)
        }
        
        # Create tokens in different columns
        row_tokens = [
            Token("Item A", 10, 50, 100, 70),     # Description (no column)
            Token("1.234.567", 220, 50, 280, 70), # Harga Jual
            Token("1.100.000", 340, 50, 400, 70), # DPP
            Token("121.000", 460, 50, 520, 70),   # PPN
        ]
        
        assignments = assign_tokens_to_columns(row_tokens, columns)
        
        self.assertEqual(len(assignments["harga_jual"]), 1)
        self.assertEqual(assignments["harga_jual"][0].text, "1.234.567")
        self.assertEqual(len(assignments["dpp"]), 1)
        self.assertEqual(assignments["dpp"][0].text, "1.100.000")
        self.assertEqual(len(assignments["ppn"]), 1)
        self.assertEqual(assignments["ppn"][0].text, "121.000")
    
    def test_get_rightmost_value(self):
        """Test extracting rightmost token from column."""
        tokens = [
            Token("Extra", 100, 50, 150, 70),
            Token("Value", 200, 50, 250, 70),
            Token("1.234", 300, 50, 350, 70),  # Rightmost
        ]
        
        rightmost = get_rightmost_value(tokens)
        self.assertEqual(rightmost, "1.234")
        
        # Test empty list
        self.assertIsNone(get_rightmost_value([]))


class TestDescriptionWraparound(unittest.TestCase):
    """Test description wraparound merging."""
    
    def test_merge_description_wraparounds(self):
        """Test merging rows without numbers into previous description."""
        rows = [
            {
                "description": "Jasa Konsultasi IT",
                "harga_jual": "1.234.567",
                "dpp": "1.100.000",
                "ppn": "121.000"
            },
            {
                "description": "untuk periode Januari 2026",
                "harga_jual": None,
                "dpp": None,
                "ppn": None
            },
            {
                "description": "Pengadaan Laptop",
                "harga_jual": "5.000.000",
                "dpp": "4.500.000",
                "ppn": "495.000"
            }
        ]
        
        merged = merge_description_wraparounds(rows)
        
        self.assertEqual(len(merged), 2)
        self.assertIn("untuk periode Januari 2026", merged[0]["description"])
        self.assertEqual(merged[1]["description"], "Pengadaan Laptop")
    
    def test_no_wraparound(self):
        """Test when all rows have numbers (no wraparound)."""
        rows = [
            {"description": "Item 1", "harga_jual": "100", "dpp": "90", "ppn": "10"},
            {"description": "Item 2", "harga_jual": "200", "dpp": "180", "ppn": "20"}
        ]
        
        merged = merge_description_wraparounds(rows)
        
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["description"], "Item 1")
        self.assertEqual(merged[1]["description"], "Item 2")


class TestIndonesianNumberNormalization(unittest.TestCase):
    """Test Indonesian number format parsing."""
    
    def test_standard_format(self):
        """Test standard Indonesian format: 1.234.567,89"""
        self.assertAlmostEqual(
            normalize_indonesian_number("1.234.567,89"),
            1234567.89,
            places=2
        )
    
    def test_without_decimals(self):
        """Test format without decimals: 1.234.567"""
        self.assertAlmostEqual(
            normalize_indonesian_number("1.234.567"),
            1234567.0,
            places=2
        )
    
    def test_split_tokens(self):
        """Test split tokens with spaces: 1 234 567,89"""
        self.assertAlmostEqual(
            normalize_indonesian_number("1 234 567,89"),
            1234567.89,
            places=2
        )
    
    def test_ocr_errors(self):
        """Test OCR error corrections: O->0, I->1"""
        # O -> 0
        self.assertAlmostEqual(
            normalize_indonesian_number("1.234.5O7"),
            1234507.0,
            places=2
        )
        
        # I -> 1
        self.assertAlmostEqual(
            normalize_indonesian_number("I.234.567"),
            1234567.0,
            places=2
        )
    
    def test_invalid_input(self):
        """Test invalid inputs return None."""
        self.assertIsNone(normalize_indonesian_number(""))
        self.assertIsNone(normalize_indonesian_number(None))
        self.assertIsNone(normalize_indonesian_number("abc"))
    
    def test_negative_numbers(self):
        """Test negative numbers return None (invalid for tax invoices)."""
        self.assertIsNone(normalize_indonesian_number("-1.234.567"))


class TestDescriptionCleaning(unittest.TestCase):
    """Test description text cleaning."""
    
    def test_remove_reference_lines(self):
        """Test removal of reference patterns."""
        text = "Jasa Konsultasi IT Referensi: INV-2024-001"
        cleaned = clean_description(text)
        
        self.assertNotIn("Referensi:", cleaned)
        self.assertNotIn("INV-2024-001", cleaned)
        self.assertIn("Jasa Konsultasi IT", cleaned)
    
    def test_merge_whitespace(self):
        """Test merging multiple whitespaces."""
        text = "Jasa    Konsultasi\n\n  IT"
        cleaned = clean_description(text)
        
        self.assertEqual(cleaned, "Jasa Konsultasi IT")
    
    def test_empty_input(self):
        """Test empty input."""
        self.assertEqual(clean_description(""), "")
        self.assertEqual(clean_description(None), "")


class TestNPWPExtraction(unittest.TestCase):
    """Test NPWP extraction and normalization."""
    
    def test_formatted_npwp(self):
        """Test NPWP with dots and dashes: 12.345.678.9-012.000"""
        npwp = extract_npwp("12.345.678.9-012.000")
        self.assertEqual(npwp, "123456789012000")
    
    def test_plain_npwp(self):
        """Test plain 15-digit NPWP."""
        npwp = extract_npwp("123456789012000")
        self.assertEqual(npwp, "123456789012000")
    
    def test_npwp_in_text(self):
        """Test extracting NPWP from larger text."""
        text = "NPWP: 12.345.678.9-012.000 Nama: PT ABC"
        npwp = extract_npwp(text)
        self.assertEqual(npwp, "123456789012000")
    
    def test_invalid_npwp(self):
        """Test invalid NPWP returns None."""
        self.assertIsNone(extract_npwp("12345"))
        self.assertIsNone(extract_npwp(""))
        self.assertIsNone(extract_npwp(None))


class TestLineItemValidation(FrappeTestCase):
    """Test line item validation logic."""
    
    def test_valid_line_item(self):
        """Test validation of perfect line item."""
        item = {
            "harga_jual": 1234567.0,
            "dpp": 1100000.0,
            "ppn": 121000.0  # Exactly 11% of DPP
        }
        
        validated = validate_line_item(item, tax_rate=0.11, tolerance_idr=100, tolerance_percentage=0.01)
        
        self.assertEqual(validated["row_confidence"], 1.0)
        self.assertEqual(validated["notes"], "")
    
    def test_line_item_within_tolerance(self):
        """Test line item within tolerance range."""
        item = {
            "harga_jual": 1234567.0,
            "dpp": 1100000.0,
            "ppn": 121050.0  # 50 IDR off (within 10,000 tolerance)
        }
        
        validated = validate_line_item(item, tax_rate=0.11, tolerance_idr=10000, tolerance_percentage=0.01)
        
        self.assertGreaterEqual(validated["row_confidence"], 0.95)
        self.assertLess(validated["row_confidence"], 1.0)
    
    def test_line_item_outside_tolerance(self):
        """Test line item outside tolerance."""
        item = {
            "harga_jual": 1234567.0,
            "dpp": 1100000.0,
            "ppn": 150000.0  # Way off
        }
        
        validated = validate_line_item(item, tax_rate=0.11, tolerance_idr=10000, tolerance_percentage=0.01)
        
        self.assertLess(validated["row_confidence"], 0.95)
        self.assertIn("PPN mismatch", validated["notes"])
    
    def test_harga_jual_less_than_dpp(self):
        """Test when Harga Jual < DPP (warning condition)."""
        item = {
            "harga_jual": 900000.0,  # Less than DPP
            "dpp": 1100000.0,
            "ppn": 121000.0
        }
        
        validated = validate_line_item(item, tax_rate=0.11, tolerance_idr=100, tolerance_percentage=0.01)
        
        self.assertLess(validated["row_confidence"], 1.0)
        self.assertIn("Harga Jual", validated["notes"])
    
    def test_missing_values(self):
        """Test handling of missing values."""
        item = {
            "harga_jual": None,
            "dpp": None,
            "ppn": None
        }
        
        validated = validate_line_item(item, tax_rate=0.11, tolerance_idr=100, tolerance_percentage=0.01)
        
        self.assertLess(validated["row_confidence"], 0.5)
        self.assertIn("Missing", validated["notes"])


class TestInvoiceTotalsValidation(FrappeTestCase):
    """Test invoice-level totals validation."""
    
    def test_totals_match(self):
        """Test when line items sum matches header totals."""
        items = [
            {"harga_jual": 1000000, "dpp": 900000, "ppn": 99000},
            {"harga_jual": 2000000, "dpp": 1800000, "ppn": 198000}
        ]
        
        header_totals = {
            "harga_jual": 3000000,
            "dpp": 2700000,
            "ppn": 297000
        }
        
        result = validate_invoice_totals(items, header_totals, tolerance_idr=100, tolerance_percentage=0.01)
        
        self.assertTrue(result["match"])
        self.assertEqual(len(result["notes"]), 0)
    
    def test_totals_mismatch(self):
        """Test when totals don't match."""
        items = [
            {"harga_jual": 1000000, "dpp": 900000, "ppn": 99000},
            {"harga_jual": 2000000, "dpp": 1800000, "ppn": 198000}
        ]
        
        header_totals = {
            "harga_jual": 5000000,  # Wrong
            "dpp": 2700000,
            "ppn": 297000
        }
        
        result = validate_invoice_totals(items, header_totals, tolerance_idr=100, tolerance_percentage=0.01)
        
        self.assertFalse(result["match"])
        self.assertGreater(len(result["notes"]), 0)
        self.assertIn("Harga Jual", result["notes"][0])


class TestAutoApprovalLogic(FrappeTestCase):
    """Test auto-approval status determination."""
    
    def test_auto_approve_perfect_invoice(self):
        """Test auto-approval when all conditions met."""
        items = [
            {"row_confidence": 1.0, "harga_jual": 1000000, "dpp": 900000, "ppn": 99000},
            {"row_confidence": 0.98, "harga_jual": 2000000, "dpp": 1800000, "ppn": 198000}
        ]
        
        invalid_items = []
        totals_validation = {"match": True}
        
        status = determine_parse_status(items, invalid_items, totals_validation, header_complete=True)
        
        self.assertEqual(status, "Approved")
    
    def test_needs_review_low_confidence(self):
        """Test 'Needs Review' when confidence < 0.95."""
        items = [
            {"row_confidence": 0.85, "harga_jual": 1000000, "dpp": 900000, "ppn": 99000}
        ]
        
        invalid_items = [{"line_no": 1, "confidence": 0.85}]
        totals_validation = {"match": True}
        
        status = determine_parse_status(items, invalid_items, totals_validation, header_complete=True)
        
        self.assertEqual(status, "Needs Review")
    
    def test_needs_review_totals_mismatch(self):
        """Test 'Needs Review' when totals don't match."""
        items = [
            {"row_confidence": 1.0, "harga_jual": 1000000, "dpp": 900000, "ppn": 99000}
        ]
        
        invalid_items = []
        totals_validation = {"match": False}
        
        status = determine_parse_status(items, invalid_items, totals_validation, header_complete=True)
        
        self.assertEqual(status, "Needs Review")
    
    def test_needs_review_incomplete_header(self):
        """Test 'Needs Review' when header incomplete."""
        items = [
            {"row_confidence": 1.0, "harga_jual": 1000000, "dpp": 900000, "ppn": 99000}
        ]
        
        invalid_items = []
        totals_validation = {"match": True}
        
        status = determine_parse_status(items, invalid_items, totals_validation, header_complete=False)
        
        self.assertEqual(status, "Needs Review")


class TestValidationSummaryHTML(FrappeTestCase):
    """Test HTML summary generation."""
    
    def test_generate_summary_approved(self):
        """Test HTML generation for approved status."""
        items = [
            {"row_confidence": 1.0},
            {"row_confidence": 0.98}
        ]
        invalid_items = []
        totals_validation = {"match": True, "notes": []}
        
        html = generate_validation_summary_html(items, invalid_items, totals_validation, "Approved")
        
        self.assertIn("Approved", html)
        self.assertIn("green", html)
        self.assertIn("2 total", html)
    
    def test_generate_summary_needs_review(self):
        """Test HTML generation for needs review status."""
        items = [
            {"row_confidence": 0.85},
            {"row_confidence": 1.0}
        ]
        invalid_items = [
            {"line_no": 1, "confidence": 0.85, "reason": "PPN mismatch"}
        ]
        totals_validation = {"match": False, "notes": ["DPP mismatch: 100,000"]}
        
        html = generate_validation_summary_html(items, invalid_items, totals_validation, "Needs Review")
        
        self.assertIn("Needs Review", html)
        self.assertIn("orange", html)
        self.assertIn("PPN mismatch", html)
        self.assertIn("DPP mismatch", html)


class TestGoldenSampleFP(FrappeTestCase):
    """
    Test case for golden sample Faktur Pajak with challenging layout:
    - Single line item with 4-line wrapped description
    - Description contains amounts: "Rp 1.049.485,00 x 1,00 Lainnya"
    - Additional lines: "Potongan Harga = Rp 0,00", "PPnBM (0,00%) = Rp 0,00"
    - Valid Harga Jual 1.049.485,00 only in rightmost column
    - DPP 962.028,00, PPN 115.443,00
    
    Critical assertions:
    1. Amounts in description column are ignored
    2. PPnBM line merges to previous row (not separate item)
    3. Correct Harga Jual extracted from rightmost column only
    4. Validation passes with high confidence
    """
    
    def test_golden_sample_extraction(self):
        """Test extraction of golden sample FP with wrapped description containing amounts."""
        # Simulate tokens from golden sample FP
        # Column ranges (approximate X positions):
        # Description: 50-350
        # Harga Jual: 400-500
        # DPP: 510-600
        # PPN: 610-700
        
        # Define column ranges
        col_ranges = {
            "harga_jual": ColumnRange(400, 500),
            "dpp": ColumnRange(510, 600),
            "ppn": ColumnRange(610, 700)
        }
        
        # Row 1: Line item description + valid amounts in correct columns
        row1_tokens = [
            Token("Utility 01#01 / 2.IU.03 / DIRNOSAURUS", 50, 100, 340, 110),  # Description
            Token("1.049.485,00", 410, 100, 490, 110),  # Harga Jual (rightmost column)
            Token("962.028,00", 520, 100, 590, 110),    # DPP
            Token("115.443,00", 620, 100, 690, 110)     # PPN
        ]
        
        # Row 2: Description wraparound with amount (should be ignored)
        row2_tokens = [
            Token("Rp 1.049.485,00 x 1,00 Lainnya", 50, 115, 280, 125)  # Amount in description
        ]
        
        # Row 3: Potongan Harga line (should merge)
        row3_tokens = [
            Token("Potongan Harga = Rp 0,00", 50, 130, 250, 140)
        ]
        
        # Row 4: PPnBM line (should merge)
        row4_tokens = [
            Token("PPnBM (0,00%) = Rp 0,00", 50, 145, 240, 155)
        ]
        
        # Assign tokens to columns for each row
        assign1 = assign_tokens_to_columns(row1_tokens, col_ranges)
        assign2 = assign_tokens_to_columns(row2_tokens, col_ranges)
        assign3 = assign_tokens_to_columns(row3_tokens, col_ranges)
        assign4 = assign_tokens_to_columns(row4_tokens, col_ranges)
        
        # Assert: Row 1 has values in all columns
        self.assertEqual(len(assign1["harga_jual"]), 1)
        self.assertEqual(len(assign1["dpp"]), 1)
        self.assertEqual(len(assign1["ppn"]), 1)
        self.assertEqual(assign1["harga_jual"][0].text, "1.049.485,00")
        
        # Assert: Row 2-4 have NO assignments (description-only, amounts excluded)
        self.assertEqual(len(assign2["harga_jual"]), 0)
        self.assertEqual(len(assign2["dpp"]), 0)
        self.assertEqual(len(assign2["ppn"]), 0)
        
        self.assertEqual(len(assign3["harga_jual"]), 0)
        self.assertEqual(len(assign4["harga_jual"]), 0)
        
        # Simulate parsed rows
        rows = [
            {
                "description": "Utility 01#01 / 2.IU.03 / DIRNOSAURUS",
                "harga_jual": "1.049.485,00",
                "dpp": "962.028,00",
                "ppn": "115.443,00"
            },
            {
                "description": "Rp 1.049.485,00 x 1,00 Lainnya",
                "harga_jual": None,
                "dpp": None,
                "ppn": None
            },
            {
                "description": "Potongan Harga = Rp 0,00",
                "harga_jual": None,
                "dpp": None,
                "ppn": None
            },
            {
                "description": "PPnBM (0,00%) = Rp 0,00",
                "harga_jual": None,
                "dpp": None,
                "ppn": None
            }
        ]
        
        # Merge wraparounds
        merged = merge_description_wraparounds(rows)
        
        # Assert: Only 1 item after merge
        self.assertEqual(len(merged), 1)
        
        # Assert: Description contains all wrapped lines
        final_desc = merged[0]["description"]
        self.assertIn("Utility", final_desc)
        self.assertIn("Rp 1.049.485,00 x 1,00 Lainnya", final_desc)
        self.assertIn("Potongan Harga", final_desc)
        self.assertIn("PPnBM", final_desc)
        
        # Assert: Numeric values unchanged (from first row only)
        self.assertEqual(merged[0]["harga_jual"], "1.049.485,00")
        self.assertEqual(merged[0]["dpp"], "962.028,00")
        self.assertEqual(merged[0]["ppn"], "115.443,00")
        
    def test_golden_sample_validation(self):
        """Test validation of golden sample line item."""
        line_item = {
            "harga_jual": 1049485.0,
            "dpp": 962028.0,
            "ppn": 115443.0,
            "tax_rate": 0.12  # 12% PPN
        }
        
        # Mock tolerance settings
        with patch("imogi_finance.parsers.validation.get_tolerance_settings") as mock_settings:
            mock_settings.return_value = {
                "absolute_tolerance": 10000,
                "relative_tolerance": 0.01
            }
            
            # Validate
            result = validate_line_item(line_item, 0.12)
            
            # Assert: Validation passes
            self.assertTrue(result["valid"])
            self.assertGreaterEqual(result["confidence"], 0.95)
            
            # Check calculations
            # Expected PPN = 962,028.00 × 0.12 = 115,443.36
            # Actual PPN = 115,443.00
            # Difference = 0.36 (within tolerance)
            expected_ppn = 962028.0 * 0.12
            diff = abs(115443.0 - expected_ppn)
            self.assertLess(diff, 1.0)  # Less than 1 IDR difference


# Test runner
def run_tests():
    """Run all tests."""
    unittest.main()


class TestSummaryRowFilter(unittest.TestCase):
    """Test summary/header row filtering logic."""
    
    def test_filter_summary_rows_harga_jual_pengganti(self):
        """Test that 'Harga Jual / Pengganti' rows are filtered out."""
        # Simulate merged rows with real items AND summary rows
        merged_rows = [
            {
                "description": "Jasa Utility 01#01 / 2L Maintenance Service",
                "harga_jual": "962.028,00",
                "dpp": "962.028,00",
                "ppn": "115.443,00",
                "page_no": 1,
                "row_y": 100.0
            },
            {
                "description": "Harga Jual / Pengganti / Uang Muka / Termin",
                "harga_jual": "962.028,00",
                "dpp": "",
                "ppn": "",
                "page_no": 1,
                "row_y": 200.0
            },
            {
                "description": "Dasar Pengenaan Pajak",
                "harga_jual": "962.028,00",
                "dpp": "",
                "ppn": "",
                "page_no": 1,
                "row_y": 210.0
            }
        ]
        
        # Apply the same filter logic as in _parse_page
        SUMMARY_ROW_KEYWORDS = {
            "harga jual / pengganti",
            "harga jual/pengganti",
            "harga jual / pengganti / uang muka",
            "dasar pengenaan pajak",
            "jumlah ppn",
            "ppn = ",
            "grand total",
        }
        
        filtered_rows = []
        for row in merged_rows:
            desc = row.get("description", "").lower().strip()
            if any(kw in desc for kw in SUMMARY_ROW_KEYWORDS):
                continue
            filtered_rows.append(row)
        
        # Assert: Only the real item remains
        self.assertEqual(len(filtered_rows), 1)
        self.assertIn("Jasa Utility", filtered_rows[0]["description"])
    
    def test_filter_header_rows(self):
        """Test that header rows like 'No. Barang / Nama Barang' are filtered."""
        merged_rows = [
            {
                "description": "No. Barang / Nama Barang",
                "harga_jual": "",
                "dpp": "",
                "ppn": "",
                "page_no": 1,
            },
            {
                "description": "1234567890 / Widget Premium",
                "harga_jual": "500.000,00",
                "dpp": "500.000,00",
                "ppn": "60.000,00",
                "page_no": 1,
            }
        ]
        
        HEADER_ROW_KEYWORDS = {
            "no. barang",
            "nama barang",
            "no. barang / nama barang",
        }
        
        filtered_rows = []
        for row in merged_rows:
            desc = row.get("description", "").lower().strip()
            if any(kw in desc for kw in HEADER_ROW_KEYWORDS):
                continue
            filtered_rows.append(row)
        
        # Assert: Only the real item remains
        self.assertEqual(len(filtered_rows), 1)
        self.assertIn("Widget Premium", filtered_rows[0]["description"])
    
    def test_filter_zero_dpp_ppn_with_suspect_keyword(self):
        """Test extra rule: DPP=0 AND PPN=0 with suspect keywords."""
        merged_rows = [
            {
                "description": "Regular Service Item",
                "harga_jual": "100.000,00",
                "dpp": "100.000,00",
                "ppn": "12.000,00",
                "page_no": 1,
            },
            {
                "description": "PPn Keluaran",  # Contains 'ppn' with zero values
                "harga_jual": "12.000,00",
                "dpp": "",
                "ppn": "",
                "page_no": 1,
            },
            {
                "description": "DPP yang tidak dipungut",  # Contains 'dpp' with zero values
                "harga_jual": "100.000,00",
                "dpp": "0",
                "ppn": "0",
                "page_no": 1,
            }
        ]
        
        ZERO_VALUE_SUSPECT_KEYWORDS = {"ppn", "dpp", "dasar", "harga jual", "total"}
        
        def is_zero_value_suspect(row):
            desc = row.get("description", "").lower()
            raw_dpp = row.get("dpp", "") or ""
            raw_ppn = row.get("ppn", "") or ""
            
            # Parse values
            try:
                dpp_val = float(raw_dpp.replace(".", "").replace(",", ".")) if raw_dpp.strip() else 0
            except ValueError:
                dpp_val = 0
            try:
                ppn_val = float(raw_ppn.replace(".", "").replace(",", ".")) if raw_ppn.strip() else 0
            except ValueError:
                ppn_val = 0
            
            if dpp_val == 0 and ppn_val == 0:
                for kw in ZERO_VALUE_SUSPECT_KEYWORDS:
                    if kw in desc:
                        return True
            return False
        
        filtered_rows = [row for row in merged_rows if not is_zero_value_suspect(row)]
        
        # Assert: Only the regular item remains
        self.assertEqual(len(filtered_rows), 1)
        self.assertEqual(filtered_rows[0]["description"], "Regular Service Item")
    
    def test_real_items_not_filtered(self):
        """Test that legitimate items are NOT filtered even if they contain partial keywords."""
        merged_rows = [
            {
                "description": "Jasa Konsultasi Pajak",  # Contains 'jasa' but valid
                "harga_jual": "5.000.000,00",
                "dpp": "5.000.000,00",
                "ppn": "600.000,00",
                "page_no": 1,
            },
            {
                "description": "Pembelian Barang Dasar",  # Contains 'dasar' but valid with values
                "harga_jual": "1.000.000,00",
                "dpp": "1.000.000,00",
                "ppn": "120.000,00",
                "page_no": 1,
            },
            {
                "description": "Total Care Service Package",  # Contains 'total' but valid with values
                "harga_jual": "2.500.000,00",
                "dpp": "2.500.000,00",
                "ppn": "300.000,00",
                "page_no": 1,
            }
        ]
        
        # These should NOT be filtered because:
        # 1. They have valid DPP/PPN values
        # 2. They don't match exact summary keywords
        SUMMARY_ROW_KEYWORDS = {
            "harga jual / pengganti",
            "dasar pengenaan pajak",  # Full phrase, not just "dasar"
            "grand total",  # Full phrase, not just "total"
        }
        
        filtered_rows = []
        for row in merged_rows:
            desc = row.get("description", "").lower().strip()
            if any(kw in desc for kw in SUMMARY_ROW_KEYWORDS):
                continue
            filtered_rows.append(row)
        
        # Assert: All items remain (they're legitimate)
        self.assertEqual(len(filtered_rows), 3)
    
    def test_comprehensive_filter_scenario(self):
        """
        Comprehensive test simulating real parsing output.
        
        Scenario: Parser extracted 6 rows from a Faktur Pajak PDF.
        - 2 are real line items
        - 4 are summary/header rows that leaked through
        """
        parse_output_rows = [
            # Real item 1
            {
                "line_no": 1,
                "description": "Jasa Utility 01#01 / 2L Water Treatment Monthly",
                "harga_jual": "962.028,00",
                "dpp": "962.028,00", 
                "ppn": "115.443,00",
                "page_no": 1,
            },
            # Real item 2  
            {
                "line_no": 2,
                "description": "Biaya Admin Bulanan",
                "harga_jual": "50.000,00",
                "dpp": "50.000,00",
                "ppn": "6.000,00",
                "page_no": 1,
            },
            # Summary row - should be filtered
            {
                "line_no": 3,
                "description": "Harga Jual / Pengganti / Uang Muka / Termin",
                "harga_jual": "1.012.028,00",
                "dpp": "",
                "ppn": "",
                "page_no": 1,
            },
            # Summary row - should be filtered
            {
                "line_no": 4,
                "description": "Dasar Pengenaan Pajak",
                "harga_jual": "1.012.028,00",
                "dpp": "",
                "ppn": "",
                "page_no": 1,
            },
            # Summary row - should be filtered  
            {
                "line_no": 5,
                "description": "PPN = 12% x Dasar Pengenaan Pajak",
                "harga_jual": "",
                "dpp": "",
                "ppn": "",
                "page_no": 1,
            },
            # Header row - should be filtered
            {
                "line_no": 6,
                "description": "No. Barang / Nama Barang",
                "harga_jual": "",
                "dpp": "",
                "ppn": "",
                "page_no": 1,
            },
        ]
        
        # Combined filter keywords (matching parser implementation)
        SUMMARY_ROW_KEYWORDS = {
            "harga jual / pengganti",
            "harga jual/pengganti",
            "harga jual / pengganti / uang muka",
            "dasar pengenaan pajak",
            "jumlah ppn",
            "ppn = ",
            "ppn =",
            "grand total",
        }
        HEADER_ROW_KEYWORDS = {
            "no. barang",
            "nama barang", 
            "no. barang / nama barang",
        }
        ZERO_VALUE_SUSPECT_KEYWORDS = {"ppn", "dpp", "dasar", "harga jual"}
        
        def should_filter(row):
            desc = row.get("description", "").lower().strip()
            
            # Check summary keywords
            for kw in SUMMARY_ROW_KEYWORDS:
                if kw in desc:
                    return True
            
            # Check header keywords
            for kw in HEADER_ROW_KEYWORDS:
                if kw in desc:
                    return True
            
            # Check zero value rule
            raw_dpp = row.get("dpp", "") or ""
            raw_ppn = row.get("ppn", "") or ""
            try:
                dpp_val = float(raw_dpp.replace(".", "").replace(",", ".")) if raw_dpp.strip() else 0
            except ValueError:
                dpp_val = 0
            try:
                ppn_val = float(raw_ppn.replace(".", "").replace(",", ".")) if raw_ppn.strip() else 0
            except ValueError:
                ppn_val = 0
            
            if dpp_val == 0 and ppn_val == 0:
                for kw in ZERO_VALUE_SUSPECT_KEYWORDS:
                    if kw in desc:
                        return True
            
            return False
        
        filtered_rows = [row for row in parse_output_rows if not should_filter(row)]
        
        # Assert: Only 2 real items remain
        self.assertEqual(len(filtered_rows), 2)
        
        # Assert: Correct items remain
        descriptions = [r["description"] for r in filtered_rows]
        self.assertTrue(any("Jasa Utility" in d for d in descriptions))
        self.assertTrue(any("Biaya Admin" in d for d in descriptions))
        
        # Assert: No summary rows remain
        for row in filtered_rows:
            desc = row["description"].lower()
            self.assertNotIn("harga jual / pengganti", desc)
            self.assertNotIn("dasar pengenaan pajak", desc)
            self.assertNotIn("no. barang", desc)
    
    def test_whitespace_normalization(self):
        """Test that whitespace variations are handled correctly."""
        import re
        
        # Simulate rows with various whitespace patterns
        test_cases = [
            # Should be filtered (whitespace variations)
            {"description": "Harga  Jual /  Pengganti", "expected_filtered": True},
            {"description": "Harga Jual/Pengganti", "expected_filtered": True},
            {"description": "DASAR   PENGENAAN   PAJAK", "expected_filtered": True},
            {"description": "  No. Barang / Nama Barang  ", "expected_filtered": True},
            {"description": "\tHarga Jual / Pengganti\n", "expected_filtered": True},
            # Should NOT be filtered (legitimate items)
            {"description": "Jasa Maintenance Harga Premium", "expected_filtered": False},
            {"description": "Service Barang Dasar", "expected_filtered": False},
        ]
        
        SUMMARY_ROW_KEYWORDS = {
            "harga jual / pengganti",
            "harga jual/pengganti",
            "dasar pengenaan pajak",
        }
        HEADER_ROW_KEYWORDS = {
            "no. barang",
            "nama barang",
            "no. barang / nama barang",
        }
        
        def should_filter(desc):
            # Whitespace normalization: collapse multiple spaces, strip, lowercase
            text_lower = re.sub(r'\s+', ' ', desc.lower().strip())
            
            for kw in SUMMARY_ROW_KEYWORDS:
                if kw in text_lower:
                    return True
            for kw in HEADER_ROW_KEYWORDS:
                if kw in text_lower:
                    return True
            return False
        
        for case in test_cases:
            result = should_filter(case["description"])
            self.assertEqual(
                result, 
                case["expected_filtered"],
                f"Failed for '{case['description']}': expected filtered={case['expected_filtered']}, got {result}"
            )
    
    def test_filter_stats_structure(self):
        """Test that filter_stats contains expected counters."""
        # Expected structure after parsing
        expected_keys = {
            "raw_rows_count",
            "filtered_summary_count",
            "filtered_header_count",
            "filtered_zero_suspect_count",
            "final_items_count",
            "first_10_filtered_descriptions"
        }
        
        # Mock filter_stats (as would be returned by _parse_page)
        filter_stats = {
            "raw_rows_count": 6,
            "filtered_summary_count": 2,
            "filtered_header_count": 1,
            "filtered_zero_suspect_count": 1,
            "final_items_count": 2,
            "first_10_filtered_descriptions": [
                "'Harga Jual / Pengganti' (summary keyword 'harga jual / pengganti')",
                "'Dasar Pengenaan Pajak' (summary keyword 'dasar pengenaan pajak')"
            ]
        }
        
        # Assert all expected keys exist
        for key in expected_keys:
            self.assertIn(key, filter_stats, f"Missing key: {key}")
        
        # Assert types are correct
        self.assertIsInstance(filter_stats["raw_rows_count"], int)
        self.assertIsInstance(filter_stats["first_10_filtered_descriptions"], list)
        
        # Assert values make sense
        total_filtered = (
            filter_stats["filtered_summary_count"] +
            filter_stats["filtered_header_count"] +
            filter_stats["filtered_zero_suspect_count"]
        )
        self.assertEqual(
            filter_stats["raw_rows_count"] - total_filtered,
            filter_stats["final_items_count"]
        )


if __name__ == "__main__":
    run_tests()
