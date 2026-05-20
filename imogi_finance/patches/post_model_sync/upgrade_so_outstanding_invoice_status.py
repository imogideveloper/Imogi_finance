"""Outstanding SO = SO total − invoiced; status Partial Paid → Outstanding Invoice."""

import frappe

from imogi_finance.sales_order_payment_status import update_sales_order_payment_status


def execute():
	_update_custom_field_options()
	_migrate_partial_paid_status()
	_recalculate_submitted_sales_orders()


def _update_custom_field_options():
	frappe.db.set_value(
		"Custom Field",
		"Sales Order-custom_payment_status",
		{
			"label": "Outstanding Invoice",
			"options": "\nDraft\nSubmitted\nSI Created\nOutstanding Invoice\nPaid\nCancelled",
		},
	)
	frappe.db.set_value(
		"Custom Field",
		"Sales Order-outstanding_amount",
		{
			"depends_on": "eval:['Outstanding Invoice','Partial Paid'].includes(doc.custom_payment_status)",
			"description": "Selisih Grand Total SO dengan total Grand Total Sales Invoice yang sudah submit.",
		},
	)


def _migrate_partial_paid_status():
	frappe.db.sql(
		"""
		UPDATE `tabSales Order`
		SET custom_payment_status = 'Outstanding Invoice'
		WHERE custom_payment_status = 'Partial Paid'
		"""
	)


def _recalculate_submitted_sales_orders():
	for name in frappe.get_all("Sales Order", filters={"docstatus": 1}, pluck="name"):
		update_sales_order_payment_status(name)
