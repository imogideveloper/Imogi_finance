import frappe
from frappe.utils import cint


def execute():
	"""Pastikan Maximum Number of Fields cukup agar kolom Outstanding tidak terpotong."""
	# Harus salah satu opsi valid Select di Frappe: 4,5,6,7,8,9,10
	min_total_fields = "10"

	if not frappe.db.exists("List View Settings", "Sales Order"):
		return

	current_raw = frappe.db.get_value("List View Settings", "Sales Order", "total_fields")
	valid = {"", "4", "5", "6", "7", "8", "9", "10"}
	if current_raw in valid and cint(current_raw or 0) >= cint(min_total_fields):
		return

	frappe.db.set_value(
		"List View Settings",
		"Sales Order",
		"total_fields",
		min_total_fields,
		update_modified=True,
	)
	frappe.clear_cache(doctype="Sales Order")
