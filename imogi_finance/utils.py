# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""Compatibility module for app hooks.

The app's Python package lives in ``imogi_finance/imogi_finance``. Frappe hook
paths expect ``imogi_finance.utils`` to resolve, so re-export the helpers here.
"""

from __future__ import annotations

from .imogi_finance.utils import ensure_advances_allow_on_submit, ensure_coretax_export_doctypes

__all__ = ["ensure_coretax_export_doctypes", "ensure_advances_allow_on_submit"]

_OLD_ROUND_CALL = "self.doc.round_floats_in(item, do_not_round_fields=do_not_round_fields)"
_NEW_ROUND_CALL = "self.doc.round_floats_in(item)"


def patch_round_floats_compatibility(bootinfo=None):
	"""One-time ERPNext source patch (after_migrate only — not on login)."""
	import os

	import frappe

	target = os.path.join(
		frappe.get_app_path("erpnext"),
		"controllers",
		"taxes_and_totals.py",
	)

	if not os.path.isfile(target):
		return

	with open(target, encoding="utf-8") as f:
		content = f.read()

	if _OLD_ROUND_CALL not in content:
		return

	content = content.replace(_OLD_ROUND_CALL, _NEW_ROUND_CALL)
	with open(target, "w", encoding="utf-8") as f:
		f.write(content)

	# Clear stale bytecode if present
	cache_dir = os.path.join(os.path.dirname(target), "__pycache__")
	if os.path.isdir(cache_dir):
		for name in os.listdir(cache_dir):
			if name.startswith("taxes_and_totals.") and name.endswith(".pyc"):
				try:
					os.remove(os.path.join(cache_dir, name))
				except OSError:
					pass
