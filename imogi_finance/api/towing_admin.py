# ============================================================
# towing_admin.py
# API khusus Administrator untuk operasi maintenance Towing Imogi
# ============================================================

import frappe
from frappe import _


def _only_administrator():
    if frappe.session.user != "Administrator":
        frappe.throw(_("Akses ditolak. Hanya Administrator yang bisa menjalankan ini."),
                     frappe.PermissionError)


def _collect_towing_names():
    """Kumpulkan semua nama dokumen transaksi towing (urutan dari bawah ke atas)."""
    do_names = frappe.db.sql_list("SELECT name FROM `tabDelivery Order Towing`")

    po_names = []
    if frappe.db.has_column("Purchase Order", "custom_delivery_order"):
        po_names = frappe.db.sql_list(
            "SELECT name FROM `tabPurchase Order` "
            "WHERE custom_delivery_order IS NOT NULL AND custom_delivery_order != ''"
        )

    pi_names = []
    if po_names:
        ph = ", ".join(["%s"] * len(po_names))
        pi_names = frappe.db.sql_list(f"""
            SELECT DISTINCT pi.name
            FROM `tabPurchase Invoice` pi
            INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
            WHERE pii.purchase_order IN ({ph})
        """, po_names)

    pe_names = []
    if pi_names:
        ph = ", ".join(["%s"] * len(pi_names))
        pe_names = frappe.db.sql_list(f"""
            SELECT DISTINCT pe.name
            FROM `tabPayment Entry` pe
            INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
            WHERE per.reference_doctype IN ('Purchase Invoice', 'Purchase Order')
              AND per.reference_name IN ({ph})
        """, pi_names)

    so_names = frappe.db.sql_list("""
        SELECT DISTINCT sales_order FROM `tabDelivery Order Towing`
        WHERE sales_order IS NOT NULL AND sales_order != ''
    """) if do_names else []

    # Sales Invoice yang ter-link ke SO towing
    si_names = []
    if so_names:
        ph = ", ".join(["%s"] * len(so_names))
        si_names = frappe.db.sql_list(f"""
            SELECT DISTINCT si.name FROM `tabSales Invoice` si
            INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
            WHERE sii.sales_order IN ({ph})
        """, so_names)

    return {
        "Payment Entry":         pe_names,
        "Purchase Invoice":      pi_names,
        "Purchase Order":        po_names,
        "Sales Invoice":         si_names,
        "Delivery Order Towing": do_names,
        "Sales Order":           so_names,
    }


# ─────────────────────────────────────────────────────────────
# PREVIEW: Hitung dokumen yang akan dihapus
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def preview_towing_data():
    """Hitung semua dokumen towing yang akan dihapus."""
    _only_administrator()

    groups = _collect_towing_names()
    summary = {}
    total = 0
    for doctype, names in groups.items():
        summary[doctype] = len(names)
        total += len(names)

    return {"summary": summary, "total": total}


# ─────────────────────────────────────────────────────────────
# EKSEKUSI: Hapus semua dokumen transaksi towing
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def purge_towing_data(confirm="no"):
    """
    Hapus semua dokumen transaksi towing (PE → PI → PO → SI → DO → SO).
    Dokumen submitted di-cancel dulu sebelum dihapus.
    Hanya bisa dijalankan oleh Administrator.
    """
    _only_administrator()

    if confirm != "HAPUS":
        frappe.throw(
            _("Konfirmasi tidak valid. Ketik 'HAPUS' untuk melanjutkan."),
            frappe.ValidationError
        )

    groups = _collect_towing_names()
    deleted  = {}
    failed   = {}

    # Urutan hapus: dari dokumen paling bawah ke atas
    delete_order = [
        "Payment Entry",
        "Purchase Invoice",
        "Purchase Order",
        "Sales Invoice",
        "Delivery Order Towing",
        "Sales Order",
    ]

    for doctype in delete_order:
        names = groups.get(doctype, [])
        ok, fail = _force_delete_docs(doctype, names)
        deleted[doctype] = ok
        if fail:
            failed[doctype] = fail

    frappe.db.commit()

    total = sum(deleted.values())
    frappe.log_error(
        f"[Towing Admin] Administrator menghapus {total} dokumen towing.\n"
        f"Berhasil: {deleted}\nGagal: {failed}",
        "Towing Data Purge"
    )

    return {
        "success": True,
        "total_deleted": total,
        "detail": deleted,
        "failed": failed,
    }


def _force_delete_docs(doctype, names):
    """Cancel (jika submitted) lalu delete. Return (ok_count, failed_list)."""
    ok = 0
    fail = []

    for name in names:
        try:
            docstatus = frappe.db.get_value(doctype, name, "docstatus")
            if docstatus is None:
                continue  # sudah tidak ada

            if docstatus == 1:
                # Submitted → cancel dulu
                doc = frappe.get_doc(doctype, name)
                doc.flags.ignore_permissions   = True
                doc.flags.ignore_links         = True
                doc.flags.skip_cancel_check    = True
                doc.flags.ignore_on_update     = True
                doc.cancel()
                frappe.db.commit()

            # Hapus semua riwayat dulu agar tidak ada link error
            _delete_doc_history(doctype, name)

            frappe.delete_doc(
                doctype, name,
                ignore_permissions=True,
                force=True,
                ignore_on_trash=True,
            )
            frappe.db.commit()
            ok += 1

        except Exception as e:
            frappe.db.rollback()
            fail.append({"name": name, "error": str(e)})
            frappe.log_error(
                f"Gagal hapus {doctype} {name}: {e}",
                "Towing Purge Error"
            )

    return ok, fail


def _delete_doc_history(doctype, name):
    """Hapus Version/Comment/Communication/Activity Log untuk satu dokumen."""
    frappe.db.sql(
        "DELETE FROM `tabVersion` WHERE ref_doctype = %s AND docname = %s",
        (doctype, name)
    )
    frappe.db.sql(
        "DELETE FROM `tabComment` WHERE reference_doctype = %s AND reference_name = %s",
        (doctype, name)
    )
    frappe.db.sql(
        "DELETE FROM `tabCommunication` WHERE reference_doctype = %s AND reference_name = %s",
        (doctype, name)
    )
    frappe.db.sql(
        "DELETE FROM `tabActivity Log` WHERE reference_doctype = %s AND reference_name = %s",
        (doctype, name)
    )
