# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance.services.tax_invoice_service import sync_tax_invoice_with_sales
from imogi_finance.tax_invoice_ocr import NPWP_REGEX, normalize_npwp


def _validate_tax_invoice_no(tax_invoice_no: str | None):
    if not tax_invoice_no:
        frappe.throw(_("Tax Invoice Number is required."))

    if not re.fullmatch(r"\d{16}", tax_invoice_no or ""):
        frappe.throw(_("Tax Invoice Number must be exactly 16 digits."))


def _validate_npwp(npwp: str | None):
    if not npwp:
        frappe.throw(_("Customer NPWP is required."))

    if not NPWP_REGEX.fullmatch(npwp):
        normalized = normalize_npwp(npwp)
        if not normalized or not re.fullmatch(r"\d{15,20}", normalized):
            frappe.throw(_("Customer NPWP is not valid."))


def _ensure_file_exists(file_url: str | None):
    if not file_url:
        frappe.throw(_("Tax Invoice PDF is required."))

    if frappe.db.exists("File", {"file_url": file_url, "attached_to_doctype": "Tax Invoice Upload"}):
        return

    if frappe.db.exists("File", {"file_url": file_url}):
        return

    frappe.throw(_("Tax Invoice PDF could not be found. Please re-upload the file."))


def _ensure_unique_tax_invoice_no(doc: Document):
    existing = frappe.db.exists(
        "Tax Invoice Upload",
        {
            "tax_invoice_no": doc.tax_invoice_no,
            "name": ["!=", doc.name or ""],
        },
    )
    if existing:
        frappe.throw(_("Tax Invoice Number already exists on Tax Invoice Upload {0}.").format(existing))


class TaxInvoiceUpload(Document):
    def validate(self):
        self.tax_invoice_no = (self.tax_invoice_no or "").strip()
        _validate_tax_invoice_no(self.tax_invoice_no)
        _validate_npwp(self.customer_npwp)
        _ensure_unique_tax_invoice_no(self)
        _ensure_file_exists(self.invoice_pdf)

    def _should_attempt_sync(self) -> bool:
        return bool(self.linked_sales_invoice) and (self.status or "Draft") != "Synced"

    def _sync_on_change(self):
        if getattr(frappe.flags, "in_tax_invoice_upload_sync", False):
            return
        if not self._should_attempt_sync():
            return

        sync_tax_invoice_with_sales(self, fail_silently=True)

    def after_insert(self):
        self._sync_on_change()

    def on_update(self):
        self._sync_on_change()
    
    def on_trash(self):
        """Prevent accidental deletion of synced records.
        
        Does NOT cascade delete to Sales Invoice (safe delete).
        Requires confirmation for synced records.
        """
        # Require confirmation for synced records
        if self.status == "Synced":
            # Check if user has high privilege role
            if "System Manager" not in frappe.get_roles():
                frappe.throw(
                    _("Cannot delete synced Tax Invoice Upload. Only System Manager can delete synced records.")
                )
            
            # Log deletion for audit trail
            frappe.log_error(
                title=f"Tax Invoice Upload Deleted: {self.name}",
                message=f"User: {frappe.session.user}\nSI: {self.linked_sales_invoice}\nFP: {self.tax_invoice_no}"
            )
        
        # DO NOT cascade delete to Sales Invoice
        # Sales Invoice fields remain unchanged for audit trail

    @frappe.whitelist()
    def sync_now(self):
        return sync_tax_invoice_with_sales(self)
    
    @frappe.whitelist()
    def unlink_from_sales_invoice(self):
        """Clear Sales Invoice fields that were synced from this upload.
        
        This is a separate action from deletion - use when you need to
        "undo" the sync but keep the upload record.
        """
        self.check_permission("write")
        
        if not self.linked_sales_invoice:
            frappe.throw(_("No Sales Invoice linked"))
        
        # Only clear if the SI fields match this upload's data
        si = frappe.get_doc("Sales Invoice", self.linked_sales_invoice)
        
        updates = {}
        if si.out_fp_tax_invoice_pdf == self.invoice_pdf:
            updates["out_fp_tax_invoice_pdf"] = None
        
        if si.out_fp_no == self.tax_invoice_no:
            updates.update({
                "out_fp_no": None,
                "out_fp_no_seri": None,
                "out_fp_no_faktur": None,
                "out_fp_date": None,
                "out_fp_customer_npwp": None,
                "out_fp_dpp": None,
                "out_fp_ppn": None
            })
        
        if updates:
            frappe.db.set_value("Sales Invoice", self.linked_sales_invoice, updates, update_modified=False)
            
            # Add comment to SI
            si.add_comment(
                "Info",
                f"Tax Invoice Upload {self.name} unlinked by {frappe.session.user}"
            )
            
            # Update status
            self.status = "Draft"
            self.save()
            
            frappe.msgprint(_("Sales Invoice fields cleared"))
        else:
            frappe.msgprint(_("No matching fields found to clear"))

