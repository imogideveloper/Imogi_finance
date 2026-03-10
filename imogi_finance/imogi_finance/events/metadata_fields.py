"""Auto-populate Created By and Submit On fields for transactional doctypes."""
from __future__ import annotations

import frappe
from frappe.utils import now_datetime


def set_created_by(doc, method=None):
    """Set Created By field on document creation (validate hook).
    
    This captures the user who created the document.
    Runs on validate to capture before first save.
    """
    if not hasattr(doc, "created_by_user"):
        return
    
    # Only set if empty and document is new
    if not doc.created_by_user and doc.is_new():
        doc.created_by_user = frappe.session.user


def set_submit_on(doc, method=None):
    """Set Submit On field when document is submitted (on_submit hook).
    
    This captures the exact datetime when the document was submitted.
    """
    if not hasattr(doc, "submit_on"):
        return
    
    # Only set if empty and document is being submitted
    if not doc.submit_on and doc.docstatus == 1:
        doc.db_set("submit_on", now_datetime(), update_modified=False)
