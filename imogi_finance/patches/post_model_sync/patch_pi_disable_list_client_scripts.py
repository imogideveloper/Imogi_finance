"""Nonaktifkan Client Script list PI yang menimpa toolbar & indicator imogi_finance."""

import frappe


def execute():
	for name in ("Filter Date Purchase Invoice", "Purchase Invoice List View"):
		if not frappe.db.exists("Client Script", name):
			continue
		frappe.db.set_value("Client Script", name, "enabled", 0, update_modified=True)

	frappe.clear_cache(doctype="Client Script")
