"""Kembalikan status_field di List View Settings agar kolom badge Status tampil."""

import json

import frappe

from imogi_finance.patches.post_model_sync.patch_si_list_view_settings import SI_LIST_FIELDS


def execute():
	if not frappe.db.exists("List View Settings", "Sales Invoice"):
		return

	fields_json = json.dumps(SI_LIST_FIELDS)
	current = frappe.db.get_value("List View Settings", "Sales Invoice", "fields") or ""
	if current == fields_json:
		return

	frappe.db.set_value(
		"List View Settings",
		"Sales Invoice",
		{"fields": fields_json, "total_fields": "10"},
		update_modified=True,
	)
	frappe.clear_cache(doctype="Sales Invoice")
