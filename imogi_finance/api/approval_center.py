"""Backend for the Approval Center page (imogi_finance/page/approval_center).

This module owns the canonical list of approval queues - workshop_dashboard.py imports
APPROVAL_TYPES from here for its "Approval Pending" card, so the number on the dashboard and
the list on this page can never disagree.

Acting on a document goes through frappe.model.workflow.apply_workflow, never through a direct
field write: that is the path that runs the transition check, the self-approval check, the
docstatus change, and - via the Expense Request "validate" doc_event - imogi_finance's own
approver authorisation (events/expense_request.validate_workflow_action). Writing
workflow_state directly would bypass every one of those.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow, get_transitions
from frappe.utils import cint, flt

# Queues shown in the Approval Center, in menu order. "pending_states" are the states that are
# waiting on a human; they are matched on the workflow's own state field, NOT on docstatus -
# Administrative Payment Voucher keeps its "Pending Approval" state at docstatus 0 (Draft),
# so a docstatus filter silently hides every voucher awaiting approval.
APPROVAL_TYPES = [
	{
		"doctype": "Expense Request",
		"label": "Expense Request",
		"pending_states": ["Pending Review"],
		"amount_field": "amount",
		"date_field": "request_date",
		"subtitle_fields": ["supplier", "cost_center"],
		"detail_field": "description",
	},
	{
		"doctype": "Additional Budget Request",
		"label": "Additional Budget Request",
		"pending_states": ["Pending Approval"],
		"amount_field": "amount",
		"date_field": "posting_date",
		"subtitle_fields": ["cost_center", "account"],
		"detail_field": "reason",
	},
	{
		"doctype": "Budget Reclass Request",
		"label": "Budget Reclass Request",
		"pending_states": ["Pending Approval"],
		"amount_field": "amount",
		"date_field": "posting_date",
		"subtitle_fields": ["from_cost_center", "to_cost_center"],
		"detail_field": "reason",
	},
	{
		"doctype": "Internal Charge Request",
		"label": "Internal Charge Request",
		"pending_states": [
			"Pending Approval",
			"Pending L1 Approval",
			"Pending L2 Approval",
			"Pending L3 Approval",
			"Partially Approved",
		],
		"amount_field": "total_amount",
		"date_field": "posting_date",
		"subtitle_fields": ["source_cost_center"],
		"detail_field": None,
	},
	{
		"doctype": "Administrative Payment Voucher",
		"label": "Administrative Payment Voucher",
		"pending_states": ["Pending Approval"],
		"amount_field": "amount",
		"date_field": "posting_date",
		"subtitle_fields": ["party", "cost_center"],
		"detail_field": "reason_code",
	},
	{
		"doctype": "Transfer Application",
		"label": "Transfer Application",
		"pending_states": ["Finance Review", "Awaiting Bank Confirmation"],
		"amount_field": "total_amount",
		"date_field": "posting_date",
		"subtitle_fields": ["company"],
		"detail_field": None,
	},
	{
		"doctype": "Purchase Order",
		"label": "Purchase Order",
		"pending_states": ["Pending Approval"],
		"amount_field": "grand_total",
		"date_field": "transaction_date",
		"subtitle_fields": ["supplier", "company"],
		"detail_field": None,
	},
	{
		"doctype": "Advanced Expense Request",
		"label": "Advanced Expense Request",
		"pending_states": ["Pending Review"],
		"amount_field": "amount",
		"date_field": "posting_date",
		"subtitle_fields": ["cost_center"],
		"detail_field": "description",
	},
]

APPROVAL_TYPES_BY_DOCTYPE = {cfg["doctype"]: cfg for cfg in APPROVAL_TYPES}

# A list long enough that nobody scrolls past it in practice, short enough that resolving the
# available transitions per row (which loads each document) stays cheap.
LIST_LIMIT = 50


def _config(doctype: str) -> dict[str, Any]:
	cfg = APPROVAL_TYPES_BY_DOCTYPE.get(doctype)
	if not cfg:
		frappe.throw(_("{0} bukan antrean approval yang dikenal.").format(doctype))
	return cfg


def _state_field(doctype: str) -> str:
	"""The workflow's own state field - usually workflow_state, but read it rather than assume."""
	name = frappe.db.get_value("Workflow", {"document_type": doctype, "is_active": 1}, "name")
	if not name:
		return "workflow_state"
	return frappe.db.get_value("Workflow", name, "workflow_state_field") or "workflow_state"


def _usable(cfg: dict[str, Any]) -> bool:
	return bool(frappe.db.exists("DocType", cfg["doctype"])) and frappe.has_permission(
		cfg["doctype"], "read"
	)


def _existing_fields(doctype: str, fieldnames: list[str | None]) -> list[str]:
	meta = frappe.get_meta(doctype)
	return [f for f in fieldnames if f and meta.has_field(f)]


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_overview() -> dict[str, Any]:
	"""Menu payload: one row per queue with the number of documents waiting."""
	queues = []
	for cfg in APPROVAL_TYPES:
		if not _usable(cfg):
			continue
		queues.append(
			{
				"doctype": cfg["doctype"],
				"label": cfg["label"],
				"pending_count": _pending_count(cfg),
			}
		)

	return {
		"queues": queues,
		"user": frappe.session.user,
		"total_pending": sum(q["pending_count"] for q in queues),
	}


def _pending_count(cfg: dict[str, Any]) -> int:
	state_field = _state_field(cfg["doctype"])
	try:
		# get_list (not get_all) so a user only ever counts what they are allowed to see.
		return len(
			frappe.get_list(
				cfg["doctype"],
				filters={state_field: ["in", cfg["pending_states"]]},
				pluck="name",
				limit_page_length=0,
			)
		)
	except frappe.PermissionError:
		return 0


@frappe.whitelist()
def get_pending(doctype: str) -> dict[str, Any]:
	"""The queue itself: documents waiting, each with the actions this user may take on it."""
	cfg = _config(doctype)
	if not _usable(cfg):
		frappe.throw(_("Anda tidak punya akses ke {0}.").format(doctype))

	state_field = _state_field(doctype)
	meta = frappe.get_meta(doctype)
	fields = ["name", "owner", "modified", state_field]
	fields += _existing_fields(
		doctype,
		[
			cfg.get("amount_field"),
			cfg.get("date_field"),
			cfg.get("detail_field"),
			"current_approval_level",
			"company",
			"currency",
		]
		+ list(cfg.get("subtitle_fields") or []),
	)
	fields = list(dict.fromkeys(fields))

	rows = frappe.get_list(
		doctype,
		filters={state_field: ["in", cfg["pending_states"]]},
		fields=fields,
		order_by="modified asc",
		limit_page_length=LIST_LIMIT,
	)

	items = []
	for row in rows:
		level = cint(row.get("current_approval_level")) or 1
		expected = None
		if meta.has_field(f"level_{level}_user"):
			expected = frappe.db.get_value(doctype, row["name"], f"level_{level}_user")

		items.append(
			{
				"name": row["name"],
				"state": row.get(state_field),
				"amount": flt(row.get(cfg["amount_field"])) if cfg.get("amount_field") else None,
				"date": str(row.get(cfg["date_field"]) or "") if cfg.get("date_field") else "",
				"detail": row.get(cfg["detail_field"]) if cfg.get("detail_field") else None,
				"subtitle": [
					{"label": _label_for(meta, f), "value": row.get(f)}
					for f in (cfg.get("subtitle_fields") or [])
					if row.get(f)
				],
				"level": level,
				"expected_approver": expected,
				"requested_by": row.get("owner"),
				"actions": _actions_for(doctype, row["name"]),
			}
		)

	return {
		"doctype": doctype,
		"label": cfg["label"],
		"state_field": state_field,
		"pending_states": cfg["pending_states"],
		"items": items,
		"truncated": len(rows) >= LIST_LIMIT,
		"user": frappe.session.user,
	}


def _label_for(meta, fieldname: str) -> str:
	df = meta.get_field(fieldname)
	return df.label if df and df.label else fieldname.replace("_", " ").title()


def _actions_for(doctype: str, name: str) -> list[dict[str, str]]:
	"""Transitions frappe would offer this user on this document, right now.

	Derived from the workflow rather than hardcoded, so the buttons can never offer an action
	the backend would reject - and a queue whose workflow is missing its Approve transition
	(Advanced Expense Request, as of this writing) correctly shows no buttons at all.
	"""
	try:
		doc = frappe.get_doc(doctype, name)
		return [
			{"action": t.get("action"), "next_state": t.get("next_state")}
			for t in get_transitions(doc)
		]
	except Exception:
		# A missing workflow, an unset state, or a condition that errors must not take the
		# whole queue down - the row still renders, just without buttons.
		return []


# ---------------------------------------------------------------------------
# Act
# ---------------------------------------------------------------------------

@frappe.whitelist()
def act(doctype: str, name: str, action: str) -> dict[str, Any]:
	"""Apply one workflow action. All validation lives in apply_workflow and the doc's own hooks."""
	_config(doctype)
	if not action:
		frappe.throw(_("Aksi wajib diisi."))

	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")

	updated = apply_workflow(doc, action)
	state_field = _state_field(doctype)

	return {
		"name": name,
		"action": action,
		# queue_in_background can make apply_workflow return None; fall back to a fresh read.
		"state": (updated.get(state_field) if updated else frappe.db.get_value(doctype, name, state_field)),
	}
