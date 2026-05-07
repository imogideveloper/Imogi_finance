"""
File  : imogi_finance/events/purchase_order_towing.py
Fungsi: Hook after_insert Purchase Order
        Otomatis isi Detail Kendaraan Towing saat PO baru dibuat
        (menangani kasus PO dibuat setelah DO sudah di-submit)
"""

import frappe


def after_insert(doc, method=None):
    """Auto-populate Detail Kendaraan Towing jika PO linked ke Delivery Order Towing."""
    do_name = doc.get("custom_delivery_order")
    if not do_name:
        return
    try:
        so_name = frappe.db.get_value("Delivery Order Towing", do_name, "sales_order")
        if not so_name:
            return
        rows = frappe.db.sql(
            """
            SELECT so_item_code, nomor_rangka, nomor_polisi, tipe_model, nomor_mesin
            FROM `tabSO Towing Kendaraan`
            WHERE parent = %s AND parenttype = 'Sales Order'
            ORDER BY idx ASC
            """,
            so_name,
            as_dict=True,
        )
        if not rows:
            return
        linked = frappe.get_doc("Purchase Order", doc.name)
        linked.set("custom_towing_kendaraan", [])
        for row in rows:
            linked.append("custom_towing_kendaraan", {
                "so_item_code": row.get("so_item_code"),
                "nomor_rangka": row.get("nomor_rangka"),
                "nomor_polisi": row.get("nomor_polisi"),
                "tipe_model":   row.get("tipe_model"),
                "nomor_mesin":  row.get("nomor_mesin"),
            })
        linked.save(ignore_permissions=True)
        frappe.logger().info(
            f"[Towing] PO {doc.name}: {len(rows)} baris diisi dari SO {so_name}"
        )
    except Exception as exc:
        frappe.log_error(
            f"[Towing] Error PO after_insert {doc.name}: {exc}",
            "Auto Populate Towing",
        )
