"""Kunci End Date SSA setelah submit — perubahan hanya lewat contract baru."""

import frappe


PARENT_DOCTYPE = "Salary Structure Assignment"


def execute():
	_set_custom_field_allow_on_submit("end_date", 0)
	_set_property("end_date", "allow_on_submit", "0", "Check")
	frappe.clear_cache(doctype=PARENT_DOCTYPE)


def _set_property(fieldname: str, prop: str, value: str, property_type: str):
	ps_name = f"{PARENT_DOCTYPE}-{fieldname}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": PARENT_DOCTYPE,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		ignore_validate=True,
		is_system_generated=0,
	)


def _set_custom_field_allow_on_submit(fieldname: str, value: int):
	custom_field = frappe.db.get_value(
		"Custom Field",
		{"dt": PARENT_DOCTYPE, "fieldname": fieldname},
		"name",
	)
	if custom_field:
		frappe.db.set_value("Custom Field", custom_field, "allow_on_submit", value, update_modified=False)
