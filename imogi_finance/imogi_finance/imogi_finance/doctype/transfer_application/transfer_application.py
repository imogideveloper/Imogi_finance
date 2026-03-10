from __future__ import annotations

import frappe
from frappe import _
from imogi_finance import roles
from frappe.model.document import Document
from frappe.utils import cint, flt, money_in_words, now_datetime, today

from imogi_finance.transfer_application.payment_entries import (
    create_payment_entry_for_transfer_application,
)
from imogi_finance.transfer_application.settings import get_reference_doctype_options


class TransferApplication(Document):
    def validate(self):
        self.apply_defaults()
        self.validate_item_parties()
        self.calculate_totals()
        self.validate_reference_fields()
        self.update_amount_in_words()
        self.sync_payment_details()

    def before_submit(self):
        """Validate before submission"""
        if not self.items:
            frappe.throw(_("Cannot submit Transfer Application without items."))
        if not self.company:
            frappe.throw(_("Company is required before submission."))
        if not self.posting_date:
            frappe.throw(_("Posting Date is required before submission."))

        # Set timestamps
        if not self.submit_on:
            self.submit_on = now_datetime()
        if not self.created_by_user:
            self.created_by_user = frappe.session.user

    def on_submit(self):
        """Actions on document submission"""
        # Ensure workflow_state is set
        if not self.workflow_state or self.workflow_state == "Draft":
            self.db_set("workflow_state", "Finance Review")
            self.db_set("status", "Finance Review")

    def before_workflow_action(self, action: str, workflow_state: str, workflow_action: str):
        """
        Validation hook before workflow action is applied.
        Called by Frappe workflow engine.

        Args:
            action: The action being performed (e.g., 'Submit for Finance Review')
            workflow_state: The target workflow state
            workflow_action: The workflow action name
        """
        # Validate items exist before finance review submission
        if workflow_state == "Finance Review" and not self.items:
            frappe.throw(_("Cannot submit for Finance Review without transfer items."))

        # Validate paid_from_account before submission
        if workflow_state == "Finance Review" and not self.paid_from_account:
            frappe.throw(_("Paid From Account is required before submission."))

        # Validate Finance Controller role for approval actions
        if action in ["Approve for Transfer"] and workflow_state == "Approved for Transfer":
            if not frappe.has_role(["Finance Controller"]):
                frappe.throw(_("Only Finance Controller can approve transfers."))

            # TODO: Validate Finance Controller is assigned to this branch
            # This will be implemented when branch assignment logic is ready

        # Validate cancellation - check if Payment Entry exists and is submitted
        if workflow_state == "Cancelled":
            if self.payment_entry:
                pe_docstatus = frappe.db.get_value("Payment Entry", self.payment_entry, "docstatus")
                if pe_docstatus == 1:
                    frappe.throw(
                        _("Cannot cancel Transfer Application. Payment Entry {0} is already submitted. Please cancel the Payment Entry first.")
                        .format(frappe.bold(self.payment_entry))
                    )

    def on_workflow_action(self, workflow_state: str, action: str):
        """
        Hook called after workflow action is applied.
        Sync status with workflow_state.

        Args:
            workflow_state: The new workflow state
            action: The action that was performed
        """
        # Sync status to workflow_state
        self.status = workflow_state
        self.db_set("status", workflow_state, update_modified=False)

        # Additional actions based on state
        if workflow_state == "Finance Review" and not self.submit_on:
            self.db_set("submit_on", now_datetime(), update_modified=False)
            self.db_set("created_by_user", frappe.session.user, update_modified=False)

        # Auto-create notification or comment for state changes
        if workflow_state == "Approved for Transfer":
            self.add_comment("Workflow", _("Transfer approved and ready for bank processing."))

        elif workflow_state == "Awaiting Bank Confirmation":
            self.add_comment("Workflow", _("Bank transfer initiated. Awaiting confirmation."))

        elif workflow_state == "Paid":
            self.add_comment("Workflow", _("Transfer marked as paid. All beneficiaries should receive funds."))

        elif workflow_state == "Rejected":
            self.add_comment("Workflow", _("Transfer application rejected during finance review."))

    def apply_defaults(self):
        if not self.status:
            self.status = "Draft"
        if not self.posting_date:
            self.posting_date = today()
        if not self.requested_transfer_date:
            self.requested_transfer_date = self.posting_date

        if not self.currency:
            company_currency = None
            if self.company:
                company_currency = frappe.db.get_value("Company", self.company, "default_currency")
            self.currency = company_currency or frappe.db.get_default("currency")

        if not self.workflow_state:
            self.workflow_state = self.status or "Draft"

    def validate_item_parties(self):
        """Validate that each item has required party/beneficiary details"""
        if not self.items:
            frappe.throw(_("Please add at least one item to the Transfer Application."))

        for idx, item in enumerate(self.items, start=1):
            if not item.beneficiary_name:
                frappe.throw(_("Row {0}: Beneficiary Name is required").format(idx))
            if not item.bank_name:
                frappe.throw(_("Row {0}: Bank Name is required").format(idx))
            if not item.account_number:
                frappe.throw(_("Row {0}: Account Number is required").format(idx))

            # Sync party_type from party if set
            if item.party and not item.party_type:
                party_type = frappe.db.get_value("Party", item.party, "party_type")
                if party_type:
                    item.party_type = party_type

    def calculate_totals(self):
        """Calculate total amount and expected amount from items"""
        total_amount = 0.0
        total_expected = 0.0

        for item in self.items or []:
            total_amount += flt(item.amount)
            total_expected += flt(item.expected_amount or item.amount)

        self.amount = total_amount
        self.expected_amount = total_expected

    def validate_reference_fields(self):
        """Validate reference fields on child items"""
        allowed = set(get_reference_doctype_options())

        for item in self.items:
            if item.reference_name and not item.reference_doctype:
                frappe.throw(_("Row {0}: Please choose a Reference Doctype when Reference Name is set.").format(item.idx))
            if item.reference_doctype and not item.reference_name:
                # Allow empty name for Other/manual
                if item.reference_doctype != "Other":
                    frappe.throw(_("Row {0}: Please select a Reference Name for the chosen Reference Doctype.").format(item.idx))

            if item.reference_doctype and item.reference_doctype not in allowed:
                frappe.throw(_("Row {0}: Reference Doctype {1} is not available in this site.").format(item.idx, item.reference_doctype))

    def update_amount_in_words(self):
        if flt(self.amount) and self.currency:
            self.amount_in_words = money_in_words(self.amount, self.currency)
        else:
            self.amount_in_words = None

    def sync_payment_details(self):
        """
        Sync payment status from multiple Payment Entries.
        Status = Fully Paid only when ALL PEs are submitted.
        """
        if not self.payment_entries:
            self.payment_status = "Not Created"
            self.total_paid_amount = 0
            if self.workflow_state and self.status != "Paid":
                self.status = self.workflow_state
            return

        total_submitted = 0
        total_draft = 0
        total_cancelled = 0
        total_paid_amount = 0

        # Update status for each PE row
        for pe_row in self.payment_entries:
            if not pe_row.payment_entry:
                continue

            pe_info = frappe.db.get_value(
                "Payment Entry",
                pe_row.payment_entry,
                ["docstatus", "posting_date", "paid_amount"],
                as_dict=True,
            )

            if not pe_info:
                continue

            # Update row status
            if pe_info.docstatus == 0:
                pe_row.pe_status = "Draft"
                total_draft += 1
            elif pe_info.docstatus == 1:
                pe_row.pe_status = "Submitted"
                pe_row.posting_date = pe_info.posting_date
                total_submitted += 1
                total_paid_amount += frappe.utils.flt(pe_info.paid_amount)
            elif pe_info.docstatus == 2:
                pe_row.pe_status = "Cancelled"
                total_cancelled += 1

        # Update parent payment status
        self.total_paid_amount = total_paid_amount

        total_pes = len(self.payment_entries)
        if total_submitted == total_pes and total_pes > 0:
            # All PEs submitted
            self.payment_status = "Fully Paid"
            self.status = "Paid"
            self.workflow_state = "Paid"
        elif total_submitted > 0:
            # Some PEs submitted
            self.payment_status = "Partially Paid"
            if self.workflow_state == "Paid":
                self.workflow_state = "Awaiting Bank Confirmation"
            self.status = self.workflow_state or self.status
        else:
            # No PEs submitted yet
            self.payment_status = "Not Created" if total_draft == 0 else "Draft"
            if self.workflow_state == "Paid":
                self.workflow_state = "Awaiting Bank Confirmation"
            self.status = self.workflow_state or self.status

    def on_cancel(self):
        self.status = "Cancelled"
        self.workflow_state = "Cancelled"

    @frappe.whitelist()
    def mark_as_printed(self):
        frappe.only_for((roles.ACCOUNTS_USER, roles.ACCOUNTS_MANAGER, roles.SYSTEM_MANAGER))
        now = now_datetime()
        self.db_set({"printed_by": frappe.session.user, "printed_at": now})
        return {"printed_at": now}

    @frappe.whitelist()
    def create_payment_entry(self, submit: int | str = 0):
        if self.docstatus == 2:
            frappe.throw(_("Cannot create a Payment Entry from a cancelled Transfer Application."))

        if not self.paid_from_account:
            frappe.throw(_("Paid From Account is required to create Payment Entry."))

        submit_flag = bool(cint(submit))
        payment_entries = create_payment_entry_for_transfer_application(
            self, submit=submit_flag
        )
        self.reload()

        # Return list of created PE names
        pe_names = [pe.name for pe in payment_entries]
        return {
            "payment_entries": pe_names,
            "count": len(pe_names),
            "message": _("Created {0} Payment Entry(ies) - one per beneficiary").format(len(pe_names))
        }

    @frappe.whitelist()
    def export_to_excel(self):
        """
        Export transfer items to Excel file.
        Only available for Finance Controller after approval.
        """
        # Check role permission
        if not frappe.has_role(["Finance Controller", "System Manager"]):
            frappe.throw(_("Only Finance Controller can export transfer list."))

        # Check workflow state
        if self.workflow_state not in ["Approved for Transfer", "Awaiting Bank Confirmation", "Paid"]:
            frappe.throw(_("Export is only available after transfer is approved."))

        # Build Excel data
        import xlsxwriter
        from io import BytesIO

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Transfer List')

        # Define formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#D9E1F2',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        cell_format = workbook.add_format({
            'border': 1,
            'valign': 'top'
        })

        number_format = workbook.add_format({
            'border': 1,
            'num_format': '#,##0.00',
            'valign': 'top'
        })

        # Write header
        headers = [
            'No',
            'Beneficiary Name',
            'Bank Name',
            'Account Number',
            'Account Holder Name',
            'Branch',
            'Amount',
            'Purpose / Description'
        ]

        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_format)

        # Set column widths
        worksheet.set_column('A:A', 5)   # No
        worksheet.set_column('B:B', 30)  # Beneficiary Name
        worksheet.set_column('C:C', 20)  # Bank Name
        worksheet.set_column('D:D', 20)  # Account Number
        worksheet.set_column('E:E', 25)  # Account Holder Name
        worksheet.set_column('F:F', 20)  # Branch
        worksheet.set_column('G:G', 15)  # Amount
        worksheet.set_column('H:H', 40)  # Purpose

        # Write data rows
        row = 1
        for idx, item in enumerate(self.items or [], start=1):
            worksheet.write(row, 0, idx, cell_format)
            worksheet.write(row, 1, item.beneficiary_name or '', cell_format)
            worksheet.write(row, 2, item.bank_name or '', cell_format)
            worksheet.write(row, 3, item.account_number or '', cell_format)
            worksheet.write(row, 4, item.account_holder_name or '', cell_format)
            worksheet.write(row, 5, item.bank_branch or '', cell_format)
            worksheet.write(row, 6, flt(item.amount), number_format)

            # Purpose: use description or reference info
            purpose = item.description or ''
            if item.reference_doctype and item.reference_name:
                purpose = f"{item.reference_doctype} - {item.reference_name}: {purpose}"
            worksheet.write(row, 7, purpose, cell_format)

            row += 1

        # Write total row
        worksheet.write(row, 5, 'TOTAL:', header_format)
        worksheet.write(row, 6, flt(self.amount), number_format)

        workbook.close()
        output.seek(0)

        # Generate filename
        filename = f"Transfer_List_{self.name}_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S')}.xlsx"

        # Return file data
        frappe.response['filename'] = filename
        frappe.response['filecontent'] = output.read()
        frappe.response['type'] = 'binary'

        return {
            'filename': filename,
            'success': True
        }

    def get_grouped_items(self):
        """Group items by beneficiary for cleaner print format.
        Returns a list of dicts with beneficiary info and their items."""
        from collections import OrderedDict

        grouped = OrderedDict()

        for item in self.items or []:
            # Create unique key for each beneficiary
            key = (
                item.beneficiary_name or "",
                item.bank_name or "",
                item.account_number or "",
                item.account_holder_name or "",
                item.bank_branch or ""
            )

            if key not in grouped:
                grouped[key] = {
                    "beneficiary_name": item.beneficiary_name,
                    "bank_name": item.bank_name,
                    "bank_branch": item.bank_branch,
                    "account_number": item.account_number,
                    "account_holder_name": item.account_holder_name,
                    "party_type": item.party_type,
                    "party": item.party,
                    "items": [],
                    "total_amount": 0.0,
                    "total_expected": 0.0
                }

            grouped[key]["items"].append(item)
            grouped[key]["total_amount"] += flt(item.amount)
            grouped[key]["total_expected"] += flt(item.expected_amount or item.amount)

        return list(grouped.values())


@frappe.whitelist()
def fetch_reference_doctype_options():
    return get_reference_doctype_options()
