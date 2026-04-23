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
    """Patch file ERPNext langsung — persistent, tidak hilang saat request."""
    import os
    
    target = os.path.expanduser(
        "~/frappe-bench/apps/erpnext/erpnext/controllers/taxes_and_totals.py"
    )
    
    with open(target, "r") as f:
        content = f.read()
    
    old = "self.doc.round_floats_in(item, do_not_round_fields=do_not_round_fields)"
    new = "self.doc.round_floats_in(item)"
    
    if old in content:
        content = content.replace(old, new)
        with open(target, "w") as f:
            f.write(content)
        # Hapus pyc cache
        pyc = target.replace(".py", ".cpython-310.pyc").replace(
            "controllers/", "controllers/__pycache__/"
        )
        if os.path.exists(pyc):
            os.remove(pyc)
        print("✅ Patch applied")
    else:
        print("✅ Already patched or not needed")