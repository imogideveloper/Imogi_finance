"""Label tampilan untuk Payroll Period Date (bukan hash ID di dropdown)."""

import frappe

from imogi_finance.payroll.payroll_period_integration import (
	_format_sub_period_label,
	ensure_payroll_period_sub_periods,
)

LABEL_FIELD = "period_label"


def execute():
	_add_label_field()
	frappe.db.commit()
	frappe.clear_cache(doctype="Payroll Period Date")
	try:
		frappe.reload_doc("Payroll", "doctype", "payroll_period_date")
	except Exception:
		pass
	_set_title_field()
	_backfill_labels()
	_convert_pe_sub_period_to_select()
	frappe.clear_cache(doctype="Payroll Entry")
	frappe.clear_cache(doctype="Payroll Period Date")


def _add_label_field():
	if frappe.db.exists("Custom Field", f"Payroll Period Date-{LABEL_FIELD}"):
		return
	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Payroll Period Date",
			"fieldname": LABEL_FIELD,
			"label": "Label Periode",
			"fieldtype": "Data",
			"in_list_view": 1,
			"read_only": 1,
			"insert_after": "end_date",
		}
	).insert(ignore_permissions=True)


def _set_title_field():
	if frappe.db.exists("Property Setter", "Payroll Period Date-title_field"):
		frappe.db.set_value(
			"Property Setter", "Payroll Period Date-title_field", "value", LABEL_FIELD, update_modified=False
		)
	else:
		frappe.make_property_setter(
			{
				"doctype": "Payroll Period Date",
				"doctype_or_field": "DocType",
				"property": "title_field",
				"value": LABEL_FIELD,
				"property_type": "Data",
			},
			ignore_validate=True,
		)

	ps_link = "Payroll Period Date-show_title_field_in_link"
	if frappe.db.exists("Property Setter", ps_link):
		frappe.db.set_value("Property Setter", ps_link, "value", "1", update_modified=False)
	else:
		frappe.make_property_setter(
			{
				"doctype": "Payroll Period Date",
				"doctype_or_field": "DocType",
				"property": "show_title_field_in_link",
				"value": "1",
				"property_type": "Check",
			},
			ignore_validate=True,
		)


def _backfill_labels():
	if not frappe.get_meta("Payroll Period Date").has_field(LABEL_FIELD):
		return

	for row in frappe.db.sql(
		"""
		SELECT name, start_date, end_date, parent
		FROM `tabPayroll Period Date`
		WHERE start_date IS NOT NULL AND end_date IS NOT NULL
		""",
		as_dict=True,
	):
		label = _format_sub_period_label(row.start_date, row.end_date)
		frappe.db.set_value(
			"Payroll Period Date", row.name, LABEL_FIELD, label, update_modified=False
		)

	# Pastikan Payroll Period yang sudah ada punya baris periode
	for pp in frappe.get_all("Payroll Period", pluck="name"):
		if not frappe.db.count("Payroll Period Date", {"parent": pp}):
			ensure_payroll_period_sub_periods(pp)


def _convert_pe_sub_period_to_select():
	cf = "Payroll Entry-payroll_sub_period"
	if not frappe.db.exists("Custom Field", cf):
		return
	frappe.db.set_value(
		"Custom Field",
		cf,
		{"fieldtype": "Select", "options": ""},
		update_modified=False,
	)
