# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""API methods for Tax Period Closing operations.

This module provides whitelisted API methods for:
- Period statistics and reporting
- Period validation before closing
- Helper queries for link fields
"""

from __future__ import annotations

from typing import Dict, Any, Optional

import frappe
from frappe import _
from frappe.utils import flt
from imogi_finance import roles


@frappe.whitelist()
def get_period_statistics(closing_name: str) -> Dict[str, Any]:
    """Get comprehensive statistics for a tax period.

    Returns invoice counts, verification status, and tax totals for
    both Purchase Invoices (Input VAT) and Sales Invoices (Output VAT).

    Args:
        closing_name: Name of Tax Period Closing document

    Returns:
        dict: Statistics including:
            - purchase_invoice_count: Total PI count
            - purchase_invoice_verified: Verified PI count
            - purchase_invoice_unverified: Unverified PI count
            - sales_invoice_count: Total SI count
            - sales_invoice_verified: Verified SI count
            - sales_invoice_unverified: Unverified SI count
            - input_vat_total: Total Input VAT amount
            - output_vat_total: Total Output VAT amount
            - vat_net: Net VAT (Output - Input)
    """
    closing = frappe.get_doc("Tax Period Closing", closing_name)
    closing.check_permission("read")

    if not closing.company or not closing.date_from or not closing.date_to:
        frappe.throw(_("Period dates not set"))

    # Base filters for the period
    pi_filters = {
        "company": closing.company,
        "posting_date": ["between", [closing.date_from, closing.date_to]],
        "docstatus": 1
    }

    si_filters = pi_filters.copy()

    # Count Purchase Invoices
    pi_total = frappe.db.count("Purchase Invoice", pi_filters)

    # Purchase Invoice uses ti_verification_status field
    pi_verified_filters = pi_filters.copy()
    pi_verified_filters["ti_verification_status"] = "Verified"
    pi_verified = frappe.db.count("Purchase Invoice", pi_verified_filters)
    pi_unverified = pi_total - pi_verified

    # Count Sales Invoices
    si_total = frappe.db.count("Sales Invoice", si_filters)

    # Sales Invoice uses out_fp_status field
    si_verified_filters = si_filters.copy()
    si_verified_filters["out_fp_status"] = "Verified"
    si_verified = frappe.db.count("Sales Invoice", si_verified_filters)
    si_unverified = si_total - si_verified

    # Get VAT totals from snapshot
    input_vat_total = flt(closing.input_vat_total)
    output_vat_total = flt(closing.output_vat_total)
    vat_net = output_vat_total - input_vat_total

    return {
        "purchase_invoice_count": pi_total,
        "purchase_invoice_verified": pi_verified,
        "purchase_invoice_unverified": pi_unverified,
        "sales_invoice_count": si_total,
        "sales_invoice_verified": si_verified,
        "sales_invoice_unverified": si_unverified,
        "input_vat_total": input_vat_total,
        "output_vat_total": output_vat_total,
        "vat_net": vat_net
    }


@frappe.whitelist()
def validate_can_close_period(closing_name: str) -> Dict[str, Any]:
    """Validate if a period can be closed.

    Checks for:
    - Unverified invoices
    - Missing tax profile
    - Missing register snapshot
    - Open/draft transactions in period
    - Register configuration validity (NEW in v15+)
    - Data source quality (NEW in v15+)

    Args:
        closing_name: Name of Tax Period Closing document

    Returns:
        dict: Validation result with:
            - can_close: bool - Whether period can be closed
            - errors: list - Blocking errors
            - warnings: list - Non-blocking warnings
            - register_info: dict - Register data quality info
    """
    import json

    closing = frappe.get_doc("Tax Period Closing", closing_name)
    closing.check_permission("read")

    errors = []
    warnings = []
    register_info = {}

    # Check tax profile
    if not closing.tax_profile:
        errors.append(_("Tax Profile not set"))

    # Check register snapshot
    if not closing.register_snapshot:
        errors.append(_("Tax register snapshot not generated. Please refresh registers."))
    else:
        # Parse and validate register data
        try:
            snapshot = json.loads(closing.register_snapshot)
            meta = snapshot.get("meta", {})
            data_source = meta.get("data_source", "unknown")

            register_info = {
                "data_source": data_source,
                "input_invoice_count": snapshot.get("input_invoice_count", 0),
                "output_invoice_count": snapshot.get("output_invoice_count", 0),
                "withholding_entry_count": snapshot.get("withholding_entry_count", 0),
                "verification_status": snapshot.get("verification_status", "Unknown")
            }

            # Warn if using fallback data
            if data_source == "fallback_empty":
                errors.append(_("Register data could not be loaded. Error: {0}").format(
                    meta.get("error", "Unknown error")
                ))

            # Warn if all counts are zero
            if (snapshot.get("input_invoice_count", 0) == 0 and
                snapshot.get("output_invoice_count", 0) == 0 and
                snapshot.get("withholding_entry_count", 0) == 0):
                warnings.append(_("No tax transactions found in register snapshot. "
                                 "Verify this is correct before closing."))
        except Exception as e:
            errors.append(_("Failed to parse register snapshot: {0}").format(str(e)))

    # Validate register configuration
    from imogi_finance.imogi_finance.utils_register.register_integration import validate_register_configuration

    try:
        config_validation = validate_register_configuration(closing.company)
        if not config_validation.get("valid"):
            config_errors = []
            for register_type in ["vat_input", "vat_output", "withholding"]:
                register_val = config_validation.get(register_type, {})
                if not register_val.get("valid"):
                    config_errors.append(f"{register_type}: {register_val.get('message', 'Invalid')}")

            warnings.append(_("Register configuration issues: {0}").format("; ".join(config_errors)))
    except Exception as e:
        warnings.append(_("Could not validate register configuration: {0}").format(str(e)))

    # Check for draft transactions
    if closing.company and closing.date_from and closing.date_to:
        draft_pi = frappe.db.count("Purchase Invoice", {
            "company": closing.company,
            "posting_date": ["between", [closing.date_from, closing.date_to]],
            "docstatus": 0
        })

        draft_si = frappe.db.count("Sales Invoice", {
            "company": closing.company,
            "posting_date": ["between", [closing.date_from, closing.date_to]],
            "docstatus": 0
        })

        if draft_pi > 0:
            warnings.append(_("There are {0} draft Purchase Invoices in this period").format(draft_pi))

        if draft_si > 0:
            warnings.append(_("There are {0} draft Sales Invoices in this period").format(draft_si))

        # Check for unverified invoices
        # Purchase Invoice uses ti_verification_status field
        unverified_pi = frappe.db.count("Purchase Invoice", {
            "company": closing.company,
            "posting_date": ["between", [closing.date_from, closing.date_to]],
            "docstatus": 1,
            "ti_verification_status": ["!=", "Verified"]
        })

        # Sales Invoice uses out_fp_status field
        unverified_si = frappe.db.count("Sales Invoice", {
            "company": closing.company,
            "posting_date": ["between", [closing.date_from, closing.date_to]],
            "docstatus": 1,
            "out_fp_status": ["!=", "Verified"]
        })

        if unverified_pi > 0:
            warnings.append(_("There are {0} unverified Purchase Invoices").format(unverified_pi))

        if unverified_si > 0:
            warnings.append(_("There are {0} unverified Sales Invoices").format(unverified_si))

    can_close = len(errors) == 0

    return {
        "can_close": can_close,
        "errors": errors,
        "warnings": warnings,
        "register_info": register_info
    }


@frappe.whitelist()
def check_period_locked(company: str, posting_date: str, doctype: Optional[str] = None) -> Dict[str, Any]:
    """Check if a specific date falls within a locked tax period.

    Used by Purchase Invoice, Sales Invoice, and Expense Request to validate
    if tax invoice fields can be edited.

    Args:
        company: Company name
        posting_date: Date to check
        doctype: Optional doctype name for more specific checks

    Returns:
        dict: Lock status with:
            - is_locked: bool - Whether period is locked
            - closing_name: str - Name of closing document (if locked)
            - message: str - User-friendly message
    """
    if not company or not posting_date:
        return {"is_locked": False}

    # Check if user has privileged role (can bypass lock)
    privileged_roles = [roles.SYSTEM_MANAGER, roles.ACCOUNTS_MANAGER, roles.TAX_REVIEWER]
    user_roles = frappe.get_roles()

    if any(role in user_roles for role in privileged_roles):
        return {
            "is_locked": False,
            "message": _("Period lock bypassed due to privileged role")
        }

    # Check for submitted closing with status "Closed"
    filters = {
        "company": company,
        "status": "Closed",
        "docstatus": 1,
        "date_from": ["<=", posting_date],
        "date_to": [">=", posting_date]
    }

    closing = frappe.db.get_value(
        "Tax Period Closing",
        filters,
        ["name", "period_month", "period_year"],
        as_dict=True
    )

    if closing:
        return {
            "is_locked": True,
            "closing_name": closing.name,
            "message": _("Tax period {0}-{1} is closed. Tax invoice fields cannot be edited.").format(
                closing.period_month,
                closing.period_year
            )
        }

    return {"is_locked": False}


@frappe.whitelist()
def get_tax_profile_for_company(doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: Dict) -> list:
    """Query function for Tax Profile link field filtered by company.

    Used in tax_period_closing.js setup_queries() to filter tax profiles.

    Args:
        doctype: "Tax Profile"
        txt: Search text
        searchfield: Field being searched
        start: Pagination start
        page_len: Pagination length
        filters: Additional filters (should contain 'company')

    Returns:
        list: Matching tax profiles
    """
    company = filters.get("company")

    conditions = []
    if company:
        conditions.append(f"company = {frappe.db.escape(company)}")

    if txt:
        conditions.append(f"name LIKE {frappe.db.escape('%' + txt + '%')}")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    return frappe.db.sql(f"""
        SELECT name, company
        FROM `tabTax Profile`
        WHERE {where_clause}
        ORDER BY name
        LIMIT {start}, {page_len}
    """)


@frappe.whitelist()
def get_closed_periods_for_company(company: str) -> list:
    """Get list of closed tax periods for a company.

    Useful for dashboards and reports to show period closure history.

    Args:
        company: Company name

    Returns:
        list: Closed period details
    """
    if not company:
        return []

    periods = frappe.get_all(
        "Tax Period Closing",
        filters={
            "company": company,
            "status": "Closed",
            "docstatus": 1
        },
        fields=[
            "name",
            "period_month",
            "period_year",
            "date_from",
            "date_to",
            "input_vat_total",
            "output_vat_total",
            "vat_net",
            "vat_netting_journal_entry",
            "submit_on"
        ],
        order_by="period_year desc, period_month desc"
    )

    return periods
