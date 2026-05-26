"""Tambah End Date dan status aktif/expired di Salary Structure Assignment."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from imogi_finance.payroll.salary_structure_assignment import sync_expired_salary_structure_assignments


def execute():
	_create_fields()
	_set_from_date_list_view()
	sync_expired_salary_structure_assignments()
	frappe.clear_cache(doctype="Salary Structure Assignment")


def _create_fields():
	create_custom_fields(
		{
			"Salary Structure Assignment": [
				{
					"fieldname": "end_date",
					"label": "End Date",
					"fieldtype": "Date",
					"insert_after": "from_date",
					"allow_on_submit": 1,
					"in_list_view": 1,
					"in_standard_filter": 1,
					"description": "Tanggal akhir berlakunya assignment. Jika lewat dari tanggal ini, status menjadi Expired.",
				},
				{
					"fieldname": "status",
					"label": "Status",
					"fieldtype": "Select",
					"options": "Active\nExpired",
					"default": "Active",
					"insert_after": "end_date",
					"read_only": 1,
					"allow_on_submit": 1,
					"in_list_view": 1,
					"in_standard_filter": 1,
				},
			]
		},
		ignore_validate=True,
	)


def _set_from_date_list_view():
	_set_property("from_date", "in_list_view", "1", "Check")
	_set_property("from_date", "in_standard_filter", "1", "Check")


def _set_property(fieldname: str, prop: str, value: str, property_type: str):
	ps_name = f"Salary Structure Assignment-{fieldname}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": "Salary Structure Assignment",
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		ignore_validate=True,
		is_system_generated=0,
	)
