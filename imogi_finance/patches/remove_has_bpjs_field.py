import frappe

def execute():
    for fieldname in ["has_bpjs", "exempt_from_bpjs"]:
        name = f"Employee-{fieldname}"
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_missing=True)
    frappe.db.commit()