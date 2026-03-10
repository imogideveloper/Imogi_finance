# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance.tax_invoice_ocr import get_tax_invoice_ocr_monitoring


class TaxInvoiceOCRMonitoring(Document):
    def validate(self):
        """Auto-populate data based on Target DocType"""
        if self.target_doctype and self.target_name:
            self._populate_from_target()

    def _populate_from_target(self):
        """Fetch and populate data from various target doctypes"""
        if self.target_doctype == "Tax Invoice OCR Upload":
            self._populate_from_ocr_upload()
        elif self.target_doctype == "Purchase Invoice":
            self._populate_from_purchase_invoice()
        elif self.target_doctype == "Expense Request":
            self._populate_from_expense_request()

    def _populate_from_purchase_invoice(self):
        """Fetch data from Purchase Invoice and linked OCR Upload"""
        if not frappe.db.exists("Purchase Invoice", self.target_name):
            return

        pi = frappe.get_doc("Purchase Invoice", self.target_name)

        # Try to find linked OCR Upload via custom field
        ocr_upload_name = (
            pi.get("ti_tax_invoice_upload")
            or pi.get("tax_invoice_ocr_upload")
        )

        if ocr_upload_name and frappe.db.exists("Tax Invoice OCR Upload", ocr_upload_name):
            # Populate from linked OCR Upload
            temp_target = self.target_name
            temp_doctype = self.target_doctype
            self.target_name = ocr_upload_name
            self._populate_from_ocr_upload()
            # Restore original target
            self.target_name = temp_target
            self.target_doctype = temp_doctype
        else:
            # Populate basic data from Purchase Invoice itself
            self.npwp = pi.get("tax_id") or pi.get("supplier_tax_id")
            items = pi.get("items", []) or []
            dpp_total = sum(
                float(item.get("base_net_amount") or item.get("net_amount") or item.get("amount") or 0)
                for item in items
            )
            self.dpp = dpp_total or pi.get("net_total")
            # Calculate PPN from taxes table
            ppn_total = 0.0
            for tax in pi.get("taxes", []) or []:
                description = (tax.get("description") or "").upper()
                account_head = (tax.get("account_head") or "").upper()
                if "PPN" in description or "VAT" in description or "PPN" in account_head or "VAT" in account_head:
                    ppn_total += float(tax.get("tax_amount") or 0)
            self.ppn = ppn_total

    def _populate_from_expense_request(self):
        """Fetch data from Expense Request and linked OCR/PI"""
        if not frappe.db.exists("Expense Request", self.target_name):
            return

        er = frappe.get_doc("Expense Request", self.target_name)

        # Try to find linked Purchase Invoice or OCR Upload
        pi_name = er.get("purchase_invoice")
        ocr_name = er.get("tax_invoice_ocr_upload")

        if pi_name:
            temp_target = self.target_name
            temp_doctype = self.target_doctype
            self.target_name = pi_name
            self._populate_from_purchase_invoice()
            self.target_name = temp_target
            self.target_doctype = temp_doctype
        elif ocr_name:
            temp_target = self.target_name
            temp_doctype = self.target_doctype
            self.target_name = ocr_name
            self._populate_from_ocr_upload()
            self.target_name = temp_target
            self.target_doctype = temp_doctype

    def _populate_from_ocr_upload(self):
        """Fetch and populate data directly from Tax Invoice OCR Upload"""
        if not frappe.db.exists("Tax Invoice OCR Upload", self.target_name):
            return

        ocr_upload = frappe.get_doc("Tax Invoice OCR Upload", self.target_name)

        # Populate basic info
        self.upload_name = ocr_upload.name
        self.tax_invoice_pdf = ocr_upload.get("tax_invoice_pdf")

        # Populate extracted data - use correct field names from JSON schema
        self.ocr_confidence = ocr_upload.get("ocr_confidence") or 0
        self.fp_date = ocr_upload.get("fp_date")
        self.fp_no = ocr_upload.get("fp_no")
        self.npwp = ocr_upload.get("npwp")
        self.dpp = ocr_upload.get("dpp")
        self.ppn = ocr_upload.get("ppn")
        self.ppnbm = ocr_upload.get("ppnbm") or 0
        self.ppn_type = ocr_upload.get("ppn_type")

        # Populate validation flags
        self.duplicate_flag = 1 if ocr_upload.get("duplicate_flag") else 0
        self.npwp_match = 1 if ocr_upload.get("npwp_match") else 0

        # Populate status
        self.ocr_status = ocr_upload.get("ocr_status")
        self.verification_status = ocr_upload.get("verification_status")
        self.verification_notes = ocr_upload.get("verification_notes")

        # Check if raw JSON exists
        ocr_json = ocr_upload.get("ocr_raw_json")
        if ocr_json:
            self.ocr_raw_json_present = 1
            self.ocr_raw_json = ocr_json

    @frappe.whitelist()
    def refresh_status(self):
        if not self.target_doctype or not self.target_name:
            frappe.throw(_("Target DocType and Target Name are required to refresh status."))

        # Use new populate logic for all supported doctypes
        self._populate_from_target()
        self.save(ignore_permissions=True)
        return {"success": True, "message": _("Data refreshed successfully")}
        doc_info = result.get("doc") or {}
        job_info = result.get("job") or {}

        self.job_name = result.get("job_name")
        self.provider = result.get("provider")
        self.max_retry = result.get("max_retry")

        self.ocr_status = doc_info.get("ocr_status")
        self.verification_status = doc_info.get("verification_status")
        self.verification_notes = doc_info.get("verification_notes")
        self.upload_name = doc_info.get("upload_name")
        self.ocr_confidence = doc_info.get("ocr_confidence")
        self.fp_no = doc_info.get("fp_no")
        self.fp_date = doc_info.get("fp_date")
        self.npwp = doc_info.get("npwp")
        self.dpp = doc_info.get("dpp")
        self.ppn = doc_info.get("ppn")
        self.ppnbm = doc_info.get("ppnbm")
        self.ppn_type = doc_info.get("ppn_type")
        self.duplicate_flag = doc_info.get("duplicate_flag")
        self.npwp_match = doc_info.get("npwp_match")
        self.tax_invoice_pdf = doc_info.get("tax_invoice_pdf")
        self.ocr_raw_json_present = 1 if doc_info.get("ocr_raw_json_present") else 0
        self.ocr_raw_json = doc_info.get("ocr_raw_json")

        self.job_queue = job_info.get("queue")
        self.job_status = job_info.get("status")
        self.job_exc_info = job_info.get("exc_info")

        job_kwargs = job_info.get("kwargs")
        if isinstance(job_kwargs, str):
            self.job_kwargs = job_kwargs
        elif job_kwargs is not None:
            self.job_kwargs = json.dumps(job_kwargs, indent=2, ensure_ascii=False, default=str)
        else:
            self.job_kwargs = None

        self.enqueued_at = job_info.get("enqueued_at")
        self.started_at = job_info.get("started_at")
        self.ended_at = job_info.get("ended_at")

        return result
