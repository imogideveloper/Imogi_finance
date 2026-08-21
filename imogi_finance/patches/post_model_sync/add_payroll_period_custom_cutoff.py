"""Payroll Period: cutoff bulanan (default 25-24) sekarang bisa di-custom
per Payroll Period, bukan hardcoded. Field baru "cutoff_start_day"/
"cutoff_end_day" dibaca oleh build_cutoff_sub_periods() saat auto-generate
baris Payroll Period Date - lihat payroll_period_integration.validate_payroll_period.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from imogi_finance.payroll.payroll_period_integration import (
	DEFAULT_CUTOFF_END_DAY,
	DEFAULT_CUTOFF_START_DAY,
)


def execute():
	_create_cutoff_fields()
	_reposition_periods_table()
	_backfill_default_values()
	_update_section_label()
	frappe.clear_cache(doctype="Payroll Period")


def _update_section_label():
	# Label lama "Periode Gaji (Cutoff 25-24)" jadi menyesatkan sekarang
	# cutoff-nya bisa di-custom per Payroll Period.
	ps_name = "Payroll Period-section_break_5-label"
	value = "Periode Gaji (Cutoff Bulanan)"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return
	frappe.make_property_setter(
		{
			"doctype": "Payroll Period",
			"doctype_or_field": "DocField",
			"fieldname": "section_break_5",
			"property": "label",
			"value": value,
			"property_type": "Data",
		},
		ignore_validate=True,
		is_system_generated=0,
	)


def _create_cutoff_fields():
	create_custom_fields(
		{
			"Payroll Period": [
				{
					"fieldname": "cutoff_start_day",
					"label": "Tanggal Mulai Cutoff",
					"fieldtype": "Int",
					"insert_after": "section_break_5",
					"default": str(DEFAULT_CUTOFF_START_DAY),
					"description": "Bulan sebelumnya.",
				},
				{
					"fieldname": "column_break_cutoff",
					"fieldtype": "Column Break",
					"insert_after": "cutoff_start_day",
				},
				{
					"fieldname": "cutoff_end_day",
					"label": "Tanggal Akhir Cutoff",
					"fieldtype": "Int",
					"insert_after": "column_break_cutoff",
					"default": str(DEFAULT_CUTOFF_END_DAY),
					"description": "Bulan berjalan.",
				},
			]
		},
		ignore_validate=True,
	)


def _reposition_periods_table():
	# "periods" adalah field standar HRMS (bukan Custom Field), jadi posisinya
	# diubah lewat Property Setter, bukan langsung di record Custom Field.
	ps_name = "Payroll Period-periods-insert_after"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", "cutoff_end_day", update_modified=False)
		return
	frappe.make_property_setter(
		{
			"doctype": "Payroll Period",
			"doctype_or_field": "DocField",
			"fieldname": "periods",
			"property": "insert_after",
			"value": "cutoff_end_day",
			"property_type": "Data",
		},
		ignore_validate=True,
		is_system_generated=0,
	)


def _backfill_default_values():
	frappe.db.sql(
		"""
		update `tabPayroll Period`
		set cutoff_start_day = %s, cutoff_end_day = %s
		where cutoff_start_day is null or cutoff_end_day is null
			or cutoff_start_day = 0 or cutoff_end_day = 0
		""",
		(DEFAULT_CUTOFF_START_DAY, DEFAULT_CUTOFF_END_DAY),
	)
