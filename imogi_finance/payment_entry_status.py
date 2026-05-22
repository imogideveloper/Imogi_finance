"""Sync Payment Entry status to Allocated / Unallocated (list + form, not ERPNext Submitted)."""

import frappe
from frappe.utils import flt


def _resolve_payment_status(doc) -> str:
	if doc.docstatus == 2:
		return "Cancelled"
	if doc.docstatus == 0:
		return "Draft"
	if flt(doc.get("unallocated_amount")) > 0:
		return "Unallocated"
	return "Allocated"


def sync_payment_status(doc, save: bool = False):
	"""Set payment_status + status so list view matches form (Allocated/Unallocated)."""
	status = _resolve_payment_status(doc)
	updates = {}

	if frappe.db.has_column("Payment Entry", "payment_status") and doc.get("payment_status") != status:
		doc.payment_status = status
		updates["payment_status"] = status

	# Override ERPNext status (Submitted) for list indicator + status column
	if doc.get("status") != status:
		doc.status = status
		updates["status"] = status

	if not updates:
		return

	if save and doc.name and not doc.get("__islocal"):
		frappe.db.set_value(
			"Payment Entry",
			doc.name,
			updates,
			update_modified=False,
		)


def update_payment_status_on_validate(doc, method=None):
	sync_payment_status(doc, save=bool(doc.name and not doc.is_new()))


def update_payment_status_on_submit(doc, method=None):
	sync_payment_status(doc, save=True)


def update_payment_status_on_cancel(doc, method=None):
	sync_payment_status(doc, save=True)


def backfill_all_payment_status():
	fields = ["name", "docstatus", "unallocated_amount", "status"]
	if frappe.db.has_column("Payment Entry", "payment_status"):
		fields.append("payment_status")

	for row in frappe.get_all("Payment Entry", fields=fields):
		doc = frappe._dict(row)
		status = _resolve_payment_status(doc)
		updates = {"status": status}
		if "payment_status" in fields:
			updates["payment_status"] = status
		frappe.db.set_value(
			"Payment Entry",
			row.name,
			updates,
			update_modified=False,
		)
