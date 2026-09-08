"""Server-side handlers for the "Automatic Entries" reclass dialog on the Trial Balance report.

Lets an accountant move a balance from one GL account to another (e.g. fixing a
misclassified salary/allowance sub-ledger) without leaving the report, by
creating and submitting a Journal Entry: Debit the destination account,
Credit the source account.

This only makes sense as a "move a balance" operation when both accounts sit
on the same normal-balance side (both Expense, both Income, both Asset, ...).
Debiting one Expense account while crediting another Expense account moves
the balance across; debiting an Expense account while crediting an Income
account instead *increases both* (Income's normal balance is Credit), so
`create_reclass_entry` requires both accounts to share the same root_type.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from imogi_finance import roles

RECLASS_ROLES = (roles.SYSTEM_MANAGER, roles.ACCOUNTS_MANAGER)


@frappe.whitelist()
def get_account_balance(
    company: str,
    account: str,
    from_date: str,
    to_date: str,
    cost_center: str | None = None,
) -> float:
    """Net GL balance (debit - credit) of an account for a period.

    Used to pre-fill the reclass amount in the dialog; the user can still edit it.
    """
    frappe.only_for(RECLASS_ROLES)

    if not (company and account and from_date and to_date):
        frappe.throw(_("Company, Account, From Date and To Date are required."))

    filters = [
        ["company", "=", company],
        ["account", "=", account],
        ["is_cancelled", "=", 0],
        ["posting_date", "between", [from_date, to_date]],
    ]
    if cost_center:
        filters.append(["cost_center", "=", cost_center])

    result = frappe.get_all(
        "GL Entry",
        filters=filters,
        fields=["sum(debit) as debit_total", "sum(credit) as credit_total"],
    )
    if not result:
        return 0.0

    debit_total = flt(result[0].get("debit_total"))
    credit_total = flt(result[0].get("credit_total"))
    return debit_total - credit_total


@frappe.whitelist()
def create_reclass_entry(
    company: str,
    from_account: str,
    to_account: str,
    amount: float,
    posting_date: str | None = None,
    cost_center: str | None = None,
    remark: str | None = None,
) -> str:
    """Create and submit a reclass Journal Entry.

    Debits `to_account` and credits `from_account` for `amount`, moving the
    balance from the source account to the correct one.
    """
    frappe.only_for(RECLASS_ROLES)

    if not (company and from_account and to_account):
        frappe.throw(_("Company, From Account and To Account are required."))

    if from_account == to_account:
        frappe.throw(_("From Account and To Account must be different."))

    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Amount must be greater than zero."))

    from_root_type = frappe.db.get_value("Account", from_account, "root_type")
    to_root_type = frappe.db.get_value("Account", to_account, "root_type")
    if from_root_type != to_root_type:
        frappe.throw(
            _(
                "{0} is a {1} account and {2} is a {3} account — reclassing between "
                "different account natures isn't a simple debit/credit swap "
                "(it would increase both instead of moving a balance). Pick two "
                "accounts of the same type (e.g. two Expense accounts)."
            ).format(from_account, _(from_root_type), to_account, _(to_root_type))
        )

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Journal Entry"
    je.company = company
    je.posting_date = posting_date or nowdate()
    je.user_remark = remark or _("Account reclass: {0} → {1}").format(from_account, to_account)

    debit_line = {
        "account": to_account,
        "debit_in_account_currency": amount,
        "credit_in_account_currency": 0,
    }
    credit_line = {
        "account": from_account,
        "debit_in_account_currency": 0,
        "credit_in_account_currency": amount,
    }
    if cost_center:
        debit_line["cost_center"] = cost_center
        credit_line["cost_center"] = cost_center

    je.append("accounts", debit_line)
    je.append("accounts", credit_line)

    je.insert(ignore_permissions=True)
    je.submit()

    return je.name
