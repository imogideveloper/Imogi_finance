"""Patch: Rename 'Expense Request Multi CC' DocType to 'Advanced Expense Request'.

This patch handles the database-level rename of the DocType and its child table,
along with any related fixtures (Print Format, Workflow) that reference the old name.
Run once after deploying the code changes that renamed the doctype files.
"""
from __future__ import annotations

import frappe


def execute():
    # ── Rename child doctype first (parent rename may cascade) ──────────────
    if frappe.db.exists("DocType", "Expense Request Multi CC Item"):
        frappe.rename_doc(
            "DocType",
            "Expense Request Multi CC Item",
            "Advanced Expense Request Item",
            force=True,
        )
        frappe.db.commit()

    # ── Rename parent doctype ────────────────────────────────────────────────
    if frappe.db.exists("DocType", "Expense Request Multi CC"):
        frappe.rename_doc(
            "DocType",
            "Expense Request Multi CC",
            "Advanced Expense Request",
            force=True,
        )
        frappe.db.commit()

    # ── Rename Print Format ──────────────────────────────────────────────────
    if frappe.db.exists("Print Format", "Expense Request Multi CC"):
        if frappe.db.exists("Print Format", "Advanced Expense Request"):
            # Target already exists (e.g. created from fixtures) – drop the old one
            frappe.delete_doc("Print Format", "Expense Request Multi CC", force=True, ignore_missing=True)
        else:
            frappe.rename_doc(
                "Print Format",
                "Expense Request Multi CC",
                "Advanced Expense Request",
                force=True,
            )
        frappe.db.commit()

    # ── Rename Workflow ──────────────────────────────────────────────────────
    if frappe.db.exists("Workflow", "Expense Request Multi CC Workflow"):
        if frappe.db.exists("Workflow", "Advanced Expense Request Workflow"):
            # Target already exists – drop the old one
            frappe.delete_doc("Workflow", "Expense Request Multi CC Workflow", force=True, ignore_missing=True)
        else:
            frappe.rename_doc(
                "Workflow",
                "Expense Request Multi CC Workflow",
                "Advanced Expense Request Workflow",
                force=True,
            )
        frappe.db.commit()

    # ── Update document_type on Workflow if not handled by rename_doc ────────
    if frappe.db.exists("Workflow", "Advanced Expense Request Workflow"):
        frappe.db.set_value(
            "Workflow",
            "Advanced Expense Request Workflow",
            "document_type",
            "Advanced Expense Request",
            update_modified=False,
        )

    frappe.db.commit()
