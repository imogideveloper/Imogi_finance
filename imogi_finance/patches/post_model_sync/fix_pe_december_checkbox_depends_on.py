"""Tampilkan Run Payroll Indonesia December saat end_date di bulan Des (bukan start_date)."""

import frappe


def execute():
	cf = "Payroll Entry-run_payroll_indonesia_december"
	if not frappe.db.exists("Custom Field", cf):
		return

	frappe.db.set_value(
		"Custom Field",
		cf,
		{
			"depends_on": (
				"eval:doc.run_payroll_indonesia && doc.end_date "
				"&& (new Date(doc.end_date).getMonth() == 11)"
			),
			"description": (
				"PPh21 koreksi tahunan (Desember). Muncul jika Run Payroll Indonesia aktif "
				"dan end_date jatuh di bulan Des (pola 25–24: periode Des = 25 Nov–24 Des)."
			),
		},
		update_modified=False,
	)
	frappe.clear_cache(doctype="Payroll Entry")
