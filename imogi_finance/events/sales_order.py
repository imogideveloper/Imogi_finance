"""
Sales Order Event Handlers for IMOGI Finance

Handles outstanding amount computation for Sales Orders.
"""

from __future__ import annotations

import frappe


def compute_outstanding_amount(doc, method=None):
    """
    Compute outstanding amount for Sales Order.
    Outstanding = Grand Total (or Rounded Total) - Advance Paid
    """
    grand_total = doc.rounded_total or doc.grand_total or 0
    advance_paid = doc.advance_paid or 0
    outstanding = grand_total - advance_paid

    # Set the computed value
    doc.outstanding_amount = max(outstanding, 0)


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
