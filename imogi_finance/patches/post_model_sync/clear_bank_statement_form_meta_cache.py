"""Clear cached form meta so bank statement client scripts reload after deploy."""

from __future__ import annotations

import frappe

_DTYPES = ("Bank CSV Import", "Bank Statement")


def execute():
	for name in _DTYPES:
		frappe.cache.hdel("doctype_form_meta", name)
	frappe.clear_cache()
