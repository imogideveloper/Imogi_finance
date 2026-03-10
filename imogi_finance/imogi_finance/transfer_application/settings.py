from __future__ import annotations

from typing import Iterable, List

import frappe
from frappe.utils import flt

from imogi_finance.settings.utils import get_transfer_application_settings as _get_ta_settings


DEFAULT_REFERENCE_DOCTYPES: List[str] = [
    "Purchase Invoice",
    "Expense Claim",
    "Salary Slip",
    "Payroll Entry",
    "Journal Entry",
    "Tax Payment",
    "Tax Payment Batch",
]


def get_transfer_application_settings():
    """Get Transfer Application Settings singleton.
    
    Uses centralized helper from settings layer for consistency.
    """
    try:
        settings = _get_ta_settings()
    except frappe.DoesNotExistError:
        settings = frappe.new_doc("Transfer Application Settings")
        settings.enable_bank_txn_matching = 1
        settings.enable_auto_create_payment_entry_on_strong_match = 0
        settings.matching_amount_tolerance = 0
        settings.insert(ignore_permissions=True)
    except Exception:
        frappe.clear_document_cache("Transfer Application Settings")
        raise

    ensure_settings_defaults(settings)
    return settings


def ensure_settings_defaults(settings):
    if settings.enable_bank_txn_matching is None:
        settings.enable_bank_txn_matching = 1
    if settings.enable_auto_create_payment_entry_on_strong_match is None:
        settings.enable_auto_create_payment_entry_on_strong_match = 0
    if settings.matching_amount_tolerance is None:
        settings.matching_amount_tolerance = 0


def get_reference_doctypes() -> list[str]:
    """Load reference doctypes from Transfer Application Settings table.
    
    Strategy:
    1. Load from reference_doctypes table (enabled rows only)
    2. If table is empty or not configured, fall back to DEFAULT_REFERENCE_DOCTYPES
    
    Returns:
        List of enabled reference DocType names
    """
    try:
        settings = get_transfer_application_settings()
        rows = settings.get("reference_doctypes") or []
        
        doctypes = [
            r.get("reference_doctype")
            for r in rows
            if r.get("enabled") and r.get("reference_doctype")
        ]
        
        if doctypes:
            return doctypes
    except Exception as e:
        frappe.logger().warning(f"Failed to load reference doctypes from table: {e}. Using defaults.")
    
    # Fallback to hardcoded defaults
    return DEFAULT_REFERENCE_DOCTYPES


def get_reference_doctype_options() -> list[str]:
    """Get list of valid reference doctype options for UI dropdown.
    
    Filters to only doctypes that exist in system.
    """
    doctypes = get_reference_doctypes()
    existing = set(
        frappe.get_all("DocType", filters={"name": ("in", doctypes)}, pluck="name")
    )
    options: list[str] = [doctype for doctype in doctypes if doctype in existing]
    options.append("Other")
    return options


def get_amount_tolerance(settings=None) -> float:
    settings = settings or get_transfer_application_settings()
    return flt(settings.matching_amount_tolerance or 0)


def normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_account(value: str | None) -> str:
    return normalize_text(value).replace(" ", "").replace("-", "")
