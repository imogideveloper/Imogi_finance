"""Filter list Salary Structure Assignment — hanya field penting."""

from __future__ import annotations

import frappe

DOCTYPE = "Salary Structure Assignment"

# Sembunyikan dari standard filter bar (masih bisa lewat menu Filter).
HIDDEN_FILTERS = (
	"employee_name",
	"department",
	"designation",
	"assignment_contract_type",
	"previous_assignment_contract",
	"renewed_by_assignment_contract",
)

# Tetap tampil di kolom list walau bukan title_field filter lagi.
LIST_VIEW_FIELDS = ("employee_name",)


def execute():
	for fieldname in HIDDEN_FILTERS:
		_hide_standard_filter(fieldname)

	# employee_name = title_field HRMS → selalu jadi filter; kosongkan title_field.
	_set_doctype_property("title_field", "")

	for fieldname in LIST_VIEW_FIELDS:
		_set_property(fieldname, "in_list_view", "1", "Check")

	frappe.clear_cache(doctype=DOCTYPE)


def _hide_standard_filter(fieldname: str) -> None:
	_set_property(fieldname, "in_standard_filter", "0", "Check")

	cf_name = f"{DOCTYPE}-{fieldname}"
	if frappe.db.exists("Custom Field", cf_name):
		frappe.db.set_value("Custom Field", cf_name, "in_standard_filter", 0, update_modified=False)


def _set_property(fieldname: str, prop: str, value: str, property_type: str) -> None:
	ps_name = f"{DOCTYPE}-{fieldname}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": DOCTYPE,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		ignore_validate=True,
		is_system_generated=0,
	)


def _set_doctype_property(prop: str, value: str) -> None:
	ps_name = f"{DOCTYPE}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": DOCTYPE,
			"doctype_or_field": "DocType",
			"property": prop,
			"value": value,
			"property_type": "Data",
		},
		ignore_validate=True,
		is_system_generated=0,
	)
