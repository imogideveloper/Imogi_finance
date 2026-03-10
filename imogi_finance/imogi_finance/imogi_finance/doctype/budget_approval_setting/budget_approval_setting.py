# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class BudgetApprovalSetting(Document):
    """Budget Approval Setting - approval rules untuk budget requests tanpa amount validation."""

    def validate(self):
        """Validate budget approval setting."""
        self._validate_unique_active_per_cost_center()
        self._validate_approval_lines()

    def _validate_unique_active_per_cost_center(self):
        """Ensure only one active setting per cost center."""
        if not getattr(self, "is_active", None):
            return

        filters = {
            "is_active": 1,
            "name": ["!=", self.name or ""],
        }
        
        cost_center = getattr(self, "cost_center", None)
        if cost_center:
            filters["cost_center"] = cost_center
        else:
            # System default (no cost center)
            filters["cost_center"] = ["in", ["", None]]

        existing = frappe.get_all("Budget Approval Setting", filters=filters, limit=1)
        if existing:
            cc_label = cost_center or _("System Default")
            frappe.throw(
                _("Active Budget Approval Setting already exists for Cost Center: {0}").format(cc_label)
            )

    def _validate_approval_lines(self):
        """Validate approval lines have at least level 1."""
        lines = getattr(self, "budget_approval_lines", [])
        if not lines:
            frappe.throw(_("At least one approval line is required"))

        for line in lines:
            if not getattr(line, "level_1_user", None):
                frappe.throw(_("Level 1 Approver is required in all approval lines"))
