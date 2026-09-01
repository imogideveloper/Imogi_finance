# Copyright (c) 2026, Imogi and contributors
from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, today

from erpnext.accounts.utils import get_balance_on
from imogi_finance.services.sales_invoice_list_status import days_past_due

SO_PIPELINE_STATUS_BUCKETS = {
	"antrian": ["Open"],
	"tunggu_part": ["Waiting Part"],
	"dikerjakan": ["Prepared", "In Progress"],
	"siap_diambil": ["Finished", "QC Review", "Waiting Payment"],
	"selesai": ["Completed"],
}


def execute(filters: dict | None = None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	# Cards-only dashboard: no table, KPI summary, or chart.
	return [], [], None, None, None


def validate_filters(filters: frappe._dict):
	if not filters.get("company"):
		frappe.throw(_("Company is required"))

	if filters.get("from_date") and filters.get("to_date"):
		if getdate(filters.from_date) > getdate(filters.to_date):
			frappe.throw(_("From Date cannot be after To Date"))

	if not filters.get("from_date"):
		filters.from_date = get_first_day(today())
	if not filters.get("to_date"):
		filters.to_date = today()


@frappe.whitelist()
def get_dashboard_management_cards(company: str, from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
	if not company:
		frappe.throw(_("Company is required"))
	if not from_date:
		from_date = get_first_day(today())
	if not to_date:
		to_date = today()
	if getdate(from_date) > getdate(to_date):
		frappe.throw(_("From Date cannot be after To Date"))

	return build_dashboard_payload(company, from_date, to_date)


def build_dashboard_payload(company: str, from_date: str, to_date: str) -> dict[str, Any]:
	currency = frappe.get_cached_value("Company", company, "default_currency")

	ar_outstanding = _invoice_outstanding_summary("Sales Invoice", company)
	ar_late = _invoice_late_summary("Sales Invoice", company)
	ap_outstanding = _invoice_outstanding_summary("Purchase Invoice", company)
	ap_late = _invoice_late_summary("Purchase Invoice", company)

	return {
		"currency": currency,
		"period": {"from_date": from_date, "to_date": to_date},
		"ar": {
			"outstanding": {"amount": flt(ar_outstanding.total), "count": int(ar_outstanding.cnt or 0)},
			"late": {"amount": flt(ar_late.total), "count": int(ar_late.cnt or 0)},
			"aging_buckets": get_ar_aging_buckets(company),
		},
		"ap": {
			"outstanding": {"amount": flt(ap_outstanding.total), "count": int(ap_outstanding.cnt or 0)},
			"late": {"amount": flt(ap_late.total), "count": int(ap_late.cnt or 0)},
		},
		"cash_bank": get_cash_bank_balance(company, to_date),
		"pnl": get_pnl_summary(company, from_date, to_date),
		"pnl_trend": get_pnl_trend(company, months=6),
		"so_pipeline": get_service_order_pipeline(),
		"ap_due_list": get_ap_due_list(company),
		"ar_overdue_top": get_ar_overdue_top_list(company),
	}


# --- AR / AP outstanding -----------------------------------------------------

def _invoice_outstanding_summary(doctype: str, company: str) -> frappe._dict:
	table = f"tab{doctype}"
	return frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(outstanding_amount), 0) AS total, COUNT(*) AS cnt
		FROM `{table}`
		WHERE docstatus = 1
		  AND company = %s
		  AND IFNULL(outstanding_amount, 0) > 0.005
		""",
		company,
		as_dict=True,
	)[0]


def _invoice_late_summary(doctype: str, company: str) -> frappe._dict:
	table = f"tab{doctype}"
	return frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(outstanding_amount), 0) AS total, COUNT(*) AS cnt
		FROM `{table}`
		WHERE docstatus = 1
		  AND company = %s
		  AND IFNULL(outstanding_amount, 0) > 0.005
		  AND due_date IS NOT NULL
		  AND due_date < %s
		""",
		(company, today()),
		as_dict=True,
	)[0]


def get_ar_aging_buckets(company: str) -> dict[str, float]:
	"""Outstanding AR amount by days past due, in 0-30/31-60/61-90/90+ buckets."""
	buckets = {
		"not_due": 0.0,
		"days_0_30": 0.0,
		"days_31_60": 0.0,
		"days_61_90": 0.0,
		"days_90_plus": 0.0,
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
		elif late_days <= 30:
			buckets["days_0_30"] += amount
		elif late_days <= 60:
			buckets["days_31_60"] += amount
		elif late_days <= 90:
			buckets["days_61_90"] += amount
		else:
			buckets["days_90_plus"] += amount

	return buckets


# --- Cash & Bank --------------------------------------------------------------

def get_cash_bank_balance(company: str, as_of_date: str) -> dict[str, float]:
	cash = flt(get_balance_on(company=company, date=as_of_date, account_type="Cash"))
	bank = flt(get_balance_on(company=company, date=as_of_date, account_type="Bank"))
	return {"cash": cash, "bank": bank, "total": cash + bank}


# --- P&L -----------------------------------------------------------------------

def _gl_income_expense_totals(company: str, from_date: str, to_date: str) -> frappe._dict:
	return frappe.db.sql(
		"""
		SELECT
			SUM(CASE WHEN acc.root_type = 'Income'
			         THEN gle.credit - gle.debit ELSE 0 END) AS omzet,
			SUM(CASE WHEN acc.root_type = 'Expense' AND acc.account_type = 'Cost of Goods Sold'
			         THEN gle.debit - gle.credit ELSE 0 END) AS hpp,
			SUM(CASE WHEN acc.root_type = 'Expense'
			         THEN gle.debit - gle.credit ELSE 0 END) AS total_expense
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.company = %(company)s
		  AND gle.is_cancelled = 0
		  AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND acc.is_group = 0
		  AND acc.root_type IN ('Income', 'Expense')
		""",
		{"company": company, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	)[0]


def get_pnl_summary(company: str, from_date: str, to_date: str) -> dict[str, Any]:
	totals = _gl_income_expense_totals(company, from_date, to_date)
	omzet = flt(totals.omzet)
	hpp = flt(totals.hpp)
	total_expense = flt(totals.total_expense)
	opex = total_expense - hpp
	gross_profit = omzet - hpp
	net_profit = gross_profit - opex

	return {
		"omzet": omzet,
		"hpp": hpp,
		"opex": opex,
		"gross_profit": gross_profit,
		"net_profit": net_profit,
		"gross_margin_pct": (gross_profit / omzet * 100) if omzet else 0.0,
		"net_margin_pct": (net_profit / omzet * 100) if omzet else 0.0,
	}


def get_pnl_trend(company: str, months: int = 6) -> list[dict[str, Any]]:
	month_starts = []
	for offset in range(months - 1, -1, -1):
		month_starts.append(get_first_day(add_months(today(), -offset)))

	trend_from = month_starts[0]
	trend_to = get_last_day(month_starts[-1])

	rows = frappe.db.sql(
		"""
		SELECT
			DATE_FORMAT(gle.posting_date, '%%Y-%%m') AS ym,
			SUM(CASE WHEN acc.root_type = 'Income'
			         THEN gle.credit - gle.debit ELSE 0 END) AS omzet,
			SUM(CASE WHEN acc.root_type = 'Expense' AND acc.account_type = 'Cost of Goods Sold'
			         THEN gle.debit - gle.credit ELSE 0 END) AS hpp,
			SUM(CASE WHEN acc.root_type = 'Expense'
			         THEN gle.debit - gle.credit ELSE 0 END) AS total_expense
		FROM `tabGL Entry` gle
		INNER JOIN `tabAccount` acc ON acc.name = gle.account
		WHERE gle.company = %(company)s
		  AND gle.is_cancelled = 0
		  AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND acc.is_group = 0
		  AND acc.root_type IN ('Income', 'Expense')
		GROUP BY ym
		ORDER BY ym
		""",
		{"company": company, "from_date": trend_from, "to_date": trend_to},
		as_dict=True,
	)
	by_month = {row.ym: row for row in rows}

	trend = []
	for month_start in month_starts:
		ym = month_start.strftime("%Y-%m")
		row = by_month.get(ym)
		omzet = flt(row.omzet) if row else 0.0
		hpp = flt(row.hpp) if row else 0.0
		trend.append(
			{
				"month": ym,
				"month_label": month_start.strftime("%b %Y"),
				"omzet": omzet,
				"hpp": hpp,
				"gross_profit": omzet - hpp,
			}
		)

	return trend


# --- Garage Service Order pipeline ---------------------------------------------

def get_service_order_pipeline() -> dict[str, Any]:
	rows = frappe.db.sql(
		"""
		SELECT status, COUNT(*) AS cnt
		FROM `tabGarage Service Order`
		WHERE status != 'Cancelled'
		GROUP BY status
		""",
		as_dict=True,
	)
	counts_by_status = {row.status: int(row.cnt) for row in rows}

	buckets = {}
	for bucket, statuses in SO_PIPELINE_STATUS_BUCKETS.items():
		buckets[bucket] = sum(counts_by_status.get(status, 0) for status in statuses)

	buckets["total_aktif"] = buckets["tunggu_part"] + buckets["dikerjakan"]
	buckets["raw_status_counts"] = counts_by_status
	return buckets


# --- AP due / AR overdue lists --------------------------------------------------

def get_ap_due_list(company: str, limit: int = 5) -> list[dict[str, Any]]:
	return frappe.db.sql(
		"""
		SELECT name, supplier, supplier_name, due_date, outstanding_amount
		FROM `tabPurchase Invoice`
		WHERE docstatus = 1
		  AND company = %(company)s
		  AND IFNULL(outstanding_amount, 0) > 0.005
		ORDER BY due_date ASC
		LIMIT %(limit)s
		""",
		{"company": company, "limit": limit},
		as_dict=True,
	)


def get_ar_overdue_top_list(company: str, limit: int = 5) -> list[dict[str, Any]]:
	return frappe.db.sql(
		"""
		SELECT
			name, customer, customer_name, due_date, outstanding_amount,
			DATEDIFF(%(today)s, due_date) AS late_days
		FROM `tabSales Invoice`
		WHERE docstatus = 1
		  AND company = %(company)s
		  AND IFNULL(outstanding_amount, 0) > 0.005
		  AND due_date IS NOT NULL
		  AND due_date < %(today)s
		ORDER BY outstanding_amount DESC
		LIMIT %(limit)s
		""",
		{"company": company, "today": today(), "limit": limit},
		as_dict=True,
	)
