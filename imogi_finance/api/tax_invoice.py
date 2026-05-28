from __future__ import annotations

import frappe
from frappe import _
from imogi_finance import roles

from imogi_finance.tax_invoice_ocr import (
    get_tax_invoice_upload_context,
    get_tax_invoice_ocr_monitoring,
    run_ocr,
    sync_tax_invoice_upload,
    verify_tax_invoice,
)


@frappe.whitelist()
def run_ocr_for_upload(upload_name: str):
    return run_ocr(upload_name, "Tax Invoice OCR Upload")


@frappe.whitelist()
def verify_purchase_invoice_tax_invoice(pi_name: str, force: bool = False):
    doc = frappe.get_doc("Purchase Invoice", pi_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER))
    return verify_tax_invoice(doc, doctype="Purchase Invoice", force=bool(force))


@frappe.whitelist()
def verify_expense_request_tax_invoice(er_name: str, force: bool = False):
    doc = frappe.get_doc("Expense Request", er_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
    return verify_tax_invoice(doc, doctype="Expense Request", force=bool(force))


@frappe.whitelist()
def verify_sales_invoice_tax_invoice(si_name: str, force: bool = False):
    doc = frappe.get_doc("Sales Invoice", si_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER))
    return verify_tax_invoice(doc, doctype="Sales Invoice", force=bool(force))


@frappe.whitelist()
def verify_tax_invoice_upload(upload_name: str, force: bool = False):
    doc = frappe.get_doc("Tax Invoice OCR Upload", upload_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER, roles.TAX_REVIEWER))
    return verify_tax_invoice(doc, doctype="Tax Invoice OCR Upload", force=bool(force))


@frappe.whitelist()
def monitor_tax_invoice_ocr(docname: str, doctype: str):
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER, roles.TAX_REVIEWER))
    return get_tax_invoice_ocr_monitoring(docname, doctype)


@frappe.whitelist()
def get_tax_invoice_upload_context_api(target_doctype: str, target_name: str | None = None):
    return get_tax_invoice_upload_context(target_doctype=target_doctype, target_name=target_name)


@frappe.whitelist()
def apply_tax_invoice_upload(target_doctype: str, target_name: str, upload_name: str | None = None):
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER))
    doc = frappe.get_doc(target_doctype, target_name)
    return sync_tax_invoice_upload(doc, target_doctype, upload_name)


@frappe.whitelist()
def create_purchase_invoice_from_ocr(upload_name: str, supplier: str, item_code: str, qty: float = 1.0, scenario: str = "expense"):
    """
    Create Purchase Invoice directly from Tax Invoice OCR Upload.
    
    Scenarios:
    - "asset"     : Fixed Asset purchase (is_fixed_asset=1)
    - "inventory" : Stock Item purchase (is_stock_item=1)  
    - "expense"   : Regular expense (default)
    """
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.ACCOUNTS_USER, roles.SYSTEM_MANAGER))

    ocr = frappe.get_doc("Tax Invoice OCR Upload", upload_name)

    if not ocr.dpp:
        frappe.throw(_("DPP is required to create Purchase Invoice. Please complete OCR verification first."))

    if not supplier:
        frappe.throw(_("Supplier is required."))

    if not item_code:
        frappe.throw(_("Item Code is required."))

    # Validate item vs scenario
    item = frappe.get_doc("Item", item_code)
    if scenario == "asset" and not item.is_fixed_asset:
        frappe.throw(_(f"Item '{item_code}' is not a Fixed Asset. Please check 'Is Fixed Asset' on the item, or choose a different scenario."))
    if scenario == "inventory" and not item.is_stock_item:
        frappe.throw(_(f"Item '{item_code}' is not a Stock Item. Please enable 'Maintain Stock' on the item, or choose a different scenario."))

    # Build PI document
    pi = frappe.new_doc("Purchase Invoice")
    pi.company = ocr.company or frappe.defaults.get_user_default("Company")
    pi.supplier = supplier
    pi.bill_no = ocr.fp_no
    pi.bill_date = ocr.fp_date
    pi.ti_tax_invoice_upload = upload_name

    # PPN Template
    if ocr.recommended_ppn_template:
        pi.taxes_and_charges = ocr.recommended_ppn_template

    # Items
    pi_item = pi.append("items", {
        "item_code": item_code,
        "qty": float(qty),
        "rate": float(ocr.dpp),
    })

    # Scenario-specific fields
    if scenario == "asset":
        pi_item.is_fixed_asset = 1
        if item.asset_category:
            pi_item.asset_category = item.asset_category
        pi_item.asset_location = frappe.db.get_value("Location", {}, "name") or None

    # Insert (draft)
    pi.flags.ignore_permissions = False
    pi.insert()

    # Link OCR back to PI
    frappe.db.set_value("Tax Invoice OCR Upload", upload_name, "submit_on", frappe.utils.now ())

    return {
        "purchase_invoice": pi.name,
        "message": f"Purchase Invoice {pi.name} created successfully from OCR {upload_name}",
        "scenario": scenario,
    }
