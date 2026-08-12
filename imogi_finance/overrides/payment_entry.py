"""
Purchase Invoice overrides for Payment Entry creation
"""
import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry as erpnext_get_payment_entry

try:
    # HRMS also overrides the Payment Entry controller (party_type == "Employee"
    # reference doctypes, ref detail fetching for Expense Claim/Employee Advance/etc).
    # Inherit from it when installed so we don't silently drop that behaviour.
    from hrms.overrides.employee_payment_entry import EmployeePaymentEntry as _PaymentEntryBase
except ImportError:
    _PaymentEntryBase = PaymentEntry


class CustomPaymentEntry(_PaymentEntryBase):
    """Splits the submitted state into "Unreconciled" / "Reconciled" based on
    whether the entry has been matched against a Bank Transaction
    (clearance_date), so it's possible to tell at a glance which payments
    still need to go through Bank Reconciliation Tool -- instead of every
    submitted entry just showing generic "Submitted" (or, as originally
    tried, being "Reconciled" the moment it's allocated to an invoice, which
    made every entry look done immediately since PEs are usually created
    already fully allocated).
    """

    def set_status(self):
        if self.docstatus == 2:
            self.status = "Cancelled"
        elif self.docstatus == 1:
            self.status = "Reconciled" if self.clearance_date else "Unreconciled"
        else:
            self.status = "Draft"

        self.db_set("status", self.status, update_modified=True)

    def on_update_after_submit(self):
        super().on_update_after_submit()
        # Reconciliation tools (Payment Reconciliation, Bank Reconciliation Tool)
        # update references/unallocated_amount on an already-submitted entry via
        # a plain save, which doesn't otherwise re-run set_status().
        self.set_status()


@frappe.whitelist()
def get_payment_entry(dt, dn, party_amount=None, bank_account=None, bank_amount=None):
    """
    Override ERPNext get_payment_entry to include imogi_expense_request field
    
    This ensures when user clicks "Make > Payment Entry" from Purchase Invoice,
    the Expense Request link is automatically populated.
    """
    # Call original ERPNext method
    payment_entry = erpnext_get_payment_entry(dt, dn, party_amount, bank_account, bank_amount)
    
    # If source is Purchase Invoice, copy imogi_expense_request field
    if dt == "Purchase Invoice":
        pi = frappe.get_doc("Purchase Invoice", dn)
        expense_request = getattr(pi, "imogi_expense_request", None)
        
        if expense_request:
            payment_entry.imogi_expense_request = expense_request
            frappe.logger().info(
                f"[get_payment_entry override] Copied ER {expense_request} from PI {dn} to PE"
            )
    
    return payment_entry


def backfill_payment_entry_status():
    """Recompute status on existing Payment Entries to match the current
    clearance_date-based logic (Reconciled / Unreconciled / Cancelled).

    Runs on every migrate (see hooks.py after_migrate) so entries created
    before this logic existed -- or under the earlier unallocated_amount-based
    version -- get corrected without needing to be opened and resaved by
    hand. Cheap no-op once everything is already in sync.
    """
    rows = frappe.db.sql(
        """
        select name, docstatus, clearance_date, status
        from `tabPayment Entry`
        where docstatus in (1, 2)
        """,
        as_dict=True,
    )

    for row in rows:
        if row.docstatus == 2:
            correct_status = "Cancelled"
        else:
            correct_status = "Reconciled" if row.clearance_date else "Unreconciled"

        if row.status != correct_status:
            frappe.db.set_value(
                "Payment Entry", row.name, "status", correct_status, update_modified=False
            )

    frappe.db.commit()
