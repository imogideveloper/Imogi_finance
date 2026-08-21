"""Cabut field periode_hari/bulan/tahun dari Salary Slip - ternyata grouping
Year/Month/Day tidak butuh field tambahan sama sekali, cukup Client Script
(lihat add_salary_slip_nested_grouping_client_script.py) yang menghitung
langsung dari tanggal saat render, sama seperti mekanisme Payroll Entry.
"""

import json

import frappe

PERIODE_FIELDS = ("periode_hari", "periode_bulan", "periode_tahun")


def execute():
	_delete_periode_custom_fields()
	_remove_from_user_settings()
	frappe.clear_cache(doctype="Salary Slip")


def _delete_periode_custom_fields():
	for fieldname in PERIODE_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": "Salary Slip", "fieldname": fieldname}, "name")
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


def _remove_from_user_settings():
	for row in frappe.db.sql(
		"select user, data from `__UserSettings` where doctype='Salary Slip'",
		as_dict=True,
	):
		try:
			data = json.loads(row.data or "{}")
		except Exception:
			continue

		existing = data.get("group_by_fields") or []
		remaining = [f for f in existing if f not in PERIODE_FIELDS]
		if remaining == existing:
			continue

		data["group_by_fields"] = remaining
		frappe.db.sql(
			"""
			update `__UserSettings`
			set data=%s
			where user=%s and doctype='Salary Slip'
			""",
			(json.dumps(data), row.user),
		)
