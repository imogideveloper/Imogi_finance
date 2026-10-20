"""Patch: Fix "Expense Account Display" Custom Field wrongly typed as Link.

Expense Request's `custom_expense_account_display` field was created with
fieldtype "Link" (options "Account"), but the controller
(expense_request.py's set_expense_account_display()) writes a
comma-joined STRING of every distinct expense account used on the
request's line items - never a single Account name. The moment a request
used more than one expense account, save/submit failed with "Could not
find Account: <account 1>, <account 2>" (reported live by a user, Una,
trying to submit an expense with 2 different accounts).

The matching field on Purchase Invoice was already correctly typed as
"Data" - this was a one-off mistake on Expense Request's copy, now fixed
in the custom_field.json fixture (fieldtype Data, options null).

Frappe's own Custom Field validation (check_fieldtype_change) refuses to
change an EXISTING field from Link to Data via a plain save - the exact
same restriction blocked the live fix via Customize Form in the UI too.
Since this field is purely derived/display (re-populated on every save,
nothing user-entered to preserve), the safe route is to delete the old
Link-typed record here, before fixtures sync recreates it fresh as Data
right after model sync - a plain insert, not a fieldtype change, so the
validation guard never triggers.
"""
from __future__ import annotations

import frappe

_FIELD_NAME = "Expense Request-custom_expense_account_display"


def execute() -> None:
    if not frappe.db.exists("Custom Field", _FIELD_NAME):
        return

    fieldtype = frappe.db.get_value("Custom Field", _FIELD_NAME, "fieldtype")
    if fieldtype != "Link":
        # Already fixed (or fixed some other way) - nothing to do.
        return

    frappe.delete_doc("Custom Field", _FIELD_NAME, ignore_missing=True, force=True)
    frappe.logger().info(
        "Deleted Link-typed Custom Field %s - fixtures sync will recreate it as Data.",
        _FIELD_NAME,
    )
    frappe.clear_cache()
