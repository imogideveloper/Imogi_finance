"""Payroll Entry: sembunyikan field 'Periode' legacy, buat 'Periode Gaji (Bulan)'
full-width supaya nilainya (mis. "Agu 2026 (25 Jul - 24 Agu)") tidak terpotong.

Sama seperti Komponen Gaji di Salary Structure Assignment: Column Break selalu
membuat kolom layout sendiri walau field di dalamnya hidden, jadi field harus
dipindah melewati Section Break baru supaya benar-benar full width, bukan cuma
diberi CSS width.
"""

import frappe


def execute():
	_hide_legacy_periode_field()
	_make_periode_gaji_full_width()
	frappe.clear_cache(doctype="Payroll Entry")


def _hide_legacy_periode_field():
	custom_field = frappe.db.get_value(
		"Custom Field", {"dt": "Payroll Entry", "fieldname": "periode"}, "name"
	)
	if custom_field:
		frappe.db.set_value("Custom Field", custom_field, "hidden", 1, update_modified=False)
	_set_property("Payroll Entry", "periode", "hidden", "1", "Check")


def _make_periode_gaji_full_width():
	if not frappe.db.exists("Custom Field", {"dt": "Payroll Entry", "fieldname": "payroll_sub_period"}):
		return

	if not frappe.db.exists("Custom Field", {"dt": "Payroll Entry", "fieldname": "sb_periode_gaji_full"}):
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Payroll Entry",
				"fieldname": "sb_periode_gaji_full",
				"fieldtype": "Section Break",
				"insert_after": "company",
			}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("Custom Field", {"dt": "Payroll Entry", "fieldname": "cb_after_periode_gaji_full"}):
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Payroll Entry",
				"fieldname": "cb_after_periode_gaji_full",
				"fieldtype": "Section Break",
				"insert_after": "payroll_sub_period",
			}
		).insert(ignore_permissions=True)

	# insert_after ada langsung di record Custom Field (bukan lewat Property
	# Setter) - beda dengan property standar field bawaan doctype.
	_set_custom_field_insert_after("Payroll Entry", "payroll_sub_period", "sb_periode_gaji_full")
	_set_custom_field_insert_after("Payroll Entry", "payroll_period", "cb_after_periode_gaji_full")


def _set_custom_field_insert_after(doctype: str, fieldname: str, insert_after: str):
	custom_field = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": fieldname}, "name")
	if custom_field:
		frappe.db.set_value("Custom Field", custom_field, "insert_after", insert_after, update_modified=False)


def _set_property(doctype: str, fieldname: str, prop: str, value: str, property_type: str):
	ps_name = f"{doctype}-{fieldname}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": doctype,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		ignore_validate=True,
		is_system_generated=0,
	)
