"""Salary Slip: tambah field periode_hari/bulan/tahun supaya list view bisa
di-group per Hari/Bulan/Tahun, sama seperti Payroll Entry ("Periode").
"""

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from imogi_finance.payroll.salary_slip_periode import PERIODE_FIELDS, compute_periode_labels

FIELD_LABELS = {
	"periode_hari": "Periode (Hari)",
	"periode_bulan": "Periode (Bulan)",
	"periode_tahun": "Periode (Tahun)",
}


def execute():
	_create_periode_fields()
	_backfill_existing_slips()
	_enable_group_by_for_all_users()
	frappe.clear_cache(doctype="Salary Slip")


def _create_periode_fields():
	create_custom_fields(
		{
			"Salary Slip": [
				{
					"fieldname": fieldname,
					"label": FIELD_LABELS[fieldname],
					"fieldtype": "Data",
					"insert_after": "posting_date",
					"hidden": 1,
					"read_only": 1,
					"description": "Label periode otomatis, dipakai untuk Group By list view.",
				}
				for fieldname in PERIODE_FIELDS
			]
		},
		ignore_validate=True,
	)


def _backfill_existing_slips():
	rows = frappe.get_all(
		"Salary Slip",
		fields=["name", "start_date", "end_date", "posting_date"] + list(PERIODE_FIELDS),
	)
	for row in rows:
		reference_date = row.end_date or row.start_date or row.posting_date
		labels = compute_periode_labels(reference_date)
		if not labels:
			continue
		if all(row.get(f) == labels.get(f) for f in PERIODE_FIELDS):
			continue
		frappe.db.set_value("Salary Slip", row.name, labels, update_modified=False)


def _enable_group_by_for_all_users():
	for row in frappe.db.sql(
		"select user, data from `__UserSettings` where doctype='Salary Slip'",
		as_dict=True,
	):
		try:
			data = json.loads(row.data or "{}")
		except Exception:
			continue

		existing = data.get("group_by_fields") or []
		changed = False
		for fieldname in PERIODE_FIELDS:
			if fieldname not in existing:
				existing.append(fieldname)
				changed = True
		if not changed:
			continue

		data["group_by_fields"] = existing
		frappe.db.sql(
			"""
			update `__UserSettings`
			set data=%s
			where user=%s and doctype='Salary Slip'
			""",
			(json.dumps(data), row.user),
		)

	# Untuk user yang belum punya baris __UserSettings sama sekali untuk
	# Salary Slip (belum pernah buka list-nya), seed satu baris supaya
	# begitu list dibuka pertama kali opsi grouping-nya sudah tersedia.
	existing_users = {
		r.user
		for r in frappe.db.sql(
			"select user from `__UserSettings` where doctype='Salary Slip'", as_dict=True
		)
	}
	all_users = frappe.get_all("User", filters={"enabled": 1}, pluck="name")
	for user in all_users:
		if user in existing_users or user == "Guest":
			continue
		frappe.db.sql(
			"""
			insert into `__UserSettings` (user, doctype, data)
			values (%s, 'Salary Slip', %s)
			""",
			(user, json.dumps({"group_by_fields": list(PERIODE_FIELDS)})),
		)
