# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from typing import Optional, Dict, Any

import frappe
from frappe import _
from imogi_finance import roles
from frappe.model.document import Document
from frappe.utils import flt, nowdate, now

from imogi_finance.tax_operations import (
    _get_period_bounds,
    build_register_snapshot,
    create_vat_netting_entry,
    generate_coretax_export,
)


class TaxPeriodClosing(Document):
    """Monthly tax period closing that locks faktur pajak edits and tracks exports.

    This doctype manages the monthly tax period closing workflow, including:
    - Tax register snapshot generation (VAT Input/Output, PPh, PB1)
    - CoreTax export file generation (CSV/XLSX)
    - VAT netting journal entry creation
    - Period locking to prevent tax invoice edits

    Workflow States:
        Draft: Initial creation, editable
        Reviewed: Registers validated by Tax Reviewer
        Approved: Ready for submission and netting
        Closed: Submitted and locked (docstatus=1)

    Key Features:
        - Auto-fetches Tax Profile based on company
        - Validates period uniqueness (one closing per company/period)
        - Tracks last refresh timestamp
        - Supports background job for large periods
        - Creates audit trail with created_by and submit_on
    """

    # Type hints for autocomplete
    company: str
    period_month: int
    period_year: int
    date_from: str
    date_to: str
    status: str
    tax_profile: Optional[str]
    register_snapshot: Optional[str]
    last_refresh_on: Optional[str]
    is_generating: int

    def validate(self):
        """Master validation method - calls individual validators in sequence."""
        self._set_period_dates()
        self._ensure_status_default()
        self._ensure_tax_profile()
        self._validate_period_unique()
        self._validate_status_progression()
        self._validate_register_configuration()
        self._validate_register_data()

    def before_insert(self):
        """Initialize document before first save."""
        if not self.created_by_user:
            self.created_by_user = frappe.session.user

    def before_submit(self):
        """Final validation and preparation before submission."""
        self.status = "Closed"

        # Ensure snapshot exists
        if not self.register_snapshot:
            self.generate_snapshot(save=False)

        # Update totals from snapshot
        self._update_totals_from_snapshot()

        # Validate completeness
        self._validate_register_completeness()

    def on_submit(self):
        """Actions to perform on successful submission."""
        if not self.submit_on:
            frappe.db.set_value(
                self.doctype,
                self.name,
                "submit_on",
                now(),
                update_modified=False
            )

    def on_cancel(self):
        """Clean up on cancellation."""
        self.status = "Draft"

        # Auto-cancel VAT netting journal entry if it exists and is submitted
        if self.vat_netting_journal_entry:
            self._cancel_netting_journal_entry()

    def _cancel_netting_journal_entry(self):
        """Cancel the linked VAT Netting Journal Entry automatically."""
        je_name = self.vat_netting_journal_entry
        if not je_name:
            return

        try:
            je_doc = frappe.get_doc("Journal Entry", je_name)
        except frappe.DoesNotExistError:
            # JE already deleted, clear the reference
            self.db_set("vat_netting_journal_entry", None)
            return

        if je_doc.docstatus == 1:  # Submitted
            je_doc.cancel()
            frappe.msgprint(
                _("VAT Netting Journal Entry {0} has been cancelled.").format(
                    frappe.utils.get_link_to_form("Journal Entry", je_name)
                ),
                indicator="orange",
                alert=True
            )
        elif je_doc.docstatus == 2:  # Already cancelled
            pass  # Nothing to do

        # Clear the reference on this document
        self.db_set("vat_netting_journal_entry", None)

    def _ensure_status_default(self):
        """Set default status to Draft if empty."""
        if not self.status:
            self.status = "Draft"

    def _set_period_dates(self):
        """Calculate and set date_from and date_to based on period_month and period_year."""
        if not self.period_month or not self.period_year:
            return

        date_from, date_to = _get_period_bounds(int(self.period_month), int(self.period_year))
        self.date_from = date_from
        self.date_to = date_to

    def _ensure_tax_profile(self):
        """Auto-fetch Tax Profile for company if not set."""
        if self.tax_profile:
            return

        if not self.company:
            return

        profile = frappe.db.get_value("Tax Profile", {"company": self.company})
        if profile:
            self.tax_profile = profile

    def _validate_period_unique(self):
        """Ensure only one closing exists per company/period (excluding cancelled)."""
        if self.is_new():
            return

        filters = {
            "company": self.company,
            "period_month": self.period_month,
            "period_year": self.period_year,
            "docstatus": ["!=", 2],  # Exclude cancelled
            "name": ["!=", self.name]
        }

        existing = frappe.db.exists("Tax Period Closing", filters)
        if existing:
            frappe.throw(
                _("Tax Period Closing already exists for {0} {1}-{2}: {3}").format(
                    self.company,
                    self.period_month,
                    self.period_year,
                    existing
                ),
                title=_("Duplicate Period")
            )

    def _validate_status_progression(self):
        """Validate status workflow progression (flexible with warnings)."""
        if self.is_new() or not self.get_doc_before_save():
            return

        old_status = self.get_doc_before_save().status
        new_status = self.status

        if old_status == new_status:
            return

        # Define valid progressions
        valid_progressions = {
            "Draft": ["Reviewed", "Approved", "Closed"],
            "Reviewed": ["Approved", "Closed", "Draft"],
            "Approved": ["Closed", "Reviewed", "Draft"],
            "Closed": []  # Cannot change once closed (requires cancel)
        }

        if old_status == "Closed" and self.docstatus == 1:
            frappe.throw(
                _("Cannot change status of a submitted closing. Please cancel and amend if needed."),
                title=_("Invalid Status Change")
            )

        if new_status not in valid_progressions.get(old_status, []):
            # Show warning but allow if user has privileged role
            frappe.msgprint(
                _("Recommended workflow: Draft → Reviewed → Approved → Closed. You are moving from {0} to {1}.").format(
                    old_status, new_status
                ),
                title=_("Workflow Warning"),
                indicator="orange"
            )

    def _validate_register_completeness(self):
        """Validate that registers are complete before submission."""
        if not self.register_snapshot:
            frappe.throw(
                _("Cannot submit without tax register snapshot. Please refresh registers first."),
                title=_("Missing Snapshot")
            )

        # Check for unverified invoices (warning only, not blocking)
        unverified_count = self._count_unverified_invoices()
        if unverified_count > 0:
            frappe.msgprint(
                _("Warning: There are {0} unverified tax invoices in this period. "
                  "It is recommended to verify all invoices before closing.").format(unverified_count),
                title=_("Unverified Invoices"),
                indicator="orange"
            )

    def _count_unverified_invoices(self) -> int:
        """Count unverified tax invoices in the period."""
        if not self.company or not self.date_from or not self.date_to:
            return 0

        base_filters = {
            "company": self.company,
            "posting_date": ["between", [self.date_from, self.date_to]],
            "docstatus": 1
        }

        # Purchase Invoice uses ti_verification_status field
        pi_filters = base_filters.copy()
        pi_filters["ti_verification_status"] = ["!=", "Verified"]
        pi_count = frappe.db.count("Purchase Invoice", pi_filters)

        # Sales Invoice uses out_fp_status field
        si_filters = base_filters.copy()
        si_filters["out_fp_status"] = ["!=", "Verified"]
        si_count = frappe.db.count("Sales Invoice", si_filters)

        return pi_count + si_count

    def generate_snapshot(self, save: bool = True) -> dict:
        """Generate tax register snapshot for the period.

        Calls tax_operations.build_register_snapshot() to gather:
        - Input VAT from Purchase Invoices
        - Output VAT from Sales Invoices
        - PPh totals from withholding accounts
        - PB1 totals (single or multi-branch)

        Args:
            save: Whether to save document after generating snapshot

        Returns:
            dict: Snapshot data with tax totals

        Raises:
            frappe.ValidationError: If company is not set
        """
        if not self.company:
            frappe.throw(
                _("Company is required before generating tax register snapshots."),
                title=_("Missing Company")
            )

        snapshot = build_register_snapshot(self.company, self.date_from, self.date_to)
        self.register_snapshot = json.dumps(snapshot, indent=2)
        self.last_refresh_on = now()
        self._update_totals_from_snapshot()

        if save:
            self.save(ignore_permissions=True)

        return snapshot

    def _update_totals_from_snapshot(self):
        """Parse register snapshot JSON and update currency fields."""
        if not self.register_snapshot:
            return

        try:
            data = json.loads(self.register_snapshot)
        except Exception as e:
            frappe.log_error(
                message=f"Failed to parse register snapshot: {str(e)}",
                title="Tax Period Closing: Snapshot Parse Error"
            )
            data = {}

        self.input_vat_total = flt(data.get("input_vat_total"))
        self.input_vat_carry_forward = flt(data.get("input_vat_carry_forward"))
        self.effective_input_vat = flt(data.get("effective_input_vat"))
        self.output_vat_total = flt(data.get("output_vat_total"))
        self.vat_net = flt(data.get("vat_net"))
        self.pph_total = flt(data.get("pph_total"))
        self.pb1_total = flt(data.get("pb1_total"))

        # Update register-specific fields from v15+ snapshot
        self.input_invoice_count = data.get("input_invoice_count", 0)
        self.output_invoice_count = data.get("output_invoice_count", 0)
        self.withholding_entry_count = data.get("withholding_entry_count", 0)
        self.verification_status = data.get("verification_status", "Verified")

        # Extract metadata
        meta = data.get("meta", {})
        self.data_source = meta.get("data_source", "register_integration")

    def _validate_register_configuration(self):
        """Validate that all register configurations are properly set up.

        This checks that Tax Invoice OCR Settings and Tax Profile have
        the required accounts configured for register reports to work.
        """
        from imogi_finance.imogi_finance.utils_register.register_integration import validate_register_configuration

        if not self.company:
            return

        try:
            validation = validate_register_configuration(self.company)

            if not validation.get("valid"):
                # Build detailed error message
                vat_input = validation.get("vat_input", {})
                vat_output = validation.get("vat_output", {})
                withholding = validation.get("withholding", {})

                errors = []
                if not vat_input.get("valid"):
                    errors.append(f"VAT Input: {vat_input.get('message', 'Configuration error')}")
                if not vat_output.get("valid"):
                    errors.append(f"VAT Output: {vat_output.get('message', 'Configuration error')}")
                if not withholding.get("valid"):
                    errors.append(f"Withholding: {withholding.get('message', 'Configuration error')}")

                frappe.msgprint(
                    _("Register configuration issues detected:<br>{0}").format("<br>".join(errors)),
                    title=_("Configuration Warning"),
                    indicator="orange"
                )
        except Exception as e:
            frappe.log_error(
                message=f"Failed to validate register configuration: {str(e)}",
                title="Tax Period Closing: Configuration Validation Error"
            )

    def _validate_register_data(self):
        """Validate register snapshot data quality and consistency.

        Checks for:
        - Data source (register_integration vs fallback)
        - Invoice/entry counts (warn if zero)
        - Verification status
        - Metadata presence
        """
        if not self.register_snapshot:
            return

        try:
            data = json.loads(self.register_snapshot)
        except Exception:
            return

        meta = data.get("meta", {})
        data_source = meta.get("data_source", "unknown")

        # Warn if using fallback data source
        if data_source == "fallback_empty":
            error_msg = meta.get("error", "Unknown error")
            frappe.msgprint(
                _("Warning: Register data could not be loaded. Using empty fallback data.<br>"
                  "Error: {0}").format(error_msg),
                title=_("Data Quality Warning"),
                indicator="red"
            )
            return

        # Warn if all counts are zero (possible configuration issue)
        input_count = data.get("input_invoice_count", 0)
        output_count = data.get("output_invoice_count", 0)
        withholding_count = data.get("withholding_entry_count", 0)

        if input_count == 0 and output_count == 0 and withholding_count == 0:
            frappe.msgprint(
                _("Warning: No tax transactions found in this period. "
                  "This may indicate a configuration issue or genuinely empty period."),
                title=_("Empty Period"),
                indicator="orange"
            )

    def generate_exports(self, save: bool = True) -> dict:
        """Generate CoreTax export files for input and output VAT.

        Generates CSV/XLSX files formatted for CoreTax system based on
        CoreTax Export Settings configuration.

        Args:
            save: Whether to save document after generating exports

        Returns:
            dict: File URLs for input_export and output_export

        Raises:
            frappe.ValidationError: If tax profile or CoreTax settings not configured
        """
        if not self.tax_profile:
            self._ensure_tax_profile()

        export_result = {}

        if self.coretax_settings_input:
            self.coretax_input_export = generate_coretax_export(
                company=self.company,
                date_from=self.date_from,
                date_to=self.date_to,
                direction="Input",
                settings_name=self.coretax_settings_input,
                filename=f"coretax-input-{self.company}-{self.period_year}-{self.period_month}",
            )
            export_result["input_export"] = self.coretax_input_export

        if self.coretax_settings_output:
            self.coretax_output_export = generate_coretax_export(
                company=self.company,
                date_from=self.date_from,
                date_to=self.date_to,
                direction="Output",
                settings_name=self.coretax_settings_output,
                filename=f"coretax-output-{self.company}-{self.period_year}-{self.period_month}",
            )
            export_result["output_export"] = self.coretax_output_export

        if save:
            self.save(ignore_permissions=True)

        return export_result

    def _get_tax_profile_doc(self) -> Document:
        """Get cached Tax Profile document.

        Returns:
            Document: Tax Profile document

        Raises:
            frappe.ValidationError: If tax profile not set or not found
        """
        if not self.tax_profile:
            self._ensure_tax_profile()

        if not self.tax_profile:
            frappe.throw(
                _("Tax Profile is required. Please set Tax Profile for company {0}.").format(self.company),
                title=_("Missing Tax Profile")
            )

        return frappe.get_cached_doc("Tax Profile", self.tax_profile)

    def create_vat_netting_journal_entry(self, save: bool = True) -> str:
        """Create VAT netting journal entry.

        Creates a Journal Entry that nets Input VAT against Output VAT,
        with the difference posted to PPN Payable account.

        Journal Entry structure:
            Dr: PPN Output Account (Output VAT Total)
            Cr: PPN Input Account (Input VAT Total)
            Cr: PPN Payable Account (Net = Output - Input)

        Args:
            save: Whether to save closing document after creating JE

        Returns:
            str: Name of created Journal Entry

        Raises:
            frappe.PermissionError: If user lacks required roles
            frappe.ValidationError: If accounts not configured or VAT amounts missing
        """
        # Permission check
        frappe.only_for((roles.SYSTEM_MANAGER, roles.ACCOUNTS_MANAGER, roles.TAX_REVIEWER))

        profile = self._get_tax_profile_doc()

        # Ensure totals are up to date
        if not self.input_vat_total and not self.output_vat_total:
            self._update_totals_from_snapshot()

        # Get accounts
        payable_account = self.netting_payable_account or profile.get("ppn_payable_account")
        input_account = profile.get("ppn_input_account")
        output_account = profile.get("ppn_output_account")

        # Validate accounts exist
        if not (input_account and output_account and payable_account):
            frappe.throw(
                _("Please set PPN Input, PPN Output, and PPN Payable accounts on Tax Profile or this closing."),
                title=_("Missing Accounts")
            )

        posting_date = self.netting_posting_date or self.date_to or nowdate()

        # Create journal entry
        je_name = create_vat_netting_entry(
            company=self.company,
            period_month=int(self.period_month),
            period_year=int(self.period_year),
            input_vat_total=self.input_vat_total or 0,
            output_vat_total=self.output_vat_total or 0,
            input_account=input_account,
            output_account=output_account,
            payable_account=payable_account,
            posting_date=posting_date,
            reference=self.name,
        )

        # Update closing document using db_set to allow updates after submission
        self.db_set("vat_netting_journal_entry", je_name)
        self.db_set("netting_posting_date", posting_date)

        # Reload to refresh current instance
        self.reload()

        return je_name


# ==============================================================================
# WHITELISTED API METHODS
# ==============================================================================

@frappe.whitelist()
def refresh_tax_registers(closing_name: str) -> dict:
    """Regenerate tax register snapshot for a period closing.

    Permission: Accounts Manager, Tax Reviewer, System Manager

    Args:
        closing_name: Name of Tax Period Closing document

    Returns:
        dict: Updated snapshot data
    """
    frappe.only_for((roles.SYSTEM_MANAGER, roles.ACCOUNTS_MANAGER, roles.TAX_REVIEWER))

    closing = frappe.get_doc("Tax Period Closing", closing_name)
    closing.check_permission("write")

    return closing.generate_snapshot()


@frappe.whitelist()
def generate_coretax_exports(closing_name: str) -> dict:
    """Generate CoreTax export files for a period closing.

    Permission: Accounts Manager, Tax Reviewer, System Manager

    Args:
        closing_name: Name of Tax Period Closing document

    Returns:
        dict: File URLs for input and output exports
    """
    frappe.only_for((roles.SYSTEM_MANAGER, roles.ACCOUNTS_MANAGER, roles.TAX_REVIEWER))

    closing = frappe.get_doc("Tax Period Closing", closing_name)
    closing.check_permission("write")

    return closing.generate_exports()


@frappe.whitelist()
def create_vat_netting_entry_for_closing(closing_name: str) -> str:
    """Create VAT netting journal entry for a period closing.

    Permission: Accounts Manager, Tax Reviewer, System Manager

    Args:
        closing_name: Name of Tax Period Closing document

    Returns:
        str: Name of created Journal Entry
    """
    frappe.only_for((roles.SYSTEM_MANAGER, roles.ACCOUNTS_MANAGER, roles.TAX_REVIEWER))

    closing = frappe.get_doc("Tax Period Closing", closing_name)
    closing.check_permission("write")

    return closing.create_vat_netting_journal_entry()


def is_period_locked(company: str, check_date: str) -> bool:
    """Check if a tax period is locked.

    Args:
        company: Company name
        check_date: Date to check (YYYY-MM-DD)

    Returns:
        bool: True if period is locked (submitted closing exists)
    """
    from frappe.utils import getdate

    check_date = getdate(check_date)

    # Get month and year from check_date
    period_month = check_date.month
    period_year = check_date.year

    # Check if submitted closing exists for this period
    locked = frappe.db.exists(
        "Tax Period Closing",
        {
            "company": company,
            "period_month": period_month,
            "period_year": period_year,
            "docstatus": 1
        }
    )

    return bool(locked)
