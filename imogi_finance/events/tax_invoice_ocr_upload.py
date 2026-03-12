import frappe


def set_tax_invoice_display_fields(doc, method=None):
    # isi tanggal faktur pajak
    if not getattr(doc, "custom_tanggal_faktur_pajak", None):
        for fieldname in ["ti_fp_date", "tax_invoice_date", "invoice_date"]:
            value = getattr(doc, fieldname, None)
            if value:
                doc.custom_tanggal_faktur_pajak = value
                break

    # isi supplier
    if not getattr(doc, "custom_display_supplier_text", None):
        for fieldname in ["supplier", "supplier_name", "vendor", "party_name"]:
            value = getattr(doc, fieldname, None)
            if value:
                doc.custom_display_supplier_text = value
                break

    # isi status default
    if not getattr(doc, "custom_fp_status", None):
        doc.custom_fp_status = "Available"


def sync_tax_invoice_from_expense(doc, method=None):
    tax_invoice_name = doc.get("custom_tax_invoice_ocr_upload") or doc.get("ti_tax_invoice_upload")
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    frappe.db.set_value(
        "Tax Invoice OCR Upload",
        tax_invoice_name,
        {
            "custom_display_supplier_text": doc.get("supplier"),
            "custom_tanggal_faktur_pajak": doc.get("ti_fp_date") or doc.get("request_date"),
            "custom_used_in": doc.name,
            "custom_fp_status": "Used",
        },
        update_modified=False,
    )


def release_tax_invoice_on_cancel(doc, method=None):
    tax_invoice_name = doc.get("custom_tax_invoice_ocr_upload") or doc.get("ti_tax_invoice_upload")
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    frappe.db.set_value(
        "Tax Invoice OCR Upload",
        tax_invoice_name,
        {
            "custom_used_in": None,
            "custom_fp_status": "Available",
        },
        update_modified=False,
    )