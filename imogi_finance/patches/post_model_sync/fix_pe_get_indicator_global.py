"""Ensure Payment Entry list shows Allocated/Unallocated after deploy."""

import frappe

from imogi_finance.payment_entry_status import backfill_all_payment_status


def execute():
	backfill_all_payment_status()
	frappe.clear_cache(doctype="Payment Entry")
	frappe.clear_cache(doctype="Client Script")
