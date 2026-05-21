"""Nonaktifkan Client Script list SI yang menimpa toolbar & indicator imogi_finance."""

import frappe


def execute():
	name = "Filter Date Sales Invoice"
	if not frappe.db.exists("Client Script", name):
		return

	frappe.db.set_value("Client Script", name, "enabled", 0, update_modified=True)
	frappe.clear_cache(doctype="Client Script")
