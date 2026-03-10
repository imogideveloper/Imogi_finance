from __future__ import annotations

import frappe

from imogi_finance.imogi_finance.doctype.expense_deferred_settings.expense_deferred_settings import (
    get_deferrable_account_map,
)


@frappe.whitelist()
def get_deferrable_accounts():
    settings, deferrable_accounts = get_deferrable_account_map()
    accounts = []
    for prepaid_account, row in deferrable_accounts.items():
        accounts.append(
            {
                "prepaid_account": prepaid_account,
                "expense_account": getattr(row, "expense_account", None),
                "default_periods": getattr(row, "default_periods", None),
            }
        )

    return {
        "enabled": getattr(settings, "enable_deferred_expense", 1),
        "accounts": accounts,
    }
