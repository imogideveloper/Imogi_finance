import frappe
from frappe.utils import flt


def update_sales_order_payment_status(sales_order_name: str):
    if not sales_order_name:
        return

    so = frappe.db.get_value(
        "Sales Order",
        sales_order_name,
        ["name", "docstatus"],
        as_dict=True
    )

    if not so:
        return

    # Kalau SO cancel
    if so.docstatus == 2:
        frappe.db.set_value(
            "Sales Order",
            sales_order_name,
            "custom_payment_status",
            "Cancelled",
            update_modified=False
        )
        return

    # Ambil semua Sales Invoice yang linked ke Sales Order
    invoices = frappe.db.sql("""
        SELECT
            si.name,
            si.docstatus,
            si.outstanding_amount,
            si.grand_total,
            si.status
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Invoice Item` sii
            ON sii.parent = si.name
        WHERE sii.sales_order = %s
          AND si.docstatus < 2
        GROUP BY si.name
    """, (sales_order_name,), as_dict=True)

    # Belum ada invoice
    if not invoices:
        payment_status = "Draft"
    else:
        total_grand = 0
        total_outstanding = 0

        for inv in invoices:
            total_grand += flt(inv.grand_total)
            total_outstanding += flt(inv.outstanding_amount)

        if total_grand > 0 and total_outstanding <= 0:
            payment_status = "Paid"
        elif total_outstanding < total_grand:
            payment_status = "Partial Paid"
        else:
            payment_status = "SI Created"

    frappe.db.set_value(
        "Sales Order",
        sales_order_name,
        "custom_payment_status",
        payment_status,
        update_modified=False
    )


def update_from_sales_order(doc, method=None):
    update_sales_order_payment_status(doc.name)


def update_from_sales_invoice(doc, method=None):
    sales_orders = set()

    for item in doc.items:
        if item.sales_order:
            sales_orders.add(item.sales_order)

    for so_name in sales_orders:
        update_sales_order_payment_status(so_name)


def update_from_payment_entry(doc, method=None):
    sales_invoices = set()

    for ref in doc.references:
        if ref.reference_doctype == "Sales Invoice" and ref.reference_name:
            sales_invoices.add(ref.reference_name)

    if not sales_invoices:
        return

    sales_orders = set()

    for invoice_name in sales_invoices:
        rows = frappe.db.sql("""
            SELECT DISTINCT sales_order
            FROM `tabSales Invoice Item`
            WHERE parent = %s
              AND IFNULL(sales_order, '') != ''
        """, (invoice_name,), as_dict=True)

        for row in rows:
            sales_orders.add(row.sales_order)

    for so_name in sales_orders:
        update_sales_order_payment_status(so_name)