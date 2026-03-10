# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from imogi_finance import roles
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from imogi_finance.api.payroll_sync import get_bpjs_total
from imogi_finance.tax_operations import (
    _get_period_bounds,
    compute_tax_totals,
    create_tax_payment_journal_entry as build_tax_payment_journal_entry,
    create_tax_payment_entry as build_payment_entry,
)


class TaxPaymentBatch(Document):
    """Collects tax liabilities for a period and builds native Journal Entry drafts."""

    def validate(self):
        self._set_period_dates()
        self._ensure_tax_profile()
        self._ensure_status()
        self._ensure_payable_account()
        self._refresh_amount_if_needed()

    def on_submit(self):
        """Auto-create and submit Journal Entry when Tax Payment Batch is submitted.

        Tax payments to DJP are direct liability clearances (Dr Tax Payable, Cr Cash/Bank).
        Journal Entry is used instead of Payment Entry to avoid the unallocated supplier
        advance payment issue that occurs when a Payment Entry is not reconciled to an invoice.
        """
        if self.amount and self.amount > 0:
            try:
                if not self.posting_date:
                    self.db_set("posting_date", nowdate())
                je_name = build_tax_payment_journal_entry(self)
                # Auto-submit the JE
                je_doc = frappe.get_doc("Journal Entry", je_name)
                je_doc.submit()
                # Update status to Paid after JE is submitted
                self.db_set("status", "Paid", update_modified=False)
                frappe.msgprint(
                    _("Journal Entry {0} created and submitted successfully").format(
                        frappe.utils.get_link_to_form("Journal Entry", je_name)
                    ),
                    indicator="green"
                )
            except Exception as e:
                frappe.log_error(message=str(e), title="Tax Payment Batch: Failed to create Journal Entry")
                frappe.throw(_("Failed to create Journal Entry: {0}").format(str(e)))

    def _create_and_submit_payment_entry(self):
        """Create and submit Payment Entry without requiring Party Type/Party"""
        # Validate required fields
        if not self.payable_account:
            frappe.throw(_("Payable Account is required to create Payment Entry"))
        if not self.payment_account:
            frappe.throw(_("Payment Account is required to create Payment Entry"))
        if not self.amount or self.amount <= 0:
            frappe.throw(_("Payment Amount must be greater than 0"))

        # Get or create default tax authority supplier
        party = self._get_or_create_tax_authority_supplier()

        # Create Payment Entry
        pe = frappe.new_doc("Payment Entry")
        pe.company = self.company
        pe.payment_type = "Pay"

        # Set Party (required by ERPNext)
        pe.party_type = "Supplier"
        pe.party = party

        pe.posting_date = self.payment_date or self.posting_date or nowdate()
        pe.mode_of_payment = self.payment_mode or "Bank"

        # Paid From = Payment Account (Bank/Cash - where money comes from)
        # Paid To = Payable Account (Tax liability - where money goes to reduce)
        pe.paid_from = self.payment_account
        pe.paid_to = self.payable_account
        pe.paid_amount = self.amount
        pe.received_amount = self.amount

        # Reference to Tax Payment Batch
        pe.reference_no = self.name
        pe.reference_date = pe.posting_date
        title = _("Tax Payment {0} {1}/{2} - {3}").format(
            self.tax_type or "Tax",
            self.period_month or "",
            self.period_year or "",
            self.name,
        )
        pe.remarks = _("Tax payment for {0} - Period {1}/{2} - Batch {3}").format(
            self.tax_type or "Tax",
            self.period_month or "",
            self.period_year or "",
            self.name,
        )
        if getattr(pe, "meta", None) and pe.meta.get_field("title"):
            pe.title = title
        elif getattr(pe, "meta", None) and pe.meta.get_field("party_name"):
            pe.party_name = title

        # Insert and Submit
        pe.insert(ignore_permissions=True)
        pe.submit()

        # Update Tax Payment Batch with reference
        self.db_set("payment_entry", pe.name, update_modified=False)
        self.db_set("status", "Paid", update_modified=False)

        return pe.name

    def _get_or_create_tax_authority_supplier(self):
        """Get or create a default supplier for tax authority payments"""
        supplier_name = "Government - Tax Authority"

        # Check if supplier exists
        if frappe.db.exists("Supplier", supplier_name):
            return supplier_name

        # Create supplier
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = supplier_name
        supplier.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name") or "All Supplier Groups"
        supplier.supplier_type = "Company"
        supplier.country = "Indonesia"
        supplier.insert(ignore_permissions=True)

        return supplier.name

    def on_cancel(self):
        """Auto-cancel linked Journal Entry when Tax Payment Batch is cancelled."""
        je_name = self.get("journal_entry")
        if not je_name:
            return
        try:
            je_doc = frappe.get_doc("Journal Entry", je_name)
            if je_doc.docstatus == 1:
                je_doc.cancel()
                frappe.msgprint(
                    _("Journal Entry {0} has been cancelled.").format(
                        frappe.utils.get_link_to_form("Journal Entry", je_name)
                    ),
                    indicator="orange",
                    alert=True
                )
        except frappe.DoesNotExistError:
            pass
        self.db_set("status", "Draft", update_modified=False)

    def _set_period_dates(self):
        if not self.period_month or not self.period_year:
            return

        date_from, date_to = _get_period_bounds(int(self.period_month), int(self.period_year))
        self.date_from = date_from
        self.date_to = date_to

    def _ensure_tax_profile(self):
        if self.tax_profile or not self.company:
            return
        profile = frappe.db.get_value("Tax Profile", {"company": self.company})
        if profile:
            self.tax_profile = profile

    def _ensure_status(self):
        if not self.status:
            self.status = "Draft"

    def _ensure_payable_account(self):
        if self.payable_account or not self.tax_profile:
            return

        profile = frappe.get_cached_doc("Tax Profile", self.tax_profile)
        if self.tax_type == "PPN" and profile.get("ppn_payable_account"):
            self.payable_account = profile.ppn_payable_account
        elif self.tax_type == "PB1":
            # Use branch-specific PB1 account if available
            branch = getattr(self, "branch", None)
            if branch and hasattr(profile, "get_pb1_account"):
                self.payable_account = profile.get_pb1_account(branch)
            elif profile.get("pb1_payable_account"):
                self.payable_account = profile.pb1_payable_account
        elif self.tax_type == "BPJS" and profile.get("bpjs_payable_account"):
            self.payable_account = profile.bpjs_payable_account
        elif self.tax_type == "PPh" and self.pph_type:
            for row in profile.get("pph_accounts", []) or []:
                if row.pph_type == self.pph_type and row.payable_account:
                    self.payable_account = row.payable_account
                    break

    def _refresh_amount_if_needed(self):
        if self.amount:
            return
        self.pull_amounts()

    def pull_amounts(self):
        totals = None
        if self.source_closing:
            closing = frappe.get_doc("Tax Period Closing", self.source_closing)
            closing._update_totals_from_snapshot()
            totals = {
                "input_vat_total": closing.input_vat_total,
                "output_vat_total": closing.output_vat_total,
                "vat_net": closing.vat_net,
                "pph_total": closing.pph_total,
                "pb1_total": closing.pb1_total,
            }
        else:
            totals = compute_tax_totals(self.company, self.date_from, self.date_to)

        if self.tax_type == "PPN":
            self.amount = flt(totals.get("vat_net"))
        elif self.tax_type == "PPh":
            self.amount = flt(totals.get("pph_total"))
        elif self.tax_type == "PB1":
            self.amount = flt(totals.get("pb1_total"))
        elif self.tax_type == "BPJS":
            self.amount = flt(get_bpjs_total(self.company, self.date_from, self.date_to))

        if self.amount and self.amount < 0:
            self.amount = 0

    def create_journal_entry(self):
        frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
        if not self.posting_date:
            self.posting_date = nowdate()
        return build_tax_payment_journal_entry(self)

    def create_payment_entry(self):
        frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
        if not self.payment_date:
            self.payment_date = nowdate()
        return build_payment_entry(self)


@frappe.whitelist()
def refresh_tax_payment_amount(batch_name: str):
    batch = frappe.get_doc("Tax Payment Batch", batch_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
    batch.pull_amounts()
    batch.save(ignore_permissions=True)
    return batch.amount


@frappe.whitelist()
def create_tax_payment_entry(batch_name: str):
    batch = frappe.get_doc("Tax Payment Batch", batch_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
    je_name = batch.create_payment_entry()
    batch.save(ignore_permissions=True)
    return je_name


@frappe.whitelist()
def create_tax_payment_journal_entry(batch_name: str):
    batch = frappe.get_doc("Tax Payment Batch", batch_name)
    frappe.only_for((roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
    je_name = batch.create_journal_entry()
    batch.save(ignore_permissions=True)
    return je_name
