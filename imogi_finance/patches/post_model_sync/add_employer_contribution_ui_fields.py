"""Tampilan tunjangan ditanggung perusahaan di Salary Structure, Payroll Entry, Salary Slip."""

import frappe


def execute():
	_add_salary_structure_fields()
	_add_payroll_entry_fields()
	_configure_salary_slip_employer_field()
	frappe.clear_cache(doctype="Salary Structure")
	frappe.clear_cache(doctype="Payroll Entry")
	frappe.clear_cache(doctype="Salary Slip")


def _ensure_custom_field(dt: str, spec: dict) -> None:
	if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": spec["fieldname"]}):
		return
	frappe.get_doc({"doctype": "Custom Field", "dt": dt, **spec}).insert(ignore_permissions=True)


def _add_salary_structure_fields():
	_ensure_custom_field(
		"Salary Structure",
		{
			"fieldname": "employer_contributions_section",
			"label": "Tunjangan Ditanggung Perusahaan",
			"fieldtype": "Section Break",
			"insert_after": "deductions",
			"collapsible": 1,
		},
	)
	_ensure_custom_field(
		"Salary Structure",
		{
			"fieldname": "employer_contributions",
			"label": "Employer Contributions",
			"fieldtype": "Table",
			"options": "Employer Contribution Detail",
			"insert_after": "employer_contributions_section",
			"read_only": 1,
			"description": "Otomatis dari baris earnings yang komponennya Employer (BPJS perusahaan, dll.).",
		},
	)


def _add_payroll_entry_fields():
	_ensure_custom_field(
		"Payroll Entry",
		{
			"fieldname": "employer_contributions_section",
			"label": "Tunjangan Ditanggung Perusahaan",
			"fieldtype": "Section Break",
			"insert_after": "error_message",
			"collapsible": 1,
			"hidden": 1,
		},
	)
	_ensure_custom_field(
		"Payroll Entry",
		{
			"fieldname": "total_employer_contribution",
			"label": "Total Employer Contribution",
			"fieldtype": "Currency",
			"insert_after": "employer_contributions_section",
			"read_only": 1,
			"allow_on_submit": 1,
			"hidden": 1,
		},
	)
	_ensure_custom_field(
		"Payroll Entry",
		{
			"fieldname": "employer_contributions_summary",
			"label": "Employer Contributions",
			"fieldtype": "Table",
			"options": "Employer Contribution Detail",
			"insert_after": "total_employer_contribution",
			"read_only": 1,
			"allow_on_submit": 1,
			"hidden": 1,
			"description": "Agregat dari Salary Slip terkait payroll entry ini.",
		},
	)


def _configure_salary_slip_employer_field():
	_ensure_custom_field(
		"Salary Slip",
		{
			"fieldname": "employer_contributions_section",
			"label": "Tunjangan Ditanggung Perusahaan",
			"fieldtype": "Section Break",
			"insert_after": "deductions",
			"collapsible": 1,
		},
	)
	for fieldname, updates in (
		("employer_contributions", {"read_only": 1, "insert_after": "employer_contributions_section"}),
	):
		cf_name = frappe.db.get_value("Custom Field", {"dt": "Salary Slip", "fieldname": fieldname})
		if not cf_name:
			continue
		doc = frappe.get_doc("Custom Field", cf_name)
		for key, value in updates.items():
			setattr(doc, key, value)
		doc.save(ignore_permissions=True)
