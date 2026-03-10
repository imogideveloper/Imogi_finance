from __future__ import annotations

import frappe


def _copy_deferred_to_items(parent_doctype: str, item_doctype: str):
    if not frappe.db.has_column(parent_doctype, "is_deferred_expense"):
        return

    parents = frappe.get_all(
        parent_doctype,
        filters={"is_deferred_expense": 1},
        fields=["name", "deferred_start_date", "deferred_periods"],
    )

    for parent in parents:
        item_names = frappe.get_all(
            item_doctype,
            filters={"parent": parent.name},
            pluck="name",
        )

        if not item_names:
            continue

        for item_name in item_names:
            frappe.db.set_value(
                item_doctype,
                item_name,
                {
                    "is_deferred_expense": 1,
                    "deferred_start_date": parent.deferred_start_date,
                    "deferred_periods": parent.deferred_periods,
                },
                update_modified=False,
            )


def execute():
    _copy_deferred_to_items("Expense Request", "Expense Request Item")
