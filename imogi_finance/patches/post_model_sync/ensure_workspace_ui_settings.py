import frappe


def execute():
	if frappe.db.exists("DocType", "Workspace UI Settings"):
		frappe.get_single("Workspace UI Settings")
		frappe.db.commit()
