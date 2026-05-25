"""Perbaiki formula tunjangan: SSA isi nominal bulanan, bukan rate harian."""

import frappe

from imogi_finance.payroll.allowance_formulas import LEGACY_FORMULAS


def execute():
	for component, (_old, new_formula) in LEGACY_FORMULAS.items():
		if not frappe.db.exists("Salary Component", component):
			continue
		frappe.db.set_value(
			"Salary Component",
			component,
			{"formula": new_formula, "amount_based_on_formula": 1},
			update_modified=False,
		)

		frappe.db.sql(
			"""
			UPDATE `tabSalary Detail`
			SET formula = %(formula)s
			WHERE salary_component = %(component)s
			  AND parenttype = 'Salary Structure'
			  AND (formula IS NULL OR formula = '' OR formula LIKE 'payment_days * %%')
			""",
			{"formula": new_formula, "component": component},
		)

	frappe.clear_cache(doctype="Salary Component")
	frappe.clear_cache(doctype="Salary Structure")
