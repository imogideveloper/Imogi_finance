from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class ExpenseDeferredSettings(Document):
    """Controller for Expense Deferred Settings"""
    
    def validate(self):
        """Validate settings before saving"""
        self.validate_deferrable_accounts()
    
    def validate_deferrable_accounts(self):
        """Validate deferrable accounts configuration"""
        if not self.deferrable_accounts:
            return
        
        seen_accounts = set()
        for idx, row in enumerate(self.deferrable_accounts, start=1):
            if not row.prepaid_account:
                frappe.throw(
                    _("Row {0}: Prepaid Account is required").format(idx)
                )
            
            # Check for duplicate prepaid accounts
            if row.prepaid_account in seen_accounts:
                frappe.throw(
                    _("Row {0}: Duplicate Prepaid Account {1}").format(
                        idx,
                        frappe.bold(row.prepaid_account)
                    )
                )
            seen_accounts.add(row.prepaid_account)
            
            # Validate prepaid account is an asset
            account = frappe.db.get_value(
                "Account", 
                row.prepaid_account, 
                ["root_type", "is_group"], 
                as_dict=1
            )
            if not account:
                frappe.throw(
                    _("Row {0}: Prepaid Account {1} does not exist").format(
                        idx,
                        frappe.bold(row.prepaid_account)
                    )
                )
            
            if account.is_group:
                frappe.throw(
                    _("Row {0}: Prepaid Account {1} cannot be a group account").format(
                        idx,
                        frappe.bold(row.prepaid_account)
                    )
                )
            if account.root_type != "Asset":
                frappe.throw(
                    _("Row {0}: Prepaid Account {1} must be an Asset account, but is {2}").format(
                        idx,
                        frappe.bold(row.prepaid_account),
                        frappe.bold(account.root_type)
                    )
                )


def get_settings():
    """Get Expense Deferred Settings singleton"""
    return frappe.get_single("Expense Deferred Settings")


def get_deferrable_account_map():
    """Get mapping of prepaid accounts to their configuration"""
    settings = get_settings()
    accounts = {}
    for row in getattr(settings, "deferrable_accounts", []) or []:
        if not getattr(row, "is_active", 0):
            continue
        prepaid = getattr(row, "prepaid_account", None)
        if prepaid:
            accounts[prepaid] = row
    return settings, accounts
