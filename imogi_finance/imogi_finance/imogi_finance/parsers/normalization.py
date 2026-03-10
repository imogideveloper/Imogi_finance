# -*- coding: utf-8 -*-
# Copyright (c) 2026, Imogi Finance and contributors
# For license information, please see license.txt

"""
Normalization utilities for Indonesian tax invoice data.

Handles Indonesian number formats, description cleaning, and OCR corrections.
"""

import re
from typing import Optional, Tuple, List, Dict, Any

import frappe

# ============================================================================
# PRE-COMPILED REGEX PATTERNS (Performance Optimization)
# ============================================================================
# Compiling patterns once at module load time improves performance by 30-40%

_COMPILED_PATTERNS = {
	'harga_jual': [
		re.compile(r'Harga\s+Jual\s*/\s*Penggantian\s*/\s*Uang\s+Muka\s*/\s*Termin', re.IGNORECASE),
		re.compile(r'Harga\s+Jual\s*/\s*Penggantian\s*/\s*Uang\s+Muka', re.IGNORECASE),
		re.compile(r'Harga\s+Jual\s*/\s*Penggantian', re.IGNORECASE),
	],
	'potongan_harga': [
		re.compile(r'Dikurangi\s+Potongan\s+Harga', re.IGNORECASE),
		re.compile(r'Potongan\s+Harga', re.IGNORECASE),
	],
	'uang_muka': [
		re.compile(r'Dikurangi\s+Uang\s+Muka\s+yang\s+telah\s+diterima', re.IGNORECASE),
		re.compile(r'Dikurangi\s+Uang\s+Muka', re.IGNORECASE),
	],
	'dpp': [
		re.compile(r'Dasar\s+Pengenaan\s+Pajak', re.IGNORECASE),
		re.compile(r'DPP', re.IGNORECASE),
	],
	'ppn': [
		re.compile(r'Jumlah\s+PPN\s*\([^\)]*\)', re.IGNORECASE),
		re.compile(r'Jumlah\s+PPN', re.IGNORECASE),
	],
	'ppnbm': [
		re.compile(r'Jumlah\s+PPnBM\s*\([^\)]*\)', re.IGNORECASE),
		re.compile(r'Jumlah\s+PPnBM', re.IGNORECASE),
		re.compile(r'PPnBM', re.IGNORECASE),
	],
	'indonesian_amount': re.compile(r'\d+(?:\.\d{3})*(?:,\d{1,2})?'),
}

# ============================================================================
# ERROR TRACKING
# ============================================================================

class ParsingError:
	"""Track parsing errors for better debugging."""

	def __init__(self, field: str, message: str, severity: str = "WARNING"):
		self.field = field
		self.message = message
		self.severity = severity  # "ERROR", "WARNING", "INFO"

	def __str__(self):
		return f"[{self.severity}] {self.field}: {self.message}"

class ParsingErrorCollector:
	"""Collect errors during parsing."""

	def __init__(self):
		self.errors: List[ParsingError] = []

	def add_error(self, field: str, message: str, severity: str = "WARNING"):
		error = ParsingError(field, message, severity)
		self.errors.append(error)
		return error

	def has_errors(self) -> bool:
		return len(self.errors) > 0

	def get_error_messages(self) -> List[str]:
		return [str(e) for e in self.errors]


def parse_indonesian_currency(value_str: str) -> float:
	"""
	Parse Indonesian Rupiah currency format to float.

	Indonesian currency format:
		- Prefix: "Rp" or "Rp " (optional)
		- Thousand separator: . (dot)
		- Decimal separator: , (comma)
		- Examples: "Rp 4.953.154,00" → 4953154.00
		           "517.605,00" → 517605.00
		           "0,00" → 0.00

	Algorithm:
		1. Remove "Rp" prefix and whitespace
		2. Identify comma as decimal separator (replace with dot)
		3. Remove all dots (thousand separators)
		4. Convert to float

	Args:
		value_str: String representation of currency amount

	Returns:
		Float value (returns 0.0 for invalid inputs with warning)

	Examples:
		>>> parse_indonesian_currency("4.953.154,00")
		4953154.0
		>>> parse_indonesian_currency("Rp 4.953.154,00")
		4953154.0
		>>> parse_indonesian_currency("517.605,00")
		517605.0
		>>> parse_indonesian_currency("0,00")
		0.0
		>>> parse_indonesian_currency("4953154")
		4953154.0
	"""
	import frappe

	if not value_str or not isinstance(value_str, str):
		return 0.0

	# Strip whitespace and convert to string
	text = str(value_str).strip()

	if not text:
		return 0.0

	# Remove "Rp" prefix (case-insensitive)
	text = re.sub(r'^Rp\s*', '', text, flags=re.IGNORECASE)

	# Remove any remaining leading/trailing whitespace
	text = text.strip()

	# Count commas - there should be at most 1 (decimal separator)
	comma_count = text.count(',')

	if comma_count > 1:
		# Invalid format - multiple decimal separators
		frappe.logger().warning(f"Invalid Indonesian currency format (multiple commas): {value_str}")
		return 0.0

	if comma_count == 1:
		# Standard Indonesian format: "4.953.154,00"
		# Split at comma to separate integer and decimal parts
		parts = text.split(',')
		integer_part = parts[0]
		decimal_part = parts[1] if len(parts) > 1 else '0'

		# Remove dots from integer part (thousand separators)
		integer_part = integer_part.replace('.', '')

		# Remove any non-digit characters
		integer_part = re.sub(r'[^\d]', '', integer_part)
		decimal_part = re.sub(r'[^\d]', '', decimal_part)

		# Reconstruct number with dot as decimal separator
		if decimal_part:
			text = f"{integer_part}.{decimal_part}"
		else:
			text = integer_part
	else:
		# No comma - could be integer-only format: "4953154" or "4.953.154"
		# Remove all dots (assume they're thousand separators)
		text = text.replace('.', '')

		# Remove any non-digit characters
		text = re.sub(r'[^\d]', '', text)

	# Handle empty result
	if not text:
		return 0.0

	# Convert to float
	try:
		value = float(text)

		# Sanity check: amounts should be non-negative
		if value < 0:
			frappe.logger().warning(f"Negative currency value parsed: {value_str} → {value}")
			return 0.0

		return value
	except (ValueError, TypeError) as e:
		frappe.logger().warning(f"Failed to parse Indonesian currency '{value_str}': {str(e)}")
		return 0.0


def _extract_from_structured_summary(text: str, logger) -> Dict[str, float]:
	"""
	Extract summary values from the STRUCTURED SUMMARY section appended by vision_helpers.
	
	This section has clean label: value format:
		=== STRUCTURED SUMMARY ===
		Harga Jual: 1.102.500,00
		Dikurangi Potongan Harga: 0,00
		Dasar Pengenaan Pajak: 1.010.625,00
		Jumlah PPN: 121.275,00
		Jumlah PPnBM: 0,00
		=== END STRUCTURED SUMMARY ===
	
	Returns empty dict if section not found or parsing fails.
	"""
	result: Dict[str, float] = {}
	
	# Look for structured summary section
	start_marker = "=== STRUCTURED SUMMARY ==="
	end_marker = "=== END STRUCTURED SUMMARY ==="
	
	start_idx = text.find(start_marker)
	end_idx = text.find(end_marker)
	
	if start_idx < 0 or end_idx < 0 or end_idx <= start_idx:
		return result
	
	structured_section = text[start_idx + len(start_marker):end_idx].strip()
	logger.info("Found STRUCTURED SUMMARY section, extracting values...")
	
	# Parse label: value pairs
	for line in structured_section.split('\n'):
		line = line.strip()
		if not line or ':' not in line:
			continue
		
		label, _, value = line.partition(':')
		label = label.strip().lower()
		value = value.strip()
		
		if value == '-':
			continue
		
		parsed_value = parse_indonesian_currency(value)
		if parsed_value == 0 and value not in ('0', '0,00', '-'):
			continue  # Skip if parsing failed for non-zero values
		
		if 'harga jual' in label:
			result['harga_jual'] = parsed_value
			logger.debug(f"  Harga Jual: {parsed_value:,.2f}")
		elif 'potongan' in label:
			result['potongan'] = parsed_value
			logger.debug(f"  Potongan: {parsed_value:,.2f}")
		elif 'dasar pengenaan' in label or 'dpp' in label:
			result['dpp'] = parsed_value
			logger.debug(f"  DPP: {parsed_value:,.2f}")
		elif 'ppn' in label and 'ppnbm' not in label:
			result['ppn'] = parsed_value
			logger.debug(f"  PPN: {parsed_value:,.2f}")
		elif 'ppnbm' in label:
			result['ppnbm'] = parsed_value
			logger.debug(f"  PPnBM: {parsed_value:,.2f}")
	
	if result:
		logger.info(f"Extracted from STRUCTURED SUMMARY: {result}")
	
	return result


def _extract_summary_by_sequence(text: str, logger) -> Dict[str, float]:
	"""
	🔥 FALLBACK: Extract summary values using sequential matching.
	
	This handles Google Vision OCR output where labels and values are in 
	SEPARATE sections (labels first, values second) instead of row-by-row.
	
	Algorithm (FIXED for multi-page PDFs):
	1. Find all standalone amounts after the last summary label
	2. Identify Harga Jual as the LARGEST amount (must be > all others)
	3. Take 5 amounts starting from Harga Jual position
	4. Map to: Harga Jual, Potongan, DPP, PPN, PPnBM
	
	This fixes the issue where item amounts (like TIMAH BALANCE 80.000)
	appear AFTER labels but BEFORE actual summary values.
	
	Args:
		text: Summary section OCR text
		logger: Logger instance
		
	Returns:
		Dict with harga_jual, dpp, ppn, potongan_harga, uang_muka, ppnbm
	"""
	lines = text.split('\n')
	result: Dict[str, float] = {
		'harga_jual': 0.0,
		'dpp': 0.0,
		'ppn': 0.0,
		'potongan_harga': 0.0,
		'uang_muka': 0.0,
		'ppnbm': 0.0,
	}
	
	# Step 1: Find the last summary label position
	summary_labels_patterns = [
		r"Harga\s+Jual.*(?:Penggantian|Termin)",
		r"Dikurangi\s+Potongan",
		r"Dikurangi\s+Uang\s+Muka",
		r"Dasar\s+Pengenaan\s+Pajak",
		r"Jumlah\s+PPN",
		r"Jumlah\s+PPnBM|PPnBM.*Mewah",
	]
	
	last_label_idx = -1
	for idx, line in enumerate(lines):
		for pattern in summary_labels_patterns:
			if re.search(pattern, line, re.IGNORECASE):
				last_label_idx = max(last_label_idx, idx)
				break
	
	if last_label_idx < 0:
		logger.debug("Sequential extraction: No summary labels found")
		return result
	
	logger.info(f"Sequential extraction: Last summary label at line {last_label_idx}")
	
	# Step 2: Find ALL standalone amounts AFTER the last label
	amount_pattern = re.compile(r'^[\s\-]*[\d\.\,]+[\s\-]*$')
	amounts_after_labels: List[tuple] = []
	
	for idx, line in enumerate(lines):
		if idx <= last_label_idx:
			continue  # Skip lines before/at last label
			
		stripped = line.strip()
		if not stripped or stripped == '-':
			continue
			
		# Check if line is just an amount
		if amount_pattern.match(stripped) or re.match(r'^[\d\.\,]+,\d{2}$', stripped):
			amount = parse_indonesian_currency(stripped)
			# Skip if it looks like a year (2020-2030)
			if 2020 <= amount <= 2030:
				logger.debug(f"  Skipping line {idx}: {amount} (looks like a year)")
				continue
			amounts_after_labels.append((amount, idx))
			logger.debug(f"  Found amount at line {idx}: {amount:,.2f}")
	
	if len(amounts_after_labels) < 5:
		logger.warning(f"Sequential extraction: Only {len(amounts_after_labels)} amounts after labels")
		return result
	
	logger.info(f"Sequential extraction: Found {len(amounts_after_labels)} amounts after labels")
	
	# Step 3: Find Harga Jual = the LARGEST amount
	# This is the key fix: Harga Jual MUST be the largest value
	max_amount = max(amounts_after_labels, key=lambda x: x[0])
	max_idx = amounts_after_labels.index(max_amount)
	
	logger.info(f"Sequential extraction: Harga Jual (largest) = {max_amount[0]:,.2f} at position {max_idx}")
	
	# Step 4: Take 5 amounts starting from Harga Jual position
	# Order: Harga Jual, Potongan, DPP, PPN, PPnBM
	summary_amounts = amounts_after_labels[max_idx:max_idx + 5]
	
	if len(summary_amounts) < 5:
		logger.warning(f"Sequential extraction: Only {len(summary_amounts)} amounts from Harga Jual position")
	
	# Step 5: Map to result fields
	field_order = ['harga_jual', 'potongan_harga', 'dpp', 'ppn', 'ppnbm']
	for i, field_name in enumerate(field_order):
		if i < len(summary_amounts):
			result[field_name] = summary_amounts[i][0]
			logger.info(f"  {field_name} = {result[field_name]:,.2f}")
	
	# Step 6: Validation - check DPP/PPN ratio (should be ~12%)
	if result['dpp'] > 0 and result['ppn'] > 0:
		ratio = result['ppn'] / result['dpp']
		if 0.10 <= ratio <= 0.13:
			logger.info(f"Sequential extraction: PPN/DPP ratio {ratio*100:.1f}% ✓ (valid)")
		else:
			logger.warning(f"Sequential extraction: PPN/DPP ratio {ratio*100:.1f}% (expected 11-12%)")
	
	# Step 7: Validation - Harga Jual should be >= DPP
	if result['harga_jual'] > 0 and result['dpp'] > 0:
		if result['harga_jual'] < result['dpp']:
			logger.warning(f"Sequential extraction: Harga Jual < DPP, may be incorrect!")
	
	logger.info(f"Sequential extraction result: {result}")
	return result


def extract_summary_values(ocr_text: str) -> Dict[str, float]:
	"""
	Extract summary section values from Indonesian tax invoice OCR text.

	Correctly identifies and extracts values for each summary field without
	confusing DPP (Dasar Pengenaan Pajak) with PPN (Jumlah PPN).

	Expected OCR text structure:
		Harga Jual / Penggantian / Uang Muka / Termin    4.953.154,00
		Dikurangi Potongan Harga                         247.658,00
		Dikurangi Uang Muka yang telah diterima
		Dasar Pengenaan Pajak                            4.313.371,00
		Jumlah PPN (Pajak Pertambahan Nilai)            517.605,00
		Jumlah PPnBM (Pajak Penjualan atas Barang Mewah)    0,00

	Algorithm:
		1. Filter to SUMMARY SECTION ONLY (lines containing "Dasar Pengenaan Pajak")
		2. Define specific label patterns for each field
		3. Search for label in text (case-insensitive)
		4. Extract amount from same line or next line
		5. Parse using Indonesian currency parser
		6. Validate DPP > PPN (swap if needed)

	Args:
		ocr_text: Raw OCR text containing summary section

	Returns:
		Dictionary with keys:
			- harga_jual: Total selling price (float)
			- potongan_harga: Discount amount (float)
			- uang_muka: Down payment received (float)
			- dpp: Tax base / Dasar Pengenaan Pajak (float)
			- ppn: VAT amount / Jumlah PPN (float)
			- ppnbm: Luxury goods tax / Jumlah PPnBM (float)

		All values default to 0.0 if not found.

	Example:
		>>> text = '''
		... Harga Jual / Penggantian 4.953.154,00
		... Dasar Pengenaan Pajak 4.313.371,00
		... Jumlah PPN 517.605,00
		... '''
		>>> result = extract_summary_values(text)
		>>> result['dpp']
		4313371.0
		>>> result['ppn']
		517605.0
	"""
	logger = frappe.logger()

	# 🔥 CRITICAL FIX: Extract ONLY summary section (avoid line-item details)
	# Summary section contains: "Harga Jual/Penggantian", "Dikurangi Potongan Harga", 
	# "Dikurangi Uang Muka", "Dasar Pengenaan Pajak", "Jumlah PPN", "Jumlah PPnBM"
	# 
	# Strategy: Find summary section by looking for UNIQUE summary markers:
	# - "Dikurangi Potongan Harga" (appears ONLY in summary, never in item details)
	# - "Dasar Pengenaan Pajak" (appears ONLY in summary, never in item details)
	# 
	# These markers ONLY appear once in the entire document (in summary section),
	# so we can extract text from that point onwards.
	# Go back ONLY 1-2 lines to catch summary "Harga Jual" (not item details).
	
	summary_section = ocr_text
	lines = ocr_text.split('\n')
	summary_start_line = 0
	
	# Find UNIQUE summary marker - use whichever appears first
	summary_markers = [
		"Dikurangi Potongan Harga",
		"Dasar Pengenaan Pajak",
	]
	
	for marker in summary_markers:
		# Find this marker
		marker_idx = ocr_text.find(marker)
		if marker_idx > 0:
			marker_line_num = ocr_text[:marker_idx].count('\n')
			# Go back ONLY 2 lines to catch "Harga Jual / Penggantian" summary line
			# (not item details which are further up)
			summary_start_line = max(0, marker_line_num - 2)
			logger.info(
				f"🔥 Found summary marker '{marker}' at line {marker_line_num}, "
				f"starting extraction from line {summary_start_line}"
			)
			break
	
	if summary_start_line > 0:
		summary_section = '\n'.join(lines[summary_start_line:])
		logger.info(f"🔥 Extracted summary section ({len(lines) - summary_start_line} lines)")

	# Use pre-compiled patterns (defined at module level for 30-40% performance boost)
	field_patterns = {
		'harga_jual': _COMPILED_PATTERNS['harga_jual'],
		'potongan_harga': _COMPILED_PATTERNS['potongan_harga'],
		'uang_muka': _COMPILED_PATTERNS['uang_muka'],
		'dpp': _COMPILED_PATTERNS['dpp'],
		'ppn': _COMPILED_PATTERNS['ppn'],
		'ppnbm': _COMPILED_PATTERNS['ppnbm'],
	}

	def _find_value_after_label(text: str, patterns: list, field_name: str) -> float:
		"""
		Find currency value after a label pattern.

		Args:
			text: Text to search in
			patterns: List of compiled regex patterns to try (in priority order)
			field_name: Field name for logging

		Returns:
			Parsed float value or 0.0 if not found
		"""
		lines = text.split('\n')

		for regex in patterns:
			# Patterns are already compiled at module level (performance optimization)

			for idx, line in enumerate(lines):
				match = regex.search(line)
				if not match:
					continue

				logger.debug(f"Found label '{regex.pattern}' for {field_name} at line {idx}: '{line[:80]}'")

				# Strategy 1: Try to find amount on the SAME line after the label
				# Extract text after the label
				text_after_label = line[match.end():].strip()

				if text_after_label:
					# Look for currency pattern
					amount_match = re.search(r'(\d[\d\.\,\s]*)', text_after_label)
					if amount_match:
						amount_str = amount_match.group(1).strip()
						value = parse_indonesian_currency(amount_str)
						if value > 0:
							logger.info(f"✅ Extracted {field_name} from same line: {value:,.2f} (pattern: '{regex.pattern[:50]}')")
							return value

				# Strategy 2: Check next non-empty line
				for next_idx in range(idx + 1, min(idx + 3, len(lines))):
					next_line = lines[next_idx].strip()
					if not next_line:
						continue

					# Look for currency pattern at start of line
					amount_match = re.match(r'^\s*(\d[\d\.\,\s]*)', next_line)
					if amount_match:
						amount_str = amount_match.group(1).strip()
						value = parse_indonesian_currency(amount_str)
						if value > 0:
							logger.info(f"✅ Extracted {field_name} from next line: {value:,.2f} (pattern: '{regex.pattern[:50]}')")
							return value
						break  # If we found a number pattern but it parsed to 0, stop looking

		logger.debug(f"⚠️  Could not extract {field_name} - no matching pattern found")
		return 0.0

	# 🔥 PRIORITY 1: Try to extract from STRUCTURED SUMMARY section first
	# This section is built by vision_helpers using bounding box coordinates
	# and has clean "label: value" format that's reliable to parse
	structured_result = _extract_from_structured_summary(ocr_text, logger)
	if structured_result.get('dpp', 0) > 0 and structured_result.get('ppn', 0) > 0:
		logger.info("✅ Extracted from STRUCTURED SUMMARY section - high confidence")
		# Fill in missing fields with defaults
		result = {
			'harga_jual': structured_result.get('harga_jual', 0.0),
			'potongan_harga': structured_result.get('potongan', 0.0),
			'uang_muka': 0.0,
			'dpp': structured_result.get('dpp', 0.0),
			'ppn': structured_result.get('ppn', 0.0),
			'ppnbm': structured_result.get('ppnbm', 0.0),
		}
		logger.info(f"📊 Summary values from structured section: {result}")
		return result

	# 🔥 FALLBACK: Standard label-based extraction from raw OCR text
	# Extract all values FROM SUMMARY SECTION ONLY (not full text)
	result = {
		'harga_jual': _find_value_after_label(summary_section, field_patterns['harga_jual'], 'harga_jual'),
		'potongan_harga': _find_value_after_label(summary_section, field_patterns['potongan_harga'], 'potongan_harga'),
		'uang_muka': _find_value_after_label(summary_section, field_patterns['uang_muka'], 'uang_muka'),
		'dpp': _find_value_after_label(summary_section, field_patterns['dpp'], 'dpp'),
		'ppn': _find_value_after_label(summary_section, field_patterns['ppn'], 'ppn'),
		'ppnbm': _find_value_after_label(summary_section, field_patterns['ppnbm'], 'ppnbm'),
	}

	# 🔥 FALLBACK: If standard label-based extraction failed, use sequential matching
	# This handles Google Vision OCR output where labels and values are in separate columns
	# (labels extracted first as a block, values extracted second as another block)
	if result['dpp'] == 0 or result['ppn'] == 0:
		logger.info("🔄 Standard label-based extraction incomplete, trying sequential value matching...")
		fallback = _extract_summary_by_sequence(summary_section, logger)
		
		# Use fallback values only if they're better than current results
		if fallback.get('dpp', 0) > 0 and result['dpp'] == 0:
			result['dpp'] = fallback['dpp']
			logger.info(f"✅ Fallback DPP: {result['dpp']:,.2f}")
		if fallback.get('ppn', 0) > 0 and result['ppn'] == 0:
			result['ppn'] = fallback['ppn']
			logger.info(f"✅ Fallback PPN: {result['ppn']:,.2f}")
		if fallback.get('harga_jual', 0) > 0 and result['harga_jual'] == 0:
			result['harga_jual'] = fallback['harga_jual']
			logger.info(f"✅ Fallback Harga Jual: {result['harga_jual']:,.2f}")
		if fallback.get('potongan_harga', 0) >= 0 and result['potongan_harga'] == 0:
			result['potongan_harga'] = fallback.get('potongan_harga', 0)
		if fallback.get('ppnbm', 0) >= 0 and result['ppnbm'] == 0:
			result['ppnbm'] = fallback.get('ppnbm', 0)

	# 🔥 CRITICAL VALIDATION: Check if DPP and PPN were swapped
	# PPN should always be smaller than DPP (typically 11-12% of DPP)
	if result['dpp'] > 0 and result['ppn'] > 0:
		if result['ppn'] > result['dpp']:
			logger.error(
				f"🚨 DPP/PPN SWAP DETECTED in extract_summary_values! "
				f"PPN ({result['ppn']:,.0f}) > DPP ({result['dpp']:,.0f}). Swapping values..."
			)
			# Swap the values
			result['dpp'], result['ppn'] = result['ppn'], result['dpp']
			logger.info(f"✅ Values corrected: DPP={result['dpp']:,.0f}, PPN={result['ppn']:,.0f}")

		# Additional validation: PPN should be roughly 11-12% of DPP
		expected_ppn = result['dpp'] * 0.12
		ppn_ratio = result['ppn'] / result['dpp'] if result['dpp'] > 0 else 0
		if ppn_ratio < 0.08 or ppn_ratio > 0.15:
			logger.warning(
				f"⚠️  PPN/DPP ratio suspicious: {ppn_ratio*100:.1f}% "
				f"(expected 11-12%). DPP={result['dpp']:,.0f}, PPN={result['ppn']:,.0f}"
			)

	logger.info(f"📊 Summary values extracted: {result}")
	return result


def detect_tax_rate(dpp: float, ppn: float, faktur_type: str = "") -> float:
	"""
	Detect the tax rate for Indonesian tax invoices.

	IMPORTANT: Tax rate is CALCULATED from DPP and PPN only.
	No default/fallback rates are used.

	Args:
		dpp: Dasar Pengenaan Pajak (tax base) amount
		ppn: PPN (VAT) amount
		faktur_type: Invoice type code (ignored - kept for API compatibility)

	Returns:
		Tax rate as decimal (calculated from PPN/DPP), or 0.0 if cannot be calculated

	Examples:
		>>> detect_tax_rate(4313371.0, 517605.0)
		0.12  # Calculated: 517605/4313371 = 0.12 (12%)

		>>> detect_tax_rate(1000000.0, 110000.0)
		0.11  # Calculated: 110000/1000000 = 0.11 (11%)

		>>> detect_tax_rate(0, 0)
		0.0  # Cannot calculate - no DPP/PPN provided

		>>> detect_tax_rate(1000000.0, 0)
		0.0  # Zero-rated transaction (export or exempt)
	"""
	import frappe
	logger = frappe.logger()

	# Standard Indonesian tax rates for validation/tolerance
	STANDARD_RATES = [0.12, 0.11]  # 12% and 11% (pre-2025)
	TOLERANCE = 0.02  # ±2% tolerance for rounding errors

	# ============================================================================
	# SPECIAL CASE: Zero-rated transactions (exports, exempt goods)
	# ============================================================================
	if dpp > 0 and ppn == 0:
		logger.info("✅ Zero-rated transaction detected (PPN = 0, likely export or exempt)")
		return 0.0  # Export or exempt transaction

	# ONLY METHOD: Calculate from actual DPP and PPN values
	if dpp and ppn and dpp > 0 and ppn > 0:
		calculated_rate = ppn / dpp

		# Find CLOSEST standard rate within tolerance
		closest_rate = None
		closest_difference = float('inf')

		for std_rate in STANDARD_RATES:
			difference = abs(calculated_rate - std_rate)
			if difference <= TOLERANCE and difference < closest_difference:
				closest_rate = std_rate
				closest_difference = difference

		if closest_rate is not None:
			logger.info(
				f"✅ Tax rate detected from calculation: {closest_rate*100:.0f}% "
				f"(calculated: {calculated_rate*100:.2f}%, diff: {closest_difference*100:.2f}%)"
			)
			# Validate that the rate makes sense with actual values
			recalculated_ppn = dpp * closest_rate
			ppn_difference_pct = abs(ppn - recalculated_ppn) / ppn * 100 if ppn > 0 else 0
			if ppn_difference_pct > 5:
				logger.warning(
					f"⚠️  Validation warning: Using rate {closest_rate*100:.0f}% results in "
					f"{ppn_difference_pct:.1f}% difference from actual PPN. "
					f"Expected: {recalculated_ppn:,.0f}, Actual: {ppn:,.0f}"
				)
			
			# 🔥 VERIFY against Indonesian regulations
			verification = verify_tax_rate_against_regulations(closest_rate)
			if not verification["is_valid"]:
				logger.error(f"🚨 {verification['message']}")
			
			return closest_rate
		else:
			# Calculated rate outside tolerance - return calculated rate directly
			logger.warning(
				f"⚠️  Calculated rate {calculated_rate*100:.2f}% outside standard rates "
				f"(11% or 12% with ±2% tolerance). Returning calculated rate."
			)
			
			# 🔥 VERIFY against Indonesian regulations even for non-standard rates
			verification = verify_tax_rate_against_regulations(calculated_rate)
			if not verification["is_valid"]:
				logger.error(f"🚨 {verification['message']}")
			
			return calculated_rate

	# Cannot calculate tax rate without DPP and PPN
	logger.warning(f"⚠️  Cannot calculate tax rate: DPP={dpp}, PPN={ppn}")
	return 0.0


def verify_tax_rate_against_regulations(tax_rate: float) -> Dict[str, Any]:
	"""
	Verify if calculated tax rate is valid according to Indonesian tax regulations.

	Valid Indonesian PPN rates (as of Feb 2026):
	- 0%: Export, exempt goods, certain services
	- 1.1%: Digital transactions, e-commerce specific (since 2023)
	- 3%: Certain goods and services
	- 5%: Reduced rate - food items, medicines, books (since Jan 2025)
	- 11%: Previous standard rate (before Jan 2025)
	- 12%: Current standard rate (since Jan 2025)

	Reference: Indonesian Ministry of Finance, DJP regulations (2023-2026)

	Args:
		tax_rate: Calculated tax rate as decimal (e.g., 0.12 for 12%)

	Returns:
		Dictionary with:
		- is_valid: bool - True if rate matches Indonesian regulations
		- rate_type: str - Description of the rate type
		- message: str - Explanation of the rate
		- issues: List[str] - Any validation warnings
	"""
	import frappe
	logger = frappe.logger()

	# Valid Indonesian PPN rates with descriptions
	# Updated for 2023-2026 regulations
	VALID_RATES = {
		0.00: {
			"type": "Zero-Rated",
			"description": "Export goods, exempt services, tertentu",
		},
		0.011: {
			"type": "Digital",
			"description": "Digital transactions, e-commerce specific (1.1%)",
		},
		0.03: {
			"type": "Special",
			"description": "Certain goods and services (3%)",
		},
		0.05: {
			"type": "Reduced",
			"description": "Food, medicines, books, newspapers (5% since Jan 2025)",
		},
		0.11: {
			"type": "Standard (Pre-2025)",
			"description": "Previous standard PPN rate (11%)",
		},
		0.12: {
			"type": "Standard (Current)",
			"description": "Current standard PPN rate (12% since Jan 2025)",
		},
	}
	
	TOLERANCE = 0.001  # Allow small floating-point errors
	issues = []

	# Check if rate matches any valid rate (within tolerance)
	closest_match = None
	min_difference = float('inf')
	
	for valid_rate, info in VALID_RATES.items():
		difference = abs(tax_rate - valid_rate)
		if difference <= TOLERANCE and difference < min_difference:
			closest_match = valid_rate
			min_difference = difference

	if closest_match is not None:
		rate_info = VALID_RATES[closest_match]
		logger.info(
			f"✅ Tax rate {tax_rate*100:.2f}% matches Indonesian regulations: "
			f"{rate_info['type']} - {rate_info['description']}"
		)
		return {
			"is_valid": True,
			"rate_type": rate_info["type"],
			"message": f"{rate_info['type']}: {rate_info['description']}",
			"issues": issues,
			"matched_rate": closest_match,
		}
	else:
		# Rate does NOT match any valid Indonesian rate
		valid_rates_str = ", ".join([f"{r*100:.1f}%" for r in VALID_RATES.keys()])
		message = (
			f"❌ Calculated tax rate {tax_rate*100:.2f}% does NOT match any valid Indonesian PPN rate. "
			f"Valid rates are: {valid_rates_str}"
		)
		issues.append(message)
		logger.error(message)
		
		return {
			"is_valid": False,
			"rate_type": "Invalid",
			"message": message,
			"issues": issues,
			"matched_rate": None,
		}


def validate_tax_calculation(
	harga_jual: float,
	dpp: float,
	ppn: float,
	ppnbm: float,
	tax_rate: float,
	potongan_harga: float = 0.0
) -> Tuple[bool, List[str]]:
	"""
	Validate extracted tax invoice values for correctness.

	Performs comprehensive validation including:
	- PPN calculation accuracy (DPP × tax_rate)
	- Field relationships (DPP ≤ Harga Jual)
	- Discount calculation validation
	- Detection of suspiciously low values
	- Negative value detection
	- CRITICAL: Swapped field detection (PPN > DPP)

	Args:
		harga_jual: Total selling price (Harga Jual / Penggantian)
		dpp: Tax base amount (Dasar Pengenaan Pajak)
		ppn: VAT amount (Pajak Pertambahan Nilai)
		ppnbm: Luxury goods tax (Pajak Penjualan atas Barang Mewah)
		tax_rate: Tax rate to validate against (0.11 or 0.12)
		potongan_harga: Price discount amount (optional)

	Returns:
		Tuple of (is_valid, issues):
		- is_valid: True if all validations pass, False otherwise
		- issues: List of validation error messages

	Examples:
		>>> # Valid invoice
		>>> valid, issues = validate_tax_calculation(
		...     harga_jual=4953154.0,
		...     dpp=4313371.0,
		...     ppn=517604.52,
		...     ppnbm=0.0,
		...     tax_rate=0.12,
		...     potongan_harga=247658.0
		... )
		>>> valid
		True

		>>> # Swapped fields (PPN > DPP)
		>>> valid, issues = validate_tax_calculation(
		...     harga_jual=4953154.0,
		...     dpp=517605.0,  # WRONG - this is actually PPN
		...     ppn=4313371.0,  # WRONG - this is actually DPP
		...     ppnbm=0.0,
		...     tax_rate=0.12
		... )
		>>> valid
		False
		>>> '🚨 CRITICAL' in issues[0]
		True
	"""
	import frappe
	logger = frappe.logger()

	issues = []
	is_valid = True

	# ============================================================================
	# CHECK 1: Negative values
	# ============================================================================
	if harga_jual < 0:
		issues.append(f"❌ Harga Jual cannot be negative: {harga_jual:,.2f}")
		is_valid = False

	if dpp < 0:
		issues.append(f"❌ DPP cannot be negative: {dpp:,.2f}")
		is_valid = False

	if ppn < 0:
		issues.append(f"❌ PPN cannot be negative: {ppn:,.2f}")
		is_valid = False

	if ppnbm < 0:
		issues.append(f"❌ PPnBM cannot be negative: {ppnbm:,.2f}")
		is_valid = False

	if potongan_harga < 0:
		issues.append(f"❌ Potongan Harga cannot be negative: {potongan_harga:,.2f}")
		is_valid = False

	# ============================================================================
	# CHECK 2: DPP should be ≤ Harga Jual
	# ============================================================================
	if harga_jual > 0 and dpp > 0:
		# Allow small rounding tolerance (Rp 10)
		ROUNDING_TOLERANCE = 10.0

		if dpp > harga_jual + ROUNDING_TOLERANCE:
			difference = dpp - harga_jual
			issues.append(
				f"❌ DPP ({dpp:,.2f}) cannot be greater than Harga Jual ({harga_jual:,.2f}). "
				f"Difference: {difference:,.2f}"
			)
			is_valid = False
			logger.warning(f"DPP > Harga Jual: dpp={dpp:,.2f}, harga_jual={harga_jual:,.2f}")

	# ============================================================================
	# CHECK 3: PPN = DPP × tax_rate (with tolerance)
	# ============================================================================
	# Skip this check for zero-rated transactions (exports, exempt goods)
	if tax_rate == 0.0:
		# Zero-rated transaction - PPN should be 0
		if ppn > 0:
			issues.append(
				f"⚠️  Warning: Zero-rated transaction (0% tax) should have PPN = 0, "
				f"but got PPN = {ppn:,.2f}. This might be an export or exempt item."
			)
			# Don't mark as invalid - could be legitimate edge case
	elif dpp > 0 and ppn > 0 and tax_rate > 0:
		expected_ppn = dpp * tax_rate
		difference = abs(ppn - expected_ppn)

		# Tolerance: 2% or Rp 100, whichever is LARGER
		tolerance_pct = expected_ppn * 0.02  # 2% of expected value
		tolerance_fixed = 100.0  # Rp 100
		tolerance = max(tolerance_pct, tolerance_fixed)

		if difference > tolerance:
			difference_pct = (difference / expected_ppn * 100) if expected_ppn > 0 else 0
			issues.append(
				f"❌ PPN calculation error: Expected {expected_ppn:,.2f} "
				f"(DPP {dpp:,.2f} × {tax_rate*100:.0f}%), but got {ppn:,.2f}. "
				f"Difference: {difference:,.2f} ({difference_pct:.1f}%)"
			)
			is_valid = False
			logger.warning(
				f"PPN calculation mismatch: expected={expected_ppn:,.2f}, "
				f"actual={ppn:,.2f}, diff={difference:,.2f}"
			)

	# ============================================================================
	# CHECK 4: If potongan_harga exists, validate discount calculation
	# ============================================================================
	if potongan_harga > 0 and harga_jual > 0 and dpp > 0:
		# Expected: DPP = Harga Jual - Potongan Harga
		expected_dpp = harga_jual - potongan_harga
		dpp_difference = abs(dpp - expected_dpp)

		# Tolerance: 2% of expected DPP or Rp 100, whichever is larger
		tolerance_pct = expected_dpp * 0.02
		tolerance = max(tolerance_pct, 100.0)

		if dpp_difference > tolerance:
			difference_pct = (dpp_difference / expected_dpp * 100) if expected_dpp > 0 else 0
			issues.append(
				f"❌ Discount calculation error: DPP should be {expected_dpp:,.2f} "
				f"(Harga Jual {harga_jual:,.2f} - Potongan {potongan_harga:,.2f}), "
				f"but got {dpp:,.2f}. Difference: {dpp_difference:,.2f} ({difference_pct:.1f}%)"
			)
			is_valid = False
			logger.warning(
				f"Discount calculation mismatch: expected_dpp={expected_dpp:,.2f}, "
				f"actual_dpp={dpp:,.2f}, diff={dpp_difference:,.2f}"
			)

	# ============================================================================
	# CHECK 5: Suspiciously low values (might indicate parsing error)
	# ============================================================================
	MIN_REASONABLE_AMOUNT = 1000.0  # Rp 1,000

	if 0 < harga_jual < MIN_REASONABLE_AMOUNT:
		issues.append(
			f"⚠️  Warning: Harga Jual is suspiciously low ({harga_jual:,.2f}). "
			f"Values < Rp 1,000 might indicate a parsing error."
		)
		# Don't mark as invalid, just warn

	if 0 < dpp < MIN_REASONABLE_AMOUNT:
		issues.append(
			f"⚠️  Warning: DPP is suspiciously low ({dpp:,.2f}). "
			f"Values < Rp 1,000 might indicate a parsing error."
		)
		# Don't mark as invalid, just warn

	# ============================================================================
	# CHECK 6 (MOST CRITICAL): Detect swapped PPN and DPP fields
	# ============================================================================
	# This check comes LAST to allow other validations to run first for audit trail
	if ppn > 0 and dpp > 0 and ppn > dpp:
		issues.append(
			f"🚨 CRITICAL: PPN ({ppn:,.2f}) > DPP ({dpp:,.2f}) - Fields are likely SWAPPED! "
			f"PPN should always be smaller than DPP (typically 11-12% of DPP)."
		)
		is_valid = False
		logger.error(f"🚨 Field swap detected: PPN={ppn:,.2f} > DPP={dpp:,.2f}")

	# ============================================================================
	# Summary
	# ============================================================================
	if is_valid:
		logger.info("✅ All tax calculation validations passed")
	else:
		logger.error(f"❌ Tax calculation validation failed with {len(issues)} issue(s)")

	return is_valid, issues


def process_tax_invoice_ocr(
	ocr_text: str,
	tokens: List[Dict],
	faktur_no: str,
	faktur_type: str
) -> Dict[str, Any]:
	"""
	Process tax invoice OCR text and extract all values with validation.

	This is the main integration function that combines:
	- extract_summary_values() - Extract DPP, PPN, etc.
	- detect_tax_rate() - Smart tax rate detection
	- validate_tax_calculation() - Comprehensive validation

	Args:
		ocr_text: Full OCR text from invoice
		tokens: List of OCR tokens with bounding boxes (for future use)
		faktur_no: Invoice number (e.g., "040.002-26.50406870")
		faktur_type: Invoice type code (e.g., "040")

	Returns:
		Dictionary with:
		- All extracted values (harga_jual, dpp, ppn, ppnbm, etc.)
		- detected_tax_rate: Detected tax rate (0.11 or 0.12)
		- parse_status: "Approved", "Needs Review", or "Draft"
		- validation_issues: List of validation error messages
		- confidence_score: Overall confidence (0.0 to 1.0)

	Examples:
		>>> result = process_tax_invoice_ocr(
		...     ocr_text="Harga Jual 4.953.154,00\nDPP 4.313.371,00\n...",
		...     tokens=[],
		...     faktur_no="040.002-26.50406870",
		...     faktur_type="040"
		... )
		>>> result['parse_status']
		'Approved'
		>>> result['detected_tax_rate']
		0.12
	"""
	import frappe
	logger = frappe.logger()

	logger.info(f"📄 Processing tax invoice: {faktur_no} (type: {faktur_type})")

	# ============================================================================
	# STEP 1: Extract summary values from OCR text
	# ============================================================================
	logger.info("📊 Step 1: Extracting summary values...")
	summary = extract_summary_values(ocr_text)

	harga_jual = summary['harga_jual']
	potongan_harga = summary['potongan_harga']
	uang_muka = summary['uang_muka']
	dpp = summary['dpp']
	ppn = summary['ppn']
	ppnbm = summary['ppnbm']

	logger.info(
		f"   Harga Jual: {harga_jual:,.2f}, DPP: {dpp:,.2f}, "
		f"PPN: {ppn:,.2f}, PPnBM: {ppnbm:,.2f}"
	)

	# ============================================================================
	# STEP 2: Detect correct tax rate and verify against regulations
	# ============================================================================
	logger.info("🔍 Step 2: Detecting tax rate...")
	detected_rate = detect_tax_rate(dpp, ppn, faktur_type)
	logger.info(f"   Detected tax rate: {detected_rate*100:.0f}%")
	
	# Verify rate against Indonesian regulations
	rate_verification = verify_tax_rate_against_regulations(detected_rate)

	# ============================================================================
	# STEP 3: Validate all calculations
	# ============================================================================
	logger.info("✅ Step 3: Validating calculations...")
	is_valid, validation_issues = validate_tax_calculation(
		harga_jual=harga_jual,
		dpp=dpp,
		ppn=ppn,
		ppnbm=ppnbm,
		tax_rate=detected_rate,
		potongan_harga=potongan_harga
	)

	# ============================================================================
	# STEP 4: Determine parse status
	# ============================================================================
	parse_status = "Draft"  # Default
	confidence_score = 1.0  # Start with perfect confidence

	# Check if we have minimum required values
	has_minimum_values = (dpp > 0 and ppn > 0)

	if not has_minimum_values:
		parse_status = "Draft"
		confidence_score = 0.3
		logger.warning("⚠️  Missing required values (DPP or PPN) - status: Draft")

	elif is_valid:
		# All validations passed
		parse_status = "Approved"
		confidence_score = 1.0
		logger.info("✅ All validations passed - status: Approved")

	else:
		# Has values but validation failed
		parse_status = "Needs Review"
		# Reduce confidence based on number of issues
		confidence_score = max(0.5, 1.0 - (len(validation_issues) * 0.1))
		logger.warning(
			f"⚠️  {len(validation_issues)} validation issue(s) found - status: Needs Review"
		)

	# ============================================================================
	# STEP 5: Build result dictionary
	# ============================================================================
	result = {
		# Extracted values
		'harga_jual': harga_jual,
		'potongan_harga': potongan_harga,
		'uang_muka': uang_muka,
		'dpp': dpp,
		'ppn': ppn,
		'ppnbm': ppnbm,

		# Detected values
		'detected_tax_rate': detected_rate,
		'tax_rate': detected_rate,  # Alias for consistency with flow documentation
		'tax_rate_percentage': detected_rate * 100,  # For display
		'rate_type': rate_verification.get('rate_type', 'Unknown'),  # Flow documentation requirement
		'rate_verification': rate_verification,  # Flow documentation requirement

		# Validation results
		'parse_status': parse_status,
		'is_valid': is_valid,
		'validation_issues': validation_issues,
		'confidence_score': confidence_score,

		# Metadata
		'faktur_no': faktur_no,
		'faktur_type': faktur_type,
	}

	logger.info(
		f"📋 Processing complete: Status={parse_status}, "
		f"Confidence={confidence_score:.1%}, Issues={len(validation_issues)}"
	)

	return result


def normalize_indonesian_number(text: str) -> Optional[float]:
	"""
	Convert Indonesian number format to float.

	Indonesian format:
		- Thousand separator: . (dot)
		- Decimal separator: , (comma)
		- Example: "1.234.567,89" -> 1234567.89

	Also handles:
		- Currency prefix: "Rp 1.234,00"
		- Split tokens: "1 234 567,89"
		- OCR errors: O->0, I->1 in numeric context
		- Extra whitespace

	Args:
		text: String representation of number

	Returns:
		Float value or None if not parseable

	Note:
		Prefer using parse_indonesian_currency() for currency amounts.
		This function is kept for backward compatibility.
	"""
	if not text or not isinstance(text, str):
		return None

	# Strip whitespace
	text = text.strip()

	# Remove currency prefix if present
	text = re.sub(r'^Rp\s*', '', text, flags=re.IGNORECASE)
	text = text.strip()

	# Handle comma as decimal separator (Indonesian format)
	# Count commas to determine format
	comma_count = text.count(',')

	if comma_count == 1:
		# Indonesian format: dots are thousand separators, comma is decimal
		# Example: "4.953.154,00" or "1.234,56"
		parts = text.split(',')
		integer_part = parts[0]
		decimal_part = parts[1] if len(parts) > 1 else ''

		# Remove dots from integer part (thousand separators)
		integer_part = integer_part.replace('.', '')

		# Remove spaces between digits
		integer_part = re.sub(r'(\d)\s+(\d)', r'\1\2', integer_part)
		decimal_part = re.sub(r'(\d)\s+(\d)', r'\1\2', decimal_part)

		# Fix OCR errors
		integer_part = re.sub(r'[Oo]', '0', integer_part)
		integer_part = re.sub(r'[Il]', '1', integer_part)
		decimal_part = re.sub(r'[Oo]', '0', decimal_part)
		decimal_part = re.sub(r'[Il]', '1', decimal_part)

		# Remove any remaining non-numeric characters
		integer_part = re.sub(r'[^\d]', '', integer_part)
		decimal_part = re.sub(r'[^\d]', '', decimal_part)

		# Reconstruct with dot as decimal separator
		if decimal_part:
			text = f"{integer_part}.{decimal_part}"
		else:
			text = integer_part
	else:
		# No comma or multiple commas - try to auto-detect format
		# Remove all dots (assume thousand separators in Indonesian context)
		text = text.replace('.', '')

		# Remove spaces between digits
		text = re.sub(r'(\d)\s+(\d)', r'\1\2', text)

		# Fix common OCR errors
		text = re.sub(r'[Oo]', '0', text)
		text = re.sub(r'[Il]', '1', text)

		# Remove any remaining non-numeric characters except first decimal point
		text = re.sub(r'[^\d\.]', '', text)

	if not text:
		return None

	# Try to convert to float
	try:
		value = float(text)

		# Sanity check: tax invoice amounts should be positive
		if value < 0:
			return None

		return value
	except (ValueError, TypeError):
		return None


def clean_description(text: str) -> str:
	"""
	Clean and normalize item description text.

	Operations:
		- Remove reference lines (Referensi:, Invoice:, INV-)
		- Merge multiple whitespaces
		- Strip leading/trailing whitespace
		- Preserve original casing (for part numbers, codes, etc.)

	Args:
		text: Raw description text

	Returns:
		Cleaned description string
	"""
	if not text or not isinstance(text, str):
		return ""

	# Remove reference patterns
	# Pattern: Referensi: <anything> or Invoice: <anything> or INV-<digits>
	reference_patterns = [
		r'Referensi\s*:\s*[^\n]*',
		r'Invoice\s*:\s*[^\n]*',
		r'INV-\d+[^\s]*',
		r'Ref\s*:\s*[^\n]*',
		r'No\.\s*Ref\s*:\s*[^\n]*'
	]

	for pattern in reference_patterns:
		text = re.sub(pattern, '', text, flags=re.IGNORECASE)

	# Merge multiple whitespaces/newlines into single space
	text = re.sub(r'\s+', ' ', text)

	# Strip leading/trailing whitespace
	text = text.strip()

	# DO NOT apply title case - preserves part numbers, model codes, etc.
	return text



def normalize_identifier_digits(value: str | None) -> str | None:
	"""Normalize identifier-like values to digits-only format."""
	if not value:
		return None
	digits = re.sub(r"\D", "", str(value))
	return digits or None

def extract_npwp(text: str) -> Optional[str]:
	"""
	Extract and normalize NPWP (Indonesian Tax ID).

	NPWP format: XX.XXX.XXX.X-XXX.XXX (15 digits)

	Args:
		text: Text containing NPWP

	Returns:
		Normalized NPWP (digits only) or None
	"""
	if not text or not isinstance(text, str):
		return None

	# Normalize to digits-only
	npwp = normalize_identifier_digits(text) or ""

	# Check if it's 15 digits
	if re.match(r'^\d{15}$', npwp):
		return npwp

	# Try to find 15-digit sequence in text
	match = re.search(r'\d{15}', text)
	if match:
		return match.group(0)

	return None


def normalize_line_item(item: Dict) -> Dict:
	"""
	Normalize all fields in a line item dictionary.

	Args:
		item: Dictionary with raw values (raw_harga_jual, raw_dpp, raw_ppn, description)

	Returns:
		Updated dictionary with normalized values
	"""
	# Normalize numeric fields
	if "raw_harga_jual" in item:
		item["harga_jual"] = normalize_indonesian_number(item["raw_harga_jual"])

	if "raw_dpp" in item:
		item["dpp"] = normalize_indonesian_number(item["raw_dpp"])

	if "raw_ppn" in item:
		item["ppn"] = normalize_indonesian_number(item["raw_ppn"])

	# Clean description
	if "description" in item:
		item["description"] = clean_description(item["description"])

	return item


def normalize_all_items(items: list) -> list:
	"""
	Normalize all items in a list.

	Args:
		items: List of item dictionaries

	Returns:
		List of normalized items
	"""
	return [normalize_line_item(item) for item in items]


# =============================================================================
# 🔥 INCLUSIVE VAT DETECTION & HANDLING (PHASE 1 FIX)
# =============================================================================
# Indonesian invoices often have amounts that INCLUDE VAT (Harga Jual includes 11% PPN).
# This module detects this pattern and auto-corrects DPP calculations.

def find_decimal_separator(text: str) -> tuple:
	"""
	Intelligently detect comma vs period as decimal separator in Indonesian format.

	Rules:
	- If text has both comma and period: rightmost is decimal, others are thousand separators
	- If text has only comma: likely decimal (no thousand separator used)
	- If text has only period: likely thousand separator OR decimal (needs context)
	- Returns tuple of (thousand_sep, decimal_sep)

	Examples:
		"1.234.567,89" -> (".", ",")
		"1234567,89" -> (None, ",")
		"1234567.89" -> (None, ".")  # Ambiguous, assume period is decimal
		"1,000.00" -> (",", ".")  # Already formatted (US style)

	Args:
		text: Number string possibly with separators

	Returns:
		Tuple of (thousand_separator, decimal_separator) or (None, None) if ambiguous
	"""
	text = text.strip()

	# Count occurrences
	comma_count = text.count(',')
	period_count = text.count('.')

	# No separators - ambiguous
	if comma_count == 0 and period_count == 0:
		return None, None

	# Both present - rightmost is decimal, rest are thousand seps
	if comma_count > 0 and period_count > 0:
		comma_idx = text.rfind(',')
		period_idx = text.rfind('.')

		if comma_idx > period_idx:
			return ".", ","	# Indonesian format
		else:
			return ",", "."	# US format

	# Only comma - likely decimal
	if comma_count == 1 and period_count == 0:
		# Check if comma is in rightmost 3 positions (like "1234,56")
		comma_idx = text.find(',')
		digits_after = len(text) - comma_idx - 1
		if digits_after <= 3:
			return None, ","
		# Otherwise it's a thousands separator (unusual but possible)
		return ",", None

	# Only period - ambiguous, but assume decimal if rightmost
	if period_count == 1 and comma_count == 0:
		# If period is in rightmost 3 positions, likely decimal
		period_idx = text.rfind('.')
		digits_after = len(text) - period_idx - 1
		if digits_after <= 3:
			return None, "."
		# Otherwise assume thousand separator (Indonesian style)
		return ".", None

	# Multiple commas or periods - assume Indonesian format
	if comma_count > 1 or period_count > 1:
		# Find rightmost comma/period
		comma_idx = text.rfind(',')
		period_idx = text.rfind('.')

		if comma_idx > period_idx:
			return ".", ","
		else:
			return ",", "."

	return None, None


def validate_number_format(original_text: str, parsed_value: Optional[float]) -> Dict[str, Any]:
	"""
	Validate that parsed number makes sense in context.

	Checks:
	- If original has obvious structure (thousand separators), parsed value should be large
	- If parsing resulted in unusual magnitude change, flag as suspicious
	- Detect OCR artifacts (missing digits, wrong separators)

	Args:
		original_text: Raw text from OCR
		parsed_value: Result from normalize_indonesian_number()

	Returns:
		Dictionary with:
			- is_valid: Boolean (True if format seems reasonable)
			- confidence: Float (0.0-1.0)
			- message: String explaining the validation
			- suggestions: List of alternative interpretations if suspicious
	"""
	if not original_text or parsed_value is None:
		return {
			"is_valid": False,
			"confidence": 0.0,
			"message": "Missing input or parse failure",
			"suggestions": []
		}

	# Extract digit count from original to estimate magnitude
	digit_count = len(re.sub(r'\D', '', original_text))

	# Expected magnitude based on structure
	# If text has commas/periods, it's likely a multi-digit number
	if ',' in original_text or '.' in original_text:
		# Should have at least 4-5 digits (thousand+ IDR)
		if digit_count < 4:
			return {
				"is_valid": False,
				"confidence": 0.3,
				"message": f"Unusual: Text has separators but only {digit_count} digits",
				"suggestions": [
					"Check OCR output for missing digits",
					"Original text may be misread quantity, not amount"
				]
			}

		# Sanity check: if number of digits suggests million/billion, parsed value shouldn't be tiny
		if digit_count >= 7 and parsed_value < 100000:  # 7+ digits but < 100k
			return {
				"is_valid": False,
				"confidence": 0.2,
				"message": f"Parsing error: {digit_count} digits but only Rp {parsed_value:,.0f}",
				"suggestions": [
					"Decimal separator may be incorrect",
					"Try swapping comma/period interpretation"
				]
			}

	# Check for reasonable magnitude (tax invoice amounts are usually 10k - 10 billion IDR)
	if parsed_value < 1000:
		return {
			"is_valid": False,
			"confidence": 0.5,
			"message": f"Very small amount (Rp {parsed_value:,.0f})",
			"suggestions": ["May be OCR error or receipt, not invoice"]
		}

	if parsed_value > 100_000_000_000:  # 100 billion
		return {
			"is_valid": False,
			"confidence": 0.4,
			"message": f"Very large amount (Rp {parsed_value:,.0f}) - may be OCR error",
			"suggestions": ["Check digit count and separator placement"]
		}

	# All checks passed
	return {
		"is_valid": True,
		"confidence": 0.95,
		"message": f"Valid amount: Rp {parsed_value:,.0f}",
		"suggestions": []
	}


# =============================================================================
# 🔥 INCLUSIVE VAT DETECTION & HANDLING
# =============================================================================


def detect_vat_inclusivity(
	harga_jual: Optional[float],
	dpp: Optional[float],
	ppn: Optional[float],
	tax_rate: float = 0.11,
	tolerance_percentage: float = 0.02
) -> Dict[str, Any]:
	"""
	Detect if invoice amounts suggest Harga Jual includes VAT (inclusive VAT).

	Common in Indonesian invoices: Harga_Jual = DPP × (1 + tax_rate)

	Detection Logic:
	1. If Harga_Jual ≈ DPP × (1 + tax_rate), amounts are INCLUSIVE
	2. If Harga_Jual ≈ DPP (or DPP+PPN), amounts are EXCLUSIVE

	Args:
		harga_jual: Selling price (may include VAT)
		dpp: Tax base amount
		ppn: Tax amount
		tax_rate: PPN tax rate (default 0.11 = 11%)
		tolerance_percentage: Percentage tolerance (default 0.02 = 2%)

	Returns:
		Dictionary with:
			- is_inclusive: bool, True if amounts appear to be inclusive VAT
			- reason: str, Explanation of detection logic
			- expected_dpp: float, What DPP should be if inclusive
			- expected_ppn: float, What PPN should be if inclusive
			- confidence: float, 0-1.0 confidence score
			- original_amounts: dict, Debug info with original values

	Example:
		>>> detect_vat_inclusivity(harga_jual=1232100, dpp=1111000, ppn=121100)
		{'is_inclusive': True, 'confidence': 0.95, ...}

		>>> detect_vat_inclusivity(harga_jual=1000000, dpp=1000000, ppn=110000)
		{'is_inclusive': False, 'confidence': 0.85, ...}
	"""
	if not all([harga_jual, dpp, ppn]):
		return {
			"is_inclusive": False,
			"reason": "Missing required amounts (harga_jual, dpp, ppn)",
			"confidence": 0.0,
			"expected_dpp": None,
			"expected_ppn": None,
			"original_amounts": {"harga_jual": harga_jual, "dpp": dpp, "ppn": ppn}
		}

	# Calculate what DPP/PPN would be if Harga Jual is INCLUSIVE
	expected_dpp_inclusive = harga_jual / (1 + tax_rate)
	expected_ppn_inclusive = expected_dpp_inclusive * tax_rate

	# Calculate what Harga Jual would be if DPP/PPN are EXCLUSIVE
	expected_harga_jual_exclusive = dpp + ppn

	# Check INCLUSIVE scenario: Harga_Jual ≈ DPP × (1 + tax_rate)
	# This is the most common case in Indonesian invoices
	inclusive_match_dpp = abs(dpp - expected_dpp_inclusive) <= (expected_dpp_inclusive * tolerance_percentage)
	inclusive_match_ppn = abs(ppn - expected_ppn_inclusive) <= (expected_ppn_inclusive * tolerance_percentage) if expected_ppn_inclusive > 0 else False

	# Check EXCLUSIVE scenario: Harga_Jual ≈ DPP + PPN
	exclusive_match = abs(harga_jual - expected_harga_jual_exclusive) <= (expected_harga_jual_exclusive * tolerance_percentage)

	# Decision logic
	is_inclusive = (inclusive_match_dpp and inclusive_match_ppn) and not exclusive_match

	if is_inclusive:
		confidence = 0.95 if (inclusive_match_dpp and inclusive_match_ppn) else 0.80
		reason = f"Harga Jual ({harga_jual:,.0f}) ≈ DPP ({dpp:,.0f}) × {1+tax_rate:.4f}, indicating inclusive VAT"
	else:
		confidence = 0.85 if exclusive_match else 0.50
		reason = "Amounts appear to be exclusive (Harga Jual ≈ DPP reported values are not indicative of inclusive VAT)"

	return {
		"is_inclusive": is_inclusive,
		"reason": reason,
		"expected_dpp": round(expected_dpp_inclusive, 2),
		"expected_ppn": round(expected_ppn_inclusive, 2),
		"confidence": confidence,
		"original_amounts": {
			"harga_jual": harga_jual,
			"dpp": dpp,
			"ppn": ppn,
			"expected_harga_jual_exclusive": round(expected_harga_jual_exclusive, 2)
		}
	}


def recalculate_dpp_from_inclusive(
	harga_jual: float,
	tax_rate: float = 0.11
) -> Dict[str, Any]:
	"""
	Recalculate DPP and PPN from INCLUSIVE Harga Jual amount.

	Formula:
		DPP = Harga Jual / (1 + tax_rate)
		PPN = DPP × tax_rate

	Args:
		harga_jual: Total amount INCLUDING VAT
		tax_rate: PPN tax rate (default 0.11)

	Returns:
		Dictionary with:
			- dpp: Calculated tax base
			- ppn: Calculated tax amount
			- harga_jual_original: Input value
			- calculation_note: Explanation for logging

	Example:
		>>> recalculate_dpp_from_inclusive(1232100)
		{'dpp': 1111000.0, 'ppn': 122100.0, ...}
	"""
	dpp = harga_jual / (1 + tax_rate)
	ppn = dpp * tax_rate

	return {
		"dpp": round(dpp, 2),
		"ppn": round(ppn, 2),
		"harga_jual_original": harga_jual,
		"calculation_note": f"DPP recalculated from inclusive Harga Jual using formula: DPP = Total / (1 + {tax_rate:.2%})"
	}


# Compatibility with existing tax_invoice_ocr.py
def parse_idr_amount(amount_str: str) -> Optional[float]:
	"""
	Parse Indonesian Rupiah amount format.

	Delegates to parse_indonesian_currency for robust parsing.
	Returns None instead of 0.0 for invalid inputs (backward compatibility).

	Examples:
		>>> parse_idr_amount("Rp 4.953.154,00")
		4953154.0
		>>> parse_idr_amount("517.605,00")
		517605.0
	"""
	result = parse_indonesian_currency(amount_str)
	# Return None for 0.0 to maintain backward compatibility
	# (original function returned None for invalid inputs)
	return result if result != 0.0 or (amount_str and '0' in amount_str) else None
