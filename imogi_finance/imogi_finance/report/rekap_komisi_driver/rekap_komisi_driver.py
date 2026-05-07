import frappe
from frappe import _
from frappe.utils import flt

from imogi_finance.doctype.towing_commission_rate.towing_commission_rate import (
    calc_komisi_amount,
    lookup_towing_commission_rate,
)


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {
            "fieldname": "delivery_order_towing",
            "label": _("No. DO"),
            "fieldtype": "Link",
            "options": "Delivery Order Towing",
            "width": 160,
        },
        {
            "fieldname": "tanggal_do",
            "label": _("Tanggal"),
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "driver_nama",
            "label": _("Driver"),
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "fieldname": "customer",
            "label": _("Customer"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 130,
        },
        {
            "fieldname": "lokasi_pickup",
            "label": _("Lokasi Pick Up"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "lokasi_tujuan",
            "label": _("Lokasi Tujuan"),
            "fieldtype": "Data",
            "width": 150,
        },
        {
            "fieldname": "tipe_komisi",
            "label": _("Tipe Komisi"),
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "harga_jasa",
            "label": _("Harga Jasa"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "rate_value",
            "label": _("Rate Komisi"),
            "fieldtype": "Data",
            "width": 100,
            "align": "right",
        },
        {
            "fieldname": "komisi",
            "label": _("Komisi"),
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "fieldname": "status_komisi",
            "label": _("Status"),
            "fieldtype": "Data",
            "width": 90,
        },
        {
            "fieldname": "payment_ref",
            "label": _("Payment Ref"),
            "fieldtype": "Data",
            "width": 140,
        },
        # Hidden helper columns - tetap didefinisikan agar tersedia di JS
        {
            "fieldname": "driver",
            "label": _("Driver ID"),
            "fieldtype": "Data",
            "hidden": 1,
            "width": 100,
        },
        {
            "fieldname": "supplier",
            "label": _("Supplier"),
            "fieldtype": "Data",
            "hidden": 1,
            "width": 100,
        },
        {
            "fieldname": "so_item_code",
            "label": _("Item Rute"),
            "fieldtype": "Data",
            "hidden": 1,
            "width": 100,
        },
    ]


def get_data(filters):
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    driver_filter = filters.get("driver")
    status_filter = filters.get("status_komisi")

    # Semua status yang sudah selesai operasional berhak dapat komisi
    ELIGIBLE_STATUSES = ("Delivered", "Awaiting Dokument", "Done")
    status_in = ", ".join(f"'{s}'" for s in ELIGIBLE_STATUSES)
    conditions = ["dot.docstatus != 2", f"dot.status IN ({status_in})"]
    params = {}

    if from_date:
        conditions.append("dot.tanggal_do >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conditions.append("dot.tanggal_do <= %(to_date)s")
        params["to_date"] = to_date
    if driver_filter:
        conditions.append("dot.driver = %(driver)s")
        params["driver"] = driver_filter

    where_clause = " AND ".join(conditions)

    dos = frappe.db.sql(
        f"""
        SELECT
            dot.name          AS delivery_order_towing,
            dot.tanggal_do,
            dot.driver,
            dot.driver_nama,
            dot.customer,
            dot.lokasi_pickup,
            dot.lokasi_tujuan,
            dot.harga_jasa,
            drv.custom_supplier AS supplier
        FROM `tabDelivery Order Towing` dot
        LEFT JOIN `tabDriver` drv ON drv.name = dot.driver
        WHERE {where_clause}
        ORDER BY dot.driver, dot.tanggal_do ASC, dot.name ASC
        """,
        params,
        as_dict=True,
    )

    # Cek DO mana yang sudah dibayar via Driver Commission
    paid_dos = _get_paid_do_map()

    rows = []
    for do in dos:
        # Ambil item rute dari SO Towing Kendaraan
        item_code = frappe.db.get_value(
            "SO Towing Kendaraan", {"delivery_order": do.delivery_order_towing}, "so_item_code"
        )

        # Lookup rate
        rate = lookup_towing_commission_rate(item_code, do.tanggal_do) if item_code else None

        komisi = 0.0
        tipe_komisi = ""
        rate_value_display = "—"

        if rate:
            komisi = flt(calc_komisi_amount(rate["rate_type"], rate["rate_value"], do.harga_jasa))
            tipe_komisi = rate["rate_type"]
            if rate["rate_type"] == "Percent":
                rate_value_display = f"{flt(rate['rate_value']):.0f}%"
            else:
                rate_value_display = frappe.format_value(flt(rate["rate_value"]), {"fieldtype": "Currency"})

        # Status komisi
        payment_info = paid_dos.get(do.delivery_order_towing)
        if payment_info:
            status_komisi = "Paid"
            payment_ref = payment_info.get("payment_entry") or payment_info.get("dc_name", "")
        else:
            status_komisi = "Unpaid"
            payment_ref = "—"

        # Filter status
        if status_filter and status_filter != "Semua" and status_komisi != status_filter:
            continue

        rows.append({
            "delivery_order_towing": do.delivery_order_towing or "",
            "tanggal_do": do.tanggal_do,
            "driver_nama": do.driver_nama or do.driver or "",
            "customer": do.customer or "",
            "lokasi_pickup": do.lokasi_pickup or "",
            "lokasi_tujuan": do.lokasi_tujuan or "",
            "tipe_komisi": tipe_komisi or "",
            "harga_jasa": flt(do.harga_jasa),
            "rate_value": rate_value_display,
            "komisi": komisi,
            "status_komisi": status_komisi,
            "payment_ref": payment_ref,
            "driver": do.driver or "",
            "supplier": do.supplier or "",
            "so_item_code": item_code or "",
        })

    return rows


def _get_paid_do_map():
    """Return dict: {do_name: {dc_name, payment_entry}} untuk DO yang sudah ada di Driver Commission."""
    rows = frappe.db.sql(
        """
        SELECT
            dci.delivery_order_towing,
            dc.name   AS dc_name,
            dc.payment_entry,
            dc.status
        FROM `tabDriver Commission Item` dci
        INNER JOIN `tabDriver Commission` dc ON dci.parent = dc.name
        WHERE dc.docstatus != 2
          AND COALESCE(dc.status, '') != 'Cancelled'
          AND IFNULL(dci.delivery_order_towing, '') != ''
        """,
        as_dict=True,
    )
    result = {}
    for r in rows:
        result[r.delivery_order_towing] = {
            "dc_name": r.dc_name,
            "payment_entry": r.payment_entry,
            "status": r.status,
        }
    return result