"""Sales Invoice: late days field + map Overdue → Unpaid (list, form, export)."""

from __future__ import annotations

import frappe
from frappe.utils import date_diff, flt, getdate, today

OVERDUE_STATUSES = ("Overdue", "Overdue and Discounted")
UNPAID_REMAP = {
	"Overdue": "Unpaid",
	"Overdue and Discounted": "Unpaid and Discounted",
}


def days_past_due(due_date) -> int:
	if not due_date:
		return 0
	diff = date_diff(today(), getdate(due_date))
	return max(0, int(diff))


def apply_imogi_status_and_late_days(doc) -> None:
	"""Set imogi_late_days and replace Overdue status with Unpaid (in-memory)."""
	late = days_past_due(doc.get("due_date"))
	doc.imogi_late_days = late

	status = doc.get("status")
	if status in UNPAID_REMAP:
		doc.status = UNPAID_REMAP[status]


def sync_imogi_status_and_late_days(doc, method=None) -> None:
	"""Doc event: set late days + Unpaid remap before save."""
	if doc.doctype != "Sales Invoice":
		return
	apply_imogi_status_and_late_days(doc)


def sync_all_submitted_sales_invoices() -> None:
	"""Daily: fix rows after ERPNext update_invoice_status sets Overdue."""
	names = frappe.get_all(
		"Sales Invoice",
		filters={"docstatus": 1},
		pluck="name",
	)

	for name in names:
		row = frappe.db.get_value(
			"Sales Invoice",
			name,
			["status", "imogi_late_days", "due_date"],
			as_dict=True,
		)
		if not row:
			continue

		late = days_past_due(row.due_date)
		new_status = UNPAID_REMAP.get(row.status, row.status)

		if row.status == new_status and flt(row.imogi_late_days) == flt(late):
			continue

		frappe.db.set_value(
			"Sales Invoice",
			name,
			{"status": new_status, "imogi_late_days": late},
			update_modified=False,
		)

	frappe.db.commit()
