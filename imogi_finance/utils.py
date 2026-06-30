# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""Compatibility module for app hooks.

The app's Python package lives in ``imogi_finance/imogi_finance``. Frappe hook
paths expect ``imogi_finance.utils`` to resolve, so re-export the helpers here.
"""

from __future__ import annotations

from .imogi_finance.utils import ensure_advances_allow_on_submit, ensure_coretax_export_doctypes

__all__ = ["ensure_coretax_export_doctypes", "ensure_advances_allow_on_submit"]

def patch_round_floats_compatibility(bootinfo=None):
    """One-time ERPNext compat patch (after_migrate). Idempotent, no stdout."""
    import os

    import frappe

    try:
        target = os.path.join(
            frappe.get_app_path("erpnext"), "controllers", "taxes_and_totals.py"
        )
    except Exception:
        return

    if not os.path.isfile(target):
        return

    old = "self.doc.round_floats_in(item, do_not_round_fields=do_not_round_fields)"
    new = "self.doc.round_floats_in(item)"

    try:
        with open(target, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return

    if old not in content:
        return

    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(content.replace(old, new))
    except OSError as exc:
        frappe.log_error(
            f"Gagal patch round_floats di {target}: {exc}",
            "ERPNext round_floats patch",
        )
        return

    # Hapus .pyc agar perubahan langsung terbaca
    cache_dir = os.path.join(os.path.dirname(target), "__pycache__")
    if os.path.isdir(cache_dir):
        for name in os.listdir(cache_dir):
            if name.startswith("taxes_and_totals.") and name.endswith(".pyc"):
                try:
                    os.remove(os.path.join(cache_dir, name))
                except OSError:
                    pass