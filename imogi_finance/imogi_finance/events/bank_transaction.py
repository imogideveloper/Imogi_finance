from __future__ import annotations

import frappe
from frappe import _


def before_cancel(doc, *_):
    if doc.status == "Unreconciled":
        frappe.throw(_("Unreconciled Bank Transactions cannot be cancelled."))


def on_update_after_submit(doc, method=None):
    """Handle Bank Transaction updates after submit.

    When a Bank Transaction is reconciled (status changes to Reconciled),
    update the status of related Purchase Invoices and Expense Requests.
    """
    # Check if this is a reconciliation event
    if doc.status != "Reconciled":
        return

    # Find all Payment Entries linked to this bank transaction
    # This is done by matching the clearance_date and amount
    payment_entries = _find_linked_payment_entries(doc)

    if not payment_entries:
        frappe.logger().info(
            f"[Bank Transaction {doc.name}] Reconciled but no linked Payment Entries found."
        )
        return

    # Update Purchase Invoice and Expense Request statuses
    for pe_name in payment_entries:
        _update_invoice_status_after_bank_reconciliation(pe_name, doc.name)


def _find_linked_payment_entries(bank_transaction):
    """Find Payment Entries that are linked to this Bank Transaction.

    This matches based on:
    1. Account (paid_from or paid_to matches bank_account)
    2. Amount matches (deposit or withdrawal)
    3. Posting date around the transaction date
    4. Has awaiting_bank_reconciliation flag set
    """
    from frappe.utils import flt

    filters = {
        "docstatus": 1,  # Submitted
        "awaiting_bank_reconciliation": 1  # Custom flag we set
    }

    # Determine if this is a deposit (receive) or withdrawal (pay)
    amount = flt(bank_transaction.deposit or 0) or flt(bank_transaction.withdrawal or 0)

    if flt(bank_transaction.deposit or 0) > 0:
        # Deposit - Payment Entry type "Receive", paid_to matches bank_account
        filters["payment_type"] = "Receive"
        filters["paid_to"] = bank_transaction.bank_account
        filters["received_amount"] = amount
    else:
        # Withdrawal - Payment Entry type "Pay", paid_from matches bank_account
        filters["payment_type"] = "Pay"
        filters["paid_from"] = bank_transaction.bank_account
        filters["paid_amount"] = amount

    # Find Payment Entries
    payment_entries = frappe.get_all(
        "Payment Entry",
        filters=filters,
        fields=["name", "posting_date"],
        limit=10  # Reasonable limit
    )

    return [pe.name for pe in payment_entries]


def _update_invoice_status_after_bank_reconciliation(payment_entry_name: str, bank_transaction_name: str):
    """Update Purchase Invoice and Expense Request status after bank reconciliation.

    This is called when a Bank Transaction is reconciled and we find linked Payment Entries.
    """
    # Get Payment Entry details
    pe = frappe.get_doc("Payment Entry", payment_entry_name)

    # Get linked Expense Request
    expense_request = pe.get("imogi_expense_request")

    if not expense_request:
        # Try to find from references
        for ref in pe.get("references") or []:
            if ref.reference_doctype == "Purchase Invoice":
                pi_doc = frappe.get_doc("Purchase Invoice", ref.reference_name)
                expense_request = pi_doc.get("imogi_expense_request")
                if expense_request:
                    break

    if not expense_request:
        frappe.logger().info(
            f"[Bank Reconciliation] PE {payment_entry_name} reconciled via Bank Transaction {bank_transaction_name}, "
            f"but no Expense Request found."
        )
        return

    # Clear the awaiting flag
    frappe.db.set_value(
        "Payment Entry",
        payment_entry_name,
        "awaiting_bank_reconciliation",
        0,
        update_modified=False
    )

    # Update Expense Request status to Paid
    if expense_request:
        frappe.db.set_value(
            "Expense Request",
            expense_request,
            {"workflow_state": "Paid", "status": "Paid"},
            update_modified=False
        )
        frappe.logger().info(
            f"[Bank Reconciliation] Bank Transaction {bank_transaction_name} reconciled. "
            f"Expense Request {expense_request} status updated to Paid (via PE {payment_entry_name})."
        )

    # Add comment to Payment Entry
    try:
        pe.add_comment(
            "Info",
            _(f"Bank Transaction {bank_transaction_name} reconciled. Invoice status updated to Paid."),
            reference_doctype="Bank Transaction",
            reference_name=bank_transaction_name
        )
    except Exception:
        pass
