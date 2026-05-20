# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""Sales Invoice event handlers for VAT OUT Batch integration."""

from __future__ import annotations


import frappe
from frappe import _
from frappe.utils import flt


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

def fix_rounding_status(doc, method=None):
    from frappe.utils import flt
    tolerance = 1.0
    outstanding = flt(doc.outstanding_amount)
    grand_total = flt(doc.grand_total)
    paid_amount = grand_total - outstanding

    print(f"🔥 fix_rounding_status: outstanding={outstanding}, grand_total={grand_total}, paid={paid_amount}")

    if 0 < paid_amount <= tolerance:
        frappe.db.set_value("Sales Invoice", doc.name, {
            "outstanding_amount": grand_total,
            "status": "Unpaid"
        })
        print(f"🔥 Fixed {doc.name} → Unpaid")


def reapply_imogi_so_down_payment(doc, method=None):
	"""Re-apply DP line amounts after ERPNext validate recalculates items to full SO value."""
	from imogi_finance.sales_invoice_from_so import (
		apply_down_payment_keep_qty_scale_rate,
		get_si_down_payment_ratio,
	)

	ratio = get_si_down_payment_ratio(doc)
	if 0 < ratio < 1:
		apply_down_payment_keep_qty_scale_rate(doc, ratio)