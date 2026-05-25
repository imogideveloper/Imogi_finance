"""Ubah label section Salary Structure Assignment menjadi Assignment Contract."""

import frappe

SECTION_FIELD = "section_break_7"
SECTION_LABEL = "Assignment Contract"


def execute():
	_set_section_label()
	frappe.clear_cache(doctype="Salary Structure Assignment")


def _set_section_label():
	ps_name = f"Salary Structure Assignment-{SECTION_FIELD}-label"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", SECTION_LABEL, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": "Salary Structure Assignment",
			"doctype_or_field": "DocField",
			"fieldname": SECTION_FIELD,
			"property": "label",
			"value": SECTION_LABEL,
			"property_type": "Data",
		},
		ignore_validate=True,
	)
