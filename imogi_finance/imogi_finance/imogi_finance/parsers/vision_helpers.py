# -*- coding: utf-8 -*-
# Copyright (c) 2026, Imogi Finance and contributors
# For license information, please see license.txt

"""
Helper utilities for Google Vision API response processing.
"""

from typing import Dict, Any, Optional, List


def _resolve_full_text_annotation(vision_json: Dict[str, Any]) -> Optional[Dict[str, Any]]:
	"""
	Extract fullTextAnnotation from Vision API JSON response.
	
	🔥 FIX: For multi-page PDFs, MERGE all pages from all responses.
	Google Vision returns separate response entries for each page.
	
	Handles:
	  1. Direct: {"fullTextAnnotation": {...}}
	  2. Single response: {"responses": [{"fullTextAnnotation": {...}}]}
	  3. Multi-page: {"responses": [{"fullTextAnnotation": page1}, {"fullTextAnnotation": page2}]}
	  4. Nested: {"responses": [{"responses": [{"fullTextAnnotation": ...}]}]}
	
	Args:
		vision_json: Raw Vision API JSON response
		
	Returns:
		Merged fullTextAnnotation dict with combined pages, or None if not found
	"""
	if not vision_json:
		return None
	
	all_pages: List[Dict[str, Any]] = []
	all_text_parts: List[str] = []
	
	def _extract_from_entry(entry: Dict[str, Any]) -> None:
		"""Extract pages from a single response entry."""
		fta = entry.get("fullTextAnnotation")
		if fta:
			text = fta.get("text", "")
			pages = fta.get("pages", [])
			if text:
				all_text_parts.append(text)
			if pages:
				all_pages.extend(pages)
	
	def _process_responses(responses: List[Dict[str, Any]]) -> None:
		"""Process a list of response entries."""
		for response in responses:
			if not isinstance(response, dict):
				continue
			
			# Check for nested responses
			nested = response.get("responses")
			if isinstance(nested, list) and len(nested) > 0:
				_process_responses(nested)
			else:
				_extract_from_entry(response)
	
	# Handle nested responses array format
	if "responses" in vision_json and isinstance(vision_json["responses"], list):
		_process_responses(vision_json["responses"])
	else:
		# Handle direct response format
		_extract_from_entry(vision_json)
	
	# If we found any pages, return merged result
	if all_pages or all_text_parts:
		return {
			"text": "\n".join(all_text_parts),
			"pages": all_pages,
		}
	
	return None


def build_structured_summary_text(vision_json: Dict[str, Any]) -> str:
	"""
	Build structured OCR text for summary section by matching labels with values
	using bounding box coordinates.
	
	Google Vision reads PDF by column, causing labels and values to appear
	in separate blocks. This function matches them by Y coordinate (same row).
	
	Output format:
		Harga Jual: 1.102.500,00
		Dikurangi Potongan Harga: 0,00
		Dasar Pengenaan Pajak: 1.010.625,00
		Jumlah PPN: 121.275,00
		Jumlah PPnBM: 0,00
	
	Args:
		vision_json: Raw Google Vision API JSON response
		
	Returns:
		Structured text with label: value pairs for summary section
	"""
	import re
	
	fta = _resolve_full_text_annotation(vision_json)
	if not fta:
		return ""
	
	pages = fta.get("pages", [])
	if not pages:
		return ""
	
	# Extract all blocks with their text and bounding boxes
	all_blocks: List[Dict[str, Any]] = []
	
	for page in pages:
		blocks = page.get("blocks", [])
		for block in blocks:
			# Extract text from block
			text_parts = []
			for para in block.get("paragraphs", []):
				for word in para.get("words", []):
					word_text = "".join(
						sym.get("text", "") for sym in word.get("symbols", [])
					)
					text_parts.append(word_text)
			
			block_text = " ".join(text_parts).strip()
			if not block_text:
				continue
			
			# Extract bounding box
			bbox = block.get("boundingBox", {})
			vertices = bbox.get("normalizedVertices", [])
			if len(vertices) >= 4:
				y_min = min(v.get("y", 0) for v in vertices)
				y_max = max(v.get("y", 0) for v in vertices)
				x_min = min(v.get("x", 0) for v in vertices)
				x_max = max(v.get("x", 0) for v in vertices)
				
				all_blocks.append({
					"text": block_text,
					"y_min": y_min,
					"y_max": y_max,
					"y_center": (y_min + y_max) / 2,
					"x_min": x_min,
					"x_max": x_max,
					"x_center": (x_min + x_max) / 2,
				})
	
	if not all_blocks:
		return ""
	
	# Define summary labels to look for
	summary_label_patterns = [
		(r"Harga\s+Jual.*(?:Penggantian|Termin)", "Harga Jual"),
		(r"Dikurangi\s+Potongan\s+Harga", "Dikurangi Potongan Harga"),
		(r"Dikurangi\s+Uang\s+Muka", "Dikurangi Uang Muka"),
		(r"Dasar\s+Pengenaan\s+Pajak", "Dasar Pengenaan Pajak"),
		(r"Jumlah\s+PPN.*Nilai", "Jumlah PPN"),
		(r"Jumlah\s+PPnBM|PPnBM.*Mewah", "Jumlah PPnBM"),
	]
	
	# Find label blocks and their Y positions
	label_rows: List[Dict[str, Any]] = []
	for pattern, label_name in summary_label_patterns:
		for block in all_blocks:
			if re.search(pattern, block["text"], re.IGNORECASE):
				label_rows.append({
					"label": label_name,
					"y_center": block["y_center"],
					"y_min": block["y_min"],
					"y_max": block["y_max"],
					"x_max": block["x_max"],
				})
				break
	
	if not label_rows:
		return ""
	
	# Find amount blocks (numbers with Indonesian format: 1.234.567,00)
	amount_pattern = re.compile(r'^[\d\.\,]+,\d{2}$')
	amount_blocks: List[Dict[str, Any]] = []
	
	for block in all_blocks:
		text = block["text"].strip()
		if amount_pattern.match(text):
			# Parse the amount value
			try:
				value = float(text.replace(".", "").replace(",", "."))
				amount_blocks.append({
					"text": text,
					"value": value,
					"y_center": block["y_center"],
					"x_min": block["x_min"],
				})
			except ValueError:
				continue
	
	# Match labels with values by Y coordinate
	# Tolerance for "same row": 2% of page height
	y_tolerance = 0.02
	structured_lines: List[str] = []
	
	for label_row in label_rows:
		label_y = label_row["y_center"]
		label_name = label_row["label"]
		
		# Find amount on same row (similar Y coordinate, to the RIGHT of label)
		matched_value = None
		for amount in amount_blocks:
			if abs(amount["y_center"] - label_y) <= y_tolerance:
				if amount["x_min"] > label_row["x_max"] - 0.05:  # Must be to the right
					matched_value = amount["text"]
					break
		
		if matched_value:
			structured_lines.append(f"{label_name}: {matched_value}")
		else:
			structured_lines.append(f"{label_name}: -")
	
	return "\n".join(structured_lines)


def enhance_ocr_text_with_structured_summary(
	raw_ocr_text: str, 
	vision_json: Dict[str, Any]
) -> str:
	"""
	Enhance raw OCR text by appending structured summary section.
	
	This preserves the original OCR text but adds a clearly structured
	summary at the end for reliable parsing.
	
	Args:
		raw_ocr_text: Original OCR text from fullTextAnnotation.text
		vision_json: Raw Google Vision API JSON response
		
	Returns:
		Enhanced OCR text with structured summary appended
	"""
	enhanced = raw_ocr_text.rstrip()
	
	# Add structured line items
	structured_items = build_structured_line_items_text(vision_json)
	if structured_items:
		enhanced += "\n\n=== STRUCTURED LINE ITEMS ===\n"
		enhanced += structured_items
		enhanced += "\n=== END STRUCTURED LINE ITEMS ===\n"
	
	# Add structured summary
	structured_summary = build_structured_summary_text(vision_json)
	if structured_summary:
		enhanced += "\n=== STRUCTURED SUMMARY ===\n"
		enhanced += structured_summary
		enhanced += "\n=== END STRUCTURED SUMMARY ===\n"
	
	return enhanced


def build_structured_line_items_text(vision_json: Dict[str, Any]) -> str:
	"""
	Build structured OCR text for line items section by matching columns
	using bounding box coordinates.
	
	Line items in Indonesian tax invoice have:
	- No (nomor urut) - left column
	- Nama Barang/Jasa - center column
	- Harga Satuan/Qty/Subtotal - right column
	
	Output format:
		No | Nama Barang/Jasa | Harga Jual | Qty | Subtotal
		1 | TIMAH BALANCE KB (0.125Kg) | 80.000,00 | 1 | 80.000,00
		2 | SERVICE BEARING | 50.000,00 | 1 | 50.000,00
	
	Args:
		vision_json: Raw Google Vision API JSON response
		
	Returns:
		Structured text with pipe-delimited line items
	"""
	import re
	
	fta = _resolve_full_text_annotation(vision_json)
	if not fta:
		return ""
	
	pages = fta.get("pages", [])
	if not pages:
		return ""
	
	# Extract all blocks with their text and bounding boxes
	all_blocks: List[Dict[str, Any]] = []
	
	for page in pages:
		blocks = page.get("blocks", [])
		for block in blocks:
			# Extract text from block
			text_parts = []
			for para in block.get("paragraphs", []):
				for word in para.get("words", []):
					word_text = "".join(
						sym.get("text", "") for sym in word.get("symbols", [])
					)
					text_parts.append(word_text)
			
			block_text = " ".join(text_parts).strip()
			if not block_text:
				continue
			
			# Extract bounding box
			bbox = block.get("boundingBox", {})
			vertices = bbox.get("normalizedVertices", [])
			if len(vertices) >= 4:
				y_min = min(v.get("y", 0) for v in vertices)
				y_max = max(v.get("y", 0) for v in vertices)
				x_min = min(v.get("x", 0) for v in vertices)
				x_max = max(v.get("x", 0) for v in vertices)
				
				all_blocks.append({
					"text": block_text,
					"y_min": y_min,
					"y_max": y_max,
					"y_center": (y_min + y_max) / 2,
					"x_min": x_min,
					"x_max": x_max,
					"x_center": (x_min + x_max) / 2,
				})
	
	if not all_blocks:
		return ""
	
	# Find the line items table boundary
	# Line items are between "Nama Barang" header and summary section
	table_y_start = 0.0
	table_y_end = 1.0
	
	header_patterns = [
		r"Nama\s+Barang",
		r"Harga\s+Satuan",
		r"Jumlah\s+Harga",
	]
	
	summary_patterns = [
		r"Harga\s+Jual.*(?:Penggantian|Termin)",
		r"Dikurangi\s+Potongan",
		r"Dasar\s+Pengenaan",
	]
	
	# Find table header (start of line items)
	for block in all_blocks:
		for pattern in header_patterns:
			if re.search(pattern, block["text"], re.IGNORECASE):
				table_y_start = max(table_y_start, block["y_max"])
				break
	
	# Find summary section (end of line items)
	for block in all_blocks:
		for pattern in summary_patterns:
			if re.search(pattern, block["text"], re.IGNORECASE):
				table_y_end = min(table_y_end, block["y_min"])
				break
	
	if table_y_start >= table_y_end:
		return ""  # Could not determine table boundaries
	
	# Filter blocks within line items table area
	item_blocks = [
		b for b in all_blocks 
		if b["y_center"] > table_y_start and b["y_center"] < table_y_end
	]
	
	if not item_blocks:
		return ""
	
	# Group blocks by row (similar Y coordinate)
	# Tolerance: 2% of page height
	y_tolerance = 0.02
	
	# Sort by Y position first
	item_blocks.sort(key=lambda b: b["y_center"])
	
	rows: List[List[Dict[str, Any]]] = []
	current_row: List[Dict[str, Any]] = []
	current_y = item_blocks[0]["y_center"] if item_blocks else 0
	
	for block in item_blocks:
		if abs(block["y_center"] - current_y) <= y_tolerance:
			current_row.append(block)
		else:
			if current_row:
				rows.append(current_row)
			current_row = [block]
			current_y = block["y_center"]
	
	if current_row:
		rows.append(current_row)
	
	# Sort each row by X position (left to right)
	for row in rows:
		row.sort(key=lambda b: b["x_min"])
	
	# Build structured output
	structured_lines: List[str] = []
	
	# Add header
	structured_lines.append("No | Nama Barang/Jasa | Detail")
	structured_lines.append("---")
	
	item_number = 0
	for row in rows:
		if not row:
			continue
		
		# Combine all text in this row
		row_texts = [b["text"] for b in row]
		
		# Try to identify if this is a line item row (starts with number)
		first_text = row_texts[0].strip() if row_texts else ""
		
		# Check if first block is a row number (1, 2, 3, etc.)
		if re.match(r'^\d{1,2}$', first_text):
			item_number = int(first_text)
			remaining = row_texts[1:] if len(row_texts) > 1 else []
			
			# Find item name (usually the longest text)
			item_name = ""
			amounts = []
			
			for text in remaining:
				# Check if it's an amount (Indonesian currency format)
				if re.match(r'^[\d\.\,]+,\d{2}$', text.strip()):
					amounts.append(text.strip())
				elif len(text) > len(item_name):
					item_name = text
			
			# Format: No | Name | Amounts
			detail = " | ".join(amounts) if amounts else "-"
			structured_lines.append(f"{item_number} | {item_name} | {detail}")
		else:
			# Not a numbered row, might be continuation or description
			# Join all texts
			combined = " ".join(row_texts)
			
			# Skip if it's just headers or empty
			if not combined.strip():
				continue
			if any(re.search(p, combined, re.IGNORECASE) for p in header_patterns):
				continue
			
			# Add as continuation of previous item
			structured_lines.append(f"  | {combined} |")
	
	if len(structured_lines) <= 2:  # Only header and separator
		return ""
	
	return "\n".join(structured_lines)