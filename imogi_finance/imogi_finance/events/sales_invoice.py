# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""Sales Invoice event handlers for VAT OUT Batch integration."""

from __future__ import annotations

import frappe
from frappe import _


def on_update_after_submit(doc, method=None):
	"""
	Handle Sales Invoice updates after submit.
	
	Prevents modification of VAT OUT Batch linked invoices after batch is exported.
	"""
	# Check if invoice is part of an exported VAT OUT Batch
	if not doc.out_fp_batch:
		return
	
	batch = frappe.get_cached_doc("VAT OUT Batch", doc.out_fp_batch)
	
	# If batch is exported, prevent changes to tax fields
	if batch.exported_on:
		# Get previous doc
		previous = getattr(doc, "_doc_before_save", None)
		if not previous:
			return
		
		# Fields that should not change after export
		guarded_fields = [
			"out_fp_dpp",
			"out_fp_ppn",
			"out_fp_status",
			"customer",
			"posting_date",
			"grand_total"
		]
		
		changed_fields = []
		for field in guarded_fields:
			if getattr(previous, field, None) != getattr(doc, field, None):
				changed_fields.append(field)
		
		if changed_fields:
			frappe.throw(
				_("Cannot modify Sales Invoice {0} because it is part of exported VAT OUT Batch {1}. Changed fields: {2}").format(
					doc.name,
					doc.out_fp_batch,
					", ".join(changed_fields)
				),
				title=_("VAT OUT Batch Locked")
			)
