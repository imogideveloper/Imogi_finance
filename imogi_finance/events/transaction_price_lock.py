# =============================================================================
# transaction_price_lock.py
# Lokasi: imogi_finance/imogi_finance/events/transaction_price_lock.py
# =============================================================================
# Fungsi: Server-side guard untuk lock field harga di SO, SI, PO, PI, PE.
# Yang boleh edit: Administrator + Finance Manager.
#
# Behavior:
#   • New doc            → tidak ada lock (boleh isi rate manual saat create)
#   • Saved/Submitted    → field harga TIDAK BISA diubah
#   • Bypass             → Administrator & Finance Manager
#
# Note: Cek dilakukan dengan compare nilai DB vs nilai doc saat validate.
#       Kalau ada perbedaan di field yang dilock, throw error.
# =============================================================================

import frappe
from frappe import _


UNLOCK_ROLES = ["Administrator", "Finance Manager"]


# ─────────────────────────────────────────────────────────────────────────────
# Field config per doctype
# ─────────────────────────────────────────────────────────────────────────────

# Header fields (di doc utama)
HEADER_LOCKED_FIELDS = {
    "Sales Order":      ["selling_price_list"],
    "Sales Invoice":    ["selling_price_list"],
    "Purchase Order":   ["buying_price_list"],
    "Purchase Invoice": ["buying_price_list"],
    "Payment Entry":    ["paid_amount", "received_amount"],
}

# Item child table fields (di items child table)
ITEM_LOCKED_FIELDS = [
    "rate",
    "price_list_rate",
    "discount_amount",
    "discount_percentage",
    "amount",
    "base_rate",
    "base_amount",
    "base_price_list_rate",
]

# Mapping doctype → child doctype name (untuk items)
ITEM_CHILD_DOCTYPE = {
    "Sales Order":      "Sales Order Item",
    "Sales Invoice":    "Sales Invoice Item",
    "Purchase Order":   "Purchase Order Item",
    "Purchase Invoice": "Purchase Invoice Item",
}

# Field labels untuk error message
FIELD_LABELS = {
    "rate": "Rate",
    "price_list_rate": "Price List Rate",
    "discount_amount": "Discount Amount",
    "discount_percentage": "Discount %",
    "amount": "Amount",
    "base_rate": "Base Rate",
    "base_amount": "Base Amount",
    "base_price_list_rate": "Base Price List Rate",
    "selling_price_list": "Selling Price List",
    "buying_price_list": "Buying Price List",
    "paid_amount": "Paid Amount",
    "received_amount": "Received Amount",
    "allocated_amount": "Allocated Amount",
}


# ─────────────────────────────────────────────────────────────────────────────
# Main hook
# ─────────────────────────────────────────────────────────────────────────────

def validate_no_price_change(doc, method=None):
    """
    Hook: validate pada SO/SI/PO/PI/PE.
    Block perubahan field harga (kecuali Admin/Finance Manager).
    """
    # New doc → izinkan (saat create boleh input rate manual)
    if doc.is_new():
        return

    # Bypass untuk Administrator atau Finance Manager
    if _user_can_unlock():
        return

    doctype = doc.doctype
    changes = []

    # ─── Cek HEADER fields ───────────────────────────────────────
    header_fields = HEADER_LOCKED_FIELDS.get(doctype, [])
    if header_fields:
        db_header = frappe.db.get_value(doctype, doc.name, header_fields, as_dict=True)
        if db_header:
            for field in header_fields:
                old_val = db_header.get(field)
                new_val = doc.get(field)
                if _value_changed(old_val, new_val):
                    changes.append({
                        "type": "header",
                        "field": field,
                        "old": old_val,
                        "new": new_val,
                        "row": None,
                    })

    # ─── Cek ITEMS child table (skip untuk PE karena beda struktur) ───
    if doctype != "Payment Entry":
        child_doctype = ITEM_CHILD_DOCTYPE.get(doctype)
        if child_doctype:
            for item_row in (doc.items or []):
                if not item_row.name:
                    continue  # row baru, skip

                db_item = frappe.db.get_value(
                    child_doctype, item_row.name, ITEM_LOCKED_FIELDS, as_dict=True
                )
                if not db_item:
                    continue  # row baru di server, skip

                for field in ITEM_LOCKED_FIELDS:
                    old_val = db_item.get(field)
                    new_val = item_row.get(field)
                    if _value_changed(old_val, new_val):
                        changes.append({
                            "type": "item",
                            "field": field,
                            "old": old_val,
                            "new": new_val,
                            "row": item_row.idx,
                            "item_code": item_row.get("item_code", ""),
                        })

    # ─── Khusus Payment Entry: cek references (allocated_amount) ───
    if doctype == "Payment Entry":
        for ref in (doc.references or []):
            if not ref.name:
                continue

            db_alloc = frappe.db.get_value(
                "Payment Entry Reference", ref.name, "allocated_amount"
            )
            if db_alloc is None:
                continue

            new_alloc = ref.get("allocated_amount")
            if _value_changed(db_alloc, new_alloc):
                changes.append({
                    "type": "reference",
                    "field": "allocated_amount",
                    "old": db_alloc,
                    "new": new_alloc,
                    "row": ref.idx,
                    "reference": ref.get("reference_name", ""),
                })

    # ─── Kalau ada perubahan, throw ──────────────────────────────
    if changes:
        _throw_lock_error(doctype, changes)


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _user_can_unlock() -> bool:
    """Cek apakah user boleh unlock field harga."""
    if frappe.session.user == "Administrator":
        return True
    user_roles = set(frappe.get_roles(frappe.session.user))
    return any(role in user_roles for role in UNLOCK_ROLES)


def _value_changed(old_val, new_val) -> bool:
    """Cek apakah nilai berubah dengan toleransi floating point."""
    # Normalisasi None vs 0 vs ""
    if old_val in (None, "") and new_val in (None, "", 0, 0.0):
        return False
    if old_val in (None, "", 0, 0.0) and new_val in (None, ""):
        return False

    # Numeric comparison dengan toleransi
    try:
        old_num = float(old_val or 0)
        new_num = float(new_val or 0)
        return abs(old_num - new_num) > 0.0001
    except (TypeError, ValueError):
        # String comparison
        old_str = str(old_val or "").strip()
        new_str = str(new_val or "").strip()
        return old_str != new_str


def _throw_lock_error(doctype: str, changes: list):
    """Throw error dengan detail field yang berubah."""
    msg_lines = [
        _("❌ Tidak bisa mengubah field harga di {0} yang sudah di-save.").format(doctype),
        "",
        _("Perubahan yang ditolak:"),
        "",
    ]

    for ch in changes:
        label = FIELD_LABELS.get(ch["field"], ch["field"])
        old_v = ch.get("old", "")
        new_v = ch.get("new", "")

        if ch["type"] == "header":
            msg_lines.append(
                f"&nbsp;&nbsp;&nbsp;&nbsp;• <b>{label}</b>: "
                f"<code>{old_v}</code> → <code>{new_v}</code>"
            )
        elif ch["type"] == "item":
            item_code = ch.get("item_code", "")
            msg_lines.append(
                f"&nbsp;&nbsp;&nbsp;&nbsp;• Row {ch['row']} ({item_code}) — <b>{label}</b>: "
                f"<code>{old_v}</code> → <code>{new_v}</code>"
            )
        elif ch["type"] == "reference":
            ref_name = ch.get("reference", "")
            msg_lines.append(
                f"&nbsp;&nbsp;&nbsp;&nbsp;• Row {ch['row']} ({ref_name}) — <b>{label}</b>: "
                f"<code>{old_v}</code> → <code>{new_v}</code>"
            )

    msg_lines.append("")
    msg_lines.append(
        _("Hanya <b>Administrator</b> atau <b>Finance Manager</b> yang bisa mengubah harga. "
          "Untuk mengubah harga, hubungi Finance Manager atau buat dokumen baru.")
    )

    frappe.throw("<br>".join(msg_lines), title=_("Field Harga Terkunci"))