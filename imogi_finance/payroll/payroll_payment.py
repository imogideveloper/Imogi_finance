"""Bridge Payroll Entry to Administrative Payment Voucher (APV) so payroll
disbursement goes through the same wet-signature approval/payment flow as
other administrative payments - see
imogi_finance.imogi_finance.doctype.administrative_payment_voucher."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, nowdate


@frappe.whitelist()
def request_payroll_payment(payroll_entry_name: str) -> dict[str, object]:
    """Create (or reuse) the Administrative Payment Voucher for a Payroll Entry."""
    pe = frappe.get_doc("Payroll Entry", payroll_entry_name)

    if pe.docstatus != 1:
        frappe.throw(_("Payroll Entry harus sudah Submitted sebelum mengajukan pembayaran."))

    existing = getattr(pe, "linked_payment_voucher", None)
    if existing and frappe.db.exists("Administrative Payment Voucher", existing):
        if frappe.db.get_value("Administrative Payment Voucher", existing, "docstatus") != 2:
            return {"payment_voucher": existing}

    amount = flt(getattr(pe, "total_amount", 0))
    if amount <= 0:
        frappe.throw(_("Total Amount Payroll Entry ini masih 0 - belum ada slip gaji yang bisa dibayar."))

    if not getattr(pe, "payroll_payable_account", None):
        frappe.throw(_("Payroll Payable Account belum diisi di Payroll Entry ini."))

    if not getattr(pe, "payment_account", None):
        frappe.throw(
            _("Payment Account belum diisi di Payroll Entry ini (tab Accounting & Payment).")
        )

    cost_center = getattr(pe, "cost_center", None) or frappe.db.get_value(
        "Company", pe.company, "cost_center"
    )

    apv = frappe.new_doc("Administrative Payment Voucher")
    apv.company = pe.company
    apv.posting_date = pe.posting_date or nowdate()
    apv.direction = "Pay"
    apv.amount = amount
    apv.bank_cash_account = pe.payment_account
    apv.target_gl_account = pe.payroll_payable_account
    apv.cost_center = cost_center
    apv.branch = getattr(pe, "branch", None)
    apv.reference_doctype = "Payroll Entry"
    apv.reference_name = pe.name
    apv.justification = _("Pembayaran Payroll {0}").format(getattr(pe, "periode", None) or pe.name)
    apv.insert(ignore_permissions=True)

    pe.db_set("linked_payment_voucher", apv.name)
    frappe.db.commit()

    return {"payment_voucher": apv.name}
