"""Izinkan update field ringkasan employer setelah Payroll Entry di-submit."""

import frappe


def execute():
	for fieldname in ("total_employer_contribution", "employer_contributions_summary"):
		cf = frappe.db.get_value("Custom Field", {"dt": "Payroll Entry", "fieldname": fieldname})
		if cf:
			frappe.db.set_value("Custom Field", cf, "allow_on_submit", 1, update_modified=False)

	frappe.clear_cache(doctype="Payroll Entry")
