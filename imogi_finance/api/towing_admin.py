# ============================================================
# towing_admin.py
# API khusus Administrator untuk operasi maintenance Towing Imogi
# ============================================================

import frappe
from frappe import _

# Doctype yang termasuk ekosistem Towing Imogi
TOWING_DOCTYPES = [
    "Delivery Order Towing",
    "Purchase Order",       # hanya yang custom_delivery_order != NULL
    "Purchase Invoice",     # hanya yang custom_delivery_order != NULL
    "Payment Entry",        # hanya yang referensi ke PI/PO towing
    "Sales Order",          # hanya yang ada DO Towing linked
]

# Tabel Version/Comment/Log Frappe
HISTORY_TABLES = [
    ("tabVersion",       "ref_doctype, docname"),
    ("tabComment",       "reference_doctype, reference_name"),
    ("tabCommunication", "reference_doctype, reference_name"),
    ("tabActivity Log",  "reference_doctype, reference_name"),
]


def _only_administrator():
    if frappe.session.user != "Administrator":
        frappe.throw(_("Akses ditolak. Hanya Administrator yang bisa menjalankan ini."),
                     frappe.PermissionError)


# ─────────────────────────────────────────────────────────────
# PREVIEW: Hitung berapa record riwayat yang akan dihapus
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def preview_towing_history():
    """Hitung riwayat (Version/Comment/Communication/Activity Log) yang akan dihapus."""
    _only_administrator()

    result = {}

    # 1. Delivery Order Towing
    do_names = frappe.db.sql_list("SELECT name FROM `tabDelivery Order Towing`")
    result["Delivery Order Towing"] = _count_history("Delivery Order Towing", do_names)

    # 2. PO Uang Jalan towing
    po_names = []
    if frappe.db.has_column("Purchase Order", "custom_delivery_order"):
        po_names = frappe.db.sql_list(
            "SELECT name FROM `tabPurchase Order` WHERE custom_delivery_order IS NOT NULL AND custom_delivery_order != ''"
        )
    result["Purchase Order (Towing)"] = _count_history("Purchase Order", po_names)

    # 3. PI dari PO towing
    pi_names = []
    if po_names:
        pi_names = frappe.db.sql_list("""
            SELECT DISTINCT pi.name
            FROM `tabPurchase Invoice` pi
            INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
            WHERE pii.purchase_order IN ({})
        """.format(", ".join(["%s"] * len(po_names))), po_names)
    result["Purchase Invoice (Towing)"] = _count_history("Purchase Invoice", pi_names)

    # 4. PE dari PI towing
    pe_names = []
    if pi_names:
        pe_names = frappe.db.sql_list("""
            SELECT DISTINCT pe.name
            FROM `tabPayment Entry` pe
            INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
            WHERE per.reference_doctype IN ('Purchase Invoice', 'Purchase Order')
              AND per.reference_name IN ({})
        """.format(", ".join(["%s"] * len(pi_names))), pi_names)
    result["Payment Entry (Towing)"] = _count_history("Payment Entry", pe_names)

    # 5. SO yang punya DO towing
    so_names = []
    if do_names:
        so_names = frappe.db.sql_list("""
            SELECT DISTINCT sales_order
            FROM `tabDelivery Order Towing`
            WHERE sales_order IS NOT NULL AND sales_order != ''
        """)
    result["Sales Order (Towing)"] = _count_history("Sales Order", so_names)

    total = sum(v.get("total", 0) for v in result.values())
    return {"summary": result, "total": total}


def _count_history(doctype, names):
    if not names:
        return {"total": 0, "version": 0, "comment": 0, "communication": 0, "activity_log": 0}

    placeholders = ", ".join(["%s"] * len(names))
    counts = {}

    counts["version"] = frappe.db.sql(
        f"SELECT COUNT(*) FROM `tabVersion` WHERE ref_doctype = %s AND docname IN ({placeholders})",
        [doctype] + names
    )[0][0]

    counts["comment"] = frappe.db.sql(
        f"SELECT COUNT(*) FROM `tabComment` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
        [doctype] + names
    )[0][0]

    counts["communication"] = frappe.db.sql(
        f"SELECT COUNT(*) FROM `tabCommunication` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
        [doctype] + names
    )[0][0]

    counts["activity_log"] = frappe.db.sql(
        f"SELECT COUNT(*) FROM `tabActivity Log` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
        [doctype] + names
    )[0][0]

    counts["total"] = sum(counts.values())
    return counts


# ─────────────────────────────────────────────────────────────
# EKSEKUSI: Hapus riwayat transaksi towing
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def purge_towing_history(confirm="no"):
    """
    Hapus riwayat (Version, Comment, Communication, Activity Log)
    dari semua dokumen yang terhubung ke Towing Imogi.

    TIDAK menghapus dokumen aslinya, hanya riwayat/log-nya.
    Hanya bisa dijalankan oleh Administrator.
    """
    _only_administrator()

    if confirm != "HAPUS":
        frappe.throw(
            _("Konfirmasi tidak valid. Kirim confirm='HAPUS' untuk melanjutkan."),
            frappe.ValidationError
        )

    deleted = {}

    # 1. Kumpulkan semua nama dokumen towing
    do_names = frappe.db.sql_list("SELECT name FROM `tabDelivery Order Towing`")

    po_names = []
    if frappe.db.has_column("Purchase Order", "custom_delivery_order"):
        po_names = frappe.db.sql_list(
            "SELECT name FROM `tabPurchase Order` WHERE custom_delivery_order IS NOT NULL AND custom_delivery_order != ''"
        )

    pi_names = []
    if po_names:
        pi_names = frappe.db.sql_list("""
            SELECT DISTINCT pi.name
            FROM `tabPurchase Invoice` pi
            INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
            WHERE pii.purchase_order IN ({})
        """.format(", ".join(["%s"] * len(po_names))), po_names)

    pe_names = []
    if pi_names:
        pe_names = frappe.db.sql_list("""
            SELECT DISTINCT pe.name
            FROM `tabPayment Entry` pe
            INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
            WHERE per.reference_doctype IN ('Purchase Invoice', 'Purchase Order')
              AND per.reference_name IN ({})
        """.format(", ".join(["%s"] * len(pi_names))), pi_names)

    so_names = frappe.db.sql_list("""
        SELECT DISTINCT sales_order
        FROM `tabDelivery Order Towing`
        WHERE sales_order IS NOT NULL AND sales_order != ''
    """) if do_names else []

    doc_groups = {
        "Delivery Order Towing": do_names,
        "Purchase Order":        po_names,
        "Purchase Invoice":      pi_names,
        "Payment Entry":         pe_names,
        "Sales Order":           so_names,
    }

    # 2. Hapus riwayat per doctype
    for doctype, names in doc_groups.items():
        if not names:
            deleted[doctype] = 0
            continue

        placeholders = ", ".join(["%s"] * len(names))
        args = [doctype] + names
        count = 0

        # Hitung dulu, lalu hapus — frappe.db.sql DELETE mengembalikan tuple bukan int
        count += frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabVersion` WHERE ref_doctype = %s AND docname IN ({placeholders})",
            args
        )[0][0]
        frappe.db.sql(
            f"DELETE FROM `tabVersion` WHERE ref_doctype = %s AND docname IN ({placeholders})",
            args
        )

        count += frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabComment` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
            args
        )[0][0]
        frappe.db.sql(
            f"DELETE FROM `tabComment` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
            args
        )

        count += frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabCommunication` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
            args
        )[0][0]
        frappe.db.sql(
            f"DELETE FROM `tabCommunication` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
            args
        )

        count += frappe.db.sql(
            f"SELECT COUNT(*) FROM `tabActivity Log` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
            args
        )[0][0]
        frappe.db.sql(
            f"DELETE FROM `tabActivity Log` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
            args
        )

        deleted[doctype] = count

    frappe.db.commit()

    total = sum(deleted.values())
    frappe.log_error(
        f"[Towing Admin] Administrator menghapus {total} riwayat transaksi towing.\nDetail: {deleted}",
        "Towing History Purge"
    )

    return {
        "success": True,
        "total_deleted": total,
        "detail": deleted,
        "message": f"Berhasil menghapus {total} record riwayat dari semua dokumen towing."
    }
