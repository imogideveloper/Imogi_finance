# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""Shared utilities for Imogi Finance.

This package contains utility modules used across multiple reports and features.

NOTE: ERPNext v15+ Compatibility
---------------------------------
This module has been updated to follow ERPNext v15+ best practices:
- Uses frappe.db.exists() instead of deprecated frappe.reload_doc()
- Relies on fixtures for Property Setters (no programmatic creation)
- No manual transaction commits in migration hooks

Structure:
----------
/imogi_finance/                     # App root (hooks.py, setup.py)
  ├── utils.py                      # Compatibility shim for hooks
  └── imogi_finance/                # Python package (actual code)
      └── utils/                    # THIS MODULE
          ├── __init__.py           # Re-exports + migration hooks
          └── tax_report_utils.py  # Tax utilities

The nested structure exists because app_name == "imogi_finance" requires
imogi_finance/imogi_finance/ to avoid hook path conflicts.
See imogi_finance/utils.py for the compatibility shim that makes this work.
"""

from __future__ import annotations

# Re-export commonly used functions for convenience
from .tax_report_utils import (
    get_tax_amount_from_gl,
    get_tax_amounts_batch,
    validate_tax_register_configuration,
    validate_vat_input_configuration,
    validate_vat_output_configuration,
    validate_withholding_configuration,
)

# Re-export from imogi_finance.imogi_finance.utils for hooks compatibility
def ensure_coretax_export_doctypes():
    """Ensure CoreTax Export DocTypes exist.

    This is called from hooks after_install and after_migrate.
    
    ERPNext v15+ Compatibility:
    - Uses frappe.db.exists() instead of deprecated frappe.reload_doc()
    - Bench migrate automatically syncs DocTypes from JSON files
    - This function only validates they exist post-migration
    """
    import frappe

    required_doctypes = [
        "CoreTax Export Settings",
        "CoreTax Column Mapping",
        "Tax Profile PPh Account",
    ]

    missing = []
    for doctype in required_doctypes:
        if not frappe.db.exists("DocType", doctype):
            missing.append(doctype)

    if missing:
        error_msg = f"Missing CoreTax DocTypes after migration: {', '.join(missing)}"
        frappe.log_error(
            message=error_msg,
            title="CoreTax DocType Validation Failed",
        )
        frappe.throw(
            frappe._("Required CoreTax DocTypes not found. Please run 'bench migrate' again.")
        )


def ensure_advances_allow_on_submit():
    """
    Ensure 'advances' field allows updates after submit.

    ERPNext v15+ Compatibility:
    - Property Setters are managed via fixtures/property_setter.json
    - Bench migrate applies them automatically
    - This function is retained for backwards compatibility but performs no action
    
    The following Property Setters are defined in fixtures:
    - Purchase Invoice.advances.allow_on_submit = 1
    - Sales Invoice.advances.allow_on_submit = 1
    - Expense Claim.advances.allow_on_submit = 1
    """
    # No-op: Fixtures handle this automatically
    pass


__all__ = [
    "get_tax_amount_from_gl",
    "get_tax_amounts_batch",
    "validate_tax_register_configuration",
    "validate_vat_input_configuration",
    "validate_vat_output_configuration",
    "validate_withholding_configuration",
    "ensure_coretax_export_doctypes",
    "ensure_advances_allow_on_submit",
]


def ensure_budget_control_settings():
    """Load default Budget Control Settings from fixtures after migrate."""
    import json
    import os
    import frappe

    fixture_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "fixtures", "budget_control_settings.json"
    )
    if not os.path.exists(fixture_path):
        return

    with open(fixture_path, "r") as f:
        data = json.load(f)

    if not data:
        return

    doc_data = data[0]
    try:
        doc = frappe.get_doc("Budget Control Settings")
        # Hanya update jika belum pernah di-set (masih default)
        if not doc.enable_budget_lock and not doc.enable_internal_charge:
            for key, value in doc_data.items():
                if key not in ["doctype", "name", "idx", "docstatus"]:
                    setattr(doc, key, value)
            doc.save()
            frappe.db.commit()
    except Exception as e:
        frappe.log_error(title="ensure_budget_control_settings failed", message=str(e))


def ensure_installment_items():
    """Create default non-stock Items used by auto-generated Installment Purchase Orders.

    2 item terpisah (pokok & bunga) supaya tiap baris PO bisa di-override
    expense_account-nya masing-masing untuk split GL yang benar.
    """
    import frappe

    item_codes = ["Angsuran Pokok", "Angsuran Bunga"]

    for item_code in item_codes:
        if frappe.db.exists("Item", item_code):
            continue

        try:
            item_group = "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups"
            stock_uom = frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos"

            item = frappe.new_doc("Item")
            item.item_code = item_code
            item.item_name = item_code
            item.item_group = item_group
            item.stock_uom = stock_uom
            item.is_stock_item = 0
            item.include_item_in_manufacturing = 0
            item.is_purchase_item = 1
            item.description = "Item generik untuk baris Purchase Order cicilan/angsuran yang dibuat otomatis"
            item.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error(title="ensure_installment_items failed", message=f"{item_code}: {e}")
