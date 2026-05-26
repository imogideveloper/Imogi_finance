"""Pastikan custom grouping Payroll Entry mengikuti bulan gaji."""

import frappe


SCRIPT_NAME = "Client Script Payroll Entry"


def execute():
	_fix_client_script_date_source()
	frappe.clear_cache(doctype="Payroll Entry")


def _fix_client_script_date_source():
	if not frappe.db.exists("Client Script", SCRIPT_NAME):
		return

	script = frappe.db.get_value("Client Script", SCRIPT_NAME, "script") or ""
	updated = script

	updated = updated.replace(
		'add_fields: ["name", "status", "docstatus", "periode", "total_karyawan", "total_amount", "currency", "start_date", "company"],',
		'add_fields: ["name", "status", "docstatus", "periode", "posting_date", "end_date", "total_karyawan", "total_amount", "currency", "company"],',
	)
	updated = updated.replace('var DATE_FIELD = "start_date";', 'var DATE_FIELD = "posting_date";')
	updated = updated.replace(
		'var selected_groups = ["Year", "Month"];',
		'var selected_groups = ["Month"];',
	)
	updated = updated.replace(
		"var d = pd(doc[DATE_FIELD]);",
		"var d = pd(doc[DATE_FIELD] || doc.end_date || doc.start_date);",
	)
	updated = updated.replace(
		"var d = getDoc(n), dv = d ? d[DATE_FIELD] : null, dObj = pd(dv);",
		"var d = getDoc(n), dv = d ? (d[DATE_FIELD] || d.end_date || d.start_date) : null, dObj = pd(dv);",
	)

	if updated != script:
		frappe.db.set_value("Client Script", SCRIPT_NAME, "script", updated)
