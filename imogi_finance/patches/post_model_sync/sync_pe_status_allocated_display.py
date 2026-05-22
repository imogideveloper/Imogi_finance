"""Payment Entry: status field = Allocated/Unallocated + DocType states for list view."""

import frappe

from imogi_finance.payment_entry_status import backfill_all_payment_status

PE_STATES = [
	{"title": "Draft", "color": "Gray"},
	{"title": "Allocated", "color": "Green"},
	{"title": "Unallocated", "color": "Orange"},
	{"title": "Cancelled", "color": "Red"},
]

STATUS_OPTIONS = "Draft\nUnallocated\nAllocated\nCancelled"


def execute():
	_update_doctype_states()
	_update_status_field_options()
	backfill_all_payment_status()
	frappe.clear_cache(doctype="Payment Entry")


def _update_doctype_states():
	if not frappe.db.exists("DocType", "Payment Entry"):
		return

	doc = frappe.get_doc("DocType", "Payment Entry")
	doc.states = []
	for row in PE_STATES:
		doc.append("states", row)
	doc.save(ignore_permissions=True)


def _update_status_field_options():
	frappe.make_property_setter(
		{
			"doctype": "Payment Entry",
			"doctype_or_field": "DocField",
			"fieldname": "status",
			"property": "options",
			"value": STATUS_OPTIONS,
			"property_type": "Text",
		},
		ignore_validate=True,
		is_system_generated=0,
	)
