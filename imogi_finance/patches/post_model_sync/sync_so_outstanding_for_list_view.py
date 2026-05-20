import json

import frappe

from imogi_finance.sales_order_payment_status import update_sales_order_payment_status


def execute():
	"""Sync outstanding_amount from linked Sales Invoices and ensure list column is configured."""
	for row in frappe.get_all(
		"Sales Order",
		filters={
			"docstatus": 1,
			"custom_payment_status": ("in", ["Outstanding Invoice", "Partial Paid", "SI Created", "Paid"]),
		},
		pluck="name",
	):
		update_sales_order_payment_status(row)

	fields = [
		{"fieldname": "customer_name", "label": "Customer Name"},
		{"fieldname": "name", "label": "ID"},
		{"fieldname": "custom_payment_status", "label": "Payment Status"},
		{"fieldname": "delivery_date", "label": "Delivery Date"},
		{"fieldname": "grand_total", "label": "Grand Total"},
		{"fieldname": "outstanding_amount", "label": "Outstanding"},
	]

	# Frappe UI hanya mengizinkan 4–10; pakai 10 (maksimum) agar Outstanding tidak terpotong
	min_total_fields = "10"

	if frappe.db.exists("List View Settings", "Sales Order"):
		frappe.db.set_value(
			"List View Settings",
			"Sales Order",
			{"fields": json.dumps(fields), "total_fields": min_total_fields},
			update_modified=True,
		)

	frappe.clear_cache(doctype="Sales Order")
