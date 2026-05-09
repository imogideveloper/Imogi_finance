# =============================================================================
# item_price_lock.py
# Lokasi: imogi_finance/imogi_finance/events/item_price_lock.py
# =============================================================================
# Fungsi: Server-side guard untuk Item Price.
# Yang boleh edit: Administrator + Finance Manager.
# =============================================================================

import frappe
from frappe import _


UNLOCK_ROLES = ["Administrator", "Finance Manager"]

LOCKED_FIELDS = [
    "price_list_rate",   # Rate
    "price_list",        # Price List
]


def validate_no_price_change(doc, method=None):
    """Block perubahan field harga di Item Price (kecuali Admin/Finance Manager)."""
    if doc.is_new():
        return

    # Bypass untuk Administrator atau Finance Manager
    if _user_can_unlock():
        return

    db_values = frappe.db.get_value(
        "Item Price", doc.name, LOCKED_FIELDS, as_dict=True
    )
    if not db_values:
        return

    changed_fields = []
    for field in LOCKED_FIELDS:
        old_value = db_values.get(field)
        new_value = doc.get(field)

        if field == "price_list_rate":
            if abs(float(old_value or 0) - float(new_value or 0)) > 0.0001:
                changed_fields.append((field, old_value, new_value))
        else:
            old_n = old_value if old_value not in (None, "") else None
            new_n = new_value if new_value not in (None, "") else None
            if old_n != new_n:
                changed_fields.append((field, old_value, new_value))

    if changed_fields:
        msg_lines = [
            _("❌ Tidak bisa mengubah field harga di Item Price yang sudah di-save."),
            "",
            _("Field yang dicoba diubah:"),
        ]
        field_labels = {"price_list_rate": "Rate", "price_list": "Price List"}
        for field, old_val, new_val in changed_fields:
            label = field_labels.get(field, field)
            msg_lines.append(
                f"&nbsp;&nbsp;&nbsp;&nbsp;• <b>{label}</b>: "
                f"<code>{old_val}</code> → <code>{new_val}</code>"
            )
        msg_lines.append("")
        msg_lines.append(
            _("Hanya <b>Administrator</b> atau <b>Finance Manager</b> yang bisa mengubah harga.")
        )

        frappe.throw("<br>".join(msg_lines), title=_("Field Harga Terkunci"))


def _user_can_unlock() -> bool:
    """Cek apakah user current boleh unlock field harga."""
    if frappe.session.user == "Administrator":
        return True

    user_roles = set(frappe.get_roles(frappe.session.user))
    return any(role in user_roles for role in UNLOCK_ROLES)