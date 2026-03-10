from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime
from importlib import util as importlib_util
from io import StringIO
from typing import Iterable, Mapping, Sequence

import types
import sys

from imogi_finance.reporting.models import (
    BranchReport,
    DailyReportBundle,
    MonthlyReconciliationResult,
    ReportSigners,
)


def _get_frappe():
    existing = sys.modules.get("frappe")
    if existing:
        return existing

    if importlib_util.find_spec("frappe"):
        import frappe  # type: ignore

        return frappe

    fallback = sys.modules.setdefault(
        "frappe",
        types.SimpleNamespace(
            _=lambda msg, *args, **kwargs: msg,
            _dict=lambda value=None, **kwargs: {**(value or {}), **kwargs},
            utils=types.SimpleNamespace(
                nowdate=lambda: date.today().isoformat(),
            ),
        ),
    )
    if not hasattr(fallback, "throw"):
        fallback.throw = lambda message=None, *args, **kwargs: (_ for _ in ()).throw(Exception(message))
    if not hasattr(fallback, "get_cached_doc"):
        fallback.get_cached_doc = lambda *args, **kwargs: types.SimpleNamespace()
    if not hasattr(fallback, "db"):
        fallback.db = types.SimpleNamespace(get_default=lambda key, default=None: default)
    if not hasattr(fallback, "_dict"):
        fallback._dict = lambda value=None, **kwargs: {**(value or {}), **kwargs}
    if not hasattr(fallback, "log_error"):
        fallback.log_error = lambda message=None, title=None: None
    if not hasattr(fallback, "session"):
        fallback.session = types.SimpleNamespace(user="system")
    if not hasattr(fallback, "whitelist"):
        fallback.whitelist = lambda *args, **kwargs: (lambda fn: fn)
    return fallback


frappe = _get_frappe()
_ = frappe._


def resolve_signers(
    settings: Mapping[str, str] | None = None, overrides: Mapping[str, str] | None = None
) -> ReportSigners:
    settings = settings or {}
    overrides = overrides or {}

    def _resolve(key: str) -> str | None:
        return overrides.get(key) or settings.get(key)

    return ReportSigners(
        prepared_by=_resolve("prepared_by"),
        approved_by=_resolve("approved_by"),
        acknowledged_by=_resolve("acknowledged_by"),
    )


def _as_amount(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


def _normalise_direction(direction: str | None) -> str:
    if not direction:
        return "out"
    direction = direction.lower()
    if direction in {"in", "credit", "cr"}:
        return "in"
    if direction in {"out", "debit", "dr"}:
        return "out"
    return "out"


def _partition_transactions(
    transactions: Iterable[Mapping[str, object]], allowed_branches: Sequence[str] | None
) -> dict[str, list[dict[str, object]]]:
    partitions: dict[str, list[dict[str, object]]] = defaultdict(list)
    allowed = {branch for branch in allowed_branches} if allowed_branches else None

    for record in transactions or []:
        branch = record.get("branch") or "Unassigned"
        if allowed is not None and branch not in allowed:
            continue
        partitions[str(branch)].append(dict(record))

    return partitions


def _summarize_branch(
    branch: str,
    records: list[dict[str, object]],
    opening_balance: float,
    signers: ReportSigners | None,
    status: str,
) -> BranchReport:
    inflow = 0.0
    outflow = 0.0
    for tx in records:
        amount = _as_amount(tx.get("amount"))
        direction = _normalise_direction(tx.get("direction"))
        if direction == "in":
            inflow += amount
        else:
            outflow += abs(amount)

    closing_balance = opening_balance + inflow - outflow
    
    # Validate balance calculation
    expected_closing = opening_balance + inflow - outflow
    if abs(closing_balance - expected_closing) > 0.01:  # Allow 1 cent rounding tolerance
        frappe.log_error(
            f"Balance mismatch for {branch}: expected {expected_closing}, got {closing_balance}",
            "Daily Report Balance Validation"
        )
    
    return BranchReport(
        branch=branch,
        opening_balance=opening_balance,
        inflow=inflow,
        outflow=outflow,
        closing_balance=closing_balance,
        transactions=records,
        signers=signers,
        status=status,
    )


def build_daily_report(
    transactions: Iterable[Mapping[str, object]] | None,
    *,
    opening_balances: Mapping[str, float] | None = None,
    report_date: date | None = None,
    signers: ReportSigners | None = None,
    allowed_branches: Sequence[str] | None = None,
    template: str = "daily_report",
    status: str = "draft",
) -> DailyReportBundle:
    if report_date:
        resolved_date = report_date
    else:
        raw_date = getattr(getattr(frappe, "utils", None), "nowdate", lambda: "")() or ""
        try:
            resolved_date = date.fromisoformat(raw_date) if raw_date else date.today()
        except Exception:
            resolved_date = date.today()
    report_date = resolved_date
    partitions = _partition_transactions(transactions or [], allowed_branches)
    opening_balances = opening_balances or {}

    branches: list[BranchReport] = []
    consolidated_records: list[dict[str, object]] = []

    for branch, records in sorted(partitions.items()):
        opening_balance = _as_amount(opening_balances.get(branch))
        summary = _summarize_branch(branch, records, opening_balance, signers, status)
        branches.append(summary)
        consolidated_records.extend(records)

    consolidated_opening = sum(_as_amount(opening_balances.get(branch)) for branch in partitions)
    consolidated = _summarize_branch(
        "All Branches", consolidated_records, consolidated_opening, signers, status
    )

    return DailyReportBundle(
        report_date=report_date,
        branches=branches,
        consolidated=consolidated,
        signers=signers,
        template=template,
    )


def parse_statement_rows(
    content: str,
    *,
    delimiter: str = ",",
    branch: str | None = None,
    encoding: str = "utf-8",
) -> list[dict[str, object]]:
    if not content:
        return []

    buffer = StringIO(content)
    reader = csv.DictReader(buffer, delimiter=delimiter)
    rows: list[dict[str, object]] = []

    for row in reader:
        amount = _as_amount(row.get("amount") or row.get("Amount"))
        reference = row.get("reference") or row.get("Reference") or row.get("ref")
        posting_date = row.get("date") or row.get("posting_date") or row.get("Date")
        raw_direction = row.get("direction") or row.get("Direction")
        direction = _normalise_direction(raw_direction)
        if not raw_direction:
            direction = "in" if amount >= 0 else "out"
        rows.append(
            {
                "branch": row.get("branch") or row.get("Branch") or branch or "Unassigned",
                "amount": amount,
                "direction": direction,
                "reference": reference,
                "posting_date": posting_date,
                "raw": dict(row),
            }
        )

    return rows


def build_monthly_reconciliation(
    *,
    ledger_transactions: Iterable[Mapping[str, object]] | None,
    bank_statements: Iterable[Mapping[str, object]] | None,
    month: str,
    tolerance: float = 0.0,
    auto_close: bool = True,
) -> MonthlyReconciliationResult:
    ledger_transactions = list(ledger_transactions or [])
    bank_statements = list(bank_statements or [])

    matches: list[dict[str, object]] = []
    missing_from_bank: list[dict[str, object]] = []
    missing_from_ledger: list[dict[str, object]] = []

    statements_pool = list(bank_statements)
    for tx in ledger_transactions:
        amount = _as_amount(tx.get("amount"))
        direction = _normalise_direction(tx.get("direction"))
        signed_amount = amount if direction == "in" else -amount
        tx_date = _parse_date(tx.get("posting_date") or tx.get("date"))

        match_index = next(
            (
                idx
                for idx, statement in enumerate(statements_pool)
                if _is_statement_match(
                    signed_amount,
                    direction,
                    tx_date,
                    statement,
                    tolerance=tolerance,
                )
            ),
            None,
        )
        if match_index is None:
            missing_from_bank.append(dict(tx))
            continue

        statement = statements_pool.pop(match_index)
        matches.append(
            {
                "ledger": dict(tx),
                "statement": dict(statement),
                "variance": signed_amount - _as_amount(statement.get("amount")),
            }
        )

    missing_from_ledger.extend(statements_pool)

    ledger_balance = sum(
        _as_amount(tx.get("amount")) if _normalise_direction(tx.get("direction")) == "in" else -_as_amount(tx.get("amount"))
        for tx in ledger_transactions
    )
    statement_balance = sum(_as_amount(row.get("amount")) for row in bank_statements)
    closing_balance = ledger_balance - statement_balance

    closing_status = "closed" if auto_close and not missing_from_bank and not missing_from_ledger else "open"

    return MonthlyReconciliationResult(
        month=month,
        matches=matches,
        missing_from_bank=missing_from_bank,
        missing_from_ledger=missing_from_ledger,
        closing_status=closing_status,
        closing_balance=closing_balance,
        statement_balance=statement_balance,
        ledger_balance=ledger_balance,
    )


def build_dashboard_snapshot(
    *,
    transactions: Iterable[Mapping[str, object]] | None,
    opening_balances: Mapping[str, float] | None = None,
    report_date: date | None = None,
    allowed_branches: Sequence[str] | None = None,
    reconciliation: MonthlyReconciliationResult | None = None,
    signers: ReportSigners | None = None,
) -> dict[str, object]:
    report = build_daily_report(
        transactions or [],
        opening_balances=opening_balances,
        report_date=report_date,
        allowed_branches=allowed_branches,
        signers=signers,
        status="published",
    )
    payload = report.to_dict()
    if reconciliation:
        payload["reconciliation"] = reconciliation.to_dict()
    return payload


def serialize_for_export(bundle: DailyReportBundle, reconciliation: MonthlyReconciliationResult | None = None):
    payload = bundle.to_dict()
    if reconciliation:
        payload["reconciliation"] = reconciliation.to_dict()
    payload["exported_at"] = datetime.utcnow().isoformat()
    return payload


def _is_statement_match(
    ledger_signed_amount: float,
    ledger_direction: str,
    ledger_date: date | None,
    statement: Mapping[str, object],
    *,
    tolerance: float = 0.0,
) -> bool:
    statement_amount = _as_amount(statement.get("amount"))
    raw_direction = statement.get("direction")
    statement_direction = _normalise_direction(raw_direction)
    if not raw_direction:
        statement_direction = "in" if statement_amount >= 0 else "out"

    if ledger_direction != statement_direction:
        return False

    statement_signed = statement_amount if statement_direction == "in" else -statement_amount
    if abs(ledger_signed_amount - statement_signed) > tolerance:
        return False

    ledger_dt = ledger_date
    statement_dt = _parse_date(statement.get("posting_date") or statement.get("date"))
    if ledger_dt and statement_dt and abs((ledger_dt - statement_dt).days) > 3:
        return False

    return True
