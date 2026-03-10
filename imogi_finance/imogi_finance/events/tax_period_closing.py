# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""Event handlers for Tax Period Closing doctype.

These handlers are called via hooks.py doc_events and provide:
- Additional validation on period completeness
- Pre-submit checks
- Post-submission notifications
- Cancellation cleanup
"""

from __future__ import annotations

import frappe
from frappe import _


def validate_period_completeness(doc, method=None):
    """Validate period data completeness during save.

    Non-blocking validation that provides warnings for potential issues.

    Args:
        doc: Tax Period Closing document
        method: Hook method name (unused)
    """
    # Skip if new document or missing required fields
    if doc.is_new() or not doc.company or not doc.date_from:
        return

    # Check if snapshot is stale (older than last modification of invoices)
    if doc.register_snapshot and doc.last_refresh_on:
        # Get latest invoice modification in period
        latest_pi = frappe.db.get_value(
            "Purchase Invoice",
            {
                "company": doc.company,
                "posting_date": ["between", [doc.date_from, doc.date_to]],
                "docstatus": ["!=", 2]
            },
            "modified",
            order_by="modified desc"
        )

        latest_si = frappe.db.get_value(
            "Sales Invoice",
            {
                "company": doc.company,
                "posting_date": ["between", [doc.date_from, doc.date_to]],
                "docstatus": ["!=", 2]
            },
            "modified",
            order_by="modified desc"
        )

        latest_invoice_mod = max(
            [m for m in [latest_pi, latest_si] if m],
            default=None
        )

        # Convert both to datetime for comparison
        from frappe.utils import get_datetime
        last_refresh = get_datetime(doc.last_refresh_on) if doc.last_refresh_on else None

        if latest_invoice_mod and last_refresh and latest_invoice_mod > last_refresh:
            frappe.msgprint(
                _("Warning: Invoices have been modified after the last snapshot refresh. "
                  "Consider refreshing the tax registers."),
                title=_("Stale Snapshot"),
                indicator="orange"
            )


def before_submit_checks(doc, method=None):
    """Perform comprehensive checks before allowing submission.

    Ensures period is ready to be closed and locked.

    Args:
        doc: Tax Period Closing document
        method: Hook method name (unused)
    """
    # Ensure snapshot exists and is recent
    if not doc.register_snapshot:
        frappe.throw(
            _("Cannot submit without tax register snapshot. Please refresh registers first."),
            title=_("Missing Snapshot")
        )

    # Check for recommended workflow progression
    if doc.status not in ["Approved", "Closed"]:
        frappe.msgprint(
            _("Recommended to set status to 'Approved' before submission. "
              "Current status: {0}").format(doc.status),
            title=_("Status Recommendation"),
            indicator="orange"
        )


def on_period_closed(doc, method=None):
    """Actions to perform when a period is closed (submitted).

    - Log period closure
    - Send notification to stakeholders
    - Update related records

    Args:
        doc: Tax Period Closing document
        method: Hook method name (unused)
    """
    # Log the closure
    frappe.logger().info(
        f"Tax Period Closing: {doc.name} submitted for {doc.company} "
        f"period {doc.period_month}/{doc.period_year}"
    )

    # Create notification for accounting team
    notify_period_closure(doc)

    # Add comment to document
    doc.add_comment(
        "Info",
        _("Tax period {0}-{1} has been closed and locked. "
          "Tax invoice fields can no longer be edited for this period.").format(
            doc.period_month,
            doc.period_year
        )
    )


def on_period_reopened(doc, method=None):
    """Actions to perform when a period is reopened (cancelled).

    - Log period reopening
    - Notify stakeholders
    - Validate linked entries

    Args:
        doc: Tax Period Closing document
        method: Hook method name (unused)
    """
    # Log the reopening
    frappe.logger().warning(
        f"Tax Period Closing: {doc.name} cancelled for {doc.company} "
        f"period {doc.period_month}/{doc.period_year} by {frappe.session.user}"
    )

    # Notify accounting team
    notify_period_reopening(doc)

    # Add comment
    doc.add_comment(
        "Info",
        _("Tax period {0}-{1} has been reopened. "
          "Tax invoices for this period can now be edited again.").format(
            doc.period_month,
            doc.period_year
        )
    )


def notify_period_closure(doc):
    """Send email notification about period closure.

    Notifies Accounts Manager and Tax Reviewer roles.

    Args:
        doc: Tax Period Closing document
    """
    # Get users with relevant roles
    recipients = get_users_with_roles(["Accounts Manager", "Tax Reviewer"])

    if not recipients:
        return

    # Build notification message
    message = _build_closure_notification_html(doc)

    # Send email
    try:
        frappe.sendmail(
            recipients=recipients,
            subject=_("Tax Period Closed: {0} {1}-{2}").format(
                doc.company,
                doc.period_month,
                doc.period_year
            ),
            message=message,
            delayed=False,
            reference_doctype=doc.doctype,
            reference_name=doc.name
        )
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Tax Period Closing: Email Notification Failed"
        )


def notify_period_reopening(doc):
    """Send email notification about period reopening.

    Args:
        doc: Tax Period Closing document
    """
    recipients = get_users_with_roles(["Accounts Manager", "Tax Reviewer"])

    if not recipients:
        return

    message = _build_reopening_notification_html(doc)

    try:
        frappe.sendmail(
            recipients=recipients,
            subject=_("Tax Period Reopened: {0} {1}-{2}").format(
                doc.company,
                doc.period_month,
                doc.period_year
            ),
            message=message,
            delayed=False,
            reference_doctype=doc.doctype,
            reference_name=doc.name
        )
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Tax Period Closing: Email Notification Failed"
        )


def get_users_with_roles(roles: list) -> list:
    """Get list of user emails with specified roles.

    Args:
        roles: List of role names

    Returns:
        list: User email addresses
    """
    if not roles:
        return []

    users = frappe.get_all(
        "Has Role",
        filters={
            "role": ["in", roles],
            "parenttype": "User"
        },
        fields=["parent as user"],
        distinct=True
    )

    # Get active user emails
    user_list = [u.user for u in users]

    if not user_list:
        return []

    emails = frappe.get_all(
        "User",
        filters={
            "name": ["in", user_list],
            "enabled": 1,
            "email": ["is", "set"]
        },
        pluck="email"
    )

    return emails


def _build_closure_notification_html(doc) -> str:
    """Build HTML email for period closure notification.

    Args:
        doc: Tax Period Closing document

    Returns:
        str: HTML email content
    """
    from frappe.utils import fmt_money

    return f"""
    <div style="font-family: Arial, sans-serif;">
        <h2 style="color: #2490EF;">Tax Period Closed</h2>

        <p>The tax period has been successfully closed with the following details:</p>

        <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Company:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{doc.company}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Period:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{doc.period_month}/{doc.period_year}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Date Range:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{doc.date_from} to {doc.date_to}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Input VAT:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{fmt_money(doc.input_vat_total or 0)}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Output VAT:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{fmt_money(doc.output_vat_total or 0)}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>VAT Net:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>{fmt_money(doc.vat_net or 0)}</strong></td>
            </tr>
        </table>

        <p style="color: #666;">
            <strong>Note:</strong> This period is now locked. Tax invoice fields cannot be edited
            for Purchase Invoices, Sales Invoices, and Expense Requests in this period.
        </p>

        <p>
            <a href="{frappe.utils.get_url()}/app/tax-period-closing/{doc.name}"
               style="background-color: #2490EF; color: white; padding: 10px 20px;
                      text-decoration: none; border-radius: 4px; display: inline-block;">
                View Tax Period Closing
            </a>
        </p>
    </div>
    """


def _build_reopening_notification_html(doc) -> str:
    """Build HTML email for period reopening notification.

    Args:
        doc: Tax Period Closing document

    Returns:
        str: HTML email content
    """
    return f"""
    <div style="font-family: Arial, sans-serif;">
        <h2 style="color: #F56B2A;">Tax Period Reopened</h2>

        <p><strong>ATTENTION:</strong> A previously closed tax period has been reopened.</p>

        <table style="border-collapse: collapse; width: 100%; margin: 20px 0;">
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Company:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{doc.company}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Period:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{doc.period_month}/{doc.period_year}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Date Range:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{doc.date_from} to {doc.date_to}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;"><strong>Reopened By:</strong></td>
                <td style="padding: 8px; border: 1px solid #ddd;">{frappe.session.user}</td>
            </tr>
        </table>

        <p style="color: #666;">
            Tax invoices for this period can now be edited again. Please ensure proper
            authorization and documentation for any changes made to this period.
        </p>

        <p>
            <a href="{frappe.utils.get_url()}/app/tax-period-closing/{doc.name}"
               style="background-color: #F56B2A; color: white; padding: 10px 20px;
                      text-decoration: none; border-radius: 4px; display: inline-block;">
                View Tax Period Closing
            </a>
        </p>
    </div>
    """
