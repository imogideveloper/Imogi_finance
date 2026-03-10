# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.model.document import Document


class TaxProfilePB1Account(Document):
    """Child table for branch-specific PB1 payable account mapping.
    
    Allows different PB1 payable accounts per branch within the same company.
    Used within Tax Profile to support multi-branch PB1 tax handling.
    """
    
    def validate(self):
        """Validate PB1 account mapping configuration."""
        if not self.branch:
            frappe.throw(frappe._("Branch is required for PB1 account mapping."))
        
        if not self.pb1_payable_account:
            frappe.throw(frappe._("PB1 Payable Account is required."))
