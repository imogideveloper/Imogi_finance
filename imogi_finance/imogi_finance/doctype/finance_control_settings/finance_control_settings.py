# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations
import frappe
from frappe import _
from frappe.model.document import Document


class FinanceControlSettings(Document):
    """Validate GL account mappings are complete and consistent."""
    
    def validate(self):
        self._validate_gl_mapping_uniqueness()
        self._validate_gl_mapping_required_purposes()
    
    def _validate_gl_mapping_uniqueness(self):
        """Ensure no duplicate (purpose, company) combinations."""
        seen = set()
        for row in self.get("gl_account_mappings") or []:
            purpose = row.get("purpose")
            company = row.get("company") or ""
            key = (purpose, company)
            
            if key in seen:
                frappe.throw(
                    _(f"Duplicate GL account mapping: purpose='{purpose}', company='{company or 'GLOBAL'}'"),
                    title=_("Duplicate GL Account Mapping")
                )
            seen.add(key)
    
    def _validate_gl_mapping_required_purposes(self):
        """Ensure all 6 required GL account purposes are configured with accounts.
        
        Required purposes:
        - digital_stamp_expense
        - digital_stamp_payment
        - default_paid_from
        - default_prepaid
        - ppn_variance
        
        Note: default_paid_to removed - paid_to must come from party account per beneficiary
        """
        from imogi_finance.settings import gl_purposes
        
        # Get all purposes in current mappings
        rows = self.get("gl_account_mappings") or []
        
        # Build set of (purpose, company) where account is filled
        configured = set()
        for row in rows:
            purpose = row.get("purpose")
            company = row.get("company") or ""
            account = row.get("account")
            
            if purpose and account:
                configured.add((purpose, company))
        
        # Check that each required purpose has at least ONE account configured
        # (either company-specific or global default)
        required_purposes = gl_purposes.ALL_PURPOSES
        missing_purposes = []
        
        for purpose in required_purposes:
            # Check if there's at least one mapping for this purpose (any company or global)
            has_mapping = any(
                p == purpose and account 
                for (p, c), (account) in [
                    ((row.get("purpose"), row.get("company") or ""), row.get("account"))
                    for row in rows
                ]
            )
            
            if not has_mapping:
                missing_purposes.append(purpose)
        
        if missing_purposes:
            missing_list = ", ".join(missing_purposes)
            frappe.throw(
                _(
                    f"Missing GL account mappings for required purposes: {missing_list}. "
                    f"Please configure all 7 GL account purposes in the GL Account Mappings table."
                ),
                title=_("Incomplete GL Account Mappings")
            )


