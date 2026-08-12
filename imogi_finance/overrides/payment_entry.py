"""
Purchase Invoice overrides for Payment Entry creation
"""
import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry as erpnext_get_payment_entry
from frappe.utils import flt

try:
    # HRMS also overrides the Payment Entry controller (party_type == "Employee"
    # reference doctypes, ref detail fetching for Expense Claim/Employee Advance/etc).
    # Inherit from it when installed so we don't silently drop that behaviour.
    from hrms.overrides.employee_payment_entry import EmployeePaymentEntry as _PaymentEntryBase
except ImportError:
    _PaymentEntryBase = PaymentEntry


class CustomPaymentEntry(_PaymentEntryBase):
    """Splits the submitted state into "Unallocated" / "Reconciled" so it's
    possible to tell at a glance which Payment Entries still need to be
    reconciled against an invoice or bank transaction, instead of every
    submitted entry just showing generic "Submitted".
    """

    def set_status(self):
        if self.docstatus == 2:
            self.status = "Cancelled"
        elif self.docstatus == 1:
            self.status = "Reconciled" if flt(self.unallocated_amount) <= 0 else "Unallocated"
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
