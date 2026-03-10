# Developer scan notes (2024-11-05):
# - Expense Request controller (imogi_finance/imogi_finance/doctype/expense_request/expense_request.py)
#   drives approval via imogi_finance.approval.get_approval_route/get_active_setting_meta with guards
#   in before_workflow_action and purchase invoice creation through imogi_finance.accounting.create_purchase_invoice_from_request.
# - Approval engine is centralized in imogi_finance.approval with Expense Approval Setting/Line doctypes.
# - Branch propagation uses imogi_finance.branching.resolve_branch/apply_branch and is enforced in events
#   such as imogi_finance.events.purchase_invoice and ExpenseRequest.apply_branch_defaults.
# - No existing budget-control or internal-charge doctypes/ledgers; accounting utilities are limited to
#   summarize_request_items and downstream link validation in imogi_finance.events.utils.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import frappe
from imogi_finance import roles
from frappe import _

DEFAULT_SETTINGS = {
    "enable_budget_lock": 0,
    "enable_budget_reclass": 0,
    "enable_additional_budget": 0,
    "enable_internal_charge": 0,
    "enable_budget_check_direct_pi": 0,  # Option A: Hard block PI without ER if budget insufficient
    "budget_controller_role": roles.BUDGET_CONTROLLER,
    "require_budget_controller_review": 1,
    "lock_on_workflow_state": "Approved",
    "enforce_mode": "Both",
    "budget_check_basis": "Fiscal Year",
    "allow_budget_overrun_role": None,
    "allow_reclass_override_role": None,
    "internal_charge_required_before_er_approval": 1,
    "internal_charge_posting_mode": "Auto JE on PI Submit",
    "dimension_mode": "Native (Cost Center + Account)",
}


@dataclass
class Dimensions:
    company: str | None
    fiscal_year: str | None
    cost_center: str | None
    account: str | None
    project: str | None = None
    branch: str | None = None

    def as_filters(self) -> dict[str, Any]:
        filters = {
            "company": self.company,
            "fiscal_year": self.fiscal_year,
            "cost_center": self.cost_center,
            "account": self.account,
        }

        if self.project:
            filters["project"] = self.project

        if self.branch:
            filters["branch"] = self.branch

        return filters


def _get_settings_doc():
    from imogi_finance.settings.utils import get_budget_control_settings
    try:
        return get_budget_control_settings()
    except Exception:
        return None


def get_settings():
    settings = DEFAULT_SETTINGS.copy()
    if not getattr(frappe, "db", None):
        return settings

    if not frappe.db.exists("DocType", "Budget Control Settings"):
        return settings

    record = _get_settings_doc()
    if not record:
        return settings

    for key in settings.keys():
        settings[key] = getattr(record, key, settings[key])

    return settings


@frappe.whitelist()
def get_settings_for_ui():
    """Whitelisted version of get_settings for browser console access."""
    return get_settings()


def is_feature_enabled(flag: str) -> bool:
    settings = get_settings()
    return bool(settings.get(flag, 0))


def resolve_company_from_cost_center(cost_center: str | None) -> str | None:
    if not cost_center or not getattr(frappe, "db", None):
        return None

    try:
        return frappe.db.get_value("Cost Center", cost_center, "company")
    except Exception:
        return None


def resolve_fiscal_year(fiscal_year: str | None, company: str | None = None) -> str | None:
    """Resolve fiscal year from various sources.
    
    Fiscal Year is a DocType with fields: name, year_start_date, year_end_date, disabled
    
    Priority order:
    1. Provided fiscal_year parameter
    2. User defaults (frappe.defaults.get_user_default)
    3. Global defaults (frappe.defaults.get_global_default)
    4. Company's default fiscal year (if available)
    5. Get fiscal year that covers current date using ERPNext's get_fiscal_year()
    6. Get any active (not disabled) fiscal year
    """
    if fiscal_year:
        return fiscal_year

    # Try user defaults
    defaults = getattr(frappe, "defaults", None)
    if defaults and hasattr(defaults, "get_user_default"):
        try:
            value = defaults.get_user_default("fiscal_year")
            if value:
                return value
        except Exception:
            pass

    # Try global defaults
    if defaults and hasattr(defaults, "get_global_default"):
        try:
            value = defaults.get_global_default("fiscal_year")
            if value:
                return value
        except Exception:
            pass

    # Try company's default fiscal year if field exists
    if company and getattr(frappe, "db", None):
        try:
            if frappe.db.has_column("Company", "default_fiscal_year"):
                value = frappe.db.get_value("Company", company, "default_fiscal_year")
                if value:
                    return value
        except Exception:
            pass
    
    # Try to get fiscal year from current date using ERPNext's built-in function
    if getattr(frappe, "db", None):
        try:
            from erpnext.accounts.utils import get_fiscal_year
            from frappe.utils import nowdate, getdate
            
            # Get fiscal year for current date and company
            fy = get_fiscal_year(date=getdate(nowdate()), company=company, as_dict=False)
            if fy:
                # get_fiscal_year returns tuple (fiscal_year_name, start_date, end_date)
                return fy[0] if isinstance(fy, (list, tuple)) else fy
        except Exception:
            pass
        
        # Last resort: get any active fiscal year from Fiscal Year DocType
        try:
            fiscal_years = frappe.get_all(
                "Fiscal Year",
                filters={"disabled": 0},
                fields=["name"],
                order_by="year_start_date desc",
                limit=1
            )
            if fiscal_years:
                return fiscal_years[0].name
        except Exception:
            pass

    return None


def allow_branch(dim_mode: str) -> bool:
    return dim_mode in ("Native + Branch (optional)",)


def allow_project(dim_mode: str) -> bool:
    return dim_mode in ("Native + Project (optional)",)
