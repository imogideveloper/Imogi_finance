"""Remove Delivery Status & Billing Status from Sales Order list filter bar."""

from __future__ import annotations

import frappe


def execute():
	for fieldname in ("delivery_status", "billing_status"):
		name = f"Sales Order-{fieldname}-in_standard_filter"
		if frappe.db.exists("Property Setter", name):
			frappe.db.set_value("Property Setter", name, "value", "0", update_modified=False)
			continue
		frappe.make_property_setter(
			{
				"doctype": "Sales Order",
				"doctype_or_field": "DocField",
				"fieldname": fieldname,
				"property": "in_standard_filter",
				"property_type": "Check",
				"value": "0",
			},
			ignore_validate=True,
			is_system_generated=0,
		)
	frappe.clear_cache(doctype="Sales Order")
