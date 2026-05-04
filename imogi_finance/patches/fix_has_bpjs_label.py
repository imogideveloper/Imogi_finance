import frappe

def execute():
    if frappe.db.exists("Custom Field", "Employee-has_bpjs"):
        frappe.db.set_value("Custom Field", "Employee-has_bpjs", {
            "label": "Bebas BPJS Indonesia",
            "insert_after": "exempt_from_pph21"
        })
        frappe.db.commit()
