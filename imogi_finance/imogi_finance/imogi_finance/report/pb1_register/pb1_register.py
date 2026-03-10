from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from imogi_finance.branching import get_branch_settings
from imogi_finance.tax_operations import _get_tax_profile


def execute(filters=None):
    filters = filters or {}
    company = filters.get("company")
    if not company:
        frappe.throw(_("Company is required"))

    profile = _get_tax_profile(company)
    branch = filters.get("branch")
    
    # Get PB1 account based on branch if multi-branch enabled
    if branch and hasattr(profile, "get_pb1_account"):
        pb1_account = profile.get_pb1_account(branch)
    else:
        pb1_account = filters.get("pb1_account") or getattr(profile, "pb1_payable_account", None)
    
    # Check if multi-branch is enabled
    branch_settings = get_branch_settings()
    show_branch_column = branch_settings.enable_multi_branch

    columns = _build_columns(show_branch_column)
    entries = _get_entries(company, pb1_account, filters.get("from_date"), filters.get("to_date"))
    return columns, entries


def _build_columns(show_branch: bool = False) -> list[dict]:
    """Build column definitions with optional branch column."""
    columns = [
        {"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 180},
    ]
    
    if show_branch:
        columns.append(
            {"label": _("Branch"), "fieldname": "branch", "fieldtype": "Data", "width": 120}
        )
    
    columns.extend([
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 130},
        {"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 140},
        {"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "width": 110},
        {"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "width": 110},
        {"label": _("Net (Credit-Debit)"), "fieldname": "net_amount", "fieldtype": "Currency", "width": 140},
        {"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 200},
    ])
    
    return columns


def _get_entries(company: str, account: str | None, date_from: str | None, date_to: str | None) -> list[dict]:
    conditions: dict[str, object] = {
        "company": company,
        "is_cancelled": 0,
    }

    if account:
        conditions["account"] = account

    if date_from and date_to:
        conditions["posting_date"] = ["between", [date_from, date_to]]
    elif date_from:
        conditions["posting_date"] = [">=", date_from]
    elif date_to:
        conditions["posting_date"] = ["<=", date_to]

    entries = frappe.get_all(
        "GL Entry",
        filters=conditions,
        fields=[
            "posting_date",
            "account",
            "voucher_type",
            "voucher_no",
            "debit",
            "credit",
            "remarks",
        ],
        order_by="posting_date asc, name asc",
    )

    for entry in entries:
        entry["net_amount"] = flt(entry.get("credit")) - flt(entry.get("debit"))

    return entries
