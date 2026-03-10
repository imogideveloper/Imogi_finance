"""
Utility API to fix Payment Entry - Expense Request linking issues
"""
import frappe
from frappe import _

from imogi_finance.events.utils import get_er_doctype


@frappe.whitelist()
def fix_payment_entry_expense_request_link(payment_entry_name, expense_request_name):
    """
    Fix broken link between Payment Entry and Expense Request

    Args:
        payment_entry_name: Name of Payment Entry
        expense_request_name: Name of Expense Request
    """
    # Validate documents exist
    if not frappe.db.exists("Payment Entry", payment_entry_name):
        frappe.throw(_("Payment Entry {0} not found").format(payment_entry_name))

    _er_doctype = get_er_doctype(expense_request_name)
    if not _er_doctype:
        frappe.throw(_("Expense Request {0} not found").format(expense_request_name))

    # Validate Payment Entry is submitted
    pe_status = frappe.db.get_value("Payment Entry", payment_entry_name, "docstatus")
    if pe_status != 1:
        frappe.throw(_("Payment Entry must be submitted"))

    # Validate Expense Request is approved
    er_status = frappe.db.get_value(_er_doctype, expense_request_name, "status")
    if er_status not in ["Approved", "PI Created", "Paid"]:
        frappe.throw(_("Expense Request must be in approved state"))

    # Update Payment Entry
    frappe.db.set_value(
        "Payment Entry",
        payment_entry_name,
        "imogi_expense_request",
        expense_request_name,
        update_modified=True
    )

    # Update Expense Request
    frappe.db.set_value(
        _er_doctype,
        expense_request_name,
        "linked_payment_entry",
        payment_entry_name,
        update_modified=True
    )

    # Update ER status to Paid if not already
    if er_status != "Paid":
        frappe.db.set_value(
            _er_doctype,
            expense_request_name,
            {
                "status": "Paid",
                "workflow_state": "Paid"
            },
            update_modified=True
        )

    frappe.db.commit()

    return {
        "success": True,
        "message": _("Successfully linked Payment Entry {0} to Expense Request {1}").format(
            payment_entry_name, expense_request_name
        )
    }
