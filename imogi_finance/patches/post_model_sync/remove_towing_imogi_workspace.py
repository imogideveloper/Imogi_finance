"""Hapus workspace Towing Imogi dari database (fixture sudah tidak menyertakannya)."""

import frappe


def execute():
	name = "Towing Imogi"
	if not frappe.db.exists("Workspace", name):
		return

	frappe.delete_doc("Workspace", name, force=1, ignore_permissions=True)
	frappe.clear_cache(doctype="Workspace")
	frappe.db.commit()
