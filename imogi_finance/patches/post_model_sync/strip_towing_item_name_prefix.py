"""
Strip the "Jasa Towing - " prefix from existing Sales Invoice Item.item_name
rows, so exports show just the plain vehicle number (chassis/plate) instead
of "Jasa Towing - <number>". New invoices are already created without the
prefix (see overrides/sales_invoice_towing.py and
overrides/delivery_order_towing.py); this only backfills old data.
"""

import frappe

PREFIX = "Jasa Towing - "


def execute():
	if not frappe.db.has_column("Sales Invoice Item", "item_name"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabSales Invoice Item`
		SET item_name = TRIM(SUBSTRING(item_name, LENGTH(%(prefix)s) + 1))
		WHERE item_name LIKE %(pattern)s
		""",
		{"prefix": PREFIX, "pattern": f"{PREFIX}%"},
	)
	frappe.db.commit()
