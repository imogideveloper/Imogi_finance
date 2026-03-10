# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ExpenseApprovalLine(Document):
    """Child table to capture approval levels for expense accounts."""

    def validate(self):
        self.validate_level_1_required()
        self.validate_level_sequence()
        self.validate_level_amounts()
        self.validate_default_vs_account()

    def validate_level_1_required(self):
        """Ensure at least Level 1 approver is configured."""
        level_1_user = getattr(self, "level_1_user", None)
        if not level_1_user:
            frappe.throw(
                _("Level 1 Approver is required. Each approval line must have at least one approver.")
            )

    def validate_level_sequence(self):
        """Ensure levels are filled sequentially (no skipping).
        
        Level 2 can only be set if Level 1 is set.
        Level 3 can only be set if Level 2 is set.
        """
        level_1_user = getattr(self, "level_1_user", None)
        level_2_user = getattr(self, "level_2_user", None)
        level_3_user = getattr(self, "level_3_user", None)

        if level_2_user and not level_1_user:
            frappe.throw(
                _("Level 2 Approver cannot be set without Level 1 Approver.")
            )

        if level_3_user and not level_2_user:
            frappe.throw(
                _("Level 3 Approver cannot be set without Level 2 Approver.")
            )

    def validate_level_amounts(self):
        """Validate level-specific amount ranges."""
        from frappe.utils import flt
        
        prev_max = None
        
        for level in (1, 2, 3):
            min_amt = getattr(self, f"level_{level}_min_amount", None)
            max_amt = getattr(self, f"level_{level}_max_amount", None)
            user = getattr(self, f"level_{level}_user", None)

            # Skip if level not configured
            if not user:
                continue

            # Normalize to float
            min_amt = flt(min_amt)
            max_amt = flt(max_amt) if max_amt else None

            # If level has approver, min amount is required
            if min_amt is None:
                frappe.throw(
                    _("Level {0} requires Min Amount when approver is configured.").format(level)
                )

            # Max amount is optional - if not set, means unlimited
            # But if set, must be >= min
            if max_amt is not None and min_amt > max_amt:
                frappe.throw(
                    _("Level {0} Min Amount ({1}) cannot exceed Max Amount ({2}).").format(
                        level, frappe.format_value(min_amt, "Currency"), 
                        frappe.format_value(max_amt, "Currency")
                    )
                )

            # Validate level continuity - higher level should have higher min
            if prev_max is not None and min_amt < prev_max:
                frappe.throw(
                    _("Level {0} Min Amount ({1}) should be >= Level {2} Max Amount ({3}) to avoid overlap.").format(
                        level, frappe.format_value(min_amt, "Currency"),
                        level - 1, frappe.format_value(prev_max, "Currency")
                    )
                )

            prev_max = max_amt

    def validate_default_vs_account(self):
        """Ensure default (Apply to All) lines do not specify an Expense Account.

        Business rule:
        - Default lines (is_default = 1 / Apply to All Accounts) are global fallbacks
          and must NOT bind to a specific Expense Account.
        - Account-specific rules should use is_default = 0 with Expense Account filled.
        """

        is_default = getattr(self, "is_default", 0)
        expense_account = getattr(self, "expense_account", None)

        if is_default and expense_account:
            frappe.throw(
                _(
                    "Default approval line (Apply to All Accounts) cannot specify an Expense Account. "
                    "Please either clear the Expense Account or uncheck Apply to All Accounts."
                )
            )