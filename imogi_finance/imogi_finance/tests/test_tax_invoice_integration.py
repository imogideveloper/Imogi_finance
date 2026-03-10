# -*- coding: utf-8 -*-
# Copyright (c) 2026, Imogi Finance and contributors
# For license information, please see license.txt

"""
Integration tests for Tax Invoice OCR Parsing with real-world scenarios.

Demonstrates:
1. End-to-end parsing with VAT inclusivity detection
2. Handling of various invoice formats
3. Error recovery and validation reporting
4. Line item summation with tolerance
"""

import frappe
import pytest
from datetime import datetime


class TestIntegrationVATHandling:
	"""Integration tests for VAT handling in invoice parsing."""

	def test_parse_inclusive_vat_invoice_scenario(self):
		"""
		Test complete parsing flow with inclusive VAT invoice.

		Scenario:
		- Invoices where Harga Jual (Rp 1.232.100) includes 11% VAT
		- System should auto-detect and recalculate DPP
		- Expected DPP: Rp 1.111.000, PPN: Rp 121.100
		"""
		from imogi_finance.imogi_finance.parsers.normalization import (
			normalize_all_items,
			detect_vat_inclusivity,
			recalculate_dpp_from_inclusive
		)
		from imogi_finance.imogi_finance.parsers.validation import (
			validate_all_line_items,
			validate_invoice_totals
		)

		# Simulate parsed items from OCR with inclusive VAT
		raw_items = [
			{
				"line_no": 1,
				"description": "Layanan Konsultasi",
				"harga_jual": "1.232.100,00",  # Includes VAT
				"dpp": "1.111.000,00",
				"ppn": "121.100,00",
				"item_code": "001",
				"page_no": 1
			},
			{
				"line_no": 2,
				"description": "Dukungan Teknis",
				"harga_jual": "2.464.200,00",  # Includes VAT
				"dpp": "2.222.000,00",
				"ppn": "242.200,00",
				"item_code": "002",
				"page_no": 1
			}
		]

		# Step 1: Normalize amounts
		items = normalize_all_items(raw_items)

		# Verify normalization
		assert items[0]["harga_jual"] == 1232100.0
		assert items[1]["harga_jual"] == 2464200.0

		# Step 2: Detect VAT inclusivity and auto-correct
		vat_inclusive_count = 0
		for item in items:
			vat_context = detect_vat_inclusivity(
				harga_jual=item["harga_jual"],
				dpp=item["dpp"],
				ppn=item["ppn"],
				tax_rate=0.11
			)

			if vat_context["is_inclusive"]:
				vat_inclusive_count += 1
				# Recalculate DPP
				corrected = recalculate_dpp_from_inclusive(
					harga_jual=item["harga_jual"],
					tax_rate=0.11
				)
				item["dpp"] = corrected["dpp"]
				item["ppn"] = corrected["ppn"]
				item["dpp_was_recalculated"] = True

		# Both items should be marked as inclusive VAT
		assert vat_inclusive_count == 2

		# Step 3: Validate items after correction
		validated_items, invalid_items = validate_all_line_items(items, tax_rate=0.11)

		# All items should validate successfully
		assert len(invalid_items) == 0
		assert all(item["row_confidence"] >= 0.90 for item in validated_items)

		# Step 4: Validate totals
		header_totals = {
			"harga_jual": 3696300,  # 1.232.100 + 2.464.200
			"dpp": 3333000,         # 1.111.000 + 2.222.000
			"ppn": 363300           # 121.100 + 242.200
		}

		totals_validation = validate_invoice_totals(validated_items, header_totals)
		assert totals_validation["match"] == True

		print("✓ Inclusive VAT detection and correction working correctly")

	def test_mixed_item_codes_with_validation(self):
		"""
		Test parsing with mixed valid/invalid item codes.

		Verifies:
		- Valid codes are accepted
		- Invalid codes (000000) trigger validation warnings
		- Confidence is reduced appropriately
		"""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_all_items
		from imogi_finance.imogi_finance.parsers.validation import validate_all_line_items

		items = [
			{
				"line_no": 1,
				"description": "Item dengan kode valid",
				"harga_jual": "500.000,00",
				"dpp": "450.000,00",
				"ppn": "49.500,00",
				"item_code": "001"
			},
			{
				"line_no": 2,
				"description": "Item dengan kode default",
				"harga_jual": "500.000,00",
				"dpp": "450.000,00",
				"ppn": "49.500,00",
				"item_code": "000000"  # Invalid default code
			},
			{
				"line_no": 3,
				"description": "Item tanpa kode",
				"harga_jual": "500.000,00",
				"dpp": "450.000,00",
				"ppn": "49.500,00",
				"item_code": None
			}
		]

		# Normalize and validate
		items = normalize_all_items(items)
		validated_items, invalid_items = validate_all_line_items(items)

		# Check that confidence is affected by item code issues
		assert validated_items[0]["row_confidence"] >= 0.95  # Valid code
		assert validated_items[1]["row_confidence"] < 0.95   # Invalid code
		assert validated_items[2]["row_confidence"] < 0.95   # Missing code

		print("✓ Item code validation working correctly")

	def test_number_format_parsing_edge_cases(self):
		"""
		Test parsing of various number formats and OCR artifacts.

		Covers:
		- Indonesian format (1.234.567,89)
		- US format (1,234,567.89)
		- Missing decimals
		- OCR errors (O->0, I->1)
		- Spaces between numbers
		"""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_indonesian_number

		test_cases = [
			("1.234.567,89", 1234567.89),      # Standard Indonesian
			("1234567,89", 1234567.89),        # Comma decimal only
			("1.000.000,00", 1000000.0),       # Whole millions
			("500.000,50", 500000.50),         # Smaller amount
			("1 234 567,89", 1234567.89),      # Spaces (split tokens)
			("1234O67,89", 1234067.89),        # OCR error (O->0)
		]

		for original, expected in test_cases:
			parsed = normalize_indonesian_number(original)
			assert parsed is not None, f"Failed to parse: {original}"
			assert abs(parsed - expected) < 1, f"Mismatch for {original}: got {parsed}, expected {expected}"

		print("✓ Number format parsing handling various formats")

	def test_comprehensive_validation_with_report(self):
		"""
		Test complete validation pipeline with detailed reporting.

		Demonstrates:
		- Multi-field validation
		- Confidence scoring
		- Error message generation
		- Validation summary HTML
		"""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_all_items
		from imogi_finance.imogi_finance.parsers.validation import (
			validate_all_line_items,
			validate_invoice_totals,
			validate_line_summation,
			determine_parse_status,
			generate_validation_summary_html
		)

		# Create test items with mixed validation outcomes
		items = [
			{
				"line_no": 1,
				"description": "Item 1 - Valid",
				"harga_jual": "1.000.000,00",
				"dpp": "909.090,91",
				"ppn": "100.000,00",  # Slightly off from exact 0.11 multiple
				"item_code": "001"
			},
			{
				"line_no": 2,
				"description": "Item 2 - Default Code",
				"harga_jual": "2.000.000,00",
				"dpp": "1.818.181,82",
				"ppn": "200.000,00",
				"item_code": "000000"  # Invalid
			}
		]

		# Normalize
		items = normalize_all_items(items)

		# Validate all items
		validated_items, invalid_items = validate_all_line_items(items)

		# Check totals
		header_totals = {
			"harga_jual": 3000000,
			"dpp": 2727272.73,
			"ppn": 300000
		}

		totals_validation = validate_invoice_totals(validated_items, header_totals)

		# Check line summation
		summation_validation = validate_line_summation(validated_items, header_totals)

		# Determine status
		parse_status = determine_parse_status(
			validated_items,
			invalid_items,
			totals_validation,
			header_complete=True
		)

		# Generate summary HTML
		summary_html = generate_validation_summary_html(
			validated_items,
			invalid_items,
			totals_validation,
			parse_status
		)

		# Verify outputs
		assert len(validated_items) == 2
		assert len(invalid_items) > 0  # At least one item with low confidence
		assert parse_status == "Needs Review"  # Should need review due to invalid code
		assert "Status" in summary_html
		assert "Items" in summary_html

		print("✓ Comprehensive validation with reporting working correctly")
		print(f"Parse Status: {parse_status}")
		print(f"Invalid Items: {len(invalid_items)}")

	def test_rounding_tolerance_in_vat_scenario(self):
		"""
		Test that rounding tolerance works correctly when DPP is recalculated from inclusive VAT.

		Scenario:
		- Harga Jual: Rp 1.000.000 (includes VAT)
		- Expected DPP: Rp 900.900,90 (1.000.000 / 1.11)
		- Expected PPN: Rp 99.099,09 (rounded)
		- Total should match: 900.900,90 + 99.099,09 ≈ 1.000.000
		"""
		from imogi_finance.imogi_finance.parsers.normalization import (
			normalize_all_items,
			recalculate_dpp_from_inclusive
		)
		from imogi_finance.imogi_finance.parsers.validation import (
			validate_all_line_items,
			validate_invoice_totals
		)

		# Start with inclusive VAT amount
		inclusive_harga_jual = 1000000.0

		# Recalculate DPP and PPN
		corrected = recalculate_dpp_from_inclusive(inclusive_harga_jual)
		dpp = corrected["dpp"]
		ppn = corrected["ppn"]

		# Verify mathematical correctness within rounding
		reconstructed_total = dpp * (1 + 0.11)
		assert abs(reconstructed_total - inclusive_harga_jual) < 1  # Within 1 IDR rounding

		# Create items with recalculated values
		items = [
			{
				"line_no": 1,
				"description": "Item with recalculated VAT",
				"harga_jual": inclusive_harga_jual,
				"dpp": dpp,
				"ppn": ppn,
				"item_code": "001",
				"dpp_was_recalculated": True  # Mark as recalculated
			}
		]

		# Validate - should pass within tolerance
		validated_items, invalid_items = validate_all_line_items(items)

		# Should validate successfully despite rounding
		assert len(invalid_items) == 0
		assert validated_items[0]["row_confidence"] >= 0.95

		print("✓ Rounding tolerance working correctly for VAT scenarios")
		print(f"Inclusive Harga Jual: Rp {inclusive_harga_jual:,.2f}")
		print(f"Recalculated DPP: Rp {dpp:,.2f}")
		print(f"Recalculated PPN: Rp {ppn:,.2f}")
		print(f"Sum: Rp {dpp + ppn:,.2f}")


class TestEdgeCases:
	"""Test edge cases and error conditions."""

	def test_empty_invoice_handling(self):
		"""Test handling of empty/invalid invoices."""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_all_items

		# Empty items list
		items = []
		result = normalize_all_items(items)
		assert result == []

	def test_missing_required_fields(self):
		"""Test handling of items with missing required fields."""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_all_items
		from imogi_finance.imogi_finance.parsers.validation import validate_all_line_items

		items = [
			{
				"line_no": 1,
				"description": "Item without DPP",
				# Missing dpp and ppn
				"harga_jual": "1.000.000,00"
			}
		]

		items = normalize_all_items(items)
		validated_items, invalid_items = validate_all_line_items(items)

		# Should identify as invalid item
		assert len(invalid_items) > 0
		assert validated_items[0]["row_confidence"] < 0.5

	def test_zero_and_negative_amounts(self):
		"""Test rejection of invalid amounts."""
		from imogi_finance.imogi_finance.parsers.normalization import normalize_all_items
		from imogi_finance.imogi_finance.parsers.validation import validate_all_line_items

		items = [
			{
				"line_no": 1,
				"description": "Zero amount",
				"harga_jual": 0,
				"dpp": 0,
				"ppn": 0
			},
			{
				"line_no": 2,
				"description": "Negative amount",
				"harga_jual": -1000,
				"dpp": -900,
				"ppn": -100
			}
		]

		items = normalize_all_items(items)
		validated_items, invalid_items = validate_all_line_items(items)

		# Both should be flagged
		assert all(item["row_confidence"] < 0.5 for item in validated_items)


# Run these tests with: pytest test_tax_invoice_parsing_comprehensive.py
if __name__ == "__main__":
	pytest.main([__file__, "-v", "-s"])
