"""Formula Tunjangan Operational dari nilai SSA (child table Komponen Gaji)."""

import frappe

from imogi_finance.payroll.allowance_formulas import OPERATIONAL_ALLOWANCE_FORMULA

COMPONENT = "Tunjangan Operational"


def execute():
	if not frappe.db.exists("Salary Component", COMPONENT):
		return

	frappe.db.set_value(
		"Salary Component",
		COMPONENT,
		{"formula": OPERATIONAL_ALLOWANCE_FORMULA, "amount_based_on_formula": 1},
		update_modified=False,
	)

	frappe.db.sql(
		"""
		UPDATE `tabSalary Detail`
		SET formula = %(formula)s, amount_based_on_formula = 1
		WHERE salary_component = %(component)s
		  AND parenttype = 'Salary Structure'
		""",
		{"formula": OPERATIONAL_ALLOWANCE_FORMULA, "component": COMPONENT},
	)

	frappe.clear_cache(doctype="Salary Component")
	frappe.clear_cache(doctype="Salary Structure")
