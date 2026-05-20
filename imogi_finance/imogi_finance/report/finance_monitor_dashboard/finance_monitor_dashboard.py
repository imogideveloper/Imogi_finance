# Copyright (c) 2026, Imogi and contributors
from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from imogi_finance.services.sales_invoice_list_status import days_past_due


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	summary = get_kpi_summary(filters)
	report_summary = build_report_summary(summary, filters.company)
	chart = build_cash_chart(summary)
	columns = get_columns()
	data = get_detail_rows(filters)

	return columns, data, None, chart, report_summary


def validate_filters(filters: frappe._dict):
	if not filters.get("company"):
		frappe.throw(_("Company is required"))

	if filters.get("from_date") and filters.get("to_date"):
		if getdate(filters.from_date) > getdate(filters.to_date):
			frappe.throw(_("From Date cannot be after To Date"))

	if not filters.get("from_date"):
		filters.from_date = frappe.defaults.get_global_default("year_start_date") or today()
	if not filters.get("to_date"):
		filters.to_date = today()


@frappe.whitelist()
def get_finance_monitor_cards(company: str) -> dict[str, Any]:
	"""Card payload for Odoo-style receivable summary (used by report JS)."""
	if not company:
		frappe.throw(_("Company is required"))
	return build_card_payload(get_kpi_summary(frappe._dict({"company": company})))


def build_card_payload(summary: dict[str, Any]) -> dict[str, Any]:
	return {
		"currency": summary.get("currency"),
		"unpaid": {
			"count": summary["unpaid_invoice_count"],
			"amount": summary["ar_outstanding"],
		},
		"late": {
			"count": summary["late_invoice_count"],
			"amount": summary["late_outstanding"],
		},
		"aging_buckets": summary.get("aging_buckets") or {},
		"so_partly_billed_count": summary.get("so_partly_billed_count", 0),
	}


def get_kpi_summary(filters: frappe._dict) -> dict[str, Any]:
	company = filters.company
	from_date = filters.from_date
	to_date = filters.to_date
	currency = frappe.get_cached_value("Company", company, "default_currency")

	ar_outstanding = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(outstanding_amount), 0) AS total, COUNT(*) AS cnt
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		  AND company = %s
		  AND IFNULL(outstanding_amount, 0) > 0.005
		""",
		company,
		as_dict=True,
	)[0]

	late = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(outstanding_amount), 0) AS total, COUNT(*) AS cnt
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		  AND company = %s
		  AND IFNULL(outstanding_amount, 0) > 0.005
		  AND due_date IS NOT NULL
		  AND due_date < %s
		""",
		(company, today()),
		as_dict=True,
	)[0]

	cash_in = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(paid_amount), 0) AS total
		FROM `tabPayment Entry`
		WHERE docstatus = 1
		  AND company = %s
		  AND payment_type = 'Receive'
		  AND posting_date BETWEEN %s AND %s
		""",
		(company, from_date, to_date),
	)[0][0]

	cash_out = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(paid_amount), 0) AS total
		FROM `tabPayment Entry`
		WHERE docstatus = 1
		  AND company = %s
		  AND payment_type = 'Pay'
		  AND posting_date BETWEEN %s AND %s
		""",
		(company, from_date, to_date),
	)[0][0]

	sales_invoiced = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(grand_total), 0) AS total
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		  AND company = %s
		  AND is_return = 0
		  AND posting_date BETWEEN %s AND %s
		""",
		(company, from_date, to_date),
	)[0][0]

	so_partly = frappe.db.sql(
		"""
		SELECT COUNT(*) AS cnt
		FROM `tabSales Order`
		WHERE docstatus = 1
		  AND company = %s
		  AND IFNULL(per_billed, 0) < 99.999
		  AND status NOT IN ('Closed', 'Cancelled')
		""",
		company,
	)[0][0]

	return {
		"currency": currency,
		"ar_outstanding": flt(ar_outstanding.total),
		"unpaid_invoice_count": int(ar_outstanding.cnt or 0),
		"late_outstanding": flt(late.total),
		"late_invoice_count": int(late.cnt or 0),
		"cash_in": flt(cash_in),
		"cash_out": flt(cash_out),
		"sales_invoiced": flt(sales_invoiced),
		"so_partly_billed_count": int(so_partly or 0),
		"aging_buckets": get_receivable_aging_buckets(company),
	}


def get_receivable_aging_buckets(company: str) -> dict[str, float]:
	"""Outstanding amount by days past due (based on due_date)."""
	buckets = {
		"not_due": 0.0,
		"days_1_7": 0.0,
		"days_8_30": 0.0,
		"days_31_60": 0.0,
		"days_60_plus": 0.0,
	}

	rows = frappe.db.sql(
		"""
		SELECT outstanding_amount, due_date
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		  AND company = %s
		  AND IFNULL(outstanding_amount, 0) > 0.005
		""",
		company,
		as_dict=True,
	)

	for row in rows:
		amount = flt(row.outstanding_amount)
		late_days = days_past_due(row.due_date)
		if late_days <= 0:
			buckets["not_due"] += amount
		elif late_days <= 7:
			buckets["days_1_7"] += amount
		elif late_days <= 30:
			buckets["days_8_30"] += amount
		elif late_days <= 60:
			buckets["days_31_60"] += amount
		else:
			buckets["days_60_plus"] += amount

	return buckets


def build_report_summary(summary: dict[str, Any], company: str):
	currency = summary.get("currency") or frappe.get_cached_value("Company", company, "default_currency")
	return [
		{
			"value": summary["ar_outstanding"],
			"label": _("Total Receivable (Outstanding)"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Red" if summary["ar_outstanding"] > 0 else "Green",
		},
		{
			"value": summary["unpaid_invoice_count"],
			"label": _("Unpaid Invoices"),
			"datatype": "Int",
			"indicator": "Orange" if summary["unpaid_invoice_count"] else "Green",
		},
		{
			"value": summary["late_invoice_count"],
			"label": _("Late Invoices"),
			"datatype": "Int",
			"indicator": "Red" if summary["late_invoice_count"] else "Green",
		},
		{
			"value": summary["late_outstanding"],
			"label": _("Late Amount"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Red" if summary["late_outstanding"] > 0 else "Green",
		},
		{
			"value": summary["cash_in"],
			"label": _("Cash In (Period)"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Green",
		},
		{
			"value": summary["cash_out"],
			"label": _("Cash Out (Period)"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		},
		{
			"value": summary["sales_invoiced"],
			"label": _("Sales Invoiced (Period)"),
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Blue",
		},
		{
			"value": summary["so_partly_billed_count"],
			"label": _("SO Partly Billed"),
			"datatype": "Int",
			"indicator": "Orange" if summary["so_partly_billed_count"] else "Green",
		},
	]


def build_cash_chart(summary: dict[str, Any]):
	return {
		"data": {
			"labels": [_("Cash In"), _("Cash Out"), _("Sales Invoiced")],
			"datasets": [
				{
					"name": _("Amount"),
					"values": [
						summary["cash_in"],
						summary["cash_out"],
						summary["sales_invoiced"],
					],
				}
			],
		},
		"type": "bar",
		"colors": ["#28a745", "#dc3545", "#5e64ff"],
		"fieldtype": "Currency",
	}


def build_aging_chart(buckets: dict[str, float]):
	return {
		"data": {
			"labels": [
				_("Not Due"),
				_("1–7 Days Late"),
				_("8–30 Days Late"),
				_("31–60 Days Late"),
				_("60+ Days Late"),
			],
			"datasets": [{"name": _("Outstanding"), "values": [
				buckets.get("not_due", 0),
				buckets.get("days_1_7", 0),
				buckets.get("days_8_30", 0),
				buckets.get("days_31_60", 0),
				buckets.get("days_60_plus", 0),
			]}],
		},
		"type": "bar",
		"colors": ["#5e64ff", "#f0ad4e", "#fd7e14", "#dc3545", "#721c24"],
		"fieldtype": "Currency",
	}


def get_columns():
	return [
		{"fieldname": "row_type", "label": _("Type"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "document",
			"label": _("Document"),
			"fieldtype": "Dynamic Link",
			"options": "reference_doctype",
			"width": 170,
		},
		{
			"fieldname": "reference_doctype",
			"label": _("Reference DocType"),
			"fieldtype": "Data",
			"hidden": 1,
			"width": 100,
		},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "grand_total", "label": _("Amount / Order Total"), "fieldtype": "Currency", "width": 140},
		{
			"fieldname": "outstanding_amount",
			"label": _("Outstanding / Unbilled Est."),
			"fieldtype": "Currency",
			"width": 160,
		},
		{"fieldname": "per_billed", "label": _("% Billed"), "fieldtype": "Percent", "width": 90},
		{"fieldname": "late_days", "label": _("Late (Days)"), "fieldtype": "Int", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
	]


def get_detail_rows(filters: frappe._dict) -> list[dict]:
	rows: list[dict] = []
	company = filters.company
	today_str = today()

	rows.append(_section_row(_("Outstanding Sales Invoices (Top 50)")))

	invoices = frappe.db.sql(
		"""
		SELECT
			name AS document,
			customer,
			posting_date,
			due_date,
			grand_total,
			outstanding_amount,
			status,
			CASE
				WHEN due_date IS NOT NULL AND due_date < %(today)s
				THEN DATEDIFF(%(today)s, due_date)
				ELSE 0
			END AS late_days
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		  AND company = %(company)s
		  AND IFNULL(outstanding_amount, 0) > 0.005
		ORDER BY late_days DESC, outstanding_amount DESC
		LIMIT 50
		""",
		{"company": company, "today": today_str},
		as_dict=True,
	)

	for inv in invoices:
		rows.append(
			{
				"row_type": _("Outstanding Invoice"),
				"document": inv.document,
				"reference_doctype": "Sales Invoice",
				"customer": inv.customer,
				"posting_date": inv.posting_date,
				"due_date": inv.due_date,
				"grand_total": inv.grand_total,
				"outstanding_amount": inv.outstanding_amount,
				"per_billed": None,
				"late_days": int(inv.late_days or 0),
				"status": inv.status,
			}
		)

	if not invoices:
		rows.append(_empty_row(_("No outstanding sales invoices.")))

	rows.append(_section_row(_("Sales Orders — Partly Billed")))

	payment_status_select = "billing_status AS payment_status"
	if frappe.db.has_column("Sales Order", "custom_payment_status"):
		payment_status_select = (
			"COALESCE(NULLIF(TRIM(custom_payment_status), ''), billing_status) AS payment_status"
		)

	orders = frappe.db.sql(
		f"""
		SELECT
			name AS document,
			customer,
			transaction_date AS posting_date,
			grand_total,
			per_billed,
			billing_status,
			{payment_status_select}
		FROM `tabSales Order`
		WHERE docstatus = 1
		  AND company = %(company)s
		  AND IFNULL(per_billed, 0) < 99.999
		  AND status NOT IN ('Closed', 'Cancelled')
		ORDER BY transaction_date DESC
		LIMIT 50
		""",
		{"company": company},
		as_dict=True,
	)

	for so in orders:
		per_billed = flt(so.per_billed)
		unbilled_est = flt(so.grand_total) * (100 - per_billed) / 100
		rows.append(
			{
				"row_type": _("Partly Billed SO"),
				"document": so.document,
				"reference_doctype": "Sales Order",
				"customer": so.customer,
				"posting_date": so.posting_date,
				"due_date": None,
				"grand_total": so.grand_total,
				"outstanding_amount": unbilled_est,
				"per_billed": per_billed,
				"late_days": None,
				"status": so.payment_status or so.billing_status,
			}
		)

	if not orders:
		rows.append(_empty_row(_("No partly billed sales orders.")))

	return rows


def _section_row(title: str) -> dict:
	return {
		"row_type": title,
		"document": "",
		"reference_doctype": "",
		"customer": "",
		"is_section": 1,
	}


def _empty_row(message: str) -> dict:
	return {
		"row_type": message,
		"document": "",
		"reference_doctype": "",
		"customer": "",
		"is_empty": 1,
	}
