from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, add_months, getdate, formatdate, nowdate
from dateutil.relativedelta import relativedelta


def execute(filters: dict | None = None):
    filters = filters or {}
    columns = get_columns(filters)
    data = get_data(filters)

    # Calculate summary from original rows BEFORE expanding to monthly breakdown.
    # add_monthly_breakdown() copies total_amount to every period row, so summing
    # after expansion would multiply each item's amount by its period count.
    summary = get_summary(data)

    # If show_breakdown is enabled, expand rows with monthly breakdown
    if filters.get("show_breakdown"):
        data = add_monthly_breakdown(data)

    return columns, data, None, None, summary


def get_columns(filters: dict) -> list[dict]:
    columns = [
        {
            "label": _("ER Number"),
            "fieldname": "expense_request",
            "fieldtype": "Link",
            "options": "Expense Request",
            "width": 160,
        },
        {"label": _("ER Date"), "fieldname": "er_date", "fieldtype": "Date", "width": 110},
        {"label": _("Item Description"), "fieldname": "description", "fieldtype": "Data", "width": 200},
    ]

    # Add period number and date if breakdown is shown
    if filters.get("show_breakdown"):
        columns.extend([
            {"label": _("Period"), "fieldname": "period_number", "fieldtype": "Int", "width": 70},
            {"label": _("Period Date"), "fieldname": "period_date", "fieldtype": "Date", "width": 110},
            {"label": _("Period Amount"), "fieldname": "period_amount", "fieldtype": "Currency", "width": 140},
            {"label": _("Period Status"), "fieldname": "period_status", "fieldtype": "Data", "width": 120},
        ])

    columns.extend([
        {
            "label": _("Prepaid Account"),
            "fieldname": "prepaid_account",
            "fieldtype": "Link",
            "options": "Account",
            "width": 180,
        },
        {
            "label": _("Expense Account"),
            "fieldname": "expense_account",
            "fieldtype": "Link",
            "options": "Account",
            "width": 180,
        },
        {
            "label": _("Total Amount"),
            "fieldname": "total_amount",
            "fieldtype": "Currency",
            "width": 130,
        },
        {"label": _("Periods"), "fieldname": "periods", "fieldtype": "Int", "width": 80},
        {"label": _("Start Date"), "fieldname": "start_date", "fieldtype": "Date", "width": 110},
        {
            "label": _("PI Number"),
            "fieldname": "purchase_invoice",
            "fieldtype": "Link",
            "options": "Purchase Invoice",
            "width": 160,
        },
        {"label": _("PI Date"), "fieldname": "pi_date", "fieldtype": "Date", "width": 110},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
        {
            "label": _("Outstanding Balance"),
            "fieldname": "outstanding_balance",
            "fieldtype": "Currency",
            "width": 160,
        },
    ])

    return columns


def get_conditions(filters: dict) -> tuple[str, dict]:
    conditions = ["er.docstatus = 1", "eri.is_deferred_expense = 1"]
    params: dict[str, str] = {}

    if filters.get("from_date"):
        conditions.append("er.request_date >= %(from_date)s")
        params["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("er.request_date <= %(to_date)s")
        params["to_date"] = filters["to_date"]

    if filters.get("prepaid_account"):
        conditions.append("eri.prepaid_account = %(prepaid_account)s")
        params["prepaid_account"] = filters["prepaid_account"]

    if filters.get("expense_account"):
        conditions.append("eri.expense_account = %(expense_account)s")
        params["expense_account"] = filters["expense_account"]

    return " AND ".join(conditions), params


def get_data(filters: dict) -> list[dict]:
    where_clause, params = get_conditions(filters)
    query = f"""
        SELECT
            er.name AS expense_request,
            er.request_date AS er_date,
            eri.description,
            eri.prepaid_account,
            eri.expense_account,
            eri.amount AS total_amount,
            eri.deferred_periods AS periods,
            eri.deferred_start_date AS start_date,
            pi.name AS purchase_invoice,
            pi.posting_date AS pi_date,
            pi.status AS status,
            COALESCE(SUM(gle.credit - gle.debit), 0) AS amortized_amount
        FROM `tabExpense Request Item` eri
        JOIN `tabExpense Request` er ON er.name = eri.parent
        LEFT JOIN `tabPurchase Invoice` pi ON pi.imogi_expense_request = er.name
        LEFT JOIN `tabPurchase Invoice Item` pii
            ON pii.parent = pi.name
            AND pii.expense_account = eri.prepaid_account
            AND pii.amount = eri.amount
            AND (pii.description = eri.description OR pii.item_name = eri.description)
        LEFT JOIN `tabGL Entry` gle
            ON gle.against_voucher_type = 'Purchase Invoice'
            AND gle.against_voucher = pi.name
            AND gle.account = eri.prepaid_account
            AND gle.is_cancelled = 0
        WHERE {where_clause}
        GROUP BY
            eri.name,
            er.name,
            er.request_date,
            eri.description,
            eri.prepaid_account,
            eri.expense_account,
            eri.amount,
            eri.deferred_periods,
            eri.deferred_start_date,
            pi.name,
            pi.posting_date,
            pi.status
        ORDER BY er.request_date DESC, er.name DESC
    """

    rows = frappe.db.sql(query, params, as_dict=True)
    for row in rows:
        amortized = flt(row.get("amortized_amount"))
        total_amount = flt(row.get("total_amount"))
        row["outstanding_balance"] = total_amount - amortized
    return rows


def get_summary(data: list[dict]) -> list[dict]:
    total_deferred = sum(flt(row.get("total_amount")) for row in data)
    total_amortized = sum(flt(row.get("amortized_amount")) for row in data)
    total_outstanding = total_deferred - total_amortized

    return [
        {
            "label": _("Total Deferred"),
            "value": total_deferred,
            "indicator": "Blue",
        },
        {
            "label": _("Total Amortized"),
            "value": total_amortized,
            "indicator": "Green",
        },
        {
            "label": _("Total Outstanding"),
            "value": total_outstanding,
            "indicator": "Orange",
        },
    ]


def add_monthly_breakdown(data: list[dict]) -> list[dict]:
    """Expand each row into monthly breakdown rows similar to Journal Entry."""
    result = []
    today = getdate(nowdate())

    for row in data:
        periods = flt(row.get("periods", 0))
        total_amount = flt(row.get("total_amount", 0))
        start_date = row.get("start_date")
        pi_name = row.get("purchase_invoice")

        if not periods or not start_date:
            # No breakdown possible, keep original row
            result.append(row)
            continue

        # Calculate amount per period
        amount_per_period = total_amount / periods

        # Get posted Journal Entries for this PI to check which periods are posted
        posted_dates = set()
        if pi_name:
            # Check Journal Entry Accounts that reference this PI
            posted_jes = frappe.db.sql("""
                SELECT DISTINCT je.posting_date
                FROM `tabJournal Entry` je
                INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
                WHERE jea.reference_type = 'Purchase Invoice'
                AND jea.reference_name = %(pi_name)s
                AND je.docstatus = 1
                AND je.voucher_type = 'Deferred Expense'
            """, {"pi_name": pi_name}, as_dict=True)
            posted_dates = {getdate(je.posting_date) for je in posted_jes}

        # Generate breakdown rows
        start_date = getdate(start_date)
        for period_num in range(1, int(periods) + 1):
            # Calculate period date (start of each month)
            period_date = start_date + relativedelta(months=period_num - 1)

            # Determine period status
            period_status = get_period_status(period_date, today, posted_dates)

            # Create breakdown row
            breakdown_row = row.copy()
            breakdown_row.update({
                "period_number": period_num,
                "period_date": period_date,
                "period_amount": amount_per_period,
                "period_status": period_status,
                "indent": 1,  # Indent breakdown rows for visual hierarchy
            })

            result.append(breakdown_row)

    return result


def get_period_status(period_date, today, posted_dates) -> str:
    """Determine status of a period based on date and posting status.

    Returns:
        - Completed: Already posted to JE (Green)
        - Overdue: Past due but not posted (Red)
        - Progress: Current period (this month) (Blue)
        - Future: Future period (Grey)
    """
    period_date = getdate(period_date)

    # Check if already posted
    if period_date in posted_dates:
        return '<span class="indicator-pill green"><span class="indicator-dot"></span>Completed</span>'

    # Check if overdue (past date but not posted)
    if period_date < today:
        return '<span class="indicator-pill red"><span class="indicator-dot"></span>Overdue</span>'

    # Check if current month
    if period_date.year == today.year and period_date.month == today.month:
        return '<span class="indicator-pill blue"><span class="indicator-dot"></span>Progress</span>'

    # Future period
    return '<span class="indicator-pill gray"><span class="indicator-dot"></span>Future</span>'
