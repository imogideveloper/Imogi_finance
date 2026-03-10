# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

try:
    from frappe.model.document import Document
except Exception:  # pragma: no cover - fallback for test stubs
    class Document:  # type: ignore
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)


class BudgetControlEntry(Document):
    """Ledger record for budget reservations and allocation deltas."""

    VALID_ENTRY_TYPES = {"RESERVATION", "CONSUMPTION", "RELEASE", "RECLASS", "SUPPLEMENT", "REVERSAL"}
    VALID_DIRECTIONS = {"IN", "OUT"}

    # Valid entry_type and direction combinations
    # NOTE: RESERVATION allows both OUT (lock budget) and IN (release lock on ER rejection/cancel)
    # RELEASE is deprecated - use RESERVATION IN instead (simplified flow)
    VALID_COMBINATIONS = {
        "RESERVATION": ["OUT", "IN"],  # OUT=lock, IN=release (replaces RELEASE)
        "CONSUMPTION": ["IN"],
        "RELEASE": ["IN"],  # DEPRECATED - kept for backward compatibility
        "REVERSAL": ["OUT"],
        "RECLASS": ["IN", "OUT"],
        "SUPPLEMENT": ["IN"]
    }

    def before_insert(self):
        """Prevent manual creation of Budget Control Entries."""
        # Check if this is being created programmatically (via ledger.post_entry)
        # by checking if ignore_permissions flag is set
        if not self.flags.get("ignore_permissions"):
            frappe.throw(
                _("""Budget Control Entries cannot be created manually.

This is an audit/logging DocType that is automatically created by:
- Expense Request approval (creates RESERVATION entries)
- Purchase Invoice submit (creates CONSUMPTION entries)
- Document cancellation (creates RELEASE/REVERSAL entries)
- Budget reclass/supplement operations (creates RECLASS/SUPPLEMENT entries)

Manual entry creation would corrupt budget tracking."""),
                title=_("Manual Creation Not Allowed")
            )

    def validate(self):
        if getattr(self, "amount", 0) is None or float(self.amount) <= 0:
            frappe.throw(_("Amount must be greater than zero."))

        if getattr(self, "entry_type", None) not in self.VALID_ENTRY_TYPES:
            frappe.throw(_("Entry Type must be one of: {0}").format(", ".join(sorted(self.VALID_ENTRY_TYPES))))

        if getattr(self, "direction", None) not in self.VALID_DIRECTIONS:
            frappe.throw(_("Direction must be IN or OUT."))

        # Validate ref_doctype and ref_name consistency
        if getattr(self, "ref_doctype", None) and not getattr(self, "ref_name", None):
            frappe.throw(_("Reference Name is required when Reference DocType is set"))

        if getattr(self, "ref_name", None) and not getattr(self, "ref_doctype", None):
            frappe.throw(_("Reference DocType is required when Reference Name is set"))

        # Validate entry_type and direction combinations
        entry_type = getattr(self, "entry_type", None)
        direction = getattr(self, "direction", None)
        if entry_type in self.VALID_COMBINATIONS:
            if direction not in self.VALID_COMBINATIONS[entry_type]:
                frappe.throw(
                    _("Invalid combination: {0} must have direction {1}").format(
                        entry_type,
                        " or ".join(self.VALID_COMBINATIONS[entry_type])
                    )
                )

    def before_cancel(self):
        """Prevent manual cancellation of Budget Control Entries.

        Budget Control Entries should only be "cancelled" via RESERVATION IN/REVERSAL entries,
        not by actual document cancellation. This prevents data corruption.

        However, we need to allow the cancel to proceed if it's triggered by:
        1. Programmatic cancellation (ignore_permissions or from_parent_cancel flag)
        2. Parent document cancellation (Expense Request or Purchase Invoice)
        3. "Cancel All Linked Documents" action from Frappe desk

        We check flags and frappe.local to determine if this is a programmatic
        cancel (allowed) or manual cancel (blocked).
        """
        # Allow programmatic cancellation (from parent document cancel flow)
        if self.flags.get("ignore_permissions") or self.flags.get("from_parent_cancel"):
            return

        # Check if parent document is being cancelled
        ref_doctype = getattr(self, "ref_doctype", None)
        ref_name = getattr(self, "ref_name", None)

        if ref_doctype == "Expense Request" and ref_name:
            cancelling_ers = getattr(frappe.local, "cancelling_expense_requests", set())
            if ref_name in cancelling_ers:
                # Set flag to indicate this is a programmatic cancellation
                self.flags.from_parent_cancel = 1
                return

        if ref_doctype == "Purchase Invoice" and ref_name:
            cancelling_pis = getattr(frappe.local, "cancelling_purchase_invoices", set())
            if ref_name in cancelling_pis:
                # Set flag to indicate this is a programmatic cancellation
                self.flags.from_parent_cancel = 1
                return

        # Check if this is triggered by "Cancel All Linked Documents" from Frappe desk
        # The API call comes from frappe.desk.form.linked_with.cancel_all_linked_docs
        form_dict = getattr(frappe, "form_dict", frappe._dict())

        # Check for cancel_all_linked_docs specific parameters
        # When called from desk, form_dict contains 'docs' list with linked docs to cancel
        if form_dict.get("docs") or form_dict.get("cmd") == "frappe.desk.form.linked_with.cancel_all_linked_docs":
            # This is being called from "Cancel All Linked Documents" action
            # Allow cancellation for Budget Control Entries
            frappe.logger().info(
                f"Allowing BCE {self.name} cancellation from cancel_all_linked_docs"
            )
            # Set flag to indicate this is a programmatic cancellation
            self.flags.from_parent_cancel = 1
            return

        # Alternative check: If this BCE is being cancelled as part of batch cancellation
        # and it has a valid ref_doctype/ref_name, allow it
        if ref_doctype and ref_name:
            # Check if the parent document exists and is being cancelled (docstatus=2)
            try:
                parent_docstatus = frappe.db.get_value(ref_doctype, ref_name, "docstatus")
                if parent_docstatus == 2:
                    # Parent is already cancelled, allow BCE cancellation
                    frappe.logger().info(
                        f"Allowing BCE {self.name} cancellation - parent {ref_doctype}/{ref_name} already cancelled"
                    )
                    # Set flag to indicate this is a programmatic cancellation
                    self.flags.from_parent_cancel = 1
                    return
            except Exception:
                pass

        # Block manual cancellation
        frappe.throw(
            _("""Budget Control Entries cannot be cancelled directly.

To reverse a budget entry:
- For Expense Request: Cancel the Expense Request (will auto-create RESERVATION IN entries)
- For Purchase Invoice: Cancel the Purchase Invoice (will auto-create REVERSAL entries)

Manual cancellation would corrupt budget tracking."""),
            title=_("Manual Cancel Not Allowed")
        )

    def on_cancel(self):
        """Log cancellation for audit purposes.

        This is called when cancellation proceeds (either programmatically allowed
        or if before_cancel somehow didn't block it).
        """
        if not self.flags.get("ignore_permissions") and not self.flags.get("from_parent_cancel"):
            frappe.log_error(
                title="Unexpected Budget Control Entry Cancellation",
                message=f"Budget Control Entry {self.name} was cancelled without proper flags! This may indicate a bug."
            )
