"""Hitung BPJS dari gaji tetap terdaftar, bukan hanya Gaji Pokok."""

import frappe

BPJS_FORMULAS = {
	"BPJS JHT Employee": "bpjs_base * get_bpjs_rate('bpjs_jht_employee_rate') / 100",
	"BPJS JP Employee": "bpjs_base * get_bpjs_rate('bpjs_pension_employee_rate') / 100",
	"BPJS Kesehatan Employee": "(bpjs_base if bpjs_base >= 5396761 else 5396761) * 0.01",
	"BPJS Kesehatan Employer": '(bpjs_base if bpjs_base >= 5396761 else 5396761) * get_bpjs_rate("bpjs_health_employer_rate") / 100',
	"BPJS JHT Employer": "bpjs_base * get_bpjs_rate('bpjs_jht_employer_rate') / 100",
	"BPJS JP Employer": "bpjs_base * get_bpjs_rate('bpjs_pension_employer_rate') / 100",
	"BPJS JKK Employer": "bpjs_base * get_bpjs_rate('bpjs_jkk_rate') / 100",
	"BPJS JKM Employer": "bpjs_base * get_bpjs_rate('bpjs_jkm_rate') / 100",
}


def execute():
	for component, formula in BPJS_FORMULAS.items():
		if not frappe.db.exists("Salary Component", component):
			continue

		frappe.db.set_value(
			"Salary Component",
			component,
			{"formula": formula, "amount_based_on_formula": 1},
			update_modified=False,
		)

		frappe.db.sql(
			"""
			UPDATE `tabSalary Detail`
			SET formula = %(formula)s, amount_based_on_formula = 1
			WHERE salary_component = %(component)s
			  AND parenttype = 'Salary Structure'
			""",
			{"formula": formula, "component": component},
		)

	frappe.clear_cache(doctype="Salary Component")
	frappe.clear_cache(doctype="Salary Structure")
