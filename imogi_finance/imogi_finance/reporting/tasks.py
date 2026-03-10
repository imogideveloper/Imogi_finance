"""Scheduled tasks for multi-branch reporting.

These callables are wired into Frappe's scheduler via hooks.py and run
daily/monthly reports automatically.
"""

from __future__ import annotations

from datetime import date

import frappe
from frappe import _

from imogi_finance.reporting.data import load_daily_inputs
from imogi_finance.reporting.service import build_daily_report, resolve_signers
from imogi_finance.settings.utils import get_finance_control_settings


def run_daily_reporting(branches: list[str] | None = None) -> None:
    """Generate and store daily cash/bank reports for all companies.

    Called by Frappe scheduler (daily). Can optionally filter by branches.
    """
    try:
        report_date = date.today()

        # Load settings for signers (use same field names as api/reporting.py)
        settings_doc = get_finance_control_settings()
        signers_dict = {
            "prepared_by": getattr(settings_doc, "daily_report_preparer", None),
            "approved_by": getattr(settings_doc, "daily_report_approver", None),
            "acknowledged_by": getattr(settings_doc, "daily_report_acknowledger", None),
        }
        signers = resolve_signers(settings=signers_dict)

        # Load transactions and build report
        transactions, opening_balances = load_daily_inputs(
            report_date=report_date,
            branches=branches,
        )

        bundle = build_daily_report(
            transactions=transactions,
            opening_balances=opening_balances,
            report_date=report_date,
            signers=signers,
            allowed_branches=branches,
            status="published",
        )

        frappe.logger().info(
            f"Daily reporting completed for {report_date.isoformat()}: "
            f"{len(bundle.branches)} branches, "
            f"consolidated balance: {bundle.consolidated.closing_balance}"
        )

    except Exception as e:
        frappe.logger().error(f"Daily reporting task failed: {e}", exc_info=True)
        # Don't re-raise to avoid stopping scheduler


def run_monthly_reconciliation() -> None:
    """Run monthly bank reconciliation for the previous month.

    Called by Frappe scheduler (monthly, typically on the 1st of each month).
    Compares ledger transactions with bank statements.
    """
    try:
        from calendar import monthrange
        from datetime import datetime

        # Target the previous month
        today = date.today()
        if today.month == 1:
            target_year = today.year - 1
            target_month = 12
        else:
            target_year = today.year
            target_month = today.month - 1

        month_key = f"{target_year}-{target_month:02d}"
        _, last_day = monthrange(target_year, target_month)
        month_end = date(target_year, target_month, last_day)

        # Load ledger transactions for the month
        transactions, _ = load_daily_inputs(report_date=month_end)

        # Note: Bank statements would need to be imported separately
        # via BCA Bank Statement Import or manual upload.
        # For now, we just log that reconciliation is due.

        frappe.logger().info(
            f"Monthly reconciliation check for {month_key}: "
            f"{len(transactions)} transactions found. "
            f"Import bank statements to complete reconciliation."
        )

        # Future enhancement: auto-fetch bank statements if integration exists

    except Exception as e:
        frappe.logger().error(f"Monthly reconciliation task failed: {e}", exc_info=True)
        # Don't re-raise to avoid stopping scheduler
