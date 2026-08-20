import frappe
from frappe.utils import flt


def update_purchase_order_payment_status(purchase_order_name: str):
    if not purchase_order_name:
        return

    po = frappe.db.get_value(
        "Purchase Order",
        purchase_order_name,
        ["name", "docstatus"],
        as_dict=True
    )

    if not po:
        return

    # Kalau PO cancel
    if po.docstatus == 2:
        frappe.db.set_value(
            "Purchase Order",
            purchase_order_name,
            "custom_payment_status",
            "Cancelled",
            update_modified=False
        )
        return

    # Ambil semua Purchase Invoice yang linked ke Purchase Order
    invoices = frappe.db.sql("""
        SELECT
            pi.name,
            pi.docstatus,
            pi.outstanding_amount,
            pi.grand_total,
            pi.status
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabPurchase Invoice Item` pii
            ON pii.parent = pi.name
        WHERE pii.purchase_order = %s
          AND pi.docstatus < 2
        GROUP BY pi.name
    """, (purchase_order_name,), as_dict=True)

    # Belum ada invoice
    if not invoices:
        payment_status = "Draft"
    else:
        total_grand = 0
        total_outstanding = 0

        for inv in invoices:
            total_grand += flt(inv.grand_total)
            total_outstanding += flt(inv.outstanding_amount)

        paid_amount = total_grand - total_outstanding
        tolerance = 1.0

        if total_grand > 0 and total_outstanding <= 0:
            payment_status = "Paid"
        elif paid_amount <= tolerance:
            payment_status = "PI Created"
        elif total_outstanding < total_grand:
            payment_status = "Partial Paid"
        else:
            payment_status = "PI Created"

    frappe.db.set_value(
        "Purchase Order",
        purchase_order_name,
        "custom_payment_status",
        payment_status,
        update_modified=False
    )


def update_from_purchase_order(doc, method=None):
    update_purchase_order_payment_status(doc.name)


def update_from_purchase_invoice(doc, method=None):
    purchase_orders = set()

    for item in doc.items:
        if item.purchase_order:
            purchase_orders.add(item.purchase_order)

    for po_name in purchase_orders:
        update_purchase_order_payment_status(po_name)


def update_from_payment_entry(doc, method=None):
    purchase_invoices = set()

    for ref in doc.references:
        if ref.reference_doctype == "Purchase Invoice" and ref.reference_name:
            purchase_invoices.add(ref.reference_name)

    if not purchase_invoices:
        return

    purchase_orders = set()

    for invoice_name in purchase_invoices:
        rows = frappe.db.sql("""
            SELECT DISTINCT purchase_order
            FROM `tabPurchase Invoice Item`
            WHERE parent = %s
              AND IFNULL(purchase_order, '') != ''
        """, (invoice_name,), as_dict=True)

        for row in rows:
            purchase_orders.add(row.purchase_order)

    for po_name in purchase_orders:
        update_purchase_order_payment_status(po_name)
