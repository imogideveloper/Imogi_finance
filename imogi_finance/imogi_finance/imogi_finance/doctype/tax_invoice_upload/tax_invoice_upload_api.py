# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from typing import Any

import frappe
from frappe import _
from frappe.utils.file_manager import get_file_path, save_file

from imogi_finance.services.tax_invoice_service import sync_tax_invoice_with_sales


def normalize_fp_number(fp_number: str) -> str:
	"""Normalize FP number to 16 digits (remove punctuation).
	
	Args:
		fp_number: FP number in any format
		
	Returns:
		str: 16-digit normalized FP number
	"""
	if not fp_number:
		return ""
	
	# Extract only digits
	digits = re.sub(r'\D', '', str(fp_number))
	
	# Return last 16 digits if longer
	return digits[-16:] if len(digits) >= 16 else digits


@frappe.whitelist()
def bulk_create_from_csv(
	batch_name: str,
	zip_url: str,
	csv_url: str,
	require_all_batch_invoices: int = 0,
	require_all_csv_have_pdf: int = 0,
	overwrite_existing: int = 0
) -> dict[str, Any]:
	"""Bulk create Tax Invoice Upload records from CSV + ZIP files.
	
	Phase 1: Validate CSV structure and content
	Phase 2: Inspect ZIP contents and match PDFs
	Phase 3: Create/update Tax Invoice Upload records
	
	Args:
		batch_name: VAT OUT Batch name
		zip_url: URL of ZIP file with FP PDFs
		csv_url: URL of CSV file with metadata
		require_all_batch_invoices: Fail if batch invoices not in CSV
		require_all_csv_have_pdf: Fail if CSV rows missing PDFs
		overwrite_existing: Update existing records with PDFs
		
	Returns:
		dict: Operation summary with counts and errors
	"""
	# Check if this should be a background job (>30 rows)
	try:
		csv_path = get_file_path(csv_url)
		with open(csv_path, 'r', encoding='utf-8-sig') as f:
			row_count = sum(1 for _ in csv.reader(f)) - 1  # Subtract header
		
		if row_count > 30:
			# Enqueue background job
			job = frappe.enqueue(
				'imogi_finance.imogi_finance.doctype.tax_invoice_upload.tax_invoice_upload_api._process_bulk_creation',
				queue='long',
				timeout=3600,
				batch_name=batch_name,
				zip_url=zip_url,
				csv_url=csv_url,
				require_all_batch_invoices=require_all_batch_invoices,
				require_all_csv_have_pdf=require_all_csv_have_pdf,
				overwrite_existing=overwrite_existing
			)
			return {
				'queued': 1,
				'job_id': job.name if hasattr(job, 'name') else str(job)
			}
	except Exception as e:
		frappe.log_error(f"Error checking CSV row count: {str(e)}")
		# Continue with synchronous processing
	
	# Process synchronously
	return _process_bulk_creation(
		batch_name, zip_url, csv_url,
		require_all_batch_invoices, require_all_csv_have_pdf, overwrite_existing
	)


def _process_bulk_creation(
	batch_name: str,
	zip_url: str,
	csv_url: str,
	require_all_batch_invoices: int = 0,
	require_all_csv_have_pdf: int = 0,
	overwrite_existing: int = 0
) -> dict[str, Any]:
	"""Internal processing function for bulk creation.
	
	Returns:
		dict: Operation summary
	"""
	# Phase 1: Validate CSV
	csv_data, csv_errors = _validate_and_parse_csv(csv_url)
	if csv_errors:
		return {
			'status': 'error',
			'created': 0,
			'updated': 0,
			'skipped': 0,
			'row_errors': csv_errors
		}
	
	# Phase 2: Inspect ZIP and match PDFs
	pdf_map = _extract_zip_and_map_pdfs(zip_url)
	csv_missing_pdf = []
	pdf_unmatched = list(pdf_map.keys())
	
	for row in csv_data:
		fp16 = row['fp16']
		if fp16 in pdf_map:
			row['pdf_content'] = pdf_map[fp16]
			pdf_unmatched.remove(fp16)
		else:
			csv_missing_pdf.append(fp16)
			row['pdf_content'] = None
	
	# Check strict requirements
	if require_all_csv_have_pdf and csv_missing_pdf:
		return {
			'status': 'error',
			'message': _('Strict mode: {0} CSV rows missing PDFs').format(len(csv_missing_pdf)),
			'csv_missing_pdf': csv_missing_pdf,
			'row_errors': []
		}
	
	# Phase 3: Create/update records
	created = 0
	updated = 0
	skipped = 0
	row_errors = []
	created_docs = []
	
	for row_idx, row_data in enumerate(csv_data, start=2):  # Start at 2 (header is row 1)
		try:
			if not row_data['pdf_content']:
				row_errors.append({
					'row': row_idx,
					'fp_number': row_data['fp_number'],
					'reason': 'PDF not found in ZIP'
				})
				skipped += 1
				continue
			
			result = _create_or_update_tax_invoice_upload(
				row_data, batch_name, overwrite_existing
			)
			
			if result['action'] == 'created':
				created += 1
				created_docs.append(result['doc_info'])
			elif result['action'] == 'updated':
				updated += 1
				created_docs.append(result['doc_info'])
			elif result['action'] == 'skipped':
				skipped += 1
			
		except Exception as e:
			row_errors.append({
				'row': row_idx,
				'fp_number': row_data.get('fp_number', 'unknown'),
				'reason': str(e)
			})
			skipped += 1
	
	frappe.db.commit()
	
	return {
		'status': 'success' if not row_errors else 'partial',
		'created': created,
		'updated': updated,
		'skipped': skipped,
		'row_errors': row_errors,
		'pdf_unmatched': pdf_unmatched,
		'csv_missing_pdf': csv_missing_pdf,
		'created_docs': created_docs
	}


def _validate_and_parse_csv(csv_url: str) -> tuple[list[dict], list[dict]]:
	"""Validate CSV structure and parse rows.
	
	Returns:
		tuple: (csv_data, errors)
	"""
	required_headers = ['fp_number', 'sales_invoice', 'dpp', 'ppn', 'fp_date', 'customer_npwp']
	csv_data = []
	errors = []
	
	try:
		csv_path = get_file_path(csv_url)
		with open(csv_path, 'r', encoding='utf-8-sig') as f:
			reader = csv.DictReader(f)
			
			# Validate headers
			if not reader.fieldnames:
				errors.append({
					'row': 1,
					'fp_number': '',
					'reason': 'CSV file is empty or has no headers'
				})
				return [], errors
			
			missing_headers = [h for h in required_headers if h not in reader.fieldnames]
			if missing_headers:
				errors.append({
					'row': 1,
					'fp_number': '',
					'reason': f'Missing required headers: {", ".join(missing_headers)}'
				})
				return [], errors
			
			# Parse rows
			for row_idx, row in enumerate(reader, start=2):
				try:
					fp_number = (row.get('fp_number') or '').strip()
					fp16 = normalize_fp_number(fp_number)
					
					if not fp16:
						errors.append({
							'row': row_idx,
							'fp_number': fp_number,
							'reason': 'FP number is empty'
						})
						continue
					
					if len(fp16) != 16:
						errors.append({
							'row': row_idx,
							'fp_number': fp_number,
							'reason': f'FP number must be 16 digits, got {len(fp16)}'
						})
						continue
					
					sales_invoice = (row.get('sales_invoice') or '').strip()
					if not sales_invoice:
						errors.append({
							'row': row_idx,
							'fp_number': fp_number,
							'reason': 'Sales invoice is required'
						})
						continue
					
					# Parse amounts and date
					try:
						dpp = float(row.get('dpp') or 0)
						ppn = float(row.get('ppn') or 0)
					except ValueError as e:
						errors.append({
							'row': row_idx,
							'fp_number': fp_number,
							'reason': f'Invalid amount: {str(e)}'
						})
						continue
					
					csv_data.append({
						'fp_number': fp_number,
						'fp16': fp16,
						'sales_invoice': sales_invoice,
						'dpp': dpp,
						'ppn': ppn,
						'fp_date': row.get('fp_date', '').strip(),
						'customer_npwp': row.get('customer_npwp', '').strip()
					})
					
				except Exception as e:
					errors.append({
						'row': row_idx,
						'fp_number': row.get('fp_number', 'unknown'),
						'reason': f'Error parsing row: {str(e)}'
					})
	
	except Exception as e:
		errors.append({
			'row': 0,
			'fp_number': '',
			'reason': f'Error reading CSV file: {str(e)}'
		})
	
	return csv_data, errors


def _extract_zip_and_map_pdfs(zip_url: str) -> dict[str, bytes]:
	"""Extract ZIP and create map of fp16 -> PDF content.
	
	Returns:
		dict: {fp16: pdf_content}
	"""
	pdf_map = {}
	
	try:
		zip_path = get_file_path(zip_url)
		extract_dir = "/tmp/tax_invoice_upload_pdfs"
		os.makedirs(extract_dir, exist_ok=True)
		
		with zipfile.ZipFile(zip_path, 'r') as zip_ref:
			# Only extract PDF files
			pdf_files = [f for f in zip_ref.namelist() if f.lower().endswith('.pdf')]
			
			for pdf_file in pdf_files:
				try:
					# Extract FP number from filename
					filename = os.path.basename(pdf_file)
					fp16 = normalize_fp_number(filename)
					
					if fp16 and len(fp16) == 16:
						# Read PDF content
						pdf_content = zip_ref.read(pdf_file)
						pdf_map[fp16] = pdf_content
				except Exception as e:
					frappe.log_error(f"Error processing {pdf_file}: {str(e)}")
		
		# Cleanup
		try:
			import shutil
			shutil.rmtree(extract_dir)
		except:
			pass
	
	except Exception as e:
		frappe.throw(_('Error extracting ZIP file: {0}').format(str(e)))
	
	return pdf_map


def _create_or_update_tax_invoice_upload(
	row_data: dict,
	batch_name: str,
	overwrite_existing: int
) -> dict[str, Any]:
	"""Create or update a single Tax Invoice Upload record.
	
	Returns:
		dict: {action: 'created'|'updated'|'skipped', doc_info: {...}}
	"""
	fp16 = row_data['fp16']
	sales_invoice = row_data['sales_invoice']
	
	# Deterministic name
	doc_name = f"TAXUP-{fp16}-{sales_invoice}"
	
	# Check if exists
	existing = frappe.db.exists("Tax Invoice Upload", doc_name)
	
	if existing:
		if not overwrite_existing:
			# Check if PDF already attached
			existing_pdf = frappe.db.get_value("Tax Invoice Upload", doc_name, "invoice_pdf")
			if existing_pdf:
				return {
					'action': 'skipped',
					'doc_info': {
						'fp_number': fp16,
						'name': doc_name,
						'sales_invoice': sales_invoice,
						'vat_out_batch': batch_name
					}
				}
		
		# Update existing
		doc = frappe.get_doc("Tax Invoice Upload", doc_name)
		
		# Update PDF if missing or overwrite mode
		if overwrite_existing or not doc.invoice_pdf:
			file_doc = save_file(
				fname=f"FP_{fp16}.pdf",
				content=row_data['pdf_content'],
				dt="Tax Invoice Upload",
				dn=doc_name,
				is_private=0
			)
			doc.invoice_pdf = file_doc.file_url
			doc.save(ignore_permissions=True)
		
		# Try to sync
		try:
			sync_tax_invoice_with_sales(doc, fail_silently=True)
		except Exception as e:
			frappe.log_error(f"Sync error for {doc_name}: {str(e)}")
		
		return {
			'action': 'updated',
			'doc_info': {
				'fp_number': fp16,
				'name': doc_name,
				'sales_invoice': sales_invoice,
				'vat_out_batch': batch_name
			}
		}
	
	# Create new record
	# First create and attach PDF
	file_doc = save_file(
		fname=f"FP_{fp16}.pdf",
		content=row_data['pdf_content'],
		dt="Tax Invoice Upload",
		dn=doc_name,
		is_private=0
	)
	
	doc = frappe.get_doc({
		'doctype': 'Tax Invoice Upload',
		'name': doc_name,
		'tax_invoice_no': fp16,
		'tax_invoice_no_raw': row_data['fp_number'],
		'tax_invoice_date': row_data['fp_date'],
		'customer_npwp': row_data['customer_npwp'],
		'linked_sales_invoice': sales_invoice,
		'vat_out_batch': batch_name,
		'dpp': row_data['dpp'],
		'ppn': row_data['ppn'],
		'invoice_pdf': file_doc.file_url
	})
	
	doc.insert(ignore_permissions=True)
	
	# Sync to Sales Invoice
	try:
		sync_tax_invoice_with_sales(doc, fail_silently=True)
	except Exception as e:
		frappe.log_error(f"Sync error for {doc_name}: {str(e)}")
	
	return {
		'action': 'created',
		'doc_info': {
			'fp_number': fp16,
			'name': doc_name,
			'sales_invoice': sales_invoice,
			'vat_out_batch': batch_name
		}
	}


@frappe.whitelist()
def get_bulk_job_status(job_id: str) -> dict[str, Any]:
	"""Get status of background bulk creation job.
	
	Args:
		job_id: Job ID returned from bulk_create_from_csv
		
	Returns:
		dict: Job status and result
	"""
	from frappe.utils.background_jobs import get_job
	
	try:
		job = get_job(job_id)
		
		if not job:
			return {
				'status': 'not_found',
				'message': _('Job not found')
			}
		
		status = job.get_status()
		
		if status == 'finished':
			result = job.result
			return {
				'status': 'finished',
				'progress_pct': 100,
				'message': _('Completed'),
				'result': result
			}
		elif status == 'failed':
			return {
				'status': 'failed',
				'message': _('Job failed: {0}').format(str(job.exc_info))
			}
		else:
			return {
				'status': 'processing',
				'progress_pct': 50,
				'message': _('Processing bulk creation...')
			}
	
	except Exception as e:
		return {
			'status': 'error',
			'message': str(e)
		}


@frappe.whitelist()
def retry_sync(names: str | list[str]) -> dict[str, Any]:
	"""Retry sync for Tax Invoice Upload records with errors.
	
	Args:
		names: Tax Invoice Upload record names (JSON string or list)
		
	Returns:
		dict: Sync results summary
	"""
	if isinstance(names, str):
		import json
		names = json.loads(names)
	
	if not isinstance(names, list):
		names = [names]
	
	synced = 0
	failed = 0
	errors = []
	
	for name in names:
		try:
			doc = frappe.get_doc("Tax Invoice Upload", name)
			doc.check_permission("write")
			
			# Retry sync
			result = sync_tax_invoice_with_sales(doc, fail_silently=False)
			
			if result and result.get('status') == 'success':
				synced += 1
			else:
				failed += 1
				errors.append({
					'name': name,
					'reason': result.get('error') if result else 'Unknown error'
				})
		
		except Exception as e:
			failed += 1
			errors.append({
				'name': name,
				'reason': str(e)
			})
	
	frappe.db.commit()
	
	return {
		'synced': synced,
		'failed': failed,
		'errors': errors,
		'message': _('{0} synced, {1} failed').format(synced, failed)
	}
