import frappe


def mark_tax_invoice_as_used_on_submit(doc, method=None):
    tax_invoice_name = getattr(doc, "custom_tax_invoice_ocr_upload", None)
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    frappe.db.set_value(
        "Tax Invoice OCR Upload",
        tax_invoice_name,
        {
            "custom_used_in": doc.name,
            "custom_fp_status": "Used"
        },
        update_modified=False
    )


def release_tax_invoice_on_cancel(doc, method=None):
    tax_invoice_name = getattr(doc, "custom_tax_invoice_ocr_upload", None)
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    frappe.db.set_value(
        "Tax Invoice OCR Upload",
        tax_invoice_name,
        {
            "custom_used_in": None,
            "custom_fp_status": "Available"
        },
        update_modified=False
    )


def sync_tax_invoice_usage(doc, method=None):
    tax_invoice_name = getattr(doc, "custom_tax_invoice_ocr_upload", None)
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    if doc.docstatus == 1:
        frappe.db.set_value(
            "Tax Invoice OCR Upload",
            tax_invoice_name,
            {
                "custom_used_in": doc.name,
                "custom_fp_status": "Used"
            },
            update_modified=False
        )
    elif doc.docstatus == 2:
        frappe.db.set_value(
            "Tax Invoice OCR Upload",
            tax_invoice_name,
            {
                "custom_used_in": None,
                "custom_fp_status": "Available"
            },
            update_modified=False
        )