import json

import frappe


# Frappe reorder_listview_fields matches Status column via fieldname "status_field" (bukan "status").
SI_LIST_FIELDS = [
	{"fieldname": "status_field", "label": "Status"},
	{"fieldname": "posting_date", "label": "Posting Date"},
	{"fieldname": "imogi_late_days", "label": "Due Date"},
	{"fieldname": "grand_total", "label": "Grand Total"},
	{"fieldname": "name", "label": "ID"},
]


def execute():
	"""Pastikan kolom list Sales Invoice memakai status_field (alias Frappe untuk kolom Status)."""
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
