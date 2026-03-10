"""Event handlers for Transfer Application DocType"""

import frappe
from frappe import _


def sync_status_with_workflow(doc, method=None):
    """
    Sync status field with workflow_state.
    Called on validate, on_update, and on_update_after_submit.
    """
    if not doc.workflow_state:
        return

    # Sync status to match workflow_state
    if doc.status != doc.workflow_state:
        doc.status = doc.workflow_state

        # Use db_set if document is already submitted
        if doc.docstatus == 1:
            doc.db_set("status", doc.workflow_state, update_modified=False)
