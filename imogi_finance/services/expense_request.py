import frappe


def mark_tax_invoice_as_used_on_submit(doc, method=None):
    tax_invoice_name = getattr(doc, "custom_tax_invoice_ocr_upload", None)
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    tax_doc = frappe.get_doc("Tax Invoice OCR Upload", tax_invoice_name)
    tax_doc.db_set("custom_used_in", doc.name, update_modified=False)
    tax_doc.db_set("custom_fp_status", "Used", update_modified=False)


def release_tax_invoice_on_cancel(doc, method=None):
    tax_invoice_name = getattr(doc, "custom_tax_invoice_ocr_upload", None)
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    tax_doc = frappe.get_doc("Tax Invoice OCR Upload", tax_invoice_name)
    tax_doc.db_set("custom_used_in", None, update_modified=False)
    tax_doc.db_set("custom_fp_status", "Released", update_modified=False)


def sync_tax_invoice_usage(doc, method=None):
    tax_invoice_name = getattr(doc, "custom_tax_invoice_ocr_upload", None)
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    tax_doc = frappe.get_doc("Tax Invoice OCR Upload", tax_invoice_name)

    if doc.docstatus == 1:
        tax_doc.db_set("custom_used_in", doc.name, update_modified=False)
        tax_doc.db_set("custom_fp_status", "Used", update_modified=False)
    elif doc.docstatus == 2:
        tax_doc.db_set("custom_used_in", None, update_modified=False)
        tax_doc.db_set("custom_fp_status", "Released", update_modified=False)