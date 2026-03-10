# -*- coding: utf-8 -*-
# Copyright (c) 2026, Imogi Finance and contributors
# For license information, please see license.txt

"""
Comprehensive tests for Tax Invoice OCR Parsing with VAT handling.

Tests cover:
1. Inclusive VAT detection and DPP auto-correction
2. Item code validation
3. Invoice date validation
4. Number format parsing and validation
5. Line item summation validation
6. Enhanced validation with context
"""

import pytest
import frappe
from datetime import datetime, timedelta


class TestVATInclusivityDetection:
	"""Test inclusive VAT detection and DPP recalculation."""

	def test_detect_inclusive_vat_standard_case(self):
		"""Test detection of inclusive VAT with invoice amounts."""
		from imogi_finance.imogi_finance.parsers.normalization import detect_vat_inclusivity

		# Standard Indonesian invoice: Harga Jual = Rp 1.232.100 (includes 11% VAT)
		# DPP should be Rp 1.111.000, PPN should be Rp 121.100
		result = detect_vat_inclusivity(
			harga_jual=1232100,
			dpp=1111000,
			ppn=121100,
			tax_rate=0.11
		)

		assert result["is_inclusive"] == True
		assert result["confidence"] >= 0.90
		assert abs(result["expected_dpp"] - 1111000) < 1  # Within rounding
		assert abs(result["expected_ppn"] - 121100) < 1

	def test_detect_separate_vat_case(self):
		"""Test detection when VAT is separate."""
		from imogi_finance.imogi_finance.parsers.normalization import detect_vat_inclusivity

		# Separate VAT: Harga Jual = DPP + PPN
		result = detect_vat_inclusivity(
			harga_jual=1000000,
			dpp=1000000,
			ppn=110000,
			tax_rate=0.11
		)

		assert result["is_inclusive"] == False
		assert "separate" in result["reason"].lower()

	def test_recalculate_dpp_from_inclusive(self):
		"""Test DPP recalculation from inclusive amount."""
		from imogi_finance.imogi_finance.parsers.normalization import recalculate_dpp_from_inclusive

		# Harga Jual = Rp 1.232.100 (inclusive of 11% VAT)
		result = recalculate_dpp_from_inclusive(harga_jual=1232100, tax_rate=0.11)

		# DPP = 1.232.100 / 1.11 = 1.111.000
		# PPN = 1.111.000 × 0.11 = 122.100
		assert abs(result["dpp"] - 1111000.00) < 1
		assert abs(result["ppn"] - 122100.00) < 1


class TestItemCodeValidation:
	"""Test item code validation."""

	def test_valid_numeric_code(self):
		"""Test acceptance of valid numeric codes."""
		from imogi_finance.imogi_finance.parsers.validation import validate_item_code

		result = validate_item_code("123456")
		assert result["is_valid"] == True
		assert result["severity"] == "ok"
		assert result["confidence_penalty"] == 1.0

	def test_invalid_default_code(self):
		"""Test rejection of default code '000000'."""
		from imogi_finance.imogi_finance.parsers.validation import validate_item_code

		result = validate_item_code("000000")
		assert result["is_valid"] == False
		assert result["severity"] == "error"
		assert result["confidence_penalty"] < 0.9

	def test_missing_code(self):
		"""Test handling of missing code."""
		from imogi_finance.imogi_finance.parsers.validation import validate_item_code

		result = validate_item_code(None)
		assert result["is_valid"] == False
		assert result["severity"] == "warning"

	def test_valid_alphanumeric_code(self):
		"""Test acceptance of alphanumeric codes."""
		from imogi_finance.imogi_finance.parsers.validation import validate_item_code

		result = validate_item_code("ABC123")
		assert result["is_valid"] == True


class TestInvoiceDateValidation:
	"""Test invoice date validation."""

	def test_valid_date_within_period(self):
		"""Test validation of date within fiscal period."""
		from imogi_finance.imogi_finance.parsers.validation import validate_invoice_date

		result = validate_invoice_date(
			invoice_date="15-01-2026",
			fiscal_period_start="2026-01-01",
			fiscal_period_end="2026-12-31"
		)

		assert result["is_valid"] == True
		assert result["in_period"] == True

	def test_date_outside_period(self):
		"""Test validation of date outside fiscal period."""
		from imogi_finance.imogi_finance.parsers.validation import validate_invoice_date

		result = validate_invoice_date(
			invoice_date="15-12-2025",
			fiscal_period_start="2026-01-01",
			fiscal_period_end="2026-12-31"
		)

		assert result["is_valid"] == False
		assert result["in_period"] == False

	def test_future_date_rejection(self):
		"""Test rejection of future dates."""
		from imogi_finance.imogi_finance.parsers.validation import validate_invoice_date

		future_date = (datetime.now() + timedelta(days=10)).strftime("%d-%m-%Y")
		result = validate_invoice_date(invoice_date=future_date)

		assert result["is_valid"] == False

	def test_missing_date(self):
		"""Test handling of missing date."""
		from imogi_finance.imogi_finance.parsers.validation import validate_invoice_date

		result = validate_invoice_date(invoice_date=None)
		assert result["is_valid"] == False


class TestNumberFormatParsing:
	"""Test Indonesian number format parsing."""

	def test_standard_indonesian_format(self):
		"""Test parsing of standard Indonesian format."""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_indonesian_number

		# 1.234.567,89 (Indonesian: dot=thousands, comma=decimal)
		result = normalize_indonesian_number("1.234.567,89")
		assert abs(result - 1234567.89) < 0.01

	def test_thousand_separator_only(self):
		"""Test parsing with thousand separator but no decimal."""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_indonesian_number

		result = normalize_indonesian_number("1.000.000")
		assert abs(result - 1000000.0) < 0.01

	def test_decimal_comma_only(self):
		"""Test parsing with decimal comma but no thousands separator."""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_indonesian_number

		result = normalize_indonesian_number("1234567,89")
		assert abs(result - 1234567.89) < 0.01

	def test_ocr_error_fixing(self):
		"""Test OCR error correction (O->0, I->1)."""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_indonesian_number

		# OCR might read O as O and 1 as I
		result = normalize_indonesian_number("1234O6789")
		assert result is not None  # Should parse despite OCR error

	def test_number_format_validation(self):
		"""Test validation of parsed number format."""
		from imogi_finance.imogi_finance.parsers.normalization import validate_number_format

		# Valid: Indonesian format amount
		result = validate_number_format("1.234.567,89", 1234567.89)
		assert result["is_valid"] == True
		assert result["confidence"] >= 0.9

		# Invalid: suspiciously small amount
		result = validate_number_format("1.234.567,89", 123.45)
		assert result["is_valid"] == False
		assert "parsing error" in result["message"].lower()


class TestLineSummationValidation:
	"""Test line item summation validation."""

	def test_matching_totals(self):
		"""Test validation when line totals match header totals."""
		from imogi_finance.imogi_finance.parsers.validation import validate_line_summation

		items = [
			{"harga_jual": 1000000, "dpp": 900000, "ppn": 99000},
			{"harga_jual": 2000000, "dpp": 1800000, "ppn": 198000}
		]
		header_totals = {
			"harga_jual": 3000000,
			"dpp": 2700000,
			"ppn": 297000
		}

		result = validate_line_summation(items, header_totals)
		assert result["is_valid"] == True
		assert result["match"] == True

	def test_mismatched_totals(self):
		"""Test validation when totals don't match."""
		from imogi_finance.imogi_finance.parsers.validation import validate_line_summation

		items = [
			{"harga_jual": 1000000, "dpp": 900000, "ppn": 99000}
		]
		header_totals = {
			"harga_jual": 2000000,
			"dpp": 1800000,
			"ppn": 198000
		}

		result = validate_line_summation(items, header_totals)
		assert result["is_valid"] == False
		assert result["match"] == False
		assert len(result["suggestions"]) > 0

	def test_tolerance_within_range(self):
		"""Test that small differences are within tolerance."""
		from imogi_finance.imogi_finance.parsers.validation import validate_line_summation

		items = [
			{"harga_jual": 1000000, "dpp": 900000, "ppn": 99000}
		]
		header_totals = {
			"harga_jual": 1000005,  # Difference of 5 IDR (within tolerance)
			"dpp": 900000,
			"ppn": 99000
		}

		result = validate_line_summation(items, header_totals, tolerance_idr=10000)
		assert result["match"] == True


class TestEnhancedLineValidation:
	"""Test enhanced line item validation with VAT context."""

	def test_validate_line_with_item_code(self):
		"""Test line validation that includes item code checking."""
		from imogi_finance.imogi_finance.parsers.validation import validate_line_item

		item = {
			"line_no": 1,
			"description": "Item 1",
			"harga_jual": 1000000,
			"dpp": 900000,
			"ppn": 99000,
			"item_code": "123456"
		}

		result = validate_line_item(item)
		assert "item_code" not in result.get("notes", "")

	def test_validate_line_with_invalid_code(self):
		"""Test line validation with invalid item code."""
		from imogi_finance.imogi_finance.parsers.validation import validate_line_item

		item = {
			"line_no": 1,
			"description": "Item 1",
			"harga_jual": 1000000,
			"dpp": 900000,
			"ppn": 99000,
			"item_code": "000000"
		}

		result = validate_line_item(item)
		assert result["row_confidence"] < 1.0
		assert "item code" in result.get("notes", "").lower()


class TestDecimalSeparatorDetection:
	"""Test detection of decimal separator in ambiguous formats."""

	def test_indonesian_format_detection(self):
		"""Test detection of Indonesian format (dot=thousand, comma=decimal)."""
		from imogi_finance.imogi_finance.parsers.normalization import find_decimal_separator

		thousand_sep, decimal_sep = find_decimal_separator("1.234.567,89")
		assert thousand_sep == "."
		assert decimal_sep == ","

	def test_us_format_detection(self):
		"""Test detection of US format (comma=thousand, period=decimal)."""
		from imogi_finance.imogi_finance.parsers.normalization import find_decimal_separator

		thousand_sep, decimal_sep = find_decimal_separator("1,234,567.89")
		assert thousand_sep == ","
		assert decimal_sep == "."

	def test_ambiguous_format_detection(self):
		"""Test detection of ambiguous format (only one separator)."""
		from imogi_finance.imogi_finance.parsers.normalization import find_decimal_separator

		# Single comma - likely decimal
		thousand_sep, decimal_sep = find_decimal_separator("1234567,89")
		assert decimal_sep == ","

		# Single period - ambiguous
		thousand_sep, decimal_sep = find_decimal_separator("1234567.89")
		# Could be either format


# Fixtures for test data
@pytest.fixture
def sample_invoice_items():
	"""Sample invoice items for testing."""
	return [
		{
			"line_no": 1,
			"description": "Item 1 - Service",
			"harga_jual": 1000000,
			"dpp": 900000,
			"ppn": 99000,
			"item_code": "001"
		},
		{
			"line_no": 2,
			"description": "Item 2 - Product",
			"harga_jual": 2000000,
			"dpp": 1800000,
			"ppn": 198000,
			"item_code": "002"
		}
	]


@pytest.fixture
def sample_header_totals():
	"""Sample header totals for testing."""
	return {
		"harga_jual": 3000000,
		"dpp": 2700000,
		"ppn": 297000,
		"fp_no": "001.001.01.01000001",
		"npwp": "000000000000000",
		"fp_date": "2026-01-15"
	}
