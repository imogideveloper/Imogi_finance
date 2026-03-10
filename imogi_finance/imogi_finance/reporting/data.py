from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from importlib import util as importlib_util
from typing import Iterable, Mapping, Sequence

import sys
import types

from imogi_finance.reporting.service import _as_amount, _normalise_direction


def _get_frappe():
    existing = sys.modules.get("frappe")
    if existing:
        return existing

    if importlib_util.find_spec("frappe"):
        import frappe  # type: ignore

        return frappe

    # Light stub for tests/offline usage
    fallback = sys.modules.setdefault(
        "frappe",
        types.SimpleNamespace(
            _=lambda msg, *args, **kwargs: msg,
            db=None,
            get_all=lambda *args, **kwargs: [],
            get_cached_doc=lambda *args, **kwargs: types.SimpleNamespace(),
        ),
    )
    if not hasattr(fallback, "db"):
        fallback.db = None
    return fallback


frappe = _get_frappe()
_ = getattr(frappe, "_", lambda msg, *args, **kwargs: msg)


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


def _coerce_list(value) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if v]


def _get_pi_description(row: Mapping[str, object]) -> str | None:
    return (
        row.get("remarks")
        or row.get("title")
        or row.get("bill_no")
        or row.get("name")
    )


def _load_expense_request_descriptions(er_names: Sequence[str]) -> dict[str, str]:
    """Load Expense Request descriptions."""
    if not er_names or not getattr(frappe, "db", None):
        return {}
    rows = frappe.get_all(
        "Expense Request",
        filters={"name": ("in", list(er_names))},
        fields=["name", "description"],
    )
    return {row["name"]: (row.get("description") or row["name"]) for row in rows if row.get("name")}


def _load_purchase_invoice_descriptions(names: Sequence[str]) -> dict[str, str]:
    if not names or not getattr(frappe, "db", None):
        return {}
    rows = frappe.get_all(
        "Purchase Invoice",
        filters={"name": ("in", list(names))},
        fields=["name", "remarks", "title", "bill_no", "imogi_expense_request"],
    )
    return {row["name"]: _get_pi_description(row) for row in rows if row.get("name")}


def _load_payment_entry_pi_map(payment_entries: Sequence[str]) -> dict[str, str]:
    if not payment_entries or not getattr(frappe, "db", None):
        return {}
    rows = frappe.get_all(
        "Payment Entry Reference",
        filters={"parent": ("in", list(payment_entries)), "reference_doctype": "Purchase Invoice"},
        fields=["parent", "reference_name"],
    )
    mapping: dict[str, str] = {}
    for row in rows:
        parent = row.get("parent")
        reference_name = row.get("reference_name")
        if parent and reference_name and parent not in mapping:
            mapping[parent] = reference_name
    return mapping


def fetch_bank_transactions(
    report_date: date | None,
    *,
    branches: Sequence[str] | None = None,
    bank_accounts: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Fetch bank transactions up to and including the report date."""

    if not getattr(frappe, "db", None):
        return []

    has_branch_column = True
    if hasattr(frappe.db, "has_column"):
        has_branch_column = frappe.db.has_column("Bank Transaction", "branch")

    filters = {}
    if report_date:
        filters["date"] = ("<=", report_date)
    branch_filter = _coerce_list(branches)
    if branch_filter and has_branch_column:
        filters["branch"] = ("in", branch_filter)
    bank_filter = _coerce_list(bank_accounts)
    if bank_filter:
        filters["bank_account"] = ("in", bank_filter)

    fields = [
        "name",
        "bank_account",
        "date",
        "deposit",
        "withdrawal",
        "reference_number",
        "description",
    ]
    if has_branch_column:
        fields.insert(1, "branch")

    rows = frappe.get_all(
        "Bank Transaction",
        filters=filters,
        fields=fields,
        order_by="date asc",
    )

    transactions: list[dict[str, object]] = []
    for row in rows:
        branch = row.get("branch") or "Unassigned"
        direction = "in" if _as_amount(row.get("deposit")) > 0 else "out"
        amount = _as_amount(row.get("deposit") or row.get("withdrawal"))
        transactions.append(
            {
                "branch": branch,
                "amount": amount,
                "direction": direction,
                "reference": row.get("reference_number") or row.get("name"),
                "posting_date": row.get("date"),
                "bank_account": row.get("bank_account"),
                "bt_description": row.get("description") or "",  # Bank Transaction description
            }
        )
    return transactions


def fetch_cash_ledger_entries(
    report_date: date | None,
    *,
    branches: Sequence[str] | None = None,
    cash_accounts: Sequence[str] | None = None,
) -> list[dict[str, object]]:
    """Fetch cash ledger entries up to and including the report date."""

    if not getattr(frappe, "db", None):
        return []

    account_filter = _coerce_list(cash_accounts)
    if not account_filter:
        return []

    has_branch_column = True
    if hasattr(frappe.db, "has_column"):
        has_branch_column = frappe.db.has_column("GL Entry", "branch")

    has_is_cancelled = True
    if hasattr(frappe.db, "has_column"):
        has_is_cancelled = frappe.db.has_column("GL Entry", "is_cancelled")

    filters = {"account": ("in", account_filter)}
    if report_date:
        filters["posting_date"] = ("<=", report_date)
    if has_is_cancelled:
        filters["is_cancelled"] = 0
    branch_filter = _coerce_list(branches)
    if branch_filter and has_branch_column:
        filters["branch"] = ("in", branch_filter)

    fields = [
        "name",
        "account",
        "posting_date",
        "debit",
        "credit",
        "voucher_no",
    ]
    if has_branch_column:
        fields.insert(1, "branch")

    rows = frappe.get_all(
        "GL Entry",
        filters=filters,
        fields=fields,
        order_by="posting_date asc",
    )

    transactions: list[dict[str, object]] = []
    for row in rows:
        debit = _as_amount(row.get("debit"))
        credit = _as_amount(row.get("credit"))
        direction = "in" if debit > 0 else "out"
        amount = debit if debit > 0 else credit
        transactions.append(
            {
                "branch": row.get("branch") or "Unassigned",
                "amount": amount,
                "direction": direction,
                "reference": row.get("voucher_no") or row.get("name"),
                "posting_date": row.get("posting_date"),
                "bank_account": row.get("account"),
            }
        )
    return transactions


def derive_opening_balances(
    transactions: Iterable[Mapping[str, object]], *, report_date: date | None
) -> dict[str, float]:
    """Compute opening balances per branch from transactions prior to the report date."""

    if not report_date:
        return {}

    openings: dict[str, float] = defaultdict(float)
    for tx in transactions:
        posting_date = _parse_date(tx.get("posting_date"))
        if posting_date and posting_date >= report_date:
            continue

        branch = str(tx.get("branch") or "Unassigned")
        amount = _as_amount(tx.get("amount"))
        direction = _normalise_direction(tx.get("direction"))
        signed = amount if direction == "in" else -amount
        openings[branch] += signed
    return dict(openings)


def get_previous_report_closing_balances(
    report_date: date,
    bank_account: str | None = None,
    cash_account: str | None = None,
) -> dict[str, float] | None:
    """Get closing balances from the previous day's report (if exists).

    Returns:
        dict[str, float]: Branch -> closing_balance mapping, or None if no previous report
    """
    if not getattr(frappe, "db", None):
        return None

    try:
        previous_date = report_date - timedelta(days=1)

        # Search for yesterday's report
        filters = {"report_date": previous_date}
        if bank_account:
            filters["bank_account"] = bank_account
        if cash_account:
            filters["cash_account"] = cash_account

        prev_reports = frappe.get_all(
            "Cash Bank Daily Report",
            filters=filters,
            fields=["name", "snapshot_json"],
            limit=1
        )

        if not prev_reports:
            return None

        snapshot_json = prev_reports[0].get("snapshot_json")
        if not snapshot_json:
            return None

        import json
        snapshot = json.loads(snapshot_json)
        branches = snapshot.get("branches") or []

        # Extract closing balances per branch
        balances = {}
        for br in branches:
            branch_name = br.get("branch")
            closing = _as_amount(br.get("closing_balance"))
            if branch_name:
                balances[branch_name] = closing

        return balances
    except Exception as e:
        frappe.log_error(f"Error fetching previous report: {e}", "Previous Report Lookup")
        return None


def load_daily_inputs(
    report_date: date | None,
    branches: Sequence[str] | None = None,
    bank_accounts: Sequence[str] | None = None,
    cash_accounts: Sequence[str] | None = None,
) -> tuple[list[dict[str, object]], dict[str, float]]:
    """Return (transactions_for_day, opening_balances) for daily reporting.

    Opening balances are derived from:
    1. Previous day's report closing balances (preferred)
    2. Cumulative transactions before report_date (fallback)
    """

    resolved_date = report_date or date.today()
    cash_filter = _coerce_list(cash_accounts)
    bank_filter = _coerce_list(bank_accounts)

    if cash_filter:
        all_transactions = fetch_cash_ledger_entries(
            resolved_date,
            branches=branches,
            cash_accounts=cash_filter,
        )
        account_for_lookup = cash_filter[0] if cash_filter else None
        is_cash = True
    else:
        all_transactions = fetch_bank_transactions(
            resolved_date,
            branches=branches,
            bank_accounts=bank_accounts,
        )
        account_for_lookup = bank_filter[0] if bank_filter else None
        is_cash = False

    day_transactions: list[dict[str, object]] = []
    for tx in all_transactions:
        posting_date = _parse_date(tx.get("posting_date"))
        if posting_date and posting_date != resolved_date:
            continue
        day_transactions.append(tx)

    references = [tx.get("reference") for tx in day_transactions if tx.get("reference")]
    reference_names = [str(ref) for ref in references if ref]

    # Load PI descriptions
    pi_direct_map = _load_purchase_invoice_descriptions(reference_names)

    # Load PE to PI mapping
    pe_to_pi = _load_payment_entry_pi_map(reference_names)
    pi_via_payment_map = _load_purchase_invoice_descriptions(list(pe_to_pi.values()))

    # Extract ER names from PIs
    all_pi_data = frappe.get_all(
        "Purchase Invoice",
        filters={"name": ("in", list(set(list(pi_direct_map.keys()) + list(pi_via_payment_map.keys()))))},
        fields=["name", "imogi_expense_request"]
    ) if frappe.db else []
    pi_to_er = {row["name"]: row.get("imogi_expense_request") for row in all_pi_data if row.get("imogi_expense_request")}
    er_names = list(set(pi_to_er.values()))
    er_descriptions = _load_expense_request_descriptions(er_names)

    for tx in day_transactions:
        amount = _as_amount(tx.get("amount"))
        direction = _normalise_direction(tx.get("direction"))
        reference = str(tx.get("reference") or "")

        # Get PI name
        pi_name = pi_direct_map.get(reference) and reference or pe_to_pi.get(reference)

        # Get PI description
        pi_description = pi_direct_map.get(reference) or pi_via_payment_map.get(pi_name) or ""

        # Get ER description if available
        er_name = pi_to_er.get(pi_name) if pi_name else None
        er_description = er_descriptions.get(er_name) if er_name else ""

        # Get BT description (from Bank Transaction itself)
        bt_description = tx.get("bt_description") or ""

        # Priority: ER description > PI description > BT description
        description = er_description or pi_description or bt_description

        tx["description"] = description
        tx["er_description"] = er_description  # Store separately for print format
        tx["pi_description"] = pi_description
        tx["bt_description"] = bt_description
        tx["deposit"] = amount if direction == "in" else 0.0
        tx["withdrawal"] = amount if direction == "out" else 0.0

    # Try to get opening balances from previous report first
    openings = None
    if is_cash:
        openings = get_previous_report_closing_balances(
            resolved_date, cash_account=account_for_lookup
        )
    else:
        openings = get_previous_report_closing_balances(
            resolved_date, bank_account=account_for_lookup
        )

    # Fallback: calculate from all transactions if no previous report
    if openings is None:
        openings = derive_opening_balances(all_transactions, report_date=resolved_date)
        # Log that we're using fallback calculation (informational, not an error)
        frappe.logger().info(
            f"[Cash Bank Report] No previous report found for {resolved_date}, "
            f"calculating opening balance from all transactions for account {account_for_lookup}"
        )

    return day_transactions, openings


def check_reporting_gaps(
    report_date: date,
    bank_account: str | None = None,
    cash_account: str | None = None,
    days_back: int = 7,
) -> list[str]:
    """Check for missing daily reports in the past N days.

    Returns:
        list[str]: List of dates (YYYY-MM-DD) with missing reports
    """
    if not getattr(frappe, "db", None):
        return []

    missing_dates = []
    for i in range(1, days_back + 1):
        check_date = report_date - timedelta(days=i)

        filters = {"report_date": check_date}
        if bank_account:
            filters["bank_account"] = bank_account
        if cash_account:
            filters["cash_account"] = cash_account

        exists = frappe.db.exists("Cash Bank Daily Report", filters)
        if not exists:
            missing_dates.append(check_date.isoformat())

    return missing_dates
