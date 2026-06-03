"""Rename SO payment field label to Status and status value Outstanding Invoice → Partial."""

from __future__ import annotations

import re

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	_update_custom_fields()
	_migrate_sales_order_status()
	_patch_client_scripts()
	frappe.clear_cache(doctype="Sales Order")


def _update_custom_fields():
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "custom_payment_status",
					"label": "Status",
					"options": "\nDraft\nSubmitted\nSI Created\nPartial\nPaid\nCancelled",
				},
				{
					"fieldname": "outstanding_amount",
					"depends_on": (
						"eval:['Partial','Partial Paid','Outstanding Invoice']"
						".includes(doc.custom_payment_status)"
					),
				},
			]
		},
		update=True,
	)


def _migrate_sales_order_status():
	frappe.db.sql(
		"""
		UPDATE `tabSales Order`
		SET custom_payment_status = 'Partial'
		WHERE custom_payment_status IN ('Outstanding Invoice', 'Partial Paid')
		"""
	)


def _patch_client_scripts():
	replacements = [
		('"Outstanding Invoice"', '"Partial"'),
		("'Outstanding Invoice'", "'Partial'"),
		('return "Outstanding Invoice"', 'return "Partial"'),
		('=== "Outstanding Invoice"', '=== "Partial"'),
		('!== "Outstanding Invoice"', '!== "Partial"'),
		('["Outstanding Invoice", "orange"]', '["Partial", "orange"]'),
		('["Outstanding Invoice",\\n        "orange"]', '["Partial",\\n        "orange"]'),
	]

	for row in frappe.get_all(
		"Client Script",
		filters={"dt": "Sales Order", "enabled": 1},
		fields=["name", "script"],
	):
		script = row.script or ""
		if "Outstanding Invoice" not in script and "Partial Paid" not in script:
			continue

		updated = script
		for old, new in replacements:
			updated = updated.replace(old, new)

		# Normalize legacy Partial Paid display mapping to Partial.
		updated = re.sub(
			r'if \(payment_status === "Partial Paid"\) return "Partial";',
			'if (payment_status === "Partial Paid" || payment_status === "Outstanding Invoice") return "Partial";',
			updated,
		)
		updated = updated.replace(
			'if (payment_status === "Partial Paid") return "Outstanding Invoice";',
			'if (payment_status === "Partial Paid" || payment_status === "Outstanding Invoice") return "Partial";',
		)

		if updated != script:
			frappe.db.set_value("Client Script", row.name, "script", updated, update_modified=True)
