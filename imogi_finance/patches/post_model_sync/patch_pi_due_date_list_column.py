"""Tampilkan kolom Due Date di list Purchase Invoice (selaras Sales Invoice)."""

import frappe


def execute():
	frappe.make_property_setter(
		{
			"doctype": "Purchase Invoice",
			"fieldname": "due_date",
			"property": "in_list_view",
			"value": "1",
			"property_type": "Check",
		},
		is_system_generated=0,
	)
	frappe.clear_cache(doctype="Purchase Invoice")
