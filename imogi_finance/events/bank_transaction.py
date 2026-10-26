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


def _recompute_linked_purchase_invoice_status(payment_entry_name: str) -> list[str]:
    """Re-run ERPNext's own set_status() on every PI this Payment Entry pays.

    events/payment_entry.py::_revert_pi_status_for_bank_payment forces a paid PI
    back to "Unpaid" when the payment goes out via bank, on the promise that it
    flips to "Paid" once the bank side is reconciled. Nothing used to keep that
    promise - this is the other half.

    set_status() is used rather than writing "Paid" directly so that debit notes,
    returns and partial payments still resolve to the status ERPNext would pick.
    """
    pe = frappe.get_doc("Payment Entry", payment_entry_name)
    updated = []

    for ref in pe.get("references") or []:
        if ref.reference_doctype != "Purchase Invoice":
            continue

        pi = frappe.get_doc("Purchase Invoice", ref.reference_name)
        if pi.docstatus != 1:
            continue

        before = pi.status
        pi.set_status(update=True)
        if pi.status != before:
            updated.append(pi.name)
            frappe.logger().info(
                f"[Bank Reconciliation] PI {pi.name}: {before} -> {pi.status} "
                f"(via PE {payment_entry_name})"
            )

    return updated


def sync_reconciled_purchase_invoice_status():
    """Sweeper: settle any Payment Entry still flagged as awaiting reconciliation
    whose bank side has in fact been cleared.

    Needed because the Bank Clearance tool writes clearance_date with a raw
    frappe.db.set_value (erpnext/accounts/doctype/bank_clearance/bank_clearance.py),
    which fires no doc event at all - so on_update_after_submit above never runs
    for payments reconciled that way, and their invoices stay stuck on "Unpaid".
    Mirrors services/sales_invoice_list_status.sync_all_submitted_sales_invoices.
    """
    stale = frappe.get_all(
        "Payment Entry",
        filters={
            "docstatus": 1,
            "awaiting_bank_reconciliation": 1,
            "clearance_date": ["is", "set"],
        },
        pluck="name",
    )

    if not stale:
        return

    frappe.logger().info(
        f"[PI status sweeper] {len(stale)} Payment Entries cleared at the bank "
        f"but still flagged awaiting reconciliation"
    )

    for pe_name in stale:
        try:
            _recompute_linked_purchase_invoice_status(pe_name)
            frappe.db.set_value(
                "Payment Entry",
                pe_name,
                "awaiting_bank_reconciliation",
                0,
                update_modified=False,
            )
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title="PI status sweeper failed",
                message=f"Payment Entry: {pe_name}\n\n{frappe.get_traceback()}",
            )


def _update_invoice_status_after_bank_reconciliation(payment_entry_name: str, bank_transaction_name: str):
    """Update Purchase Invoice and Expense Request status after bank reconciliation.

    This is called when a Bank Transaction is reconciled and we find linked Payment Entries.
    """
    # Get Payment Entry details
    pe = frappe.get_doc("Payment Entry", payment_entry_name)

    # The invoice status is the whole point of this routine, so settle it before
    # anything below can return early - an invoice with no Expense Request still
    # has to come off "Unpaid" once the money has cleared the bank.
    _recompute_linked_purchase_invoice_status(payment_entry_name)

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
