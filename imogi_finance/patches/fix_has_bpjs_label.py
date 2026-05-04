import frappe

def execute():
    if frappe.db.exists("Custom Field", "Employee-has_jht"):
        frappe.db.set_value("Custom Field", "Employee-has_jht", {
            "label": "Bebas JHT",
            "insert_after": "exempt_from_pph21"
        })
        frappe.db.commit()

    if frappe.db.exists("Custom Field", "Employee-has_jp"):
        frappe.db.set_value("Custom Field", "Employee-has_jp", {
            "label": "Bebas JP",
            "insert_after": "Employee-has_jht"
        })
        frappe.db.commit()

    if frappe.db.exists("Custom Field", "Employee-has_bpjs_kesehatan"):
        frappe.db.set_value("Custom Field", "Employee-has_bpjs_kesehatan", {
            "label": "Bebas BPJS Kesehatan",
            "insert_after": "Employee-has_jp"
        })
        frappe.db.commit()
