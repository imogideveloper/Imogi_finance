# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class TaxProfile(Document):
    """Stores tax liability accounts and export defaults per company."""

    def autoname(self):
        if self.company:
            self.name = self.company

    def _safe_throw(self, message: str, *, title: str | None = None):
        marker = getattr(frappe, "ThrowMarker", None)
        throw_fn = getattr(frappe, "throw", None)

        if callable(throw_fn):
            try:
                throw_fn(message, title=title)
                return
            except BaseException as exc:  # noqa: BLE001
                if (
                    marker
                    and isinstance(marker, type)
                    and issubclass(marker, BaseException)
                    and not isinstance(exc, marker)
                ):
                    Combined = type("CombinedThrowMarker", (exc.__class__, marker), {})  # noqa: N806
                    raise Combined(str(exc))
                raise

        if marker:
            raise marker(message)
        raise Exception(message)

    def validate(self):
        self._validate_unique_company()
        self._require_core_accounts()
        self._validate_accounts()
        self._validate_pb1_mappings()

    def _validate_unique_company(self):
        if not self.company:
            self._safe_throw(_("Company is required."))

        existing = frappe.db.exists("Tax Profile", {"company": self.company, "name": ["!=", self.name]})
        if existing:
            self._safe_throw(
                _("A Tax Profile already exists for company {0} ({1}).").format(self.company, existing),
                title=_("Duplicate Tax Profile"),
            )

    def _require_core_accounts(self):
        missing = []
        if not getattr(self, "ppn_input_account", None):
            missing.append(_("PPN Input Account"))
        if not getattr(self, "ppn_output_account", None):
            missing.append(_("PPN Output Account"))
        pb1_required = True
        if getattr(self, "enable_pb1_multi_branch", 0) and getattr(self, "pb1_account_mappings", None):
            pb1_required = False
        if pb1_required and not getattr(self, "pb1_payable_account", None):
            missing.append(_("PB1 Payable Account"))
        if not getattr(self, "pph_accounts", None):
            missing.append(_("Withholding Tax (PPh) payable accounts"))

        if missing:
            self._safe_throw(
                _("Please complete the following on the Tax Profile for {0}: {1}.").format(
                    self.company or self.name, _(", ").join(missing)
                ),
                title=_("Incomplete Tax Profile"),
            )

    def _validate_accounts(self):
        accounts = [
            acct
            for acct in [
                getattr(self, "ppn_input_account", None),
                getattr(self, "ppn_output_account", None),
                getattr(self, "pb1_payable_account", None),
                getattr(self, "bpjs_payable_account", None),
                *(row.payable_account for row in self.pph_accounts or [] if row.payable_account),
            ]
            if acct
        ]

        duplicates = {acc for acc in accounts if accounts.count(acc) > 1}
        if duplicates:
            self._safe_throw(
                _("The same account is referenced multiple times: {0}. Please review the Tax Profile.").format(
                    ", ".join(sorted(set(duplicates)))
                )
            )
    def _validate_pb1_mappings(self):
        """Validate PB1 account mappings if multi-branch is enabled."""
        if not getattr(self, "enable_pb1_multi_branch", 0):
            return
        
        if not getattr(self, "pb1_account_mappings", None):
            # Multi-branch enabled but no mappings - will fallback to default
            return
        
        # Check for duplicate branches
        branches_seen = set()
        for mapping in self.pb1_account_mappings or []:
            branch = getattr(mapping, "branch", None)
            if not branch:
                continue
            
            if branch in branches_seen:
                self._safe_throw(
                    _("Branch {0} appears multiple times in PB1 Account Mapping.").format(branch),
                    title=_("Duplicate Branch Mapping")
                )
            branches_seen.add(branch)
    
    def get_pb1_account(self, branch: str = None) -> str:
        """Get PB1 payable account based on branch mapping or fallback to default.
        
        Args:
            branch: Branch name to look up specific PB1 account
            
        Returns:
            str: PB1 payable account name
        """
        # If multi-branch not enabled or no branch specified, return default
        if not getattr(self, "enable_pb1_multi_branch", 0) or not branch:
            return getattr(self, "pb1_payable_account", None)
        
        # Check for branch-specific mapping
        for mapping in (self.pb1_account_mappings or []):
            if getattr(mapping, "branch", None) == branch:
                return getattr(mapping, "pb1_payable_account", None)
        
        # Fallback to default account
        return getattr(self, "pb1_payable_account", None)
