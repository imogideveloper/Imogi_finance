"""Isi ulang tabel employer_contributions dari earnings pada slip yang sudah ada."""

import frappe

from imogi_finance.payroll.employer_contributions import (
	sync_doc_employer_contributions,
	update_payroll_entry_employer_summary,
)


def execute():
	if not frappe.db.has_column("Salary Slip", "employer_contributions"):
		return

	payroll_entries: set[str] = set()
	for name in frappe.get_all("Salary Slip", pluck="name"):
		doc = frappe.get_doc("Salary Slip", name)
		sync_doc_employer_contributions(doc)
		doc.flags.ignore_validate = True
		doc.save(ignore_permissions=True)
		if doc.get("payroll_entry") and doc.docstatus == 1:
			payroll_entries.add(doc.payroll_entry)

	for pe in payroll_entries:
		update_payroll_entry_employer_summary(pe, persist=True)

	frappe.db.commit()
