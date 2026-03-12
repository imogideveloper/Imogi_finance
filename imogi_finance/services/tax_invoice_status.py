import frappe


def mark_tax_invoice_as_used(tax_invoice_name, used_in):
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    doc = frappe.get_doc("Tax Invoice OCR Upload", tax_invoice_name)
    doc.db_set("custom_used_in", used_in, update_modified=False)
    doc.db_set("custom_fp_status", "Used", update_modified=False)


def release_tax_invoice_usage(tax_invoice_name):
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    doc = frappe.get_doc("Tax Invoice OCR Upload", tax_invoice_name)
    doc.db_set("custom_used_in", None, update_modified=False)
    doc.db_set("custom_fp_status", "Released", update_modified=False)