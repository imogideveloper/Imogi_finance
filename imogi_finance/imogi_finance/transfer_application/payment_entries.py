from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_account
from erpnext.accounts.utils import get_company_default

from imogi_finance.transfer_application.settings import get_transfer_application_settings
from imogi_finance.settings.utils import get_gl_account
from imogi_finance.settings.gl_purposes import DEFAULT_PAID_FROM


def create_payment_entry_for_transfer_application(
    transfer_application: Document,
    *,
    submit: bool = False,
    posting_date: str | None = None,
    paid_amount: float | None = None,
    ignore_permissions: bool = False,
) -> list[Document]:
    """
    Create multiple Payment Entries - one per unique beneficiary.
    Returns list of created Payment Entry documents.
    """
    # Check if payment entries already exist
    if transfer_application.payment_entries:
        existing_pes = []
        for pe_row in transfer_application.payment_entries:
            if pe_row.payment_entry:
                pe = frappe.get_doc("Payment Entry", pe_row.payment_entry)
                if pe.docstatus != 2:  # Not cancelled
                    existing_pes.append(pe)
        if existing_pes:
            return existing_pes

    settings = get_transfer_application_settings()

    # Use paid_from_account from Transfer Application if set
    paid_from = None
    if hasattr(transfer_application, 'paid_from_account') and transfer_application.paid_from_account:
        paid_from = transfer_application.paid_from_account
    else:
        paid_from = _resolve_paid_from_account(transfer_application.company, settings=settings)

    if not paid_from:
        frappe.throw(
            _("Paid From Account is not configured for {0}. Please set it in Finance Control Settings → GL Account Mappings (purpose: default_paid_from) or provide it in Transfer Application.").format(
                transfer_application.company
            )
        )

    # Group items by beneficiary (beneficiary_name + bank_name + account_number)
    beneficiary_groups = _group_items_by_beneficiary(transfer_application.items)

    if not beneficiary_groups:
        frappe.throw(_("No items found to create Payment Entries."))

    posting_date = posting_date or transfer_application.requested_transfer_date or transfer_application.posting_date or today()

    created_pes = []

    # Create one Payment Entry per beneficiary group
    for beneficiary_key, items in beneficiary_groups.items():
        total_amount = sum(frappe.utils.flt(item.amount) for item in items)
        first_item = items[0]

        # Determine paid_to account - MUST come from party (beneficiary)
        if not first_item.party_type or not first_item.party:
            frappe.throw(
                _("Beneficiary {0}: party_type and party are required to determine destination account.").format(
                    first_item.beneficiary_name
                )
            )

        try:
            paid_to = get_party_account(first_item.party_type, first_item.party, transfer_application.company)
        except Exception as e:
            frappe.throw(
                _("Could not get account for {0} {1}: {2}").format(
                    first_item.party_type, first_item.party, str(e)
                )
            )

        if not paid_to:
            frappe.throw(
                _("No account found for {0} {1} in company {2}.").format(
                    first_item.party_type, first_item.party, transfer_application.company
                )
            )

        # Create Payment Entry
        payment_entry = frappe.new_doc("Payment Entry")
        payment_entry.payment_type = "Pay"
        payment_entry.company = transfer_application.company
        payment_entry.posting_date = posting_date
        payment_entry.paid_from = paid_from
        payment_entry.paid_to = paid_to
        payment_entry.paid_amount = total_amount
        payment_entry.received_amount = total_amount

        if transfer_application.transfer_method and frappe.db.exists("Mode of Payment", transfer_application.transfer_method):
            payment_entry.mode_of_payment = transfer_application.transfer_method

        payment_entry.reference_no = f"{transfer_application.name} - {first_item.beneficiary_name}"
        payment_entry.reference_date = posting_date

        # Build remarks with all items for this beneficiary
        item_descriptions = [item.description or f"Item {idx+1}" for idx, item in enumerate(items)]
        payment_entry.remarks = _(
            "Transfer Application {0} | Beneficiary: {1} | Items: {2}"
        ).format(
            transfer_application.name,
            first_item.beneficiary_name,
            ", ".join(item_descriptions[:3]) + ("..." if len(item_descriptions) > 3 else "")
        )

        # Set party info if available
        if first_item.party_type and first_item.party:
            payment_entry.party_type = first_item.party_type
            payment_entry.party = first_item.party
            payment_entry.party_account = paid_to

        # Add reference documents from items
        for item in items:
            if item.reference_doctype and item.reference_name:
                payment_entry.append(
                    "references",
                    {
                        "reference_doctype": item.reference_doctype,
                        "reference_name": item.reference_name,
                        "allocated_amount": frappe.utils.flt(item.amount),
                    },
                )

        if hasattr(payment_entry, "transfer_application"):
            payment_entry.transfer_application = transfer_application.name

        payment_entry.set_missing_values()

        payment_entry.flags.ignore_permissions = ignore_permissions
        payment_entry.insert(ignore_permissions=ignore_permissions)

        if submit:
            payment_entry.submit()

        created_pes.append(payment_entry)

        # Add to parent's payment_entries child table
        transfer_application.append("payment_entries", {
            "payment_entry": payment_entry.name,
            "beneficiary_name": first_item.beneficiary_name,
            "bank_name": first_item.bank_name,
            "account_number": first_item.account_number,
            "amount": total_amount,
            "pe_status": "Submitted" if payment_entry.docstatus == 1 else "Draft",
            "posting_date": payment_entry.posting_date
        })

    # Save parent to persist payment_entries child table
    transfer_application.flags.ignore_validate_update_after_submit = True
    transfer_application.save(ignore_permissions=ignore_permissions)

    return created_pes


def _group_items_by_beneficiary(items):
    """
    Group transfer items by unique beneficiary (name + bank + account).
    Returns dict with key = (beneficiary_name, bank_name, account_number)
    """
    from collections import defaultdict

    grouped = defaultdict(list)

    for item in items or []:
        if not item.beneficiary_name:
            continue

        key = (
            item.beneficiary_name or "",
            item.bank_name or "",
            item.account_number or ""
        )
        grouped[key].append(item)

    return dict(grouped)



def _resolve_paid_from_account(company: str, *, settings=None):
    """Resolve paid_from account via GL Mappings or company/bank defaults"""
    # First try GL Mappings (new approach)
    try:
        paid_from = get_gl_account(DEFAULT_PAID_FROM, company=company, required=False)
        if paid_from:
            return paid_from
    except Exception:
        pass  # Fall back to company defaults

    # Fallback: bank/cash accounts
    bank_account = _get_default_bank_cash_account(company, account_type="Bank")
    if bank_account and bank_account.get("account"):
        return bank_account.get("account")

    cash_account = _get_default_bank_cash_account(company, account_type="Cash")
    if cash_account and cash_account.get("account"):
        return cash_account.get("account")

    return None


def _get_default_bank_cash_account(company: str, *, account_type: str):
    get_default = None
    try:
        get_default = frappe.get_attr("erpnext.accounts.utils.get_default_bank_cash_account")
    except Exception:
        get_default = None

    if get_default:
        return get_default(company, account_type=account_type)

    field_map = {
        "Bank": "default_bank_account",
        "Cash": "default_cash_account",
    }
    default_field = field_map.get(account_type)
    if not default_field:
        return None

    account = get_company_default(company, default_field)
    if not account:
        return None

    return {"account": account}

