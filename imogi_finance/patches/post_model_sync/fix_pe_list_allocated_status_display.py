"""Payment Entry list/form: Allocated & Unallocated (not Submitted)."""

import frappe

from imogi_finance.patches.post_model_sync.fix_pe_list_status_client_script import (
	MERGE_MARKER,
	_patch_client_script,
)
from imogi_finance.payment_entry_status import backfill_all_payment_status


def execute():
	_patch_client_script()
	_hide_status_from_list_view()
	backfill_all_payment_status()
	frappe.clear_cache(doctype="Payment Entry")


def _hide_status_from_list_view():
	for field_name in ("status",):
		frappe.make_property_setter(
			{
				"doctype": "Payment Entry",
				"doctype_or_field": "DocField",
				"fieldname": field_name,
				"property": "in_list_view",
				"value": "0",
				"property_type": "Check",
			},
			ignore_validate=True,
			is_system_generated=0,
		)
