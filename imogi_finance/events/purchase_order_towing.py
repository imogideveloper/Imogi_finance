"""
File  : imogi_finance/events/purchase_order_towing.py
Fungsi: Hook after_insert Purchase Order
        Otomatis isi Detail Kendaraan Towing saat PO baru dibuat,
        diambil langsung dari Delivery Order Towing (bukan dari Sales Order).
"""

import frappe
from frappe.utils import now_datetime


def after_insert(doc, method=None):
    """Auto-populate Detail Kendaraan Towing dari DO jika PO linked ke Delivery Order Towing."""
    do_name = doc.get("custom_delivery_order")
    if not do_name:
        return

    # Tunggu sebentar agar populate_towing_to_linked_docs dari on_submit DO selesai duluan
    # Jika sudah ada rows (diisi oleh populate_towing_to_linked_docs), skip
    existing = frappe.db.count(
        "tabPurchase Order Detail Kendaraan",
        {"parent": doc.name, "parenttype": "Purchase Order"}
    ) if frappe.db.table_exists("tabPurchase Order Detail Kendaraan") else 0

    if existing:
        return  # Sudah diisi oleh populate_towing_to_linked_docs, tidak perlu isi lagi

    try:
        do = frappe.get_doc("Delivery Order Towing", do_name)

        item_code = frappe.db.get_value(
            "SO Towing Kendaraan",
            {"delivery_order": do_name},
            "so_item_code"
        )

        linked = frappe.get_doc("Purchase Order", doc.name)
        linked.set("custom_towing_kendaraan", [])
        linked.append("custom_towing_kendaraan", {
            "so_item_code": item_code or "",
            "nomor_rangka": do.nomor_rangka or "",
            "nomor_polisi": do.nomor_polisi or "",
            "tipe_model"  : do.tipe_kendaraan or "",
            "nomor_mesin" : do.nomor_mesin or "",
        })
        linked.flags.ignore_version   = True
        linked.flags.ignore_timestamp = True
        linked.save(ignore_permissions=True)
        frappe.logger().info(
            f"[Towing] PO {doc.name}: 1 baris diisi dari DO {do_name}"
        )
    except Exception as exc:
        frappe.log_error(
            f"[Towing] Error PO after_insert {doc.name}: {exc}",
            "Auto Populate Towing",
        )