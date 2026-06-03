import json

import frappe


PI_LIST_FIELDS = [
	{"fieldname": "status_field", "label": "Status"},
	{"fieldname": "posting_date", "label": "Posting Date"},
	{"fieldname": "due_date", "label": "Due Date"},
	{"fieldname": "grand_total", "label": "Grand Total"},
	{"fieldname": "name", "label": "ID"},
]


def execute():
	"""Pastikan kolom list Purchase Invoice selaras dengan Sales Invoice."""
	fields_json = json.dumps(PI_LIST_FIELDS)
	if frappe.db.exists("List View Settings", "Purchase Invoice"):
		current = frappe.db.get_value("List View Settings", "Purchase Invoice", "fields") or ""
		if current != fields_json:
			frappe.db.set_value(
				"List View Settings",
				"Purchase Invoice",
				{"fields": fields_json, "total_fields": "10"},
				update_modified=True,
			)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "List View Settings",
				"name": "Purchase Invoice",
				"fields": fields_json,
				"total_fields": "10",
			}
		)
		doc.insert(ignore_permissions=True)

	frappe.clear_cache(doctype="Purchase Invoice")
