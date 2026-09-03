import frappe
from frappe.utils import flt


def update_sales_order_payment_status(sales_order_name: str):
    if not sales_order_name:
        return

    so = frappe.db.get_value(
        "Sales Order",
        sales_order_name,
        ["name", "docstatus", "rounded_total", "grand_total"],
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

    # Ambil semua Sales Invoice yang linked ke Sales Order.
    # so_amount = porsi invoice ini yang beneran punya SO ini (bukan grand_total
    # invoice utuh, karena 1 SI towing bisa gabungan beberapa SO).
    invoices = frappe.db.sql("""
        SELECT
            si.name,
            si.docstatus,
            si.outstanding_amount,
            si.grand_total,
            si.status,
            SUM(sii.amount) AS so_amount
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
        so_invoiced = 0
    else:
        total_grand = 0
        total_outstanding = 0

        for inv in invoices:
            so_amount = flt(inv.so_amount)
            total_grand += so_amount
            if flt(inv.grand_total) > 0:
                # Prorate outstanding invoice berdasarkan porsi SO ini
                total_outstanding += so_amount * (flt(inv.outstanding_amount) / flt(inv.grand_total))

        paid_amount = total_grand - total_outstanding
        tolerance = 1.0

        if total_grand > 0 and total_outstanding <= 0:
            payment_status = "Paid"
        elif paid_amount <= tolerance:
            payment_status = "SI Created"
        elif total_outstanding < total_grand:
            payment_status = "Partial Paid"
        else:
            payment_status = "SI Created"

        so_invoiced = total_grand

    # per_billed field standar Frappe biasanya diupdate lewat mekanisme
    # so_detail, tapi invoice towing gak selalu ngisi so_detail (dibuat dari
    # Delivery Order Towing, bukan "Make Sales Invoice" biasa) jadi field
    # itu suka telat/gak update. Hitung ulang langsung dari data invoice
    # yang beneran ke-link, sama seperti logic status di atas.
    so_total = flt(so.rounded_total) or flt(so.grand_total)
    per_billed = min((flt(so_invoiced) / so_total * 100), 100) if so_total > 0 else 0

    frappe.db.set_value(
        "Sales Order",
        sales_order_name,
        {
            "custom_payment_status": payment_status,
            "per_billed": per_billed,
        },
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