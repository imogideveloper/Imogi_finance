"""
Sales Order Event Handlers for IMOGI Finance

Handles outstanding amount computation for Sales Orders.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt


def compute_outstanding_amount(doc, method=None):
	"""Outstanding = Grand Total SO − total Grand Total Sales Invoice (submitted)."""
	if doc.docstatus == 2:
		doc.outstanding_amount = 0
		return

	from imogi_finance.sales_order_payment_status import get_sales_order_financial_summary

	if doc.name and frappe.db.exists("Sales Order", doc.name):
		summary = get_sales_order_financial_summary(doc.name, so_doc=doc)
	else:
		so_total = flt(doc.rounded_total or doc.grand_total)
		summary = {"total_remaining": so_total}

	doc.outstanding_amount = max(flt(summary["total_remaining"]), 0)


def update_outstanding_on_payment(sales_order_name: str):
    """
    Update outstanding amount when payment is made.
    Called from Payment Entry hooks.
    """
    if not sales_order_name:
        return

    doc = frappe.get_doc("Sales Order", sales_order_name)
    grand_total = doc.rounded_total or doc.grand_total or 0
    advance_paid = doc.advance_paid or 0
    outstanding = max(grand_total - advance_paid, 0)

    frappe.db.set_value("Sales Order", sales_order_name, "outstanding_amount", outstanding, update_modified=False)


def update_sales_order_outstanding_from_payment(doc, method=None):
    """
    Update Sales Order outstanding amount from Payment Entry.
    Called on Payment Entry submit/cancel.
    """
    if not doc.get("references"):
        return

    # Find all Sales Order references in this Payment Entry
    sales_orders = set()
    for ref in doc.references:
        if ref.reference_doctype == "Sales Order" and ref.reference_name:
            sales_orders.add(ref.reference_name)

    # Update outstanding for each Sales Order
    for so_name in sales_orders:
        update_outstanding_on_payment(so_name)
