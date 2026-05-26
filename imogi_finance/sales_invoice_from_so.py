# Copyright (c) 2026, Imogi and contributors
"""Create Sales Invoice from Sales Order with payment term options (regular / % / fixed)."""

from __future__ import annotations

import json
import re

import frappe
from frappe import _
from frappe.utils import flt

@frappe.whitelist()
def get_so_billing_summary(sales_order: str) -> dict:
	"""Remaining billable amount on SO for the create-invoice dialog."""
	so = frappe.get_doc("Sales Order", sales_order)
	remaining = get_so_remaining_billable_amount(so)
	grand_total = flt(so.rounded_total or so.grand_total)
	billed = max(0, grand_total - remaining)

	return {
		"currency": so.currency,
		"grand_total": grand_total,
		"billed_amount": billed,
		"remaining_amount": remaining,
		"per_billed": flt(so.per_billed),
	}


def _parse_mapper_dialog_args(args=None) -> frappe._dict:
	"""open_mapped_doc → make_mapped_doc only passes source_name; dialog args live in frappe.flags.args."""
	if args:
		if isinstance(args, str):
			return frappe._dict(json.loads(args))
		return frappe._dict(args)

	if getattr(frappe.flags, "args", None):
		flag_args = frappe.flags.args
		if isinstance(flag_args, str):
			return frappe._dict(json.loads(flag_args))
		return frappe._dict(flag_args)

	req_args = getattr(getattr(frappe, "form_dict", None), "get", lambda _k: None)("args")
	if req_args:
		if isinstance(req_args, str):
			return frappe._dict(json.loads(req_args))
		if isinstance(req_args, dict):
			return frappe._dict(req_args)

	return frappe._dict()


@frappe.whitelist()
def make_sales_invoice_with_payment_terms(
	source_name, target_doc=None, ignore_permissions=False, args=None
):
	"""Map SO → SI; optionally scale to down-payment percentage or fixed amount."""
	args = _parse_mapper_dialog_args(args)

	invoice_mode = (args.get("invoice_mode") or "regular").strip().lower()
	so = frappe.get_doc("Sales Order", source_name)
	remaining = get_so_remaining_billable_amount(so)

	if remaining <= 0.005:
		frappe.throw(_("Sales Order is already fully billed."))

	target_amount = compute_target_amount(remaining, invoice_mode, args, so.currency)

	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice

	# ERPNext make_sales_invoice reads frappe.flags.args for optional row filters
	si = make_sales_invoice(source_name, target_doc, ignore_permissions)
	_sync_invoice_lines_with_so_pending_amount(si)

	if invoice_mode != "regular":
		scale_sales_invoice_to_amount(si, target_amount)
		line_ratio = _get_si_down_payment_line_ratio(si)
		_tag_si_down_payment_ratio(si, line_ratio)

	return si


def get_so_remaining_billable_amount(so) -> float:
	total = 0.0
	for row in so.get("items") or []:
		pending = flt(row.amount) - flt(row.billed_amt)
		if pending > 0:
			total += pending
	return flt(total)


def compute_target_amount(remaining: float, invoice_mode: str, args: frappe._dict, currency: str) -> float:
	if invoice_mode == "regular":
		return flt(remaining)

	if invoice_mode == "percentage":
		pct = _normalize_percentage(args.get("percentage"))
		if pct <= 0 or pct > 100:
			frappe.throw(_("Down payment percentage must be between 0.01 and 100."))
		return flt(remaining * pct / 100)

	if invoice_mode == "fixed_amount":
		amt = flt(args.get("fixed_amount"))
		if amt <= 0:
			frappe.throw(_("Fixed down payment amount must be greater than zero."))
		if amt > remaining + 0.005:
			formatted = frappe.format_value(remaining, {"fieldtype": "Currency", "options": currency})
			frappe.throw(
				_("Fixed amount cannot exceed remaining billable amount {0}.").format(formatted)
			)
		return flt(amt)

	frappe.throw(_("Invalid invoice type."))


def _normalize_percentage(value) -> float:
	"""Accept 50, 0.5, or locale strings like '50,000' (display) as 50 percent."""
	pct = flt(value)
	if 0 < pct <= 1:
		pct = pct * 100
	# Percent control with 3 decimals can send 50.0; values like 50000 are invalid
	if pct > 100:
		frappe.throw(_("Down payment percentage must be between 0.01 and 100."))
	return flt(pct, 2)


def _sync_invoice_lines_with_so_pending_amount(si) -> None:
	"""When SO amount is partly billed but ERPNext maps qty=0, derive qty from pending value ÷ rate."""
	changed = False
	for row in si.get("items") or []:
		if not row.get("so_detail"):
			continue

		so_item = frappe.db.get_value(
			"Sales Order Item",
			row.so_detail,
			["amount", "billed_amt", "rate"],
			as_dict=True,
		)
		if not so_item:
			continue

		pending = flt(so_item.amount) - flt(so_item.billed_amt)
		if pending <= 0.005:
			continue

		so_qty = flt(
			frappe.db.get_value("Sales Order Item", row.so_detail, "qty")
		)
		contract_rate = flt(row.rate) or flt(so_item.rate)

		# Qty already billed on a prior DP invoice but amount still pending → keep SO qty
		if so_qty > 0 and flt(row.qty) < so_qty - 0.0001:
			row.qty = so_qty
			changed = True

		if contract_rate > 0 and flt(row.qty):
			target_rate = flt(pending / flt(row.qty), row.precision("rate"))
			if abs(flt(row.rate) - target_rate) > 0.01 or flt(row.amount) > pending + 0.01:
				row.rate = target_rate
				changed = True
		elif flt(row.amount) > pending + 0.01:
			row.amount = pending
			changed = True

	if changed:
		si.run_method("calculate_taxes_and_totals")


def _tag_si_down_payment_ratio(si, ratio: float) -> None:
	"""Persist DP ratio on SI (remarks) so validate can re-apply after ERPNext recalculates lines."""
	if ratio <= 0 or ratio >= 1:
		return
	tag = f"<!--imogi_dp:{flt(ratio, 6)}-->"
	remarks = si.remarks or ""
	if tag not in remarks:
		si.remarks = (remarks.rstrip() + "\n" + tag).strip()


def get_si_down_payment_ratio(doc) -> float:
	remarks = doc.get("remarks") if isinstance(doc, dict) else getattr(doc, "remarks", None)
	match = re.search(r"<!--imogi_dp:([\d.]+)-->", remarks or "")
	return flt(match.group(1)) if match else 0.0


def _get_si_down_payment_line_ratio(si) -> float:
	"""Ratio applied to contract rate on each line (for re-apply on validate / form refresh)."""
	for row in si.get("items") or []:
		pl = flt(row.price_list_rate)
		rate = flt(row.rate)
		if pl and rate and pl > 0:
			return flt(rate / pl, 6)
	return 0.0


def _contract_rate_for_down_payment(row, ratio: float) -> float:
	"""Unscaled rate (remaining on SO) used as base before applying down-payment ratio."""
	qty = flt(row.qty) or 1
	pl = flt(row.price_list_rate)
	rate = flt(row.rate)
	amount = flt(row.amount) or flt(qty * rate)
	tolerance = max(0.01, abs(pl) * 0.002) if pl else 0.01

	# Already scaled in a prior pass: rate matches price_list_rate × ratio
	if pl and rate and abs(rate - pl * ratio) <= tolerance:
		return pl

	# Line amount is already scaled but price_list_rate is stale (e.g. original SO rate)
	if ratio and amount and abs(amount - qty * rate) <= 0.02:
		unscaled = flt(amount / ratio / qty, row.precision("rate"))
		if unscaled > rate + 0.01 and (not pl or pl > unscaled + 0.01):
			return unscaled

	return flt(amount / qty, row.precision("rate")) if qty else rate


def apply_down_payment_keep_qty_scale_rate(doc, ratio: float) -> None:
	"""Keep Qty from SO; scale Rate so Amount = Qty × Rate matches down-payment (ERPNext-native)."""
	if ratio <= 0 or ratio >= 1:
		return

	doc.flags.ignore_pricing_rule = True

	for row in doc.get("items") or []:
		qty = flt(row.qty)
		if not qty:
			qty = 1
			row.qty = qty

		contract_rate = _contract_rate_for_down_payment(row, ratio)
		if contract_rate <= 0:
			continue

		row.price_list_rate = contract_rate
		row.discount_percentage = 0
		row.discount_amount = 0
		row.rate = flt(contract_rate * ratio, row.precision("rate"))

	doc.run_method("calculate_taxes_and_totals")


@frappe.whitelist()
def sync_imogi_down_payment_invoice(doc):
	"""Re-apply DP line amounts when the SI form recalculates on the browser."""
	if isinstance(doc, str):
		doc = frappe.parse_json(doc)
	si = frappe.get_doc(doc)
	ratio = get_si_down_payment_ratio(si)
	if 0 < ratio < 1:
		apply_down_payment_keep_qty_scale_rate(si, ratio)
	return si.as_dict()


def scale_sales_invoice_to_amount(si, target_amount: float) -> None:
	si.flags.ignore_permissions = True
	items = si.get("items") or []
	if not items:
		frappe.throw(_("No invoice lines to adjust."))

	current_total = sum(flt(row.amount) for row in items)
	if current_total <= 0:
		frappe.throw(_("Cannot calculate down payment on zero amount."))

	ratio = flt(target_amount) / current_total
	apply_down_payment_keep_qty_scale_rate(si, ratio)

	actual = flt(si.net_total or sum(flt(row.amount) for row in items))
	if abs(actual - flt(target_amount)) > 1.0:
		frappe.throw(
			_("Could not apply down payment. Expected {0}, got {1}.").format(
				frappe.format_value(target_amount, {"fieldtype": "Currency", "options": si.currency}),
				frappe.format_value(actual, {"fieldtype": "Currency", "options": si.currency}),
			)
		)
