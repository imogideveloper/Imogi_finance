from __future__ import annotations

import json
from typing import List, Optional

import frappe
from frappe.model.document import Document

from imogi_finance.api import reporting as reporting_api


class CashBankDailyReport(Document):
    """Persistent wrapper around the daily cash/bank report.

    A document stores the input parameters (date, optional branches filter)
    and a JSON snapshot of the generated report so it can be printed or
    re-opened later without recomputing everything.

    Uses Frappe native workflow with states:
    - Draft: Initial state
    - Generated: Snapshot created, can be regenerated
    - Approved: Reviewed by manager, ready to print
    - Printed: Submitted (docstatus=1), locked from modifications
    - Cancelled: Cancelled (docstatus=2)

    Supports multiple reprints with tracking.
    """

    @property
    def is_submitted(self) -> bool:
        """Check if report has been submitted (Printed state)."""
        return getattr(self, "docstatus", 0) == 1

    @property
    def snapshot_data(self) -> dict:
        """Parse and return snapshot JSON as dictionary.

        This property is used in print formats to access the parsed data
        without needing custom Jinja filters.

        Returns:
            dict: Parsed snapshot data with keys: consolidated, branches, signers
        """
        if not self.snapshot_json:
            return {}

        try:
            return json.loads(self.snapshot_json)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    def validate(self):
        # Global "view only" switch from Finance Control Settings
        if self.is_new() and self._is_view_only_mode():
            frappe.throw(
                frappe._(
                    "Cash/Bank Daily Report is currently in view-only mode. New reports cannot be created."
                )
            )
        self._validate_account_selection()
        # Ensure one report per date + bank account
        self._validate_unique_per_account_and_date()
        # Ensure we don't skip previous dates that already have transactions
        self._validate_no_gaps_in_transaction_dates()

    def before_insert(self):
        # Auto-generate snapshot on first insert if report_date is set
        if self.report_date:
            self.generate_snapshot()
        # Auto-set created_by_user if not set
        if not self.created_by_user:
            self.created_by_user = frappe.session.user

    def on_update(self):
        # If user changes the date or branches on an existing doc, refresh
        # Only allow if not yet submitted
        if (self.has_value_changed("report_date") or self.has_value_changed("branches")):
            if self.is_submitted:
                frappe.throw(
                    frappe._(
                        "Cannot modify a submitted report. Cancel and create a new one if needed."
                    )
                )
            if self.report_date:
                self.generate_snapshot()

    def on_submit(self):
        """Called when report is submitted (transitioned to Printed state).

        Records first print timestamp if this is the first print.
        """
        if not self.first_printed_at:
            self.first_printed_at = frappe.utils.now_datetime()
            self.first_printed_by = frappe.session.user
            self._add_print_event("First Print")

    def on_cancel(self):
        """Called when report is cancelled.

        Validates that no related Payment Entries are dependent on this report.
        """
        # Check if any Payment Entries reference this report date
        posting_date = self.report_date
        account = self.cash_account or self.bank_account

        if account:
            pe_count = frappe.db.count(
                "Payment Entry",
                filters={
                    "posting_date": posting_date,
                    "docstatus": 1,
                    # Check if PE account matches report account
                }
            )

            if pe_count > 0:
                frappe.msgprint(
                    frappe._(
                        "Warning: There are {0} submitted Payment Entries on this date. "
                        "Cancelling this report does not affect those transactions."
                    ).format(pe_count),
                    indicator="orange",
                    alert=True
                )

    def before_workflow_action(self, workflow_state_field=None, action=None, workflow_state=None):
        """Validate workflow actions based on Finance Control Settings.

        - Approve: Must be done by designated approver from settings
        - Print & Lock: Must be done by designated approver or System Manager
        """
        if action == "Approve":
            self._validate_approver()
        elif action == "Print & Lock":
            self._validate_print_permission()

    def _validate_approver(self):
        """Validate that current user is authorized to approve this report.

        Checks:
        1. Per-account rules in Finance Control Settings (daily_report_signer_rules)
        2. Global approver (daily_report_approver)
        3. System Manager (always allowed)
        """
        current_user = frappe.session.user

        # System Manager can always approve
        if "System Manager" in frappe.get_roles():
            return

        # Get Finance Control Settings
        from imogi_finance.settings.utils import get_finance_control_settings
        settings = get_finance_control_settings()

        # Check per-account rules first
        account = self.bank_account or self.cash_account
        if account and settings.daily_report_signer_rules:
            for rule in settings.daily_report_signer_rules:
                if rule.account == account:
                    if rule.approved_by == current_user:
                        return
                    elif rule.approved_by:
                        frappe.throw(
                            frappe._(
                                "Only {0} is authorized to approve reports for account {1}"
                            ).format(rule.approved_by, account)
                        )

        # Check global approver
        if settings.daily_report_approver:
            if settings.daily_report_approver == current_user:
                return
            else:
                frappe.throw(
                    frappe._(
                        "Only {0} is authorized to approve daily reports. "
                        "Configure approvers in Finance Control Settings."
                    ).format(settings.daily_report_approver)
                )

        # No approver configured - require Accounts Manager role
        if "Accounts Manager" not in frappe.get_roles():
            frappe.throw(
                frappe._(
                    "Accounts Manager role required to approve daily reports. "
                    "Or configure specific approvers in Finance Control Settings."
                )
            )

    def _validate_print_permission(self):
        """Validate that current user can print & lock this report.

        Same validation as approve - must be authorized approver.
        """
        self._validate_approver()

    def _parse_branches_filter(self) -> Optional[List[str]]:
        if not self.branches:
            return None
        # Simple comma-separated list of branch names
        items = [b.strip() for b in (self.branches or "").split(",")]
        return [b for b in items if b]

    def _is_view_only_mode(self) -> bool:
        try:
            from imogi_finance.settings.utils import get_finance_control_settings
            settings = get_finance_control_settings()
        except Exception:
            return False
        return bool(getattr(settings, "daily_report_view_only", 0))

    def _validate_unique_per_account_and_date(self) -> None:
        account_field = None
        account_value = None
        if self.bank_account:
            account_field = "bank_account"
            account_value = self.bank_account
        elif self.cash_account:
            account_field = "cash_account"
            account_value = self.cash_account

        if not self.report_date or not account_field or not account_value:
            return

        existing = frappe.db.exists(
            "Cash Bank Daily Report",
            {
                "report_date": self.report_date,
                account_field: account_value,
                "name": ("!=", self.name) if self.name else ("!=" , ""),
            },
        )
        if existing:
            frappe.throw(
                frappe._(
                    "Daily report for account {0} on {1} already exists (document: {2})."
                ).format(
                    account_value,
                    frappe.utils.format_date(self.report_date),
                    existing,
                )
            )

    def _validate_account_selection(self) -> None:
        if self.bank_account and self.cash_account:
            frappe.throw(
                frappe._(
                    "Cannot select both Bank Account and Cash Account. "
                    "Use Bank Account for imported transactions, or Cash Account for ledger-based reporting."
                )
            )

    def _validate_no_gaps_in_transaction_dates(self) -> None:
        """Block creating a report for a date if the immediately previous
        transaction date for this account does not yet have a report.

        This enforces sequential daily reports whenever there are
        consecutive Bank Transactions.

        Note: This validation only applies to Bank Account mode.
        Cash Account mode (via GL Entry) does not require sequential validation
        as GL entries are more flexible and can be posted retroactively.
        """

        if not self.report_date or not self.bank_account or not getattr(frappe, "db", None):
            return

        # Find the latest Bank Transaction date before this report date
        prev_tx = frappe.get_all(
            "Bank Transaction",
            filters={
                "bank_account": self.bank_account,
                "date": ("<", self.report_date),
            },
            fields=["date"],
            order_by="date desc",
            limit=1,
        )

        if not prev_tx:
            return

        prev_date = prev_tx[0].get("date")
        if not prev_date:
            return

        has_prev_report = frappe.db.exists(
            "Cash Bank Daily Report",
            {"bank_account": self.bank_account, "report_date": prev_date},
        )
        if not has_prev_report:
            frappe.throw(
                frappe._(
                    "Cannot create daily report for {0} on {1} because there is no report for the previous transaction date {2}."
                ).format(
                    self.bank_account,
                    frappe.utils.format_date(self.report_date),
                    frappe.utils.format_date(prev_date),
                )
            )

    def generate_snapshot(self):
        branches = self._parse_branches_filter()
        report_date_str = (
            self.report_date if isinstance(self.report_date, str) else self.report_date.isoformat()
        )

        # Check if previous report exists
        from datetime import timedelta
        from imogi_finance.reporting.data import get_previous_report_closing_balances

        if isinstance(self.report_date, str):
            from datetime import date as date_class
            report_date_obj = date_class.fromisoformat(self.report_date)
        else:
            report_date_obj = self.report_date

        prev_balances = None
        if self.bank_account:
            prev_balances = get_previous_report_closing_balances(
                report_date_obj, bank_account=self.bank_account
            )
        elif self.cash_account:
            prev_balances = get_previous_report_closing_balances(
                report_date_obj, cash_account=self.cash_account
            )

        if prev_balances:
            self.opening_source = "Previous Report"
        else:
            self.opening_source = "Calculated from Transactions"
            # Show info message for Bank Account (required sequential)
            if self.bank_account:
                # Check for gaps in reporting
                from imogi_finance.reporting.data import check_reporting_gaps
                missing = check_reporting_gaps(
                    report_date_obj, bank_account=self.bank_account, days_back=7
                )
                if missing:
                    frappe.msgprint(
                        frappe._(
                            "⚠️ No previous report found. Missing reports for dates: {0}. "
                            "Opening balance calculated from all transactions instead of previous closing."
                        ).format(", ".join(missing[:3]) + ("..." if len(missing) > 3 else "")),
                        indicator="orange",
                        alert=True
                    )
                else:
                    frappe.msgprint(
                        frappe._(
                            "No previous report found for {0}. Opening balance calculated from all transactions."
                        ).format(frappe.utils.format_date(report_date_obj - timedelta(days=1))),
                        indicator="blue",
                        alert=True
                    )

        payload = reporting_api.preview_daily_report(
            branches=branches,
            bank_account=self.bank_account or None,
            cash_account=self.cash_account or None,
            report_date=report_date_str,
        )

        # Store full JSON snapshot for print formats / APIs
        self.snapshot_json = frappe.as_json(payload)
        self.status = "Generated"

        # Set report type based on account selection
        if self.cash_account:
            self.report_type = "Cash Ledger (GL Entry)"
        elif self.bank_account:
            self.report_type = "Bank Transaction"
        else:
            self.report_type = ""

        # Also copy consolidated totals into top-level currency fields (if present)
        consolidated = (payload or {}).get("consolidated") or {}
        self.opening_balance = consolidated.get("opening_balance") or 0
        self.inflow = consolidated.get("inflow") or 0
        self.outflow = consolidated.get("outflow") or 0
        self.closing_balance = consolidated.get("closing_balance") or 0

        # Validate balance calculation
        expected_closing = self.opening_balance + self.inflow - self.outflow
        tolerance = 0.01  # 1 cent tolerance for rounding

        if abs(self.closing_balance - expected_closing) <= tolerance:
            self.balance_status = "Balanced"
        else:
            self.balance_status = "Mismatch"
            frappe.msgprint(
                frappe._(
                    "Warning: Balance mismatch detected. Expected closing: {0}, Actual: {1}. "
                    "Please review the transactions."
                ).format(
                    frappe.format(expected_closing, {"fieldtype": "Currency"}),
                    frappe.format(self.closing_balance, {"fieldtype": "Currency"})
                ),
                indicator="orange",
                alert=True
            )


@frappe.whitelist()
def regenerate(name: str):
    """Explicit API to regenerate a report snapshot for an existing document.

    Can be wired to a custom button on the DocType.

    Note: Blocked if report has been submitted (docstatus=1).
    """

    doc = frappe.get_doc("Cash Bank Daily Report", name)

    # Check if report is submitted
    if doc.is_submitted:
        frappe.throw(
            frappe._(
                "Cannot regenerate a submitted report. Report was printed on {0} by {1}."
            ).format(
                frappe.utils.format_datetime(doc.first_printed_at) if doc.first_printed_at else "unknown",
                doc.first_printed_by or "unknown user"
            )
        )

    if not doc.report_date:
        frappe.throw("Report Date is required to regenerate the snapshot")

    doc.generate_snapshot()
    doc.save()

    frappe.msgprint(
        frappe._("Report snapshot regenerated successfully"),
        indicator="green"
    )

    return doc


@frappe.whitelist()
def reprint(name: str):
    """Record a reprint event for tracking purposes.

    This is called when user clicks the Reprint button.
    Does NOT regenerate snapshot - uses existing data.
    Only tracks the reprint event for audit trail.
    """
    doc = frappe.get_doc("Cash Bank Daily Report", name)

    if not doc.is_submitted:
        frappe.throw(
            frappe._("Can only reprint submitted reports. Please submit the report first.")
        )

    # Increment reprint counter
    doc.reprint_count = (doc.reprint_count or 0) + 1
    doc.last_reprinted_at = frappe.utils.now_datetime()
    doc.last_reprinted_by = frappe.session.user

    # Add to print history
    doc._add_print_event(f"Reprint #{doc.reprint_count}")

    # Save without triggering workflow
    doc.save(ignore_permissions=True)

    frappe.msgprint(
        frappe._(
            "Reprint #{0} recorded. Opening print view..."
        ).format(doc.reprint_count),
        indicator="blue"
    )

    return doc


def _add_print_event(self, event_type: str):
    """Add a print/reprint event to the print history."""
    import json

    history = []
    if self.print_history:
        try:
            history = json.loads(self.print_history)
        except Exception:
            history = []

    history.append({
        "event": event_type,
        "timestamp": frappe.utils.now_datetime().isoformat(),
        "user": frappe.session.user
    })

    self.print_history = json.dumps(history, indent=2)


# Add method to Document class
CashBankDailyReport._add_print_event = _add_print_event


# Remove old mark_as_printed - now handled by workflow submit
