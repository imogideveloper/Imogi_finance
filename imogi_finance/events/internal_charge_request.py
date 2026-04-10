"""Internal Charge Request event handlers for doc_events hooks."""
from __future__ import annotations
import frappe


def sync_status_with_workflow(doc, method=None):
    """Sync status field with workflow_state after save."""
    workflow_state = getattr(doc, "workflow_state", None)
    current_status = getattr(doc, "status", None)

    if not workflow_state:
        return

    if current_status != workflow_state:
        doc.db_set("status", workflow_state, update_modified=False)


def on_workflow_action(doc, method=None, workflow_action=None):
    """Handle workflow actions - update line statuses after Approve/Reject."""
    if workflow_action not in ("Approve", "Reject"):
        return

    session_user = frappe.session.user

    if workflow_action == "Approve":
        _handle_approve(doc, session_user)
    elif workflow_action == "Reject":
        _handle_reject(doc, session_user)

    frappe.db.commit()


def _handle_approve(doc, session_user):
    """Advance line statuses on Approve."""
    from imogi_finance.imogi_finance.doctype.internal_charge_request.internal_charge_request import _advance_line_status

    doc.flags.ignore_validate_update_after_submit = True

    for line in (doc.internal_charge_lines or []):
        if getattr(line, "line_status", None) in ("Pending L1", "Pending L2", "Pending L3"):
            _advance_line_status(line, session_user=session_user)
            # Persist each line via db_set
            frappe.db.set_value("Internal Charge Line", line.name, {
                "line_status": line.line_status,
                "current_approval_level": line.current_approval_level,
                "approved_by": getattr(line, "approved_by", None),
                "approved_on": getattr(line, "approved_on", None),
            })

    # Check if all lines approved
    all_statuses = set()
    for line in (doc.internal_charge_lines or []):
        status = frappe.db.get_value("Internal Charge Line", line.name, "line_status")
        all_statuses.add(status)

    if all_statuses == {"Approved"}:
        frappe.db.set_value("Internal Charge Request", doc.name, {
            "status": "Approved",
            "approved_by": session_user,
            "approved_on": frappe.utils.now_datetime(),
        }, update_modified=False)


def _handle_reject(doc, session_user):
    """Mark all pending lines as Rejected."""
    for line in (doc.internal_charge_lines or []):
        if getattr(line, "line_status", None) in ("Pending L1", "Pending L2", "Pending L3"):
            frappe.db.set_value("Internal Charge Line", line.name, {
                "line_status": "Rejected",
            })

    frappe.db.set_value("Internal Charge Request", doc.name, 
        "status", "Rejected", update_modified=False)
