"""Patch: Remove dangling Branch Expense Request custom fields.

The 'Branch Expense Request' DocType has been removed from the app.
This patch deletes the related Link custom fields from Purchase Invoice and
Payment Entry that pointed to the now-missing DocType, which would otherwise
cause a ValidationError when opening those forms.
"""
from __future__ import annotations

import frappe

_FIELDS_TO_DELETE = [
    "Purchase Invoice-branch_expense_request",
    "Payment Entry-branch_expense_request",
]


def execute() -> None:
    for name in _FIELDS_TO_DELETE:
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_missing=True, force=True)
            frappe.logger().info("Deleted dangling Custom Field: %s", name)

    frappe.clear_cache()
