"""Backfill periode / total karyawan / total amount di Payroll Entry yang sudah ada."""

import frappe

from imogi_finance.payroll.payroll_entry_summary import update_payroll_entry_summary


def execute():
	for name in frappe.get_all("Payroll Entry", filters={"docstatus": 1}, pluck="name"):
		update_payroll_entry_summary(name, persist=True)
	frappe.db.commit()
