import frappe

from imogi_finance.tax_invoice_ocr import sync_tax_invoice_upload, validate_tax_invoice_upload_link


def validate_before_submit(doc, method=None):
    """Re-sync Faktur Pajak fields from the linked OCR Upload before submit.

    Mirrors purchase_invoice.validate_before_submit(): the client-side JS
    (purchase_order_tax_invoice.js) already syncs these fields when a user
    picks an upload in the browser, but this is the server-side safety net
    so the PO's own ti_fp_* fields are correct even if that JS never ran -
    which matters here since Purchase Invoice inherits its Faktur Pajak data
    straight from this PO's fields once submitted (see
    events/purchase_invoice.py:carry_tax_invoice_from_po).
    """
    sync_tax_invoice_upload(doc, "Purchase Order", save=False)
    validate_tax_invoice_upload_link(doc, "Purchase Order")
