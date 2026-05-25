"""Payroll Entry: link ke Payroll Period + pilihan sub-periode (25–24)."""

import frappe


def execute():
	_add_payroll_entry_fields()
	_show_payroll_period_sub_periods_table()
	frappe.clear_cache(doctype="Payroll Entry")
	frappe.clear_cache(doctype="Payroll Period")


def _add_payroll_entry_fields():
	fields = (
		{
			"fieldname": "payroll_period",
			"label": "Payroll Period",
			"fieldtype": "Link",
			"options": "Payroll Period",
			"insert_after": "company",
			"in_standard_filter": 1,
			"description": (
				"Pilih periode tahun gaji. Start/End Date Payroll Entry "
				"mengikuti baris Periode Gaji (pola 25–24)."
			),
		},
		{
			"fieldname": "payroll_sub_period",
			"label": "Periode Gaji (Bulan)",
			"fieldtype": "Link",
			"options": "Payroll Period Date",
			"insert_after": "payroll_period",
			"description": "Pilih bulan gaji dari tabel Payroll Period (contoh: 25 Apr – 24 Mei = gaji Mei).",
		},
	)
	for spec in fields:
		if frappe.db.exists("Custom Field", {"dt": "Payroll Entry", "fieldname": spec["fieldname"]}):
			continue
		frappe.get_doc({"doctype": "Custom Field", "dt": "Payroll Entry", **spec}).insert(
			ignore_permissions=True
		)


def _show_payroll_period_sub_periods_table():
	for fieldname, prop, value, ptype in (
		("section_break_5", "hidden", "0", "Check"),
		("section_break_5", "label", "Periode Gaji (Cutoff 25–24)", "Data"),
		("periods", "hidden", "0", "Check"),
	):
		ps_name = f"Payroll Period-{fieldname}-{prop}"
		if frappe.db.exists("Property Setter", ps_name):
			frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
			continue
		frappe.make_property_setter(
			{
				"doctype": "Payroll Period",
				"doctype_or_field": "DocField",
				"fieldname": fieldname,
				"property": prop,
				"value": value,
				"property_type": ptype,
			},
			ignore_validate=True,
		)
