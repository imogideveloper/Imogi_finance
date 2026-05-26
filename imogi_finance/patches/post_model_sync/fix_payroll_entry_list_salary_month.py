"""Rapikan list view Payroll Entry agar grouping mengikuti bulan gaji."""

import json

import frappe


LIST_FIELDS = [
	{"fieldname": "name", "label": "ID"},
	{"fieldname": "status", "label": "Status"},
	{"fieldname": "periode", "label": "Periode"},
	{"fieldname": "posting_date", "label": "Posting Date"},
	{"fieldname": "total_karyawan", "label": "Total Karyawan"},
	{"fieldname": "total_amount", "label": "Total Amount"},
	{"fieldname": "currency", "label": "Mata Uang"},
]


def execute():
	_configure_list_fields()
	_set_date_field_list_properties()
	_reset_start_date_user_sort()
	frappe.clear_cache(doctype="Payroll Entry")


def _configure_list_fields():
	if frappe.db.exists("List View Settings", "Payroll Entry"):
		settings = frappe.get_doc("List View Settings", "Payroll Entry")
	else:
		settings = frappe.new_doc("List View Settings")
		settings.name = "Payroll Entry"
		settings.owner = "Administrator"

	settings.total_fields = len(LIST_FIELDS)
	settings.fields = json.dumps(LIST_FIELDS)
	settings.save(ignore_permissions=True)


def _set_date_field_list_properties():
	for fieldname, value in {
		"posting_date": "1",
		"end_date": "1",
		"start_date": "0",
	}.items():
		_set_property(fieldname, "in_standard_filter", value, "Check")
	_set_property("posting_date", "in_list_view", "1", "Check")


def _set_property(fieldname: str, prop: str, value: str, property_type: str):
	ps_name = f"Payroll Entry-{fieldname}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": "Payroll Entry",
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		ignore_validate=True,
		is_system_generated=0,
	)


def _reset_start_date_user_sort():
	for row in frappe.db.sql(
		"select user, data from `__UserSettings` where doctype='Payroll Entry'",
		as_dict=True,
	):
		try:
			data = json.loads(row.data or "{}")
		except Exception:
			continue

		list_settings = data.get("List") or {}
		if list_settings.get("sort_by") in (None, "modified", "start_date"):
			list_settings["sort_by"] = "posting_date"
			list_settings["sort_order"] = "desc"
			data["List"] = list_settings
			frappe.db.sql(
				"""
				update `__UserSettings`
				set data=%s
				where user=%s and doctype='Payroll Entry'
				""",
				(json.dumps(data), row.user),
			)
