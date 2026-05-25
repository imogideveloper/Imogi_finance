"""Satu intro di form; hapus description berulang di field Payroll Entry."""

import frappe

FIELDS = (
	"payroll_period",
	"payroll_sub_period",
	"run_payroll_indonesia",
	"run_payroll_indonesia_december",
	"periode",
)


def execute():
	for fieldname in FIELDS:
		name = f"Payroll Entry-{fieldname}"
		if frappe.db.exists("Custom Field", name):
			frappe.db.set_value("Custom Field", name, "description", "", update_modified=False)
	frappe.clear_cache(doctype="Payroll Entry")
