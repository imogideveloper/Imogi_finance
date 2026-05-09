import frappe

def execute():
    if frappe.db.exists("Custom Field", "Employee-exempt_from_bpjs"):
        frappe.delete_doc("Custom Field", "Employee-exempt_from_bpjs", force=True)
        frappe.db.commit()
        print("✅ Removed duplicate exempt_from_bpjs field")
    else:
        print("✅ exempt_from_bpjs field not found, skipping")
