import frappe
from frappe import _

from imogi_finance.branching import get_branch_settings, validate_branch_alignment
from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_cancel_updates,
    get_er_doctype,
    get_expense_request_links,
    get_expense_request_status,
)


def _is_bank_payment(doc) -> bool:
    """Check if Payment Entry is using Bank account (not Cash).

    Returns True if payment is via Bank account, False if Cash or other.
    """
    # Check paid_from account type for "Pay" payment type
    # Check paid_to account type for "Receive" payment type
    account_to_check = None

    if doc.payment_type == "Pay":
        account_to_check = doc.paid_from
    elif doc.payment_type == "Receive":
        account_to_check = doc.paid_to

    if not account_to_check:
        return False

    # Get account type from Account doctype
    account_type = frappe.db.get_value("Account", account_to_check, "account_type")

    # Return True if account type is Bank, False otherwise (Cash, etc)
    return account_type == "Bank"


def _resolve_expense_request(doc) -> str | None:
    """Resolve expense request from document or linked Purchase Invoice references.

    Returns:
        str | None: expense_request name or None
    """
    expense_request = doc.get("imogi_expense_request") or doc.get("expense_request")

    if expense_request:
        return expense_request

    references = doc.get("references") or []
    for ref in references:
        if ref.get("reference_doctype") != "Purchase Invoice":
            continue
        reference_name = ref.get("reference_name")
        if not reference_name:
            continue
        try:
            values = frappe.db.get_value(
                "Purchase Invoice",
                reference_name,
                ["imogi_expense_request", "expense_request"],
                as_dict=True,
            )
        except Exception:
            values = None
        if values:
            return values.get("imogi_expense_request") or values.get("expense_request")

    return None


def _ensure_expense_request_reference(doc, expense_request: str | None) -> None:
    """Ensure expense request reference is set on Payment Entry."""
    if expense_request and not doc.get("imogi_expense_request"):
        if hasattr(doc, "db_set"):
            try:
                doc.db_set("imogi_expense_request", expense_request, update_modified=False)
            except Exception:
                setattr(doc, "imogi_expense_request", expense_request)
        else:
            setattr(doc, "imogi_expense_request", expense_request)


def _validate_expense_request_link(doc, request, request_name: str) -> None:
    """Validate Payment Entry link to Expense Request.

    Note: Multiple PE per ER is allowed (1 PI can have multiple payments).
    This function is kept for future validation needs.
    """
    # ✅ Multiple PE per ER is ALLOWED
    # 1 PI can be paid via multiple Payment Entries
    # No validation needed here
    pass


def _sync_expense_request_link(
    doc, expense_request: str | None, *, allowed_statuses: frozenset[str] | set[str] | None = None
):
    """Sync Payment Entry link to Expense Request."""
    if not expense_request:
        frappe.logger().info(f"[_sync_expense_request_link] No request for PE: {doc.name}")
        return None

    frappe.logger().info(f"[_sync_expense_request_link] Syncing PE {doc.name} to ER {expense_request}")

    _ensure_expense_request_reference(doc, expense_request)

    request = get_approved_expense_request(
        expense_request, _("Payment Entry"), allowed_statuses=allowed_statuses
    )
    # ✅ Multiple PE per ER is allowed - no validation needed
    # Link established via doc.imogi_expense_request field
    # Status akan auto-update via query saat PE di-submit
    frappe.logger().info(f"[_sync_expense_request_link] Successfully synced PE {doc.name} to ER {expense_request}")
    return request


def sync_expense_request_reference(doc, method=None):
    """Persist Expense Request reference from Payment Entry references.

    This runs in validate hook to auto-populate the field before save.
    """
    # Skip if already set manually
    if doc.get("imogi_expense_request"):
        return

    expense_request = _resolve_expense_request(doc)

    # Debug logging
    frappe.logger().info(f"[Payment Entry validate] PE: {getattr(doc, 'name', 'NEW')}, Resolved ER: {expense_request}")
    frappe.logger().info(f"[Payment Entry validate] References count: {len(doc.get('references') or [])}")

    if expense_request:
        doc.imogi_expense_request = expense_request
        frappe.logger().info(f"[Payment Entry validate] Set imogi_expense_request to {expense_request}")


def on_change_expense_request(doc, method=None):
    """Auto-populate amount and description from selected Expense Request."""
    expense_request = doc.get("imogi_expense_request")

    request = None
    request_type = None

    if expense_request:
        try:
            _er_doctype = get_er_doctype(expense_request) or "Expense Request"
            request = frappe.get_doc(_er_doctype, expense_request)
            request_type = _er_doctype
        except frappe.DoesNotExistError:
            frappe.msgprint(
                _("Expense Request {0} not found").format(expense_request),
                alert=True,
                indicator="orange"
            )
            return

    if not request:
        return

    try:
        # Fetch amount from request
        amount = getattr(request, "total_amount", None)
        if amount:
            doc.paid_amount = amount
            doc.received_amount = amount

        # Fetch description from request (if remarks field exists, populate with request details)
        if request.get("name"):
            existing_remarks = doc.get("remarks") or ""
            if request_type not in existing_remarks:
                doc.remarks = _("Payment for {0} {1} - {2}").format(
                    request_type,
                    request.name,
                    request.get("description", request.get("purpose", request.get("request_type", "")))
                )
    except Exception as e:
        # Don't block document save for data fetch errors
        pass


def after_insert(doc, method=None):
    """Link Payment Entry to Expense Request immediately on draft creation."""
    # Skip - references table tidak terisi di after_insert
    # Logic di-handle di on_update dan on_submit
    pass


def on_update(doc, method=None):
    """Ensure Expense Request link syncs when set after insert."""
    if doc.get("docstatus") == 2:
        return

    # Skip if already linked
    if doc.get("imogi_expense_request"):
        return

    expense_request = _resolve_expense_request(doc)

    # Debug logging
    frappe.logger().info(f"[Payment Entry on_update] PE: {doc.name}, Resolved ER: {expense_request}")

    if not expense_request:
        return

    # Sync link to request (draft only)
    _sync_expense_request_link(doc, expense_request)





def on_submit(doc, method=None):
    expense_request = _resolve_expense_request(doc)

    if not expense_request:
        return

    # Handle Expense Request
    _handle_expense_request_submit(doc, expense_request)

    # Revert PI status to Unpaid if this is a Bank payment
    # This runs AFTER ERPNext native code updated PI to Paid
    if getattr(doc, "awaiting_bank_reconciliation", 0):
        _revert_pi_status_for_bank_payment(doc)


def _handle_expense_request_submit(doc, expense_request):
    """Handle Payment Entry submit for Expense Request."""
    # Sync link with validation for submit
    # Allow "Paid" status for re-submitting PE after previous PE was cancelled
    request = _sync_expense_request_link(
        doc, expense_request, allowed_statuses=frozenset({"PI Created", "Paid"})
    )
    if not request:
        return

    # Validate ada PI yang submitted (query dari DB)
    has_purchase_invoice = frappe.db.get_value(
        "Purchase Invoice",
        {"imogi_expense_request": request.name, "docstatus": 1},
        "name"
    )

    if not has_purchase_invoice:
        frappe.throw(
            _("Expense Request must be linked to a submitted Purchase Invoice before submitting Payment Entry.")
        )

    branch_settings = get_branch_settings()
    if branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
        validate_branch_alignment(
            getattr(doc, "branch", None),
            getattr(request, "branch", None),
            label=_("Payment Entry"),
        )

    # Check if payment is via Bank account
    is_bank_payment = _is_bank_payment(doc)

    if is_bank_payment:
        # Bank payment - PI tetap unpaid sampai bank transaction di-reconcile
        frappe.logger().info(
            f"[PE on_submit] PE {doc.name} submitted for ER {request.name} via Bank account. "
            f"PI {has_purchase_invoice} will remain Unpaid until bank transaction is reconciled."
        )
        # Set custom field to mark this PE is waiting for bank reconciliation
        doc.awaiting_bank_reconciliation = 1
    else:
        # Cash payment - PI langsung paid seperti biasa
        frappe.logger().info(
            f"[PE on_submit] PE {doc.name} submitted for ER {request.name} via Cash. "
            f"PI {has_purchase_invoice} will be marked as Paid immediately."
        )




def _revert_pi_status_for_bank_payment(doc):
    """Revert PI status to Unpaid for Bank payments.

    Called from on_submit AFTER ERPNext native code updates PI to Paid.
    This ensures PI remains Unpaid until Bank Transaction is reconciled.
    """
    # Get linked Purchase Invoices from references
    linked_pis = []
    for ref in doc.get("references") or []:
        if ref.reference_doctype == "Purchase Invoice":
            linked_pis.append(ref.reference_name)

    if not linked_pis:
        return

    frappe.logger().info(
        f"[PE on_submit] Bank payment detected. "
        f"Reverting PI status to Unpaid for {len(linked_pis)} invoices"
    )

    # Force set PI status back to Unpaid
    for pi_name in linked_pis:
        # Get PI to check current status
        pi_status = frappe.db.get_value("Purchase Invoice", pi_name, "status")

        if pi_status == "Paid":
            frappe.logger().info(
                f"[PE on_submit] Reverting PI {pi_name} from Paid to Unpaid"
            )

            # Update status directly
            frappe.db.set_value("Purchase Invoice", pi_name, "status", "Unpaid", update_modified=False)

            # Also update Expense Request status back to PI Created
            expense_request = frappe.db.get_value("Purchase Invoice", pi_name, "imogi_expense_request")
            if expense_request:
                _er_doctype = get_er_doctype(expense_request) or "Expense Request"
                frappe.db.set_value(
                    _er_doctype,
                    expense_request,
                    {"workflow_state": "PI Created", "status": "PI Created"},
                    update_modified=False
                )
                frappe.logger().info(
                    f"[PE on_submit] Reverted ER {expense_request} status to PI Created"
                )

    # Persist awaiting_bank_reconciliation flag to DB
    frappe.db.set_value("Payment Entry", doc.name, "awaiting_bank_reconciliation", 1, update_modified=False)


def on_update_after_submit(doc, method=None):
                frappe.logger().info(
                    f"[PE on_submit] Reverted ER {expense_request} status to PI Created"
                )


def on_update_after_submit(doc, method=None):
    """Handle Payment Entry updates after submit.

    For Bank payments, revert PI status back to Unpaid after ERPNext marks it as Paid.
    This is also called when PE is updated after submit.
    """
    # Check if this PE is awaiting bank reconciliation
    if not getattr(doc, "awaiting_bank_reconciliation", 0):
        return

    # Revert PI status for bank payment
    _revert_pi_status_for_bank_payment(doc)


def before_cancel(doc, method=None):
    """Pre-cancel validation and setup.

    1. Check if included in printed daily reports
    2. Set flags to ignore ALL linked documents (they should not be cancelled)
    3. Suppress "Cancel All Documents" dialog completely
    """
    # Check printed report constraint
    if _check_linked_to_printed_report(doc):
        frappe.throw(
            frappe._(
                "Cannot cancel Payment Entry {0} because it is included in a printed Cash/Bank Daily Report. "
                "Use the 'Reverse Payment Entry' button instead to create a reversal entry at today's date."
            ).format(doc.name),
            title=_("Cancellation Blocked")
        )

    # Set multiple flags to completely suppress "Cancel All Documents" dialog
    doc.flags.ignore_links = True
    doc.flags.ignore_link_validation = True
    doc.flags.skip_link_doctypes = True


def before_delete(doc, method=None):
    """Set flag to ignore link validation before deletion.

    This prevents LinkExistsError when deleting draft PE that is linked to ER.
    The actual link cleanup happens in on_trash.
    """
    expense_request = _resolve_expense_request(doc)
    if expense_request:
        doc.flags.ignore_links = True


def on_cancel(doc, method=None):
    """Handle Payment Entry cancellation.

    With multiple PE support:
    - If OTHER submitted PE still exist → Status remains "Paid"
    - If NO OTHER submitted PE exist → Status back to "PI Created"
    - Cancelled PE (docstatus=2) are automatically excluded by query

    Payment Entry is the endpoint of the payment flow and can be freely cancelled,
    EXCEPT when already included in printed Cash/Bank Daily Reports.

    Philosophy:
    - PE cancel does not invalidate upstream documents (ER, PI)
    - Links remain intact for audit trail
    - New PE can be created anytime from existing PI
    - Only constraint: printed daily reports (accounting lock)

    When PE is cancelled:
    1. Check if linked to any printed daily reports (done in before_cancel)
    2. If yes, BLOCK cancellation and suggest reversal
    3. If no, allow cancellation
    4. Status auto-sync from PI status badge (ERPNext auto-updates outstanding)
       - After PE cancelled, PI outstanding increases
       - PI status badge updates (Paid → Unpaid/Partially Paid)
       - Hook on PI on_update_after_submit will sync ER status
    """
    expense_request_name = doc.get("imogi_expense_request")

    # Update Expense Request workflow state and status based on PI status
    if expense_request_name:
        # Get current status based on PI (will reflect updated outstanding after cancel)
        _er_doctype = get_er_doctype(expense_request_name) or "Expense Request"
        request_links = get_expense_request_links(expense_request_name)
        next_status = get_expense_request_status(request_links)

        frappe.db.set_value(
            _er_doctype,
            expense_request_name,
            {"workflow_state": next_status, "status": next_status},
            update_modified=False
        )

        frappe.logger().info(
            f"[PE on_cancel] PE {doc.name} cancelled. "
            f"ER {expense_request_name} status updated to: {next_status} (based on PI status)"
        )


def _check_linked_to_printed_report(payment_entry) -> bool:
    """Check if Payment Entry is included in any printed (submitted) Cash/Bank Daily Reports.

    For Cash Account mode (GL Entry):
    - Check GL Entry posting_date and match with submitted reports

    For Bank Account mode (Bank Transaction):
    - Check Bank Transaction date and match with submitted reports

    Returns True if linked to submitted report (docstatus=1).
    """
    if not getattr(frappe, "db", None):
        return False

    # Get posting date from Payment Entry
    posting_date = getattr(payment_entry, "posting_date", None)
    if not posting_date:
        return False

    # Check for submitted (printed) reports on this date
    # For cash accounts (via GL Entry)
    printed_reports = frappe.get_all(
        "Cash Bank Daily Report",
        filters={
            "report_date": posting_date,
            "docstatus": 1  # Submitted = Printed
        },
        fields=["name", "cash_account", "bank_account"]
    )

    if not printed_reports:
        return False

    # Check if PE's account matches any printed report's account
    pe_account = getattr(payment_entry, "paid_from", None) or getattr(payment_entry, "paid_to", None)

    for report in printed_reports:
        if report.get("cash_account") == pe_account or report.get("bank_account") == pe_account:
            return True

    return False


@frappe.whitelist()
def reverse_payment_entry(payment_entry_name: str, reversal_date: str | None = None):
    """Create a reversal Payment Entry at today's date (or specified date).

    This is the proper way to reverse a Payment Entry that's already included
    in a printed Cash/Bank Daily Report, instead of cancelling it.

    The reversal entry:
    - Mirrors all amounts and accounts (flipped direction)
    - Posts at reversal_date (default: today)
    - Links back to original PE in remarks
    - Updates Expense Request status back to "PI Created"

    Args:
        payment_entry_name: Name of Payment Entry to reverse
        reversal_date: Date for reversal entry (default: today)

    Returns:
        dict: Created reversal Payment Entry
    """
    from datetime import date as date_class

    # Get original PE
    original_pe = frappe.get_doc("Payment Entry", payment_entry_name)

    if original_pe.docstatus != 1:
        frappe.throw(frappe._("Can only reverse submitted Payment Entries"))

    # Default reversal date to today
    if not reversal_date:
        reversal_date = frappe.utils.today()

    # Create reversal PE
    reversal_pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "posting_date": reversal_date,
        "payment_type": original_pe.payment_type,
        "company": original_pe.company,
        # Flip accounts
        "paid_from": original_pe.paid_to,  # Reversed
        "paid_to": original_pe.paid_from,  # Reversed
        "paid_amount": original_pe.paid_amount,
        "received_amount": original_pe.received_amount,
        # Flip account currencies to match flipped accounts
        "paid_from_account_currency": getattr(original_pe, "paid_to_account_currency", None),
        "paid_to_account_currency": getattr(original_pe, "paid_from_account_currency", None),
        "source_exchange_rate": original_pe.source_exchange_rate,
        "target_exchange_rate": original_pe.target_exchange_rate,
        "mode_of_payment": original_pe.mode_of_payment,
        "party_type": original_pe.party_type,
        "party": original_pe.party,
        # Copy party_account - this is the party's receivable/payable account
        "party_account": getattr(original_pe, "party_account", None),
        "branch": original_pe.branch if hasattr(original_pe, "branch") else None,
        "remarks": frappe._(
            "Reversal of Payment Entry {0} (original date: {1})"
        ).format(
            original_pe.name,
            frappe.utils.format_date(original_pe.posting_date)
        ),
        # Copy references if any
        "references": [
            {
                "reference_doctype": ref.reference_doctype,
                "reference_name": ref.reference_name,
                "total_amount": ref.total_amount,
                "outstanding_amount": ref.outstanding_amount,
                "allocated_amount": -ref.allocated_amount  # Negative to reverse
            }
            for ref in (original_pe.references or [])
        ] if original_pe.get("references") else [],
        # Mark as reversal
        "is_reversal": 1,
        "reversed_entry": original_pe.name
    })

    reversal_pe.insert()

    frappe.msgprint(
        frappe._(
            "Reversal Payment Entry {0} created for date {1}. "
            "Please review and submit it."
        ).format(reversal_pe.name, frappe.utils.format_date(reversal_date)),
        indicator="green",
        title=_("Reversal Created")
    )

    # Update original PE to mark it as reversed
    frappe.db.set_value("Payment Entry", payment_entry_name, {
        "is_reversed": 1,
        "reversal_entry": reversal_pe.name
    })

    # Update Expense Request workflow state
    # Check if other submitted PEs still exist
    expense_request = _resolve_expense_request(original_pe)

    if expense_request:
        # Get current status based on PI (will reflect updated outstanding after reversal)
        _er_doctype = get_er_doctype(expense_request) or "Expense Request"
        request_links = get_expense_request_links(expense_request)
        next_status = get_expense_request_status(request_links)

        frappe.db.set_value(
            _er_doctype,
            expense_request,
            {"workflow_state": next_status, "status": next_status},
            update_modified=False
        )

        frappe.logger().info(
            f"[PE reversal] PE {payment_entry_name} reversed. "
            f"ER {expense_request} status updated to: {next_status} (based on PI status)"
        )

    return reversal_pe.as_dict()


def on_trash(doc, method=None):
    """Clear links from Expense Request before deleting PE to avoid LinkExistsError."""
    expense_request, branch_request = _resolve_expense_request(doc)

    # Handle Expense Request - clear link and update workflow state and status
    if expense_request:
        _er_doctype = get_er_doctype(expense_request)
        if _er_doctype:
            updates = {}

            # Clear linked_payment_entry if it matches (THIS IS THE KEY FIX)
            # This field is what causes LinkExistsError
            current_linked = frappe.db.get_value(_er_doctype, expense_request, "linked_payment_entry")
            if current_linked == doc.name:
                updates["linked_payment_entry"] = None

            # Update workflow state and status based on remaining links
            request_links = get_expense_request_links(expense_request)
            next_status = get_expense_request_status(request_links)
            updates["workflow_state"] = next_status
            updates["status"] = next_status  # Update status field juga

            frappe.db.set_value(_er_doctype, expense_request, updates)
            frappe.db.commit()  # Commit immediately to ensure link is cleared
            frappe.logger().info(
                f"[PE trash] PE {doc.name} deleted. Updated ER {expense_request} status to {next_status}"
            )


