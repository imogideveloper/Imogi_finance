"""Global settings helpers.

Centralized access to all settings DocTypes with fallback defaults.
All modules must use these helpers instead of direct get_single() calls.

Handles both singleton (issingle=1) and non-singleton settings gracefully.
"""

from __future__ import annotations

from typing import Optional
import frappe
from frappe import _

FINANCE_CONTROL_SETTINGS_DOCTYPE = "Finance Control Settings"
RECEIPT_CONTROL_SETTINGS_DOCTYPE = "Receipt Control Settings"
TAX_INVOICE_OCR_SETTINGS_DOCTYPE = "Tax Invoice OCR Settings"
TRANSFER_APPLICATION_SETTINGS_DOCTYPE = "Transfer Application Settings"
BUDGET_CONTROL_SETTINGS_DOCTYPE = "Budget Control Settings"
EXPENSE_DEFERRED_SETTINGS_DOCTYPE = "Expense Deferred Settings"
LETTER_TEMPLATE_SETTINGS_DOCTYPE = "Letter Template Settings"


def _is_singleton_doctype(doctype: str) -> bool:
    """Check if a DocType is configured as singleton (issingle=1)."""
    try:
        if not frappe.db.exists("DocType", doctype):
            return False
        # Query DB directly to get issingle value
        is_single = frappe.db.get_value("DocType", doctype, "issingle")
        return bool(is_single)
    except Exception:
        return False


def get_single_cached(doctype: str) -> frappe.Document | None:
    """Get single document with caching for performance.
    
    Handles both singleton (issingle=1) and non-singleton settings.
    For non-singleton, fetches the most recent record.
    
    Args:
        doctype: DocType name
        
    Returns:
        Document or None if not found
    """
    try:
        if not frappe.db.exists("DocType", doctype):
            return None
        
        # Try singleton first (cached_doc)
        if _is_singleton_doctype(doctype):
            return frappe.get_cached_doc(doctype)
        
        # Fallback for non-singleton: get most recent record
        records = frappe.get_all(doctype, limit=1, order_by="modified desc")
        if records:
            return frappe.get_doc(doctype, records[0]["name"])
        
        return None
    except (frappe.DoesNotExistError, frappe.PermissionError):
        return None


def get_finance_control_settings() -> frappe.Document:
    """Get Finance Control Settings singleton."""
    doc = get_single_cached(FINANCE_CONTROL_SETTINGS_DOCTYPE)
    if not doc:
        frappe.throw(_("Finance Control Settings not configured"))
    return doc


def get_receipt_settings() -> frappe.Document:
    """Get Receipt Control Settings singleton."""
    doc = get_single_cached(RECEIPT_CONTROL_SETTINGS_DOCTYPE)
    if not doc:
        frappe.throw(_("Receipt Control Settings not configured"))
    return doc


def get_tax_invoice_ocr_settings() -> frappe.Document:
    """Get Tax Invoice OCR Settings singleton."""
    doc = get_single_cached(TAX_INVOICE_OCR_SETTINGS_DOCTYPE)
    if not doc:
        frappe.throw(_("Tax Invoice OCR Settings not configured"))
    return doc


def get_transfer_application_settings() -> frappe.Document:
    """Get Transfer Application Settings singleton."""
    doc = get_single_cached(TRANSFER_APPLICATION_SETTINGS_DOCTYPE)
    if not doc:
        frappe.throw(_("Transfer Application Settings not configured"))
    return doc


def get_budget_control_settings() -> frappe.Document:
    """Get Budget Control Settings singleton."""
    doc = get_single_cached(BUDGET_CONTROL_SETTINGS_DOCTYPE)
    if not doc:
        frappe.throw(_("Budget Control Settings not configured"))
    return doc


def get_expense_deferred_settings() -> frappe.Document:
    """Get Expense Deferred Settings singleton."""
    doc = get_single_cached(EXPENSE_DEFERRED_SETTINGS_DOCTYPE)
    if not doc:
        frappe.throw(_("Expense Deferred Settings not configured"))
    return doc


def get_letter_template_settings() -> frappe.Document:
    """Get Letter Template Settings singleton."""
    doc = get_single_cached(LETTER_TEMPLATE_SETTINGS_DOCTYPE)
    if not doc:
        frappe.throw(_("Letter Template Settings not configured"))
    return doc


def get_gl_account(
    purpose: str,
    company: str | None = None,
    required: bool = True
) -> str | None:
    """Get GL Account by purpose with multi-company support.
    
    Lookup strategy:
    1. If company specified: exact match by (purpose, company)
    2. Fallback: match by purpose with no company (global default)
    3. If required=True and not found: raise error
    4. If required=False and not found: return None
    
    Args:
        purpose: GL account mapping purpose (from gl_purposes.py)
        company: Company code (optional, for multi-company setups)
        required: Raise error if not found (default True)
        
    Returns:
        Account name (str) or None if not found and required=False
        
    Raises:
        frappe.ValidationError: If required=True and mapping not found
    """
    try:
        doc = get_finance_control_settings()
    except frappe.ValidationError:
        if not required:
            return None
        raise

    rows = doc.get("gl_account_mappings") or []

    # Strategy 1: exact match by purpose+company
    if company:
        for row in rows:
            row_purpose = row.get("purpose")
            row_company = row.get("company")
            row_account = row.get("account")
            
            if (row_purpose == purpose) and (row_company == company) and row_account:
                return row_account

    # Strategy 2: fallback to global default (purpose with no company)
    for row in rows:
        row_purpose = row.get("purpose")
        row_company = row.get("company")
        row_account = row.get("account")
        
        if (row_purpose == purpose) and not row_company and row_account:
            return row_account

    # Not found
    if required:
        company_desc = company or "DEFAULT"
        frappe.throw(
            _(
                f"GL account mapping not configured for purpose='{purpose}' "
                f"(company='{company_desc}'). Please configure in Finance Control Settings."
            ),
            title=_("Missing GL Account Mapping")
        )
    return None


def get_tax_profile(company: str) -> frappe.Document:
    """Get Tax Profile for a company.
    
    Tax Profile is NOT a singleton—it's linked by company field.
    
    Args:
        company: Company name
        
    Returns:
        Tax Profile document
        
    Raises:
        frappe.ValidationError: If Tax Profile not found for company
    """
    name = frappe.db.get_value("Tax Profile", {"company": company}, "name")
    if not name:
        frappe.throw(
            _(
                f"Tax Profile not found for company '{company}'. "
                f"Please create one and configure PPN accounts."
            ),
            title=_("Missing Tax Profile")
        )
    return frappe.get_cached_doc("Tax Profile", name)


def get_ppn_accounts(company: str) -> tuple[str, str]:
    """Get PPN Input and Output accounts from Tax Profile.
    
    Args:
        company: Company name
        
    Returns:
        Tuple of (ppn_input_account, ppn_output_account)
        
    Raises:
        frappe.ValidationError: If Tax Profile not found or accounts not configured
    """
    tp = get_tax_profile(company)
    
    if not tp.ppn_input_account:
        frappe.throw(
            _(
                f"Tax Profile '{tp.name}' is missing PPN Input Account. "
                f"Please configure it for company '{company}'."
            ),
            title=_("Missing PPN Input Account")
        )
    
    if not tp.ppn_output_account:
        frappe.throw(
            _(
                f"Tax Profile '{tp.name}' is missing PPN Output Account. "
                f"Please configure it for company '{company}'."
            ),
            title=_("Missing PPN Output Account")
        )
    
    return tp.ppn_input_account, tp.ppn_output_account


def get_vat_input_accounts(company: str) -> list[str]:
    """Get list of VAT input accounts for filtering template taxes.
    
    Used to identify which taxes in a Purchase Taxes and Charges Template
    are PPN-related (for expected PPN calculation).
    
    Args:
        company: Company name
        
    Returns:
        List containing PPN input account (single item for now)
        
    Raises:
        frappe.ValidationError: If Tax Profile or account not configured
    """
    ppn_input, _ = get_ppn_accounts(company)
    return [ppn_input]


def get_default_prepaid_account(company: str | None) -> str:
    """Get default prepaid account from GL Mappings (Finance Control Settings).
    
    This is the fallback account when no rule-based mapping exists in deferrable_accounts.
    Each deferred expense item CAN override via its own prepaid_account field.
    
    Logic flow:
    1. Check deferrable_accounts table for rule-based mapping (expense_account → prepaid)
    2. If no rule match → use this default (GL Mappings)
    3. If no default configured → throw error
    
    Args:
        company: Company name (required for GL account lookup)
        
    Returns:
        GL account name configured for DEFAULT_PREPAID purpose
        
    Raises:
        frappe.ValidationError: If account not configured or missing
    """
    from imogi_finance.settings.gl_purposes import DEFAULT_PREPAID
    
    if not company:
        frappe.throw(
            _("Company is required to resolve default prepaid account. "
              "This is a system error - please report it.")
        )
    
    return get_gl_account(DEFAULT_PREPAID, company=company, required=True)
