# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe


def on_workflow_action(doc, method=None, **kwargs):
    """Sync status field dengan workflow_state setelah workflow action."""
    if getattr(doc, "workflow_state", None):
        doc.db_set("status", doc.workflow_state, update_modified=False)


def on_submit(doc, method=None):
    """Sync status dengan workflow_state saat submit."""
    if getattr(doc, "workflow_state", None):
        doc.db_set("status", doc.workflow_state, update_modified=False)
