"""Expense Request event handlers for doc_events hooks."""
from __future__ import annotations

import frappe
from frappe import _


def validate_workflow_action(doc, method=None):
    """Validate approver authorization when workflow action is being applied.

    This is triggered via doc_events validate hook when Frappe's apply_workflow
    saves the document. We detect if a workflow transition is happening and
    validate that the current user is the authorized approver.
    """
    # Skip if not in workflow transition
    if not _is_workflow_transition(doc):
        return

    # Skip if not transitioning to/from Pending Review
    if not _is_approval_action(doc):
        return

    # Get current approval level - default to 1 if not set
    current_level = getattr(doc, "current_approval_level", None) or 1

    # Get expected approver for this level
    expected_user = getattr(doc, f"level_{current_level}_user", None)

    if not expected_user:
        # No approver configured for this level
        frappe.throw(
            _("No approver configured for level {0}.").format(current_level),
            title=_("Not Allowed"),
        )

    session_user = frappe.session.user

    if session_user != expected_user:
        frappe.throw(
            _("You are not authorized to approve at level {0}. Required: {1}.").format(
                current_level, expected_user
            ),
            title=_("Not Allowed"),
        )


def sync_status_with_workflow(doc, method=None):
    """Sync status field with workflow_state after save.

    This ensures the 'status' field matches 'workflow_state' for display consistency.
    Also handles advancing approval level when approving with multi-level approval.
    Records timestamp for each approval level.
    """
    workflow_state = getattr(doc, "workflow_state", None)
    current_status = getattr(doc, "status", None)

    if not workflow_state:
        return

    # Sync status with workflow_state if different
    if current_status != workflow_state:
        # Use db_set to update without triggering hooks again
        doc.db_set("status", workflow_state, update_modified=False)

    # Handle approval level timestamp recording
    previous = getattr(doc, "_doc_before_save", None)
    if previous:
        prev_state = getattr(previous, "workflow_state", None)

        # Record timestamp when transitioning FROM Pending Review
        if prev_state == "Pending Review":
            current_level = getattr(previous, "current_approval_level", None) or 1

            if workflow_state == "Approved":
                # Final approval - record timestamp
                _record_approval_timestamp(doc, current_level)
            elif workflow_state == "Pending Review":
                # Multi-level approval - record timestamp and advance level
                _record_approval_timestamp(doc, current_level)
                _advance_approval_level(doc)
            elif workflow_state == "Rejected":
                # Rejection - record timestamp
                _record_rejection_timestamp(doc, current_level)


def handle_budget_workflow(doc, method=None):
    """Handle budget reservation/release when workflow state changes.

    This is triggered on_update and on_update_after_submit hooks.
    Calls reserve_budget_for_request when document is approved.
    Calls release_budget_for_request when document is rejected or cancelled.
    """
    # Only proceed if workflow state changed
    previous = getattr(doc, "_doc_before_save", None)
    if not previous:
        return

    workflow_state = getattr(doc, "workflow_state", None)
    prev_state = getattr(previous, "workflow_state", None)

    if workflow_state == prev_state:
        return

    # Log the transition for debugging
    frappe.logger().info(
        f"handle_budget_workflow: {doc.name} - {prev_state} -> {workflow_state}"
    )

    try:
        # Import here to avoid circular dependency
        from imogi_finance.budget_control import workflow as budget_workflow

        # Reserve budget when approved
        if workflow_state == "Approved":
            frappe.logger().info(f"handle_budget_workflow: Calling reserve_budget for {doc.name}")
            budget_workflow.reserve_budget_for_request(doc)
            frappe.logger().info(f"handle_budget_workflow: Completed reserve_budget for {doc.name}")

        # Release budget when rejected or cancelled
        elif workflow_state == "Rejected":
            frappe.logger().info(f"handle_budget_workflow: Calling release_budget for {doc.name}")
            budget_workflow.release_budget_for_request(doc, reason="Reject")
            frappe.logger().info(f"handle_budget_workflow: Completed release_budget for {doc.name}")

    except Exception as e:
        # Log error but don't block the workflow
        frappe.logger().error(
            f"handle_budget_workflow: Error for {doc.name}: {str(e)}\n{frappe.get_traceback()}"
        )
        # Re-raise to make error visible to user
        frappe.throw(
            _("Error in budget workflow: {0}").format(str(e)),
            title=_("Budget Workflow Error")
        )


def _record_approval_timestamp(doc, level: int):
    """Record approval timestamp for a specific level."""
    timestamp_field = f"level_{level}_approved_on"
    if hasattr(doc, timestamp_field):
        from frappe.utils import now_datetime
        doc.db_set(timestamp_field, now_datetime(), update_modified=False)


def _record_rejection_timestamp(doc, level: int):
    """Record rejection timestamp for a specific level."""
    timestamp_field = f"level_{level}_rejected_on"
    if hasattr(doc, timestamp_field):
        from frappe.utils import now_datetime
        doc.db_set(timestamp_field, now_datetime(), update_modified=False)


def _is_workflow_transition(doc) -> bool:
    """Check if document is undergoing a workflow state transition."""
    # Check if there's a previous version to compare
    previous = getattr(doc, "_doc_before_save", None)
    if not previous:
        return False

    # Check if workflow_state is changing
    current_state = getattr(doc, "workflow_state", None)
    previous_state = getattr(previous, "workflow_state", None)

    return current_state != previous_state


def _is_approval_action(doc) -> bool:
    """Check if the transition involves approval (from or to Pending Review)."""
    previous = getattr(doc, "_doc_before_save", None)
    if not previous:
        return False

    current_state = getattr(doc, "workflow_state", None)
    previous_state = getattr(previous, "workflow_state", None)

    # Approval action: transitioning FROM Pending Review
    # This catches both Approve (to Pending Review or Approved) and Reject (to Rejected)
    if previous_state == "Pending Review":
        return True

    return False


def _advance_approval_level(doc):
    """Advance to next approval level for multi-level approval.

    Called when approval action keeps document in Pending Review (more levels to go).
    """
    current_level = getattr(doc, "current_approval_level", None) or 1

    # Find next level with an assigned user
    for level in range(current_level + 1, 4):
        user_field = f"level_{level}_user"
        if getattr(doc, user_field, None):
            doc.db_set("current_approval_level", level, update_modified=False)
            return

    # No more levels - shouldn't happen if workflow conditions are correct
