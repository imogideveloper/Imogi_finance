"""Perbaikan v2 atas fix_pe_periode_gaji_full_width.py dan
add_payroll_period_custom_cutoff.py - dua masalah dari versi pertama:

1. Payroll Entry: Section Break yang disisipkan SEBELUM column_break_5 memecah
   section 2-kolom itu jadi 3 section terpisah, jadi Currency/Payroll Payable
   Account/Status (yang harusnya sejajar dengan Posting Date/Company) malah
   ikut turun ke section baru dan render sendirian tanpa pasangan kiri.
   Fix: pindahkan section full-width Periode Gaji (Bulan) ke SETELAH
   currency+exchange_rate (bukan sebelum company), lalu pasangkan
   Payroll Payable Account + Status jadi 1 baris 2-kolom sendiri supaya tidak
   ada yang menggantung tanpa pasangan.

2. Payroll Period: field "periods" (tabel Payroll Periods) di-insert_after
   langsung ke cutoff_end_day, yang masih di DALAM section 2-kolom cutoff -
   jadi tabelnya ikut kejebak di kolom kanan, bukan full width. Fix: sisipkan
   Section Break baru sebelum "periods" supaya keluar dari kolom 2.
"""

import frappe


def execute():
	_fix_payroll_entry_layout()
	_fix_payroll_period_layout()
	frappe.clear_cache(doctype="Payroll Entry")
	frappe.clear_cache(doctype="Payroll Period")


def _fix_payroll_entry_layout():
	doctype = "Payroll Entry"

	# Section full-width Periode Gaji (Bulan) sekarang dipasang SETELAH
	# currency+exchange_rate, bukan sebelum company - supaya Posting Date|
	# Currency dan Company|Exchange Rate tetap sejajar seperti semula.
	_set_custom_field_insert_after(doctype, "sb_periode_gaji_full", "exchange_rate")
	_set_custom_field_insert_after(doctype, "payroll_sub_period", "sb_periode_gaji_full")
	_set_custom_field_insert_after(doctype, "payroll_period", "payroll_sub_period")
	_set_custom_field_insert_after(doctype, "cb_after_periode_gaji_full", "payroll_period")

	# Payroll Payable Account + Status dipasangkan jadi 1 baris 2-kolom
	# sendiri (bukan menggantung sendirian tanpa pasangan kiri).
	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": "cb_ppa_status"}):
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": doctype,
				"fieldname": "cb_ppa_status",
				"fieldtype": "Column Break",
				"insert_after": "payroll_payable_account",
			}
		).insert(ignore_permissions=True)

	_set_property(doctype, "payroll_payable_account", "insert_after", "cb_after_periode_gaji_full", "Data")
	_set_property(doctype, "status", "insert_after", "cb_ppa_status", "Data")


def _fix_payroll_period_layout():
	doctype = "Payroll Period"

	if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": "sb_after_cutoff"}):
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": doctype,
				"fieldname": "sb_after_cutoff",
				"fieldtype": "Section Break",
				"insert_after": "cutoff_end_day",
			}
		).insert(ignore_permissions=True)

	_set_property(doctype, "periods", "insert_after", "sb_after_cutoff", "Data")


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
