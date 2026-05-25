"""Isi ulang total_employer_contribution di Payroll Entry dari slip terkait."""

import frappe

from imogi_finance.payroll.employer_contributions import update_payroll_entry_employer_summary


def execute():
	if not frappe.get_meta("Payroll Entry").has_field("employer_contributions_summary"):
		return

	for name in frappe.get_all(
		"Payroll Entry",
		filters={"docstatus": ["!=", 2]},
		pluck="name",
	):
		update_payroll_entry_employer_summary(name, persist=True)

	frappe.db.commit()
