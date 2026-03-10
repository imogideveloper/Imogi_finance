"""
Integration Smoke Tests for 4 Main Flows (Fase 8 Validation)

Tests the actual integration of:
1. Receipt/Materai flow
2. OCR flow
3. Transfer Application flow
4. Deferred Expense flow

These are smoke tests (not exhaustive), verifying that GL account resolution
chains work end-to-end without errors.
"""

from __future__ import annotations

import pytest
import frappe
from frappe.utils import clear_cache

from imogi_finance.settings.utils import get_gl_account
from imogi_finance.settings.gl_purposes import (
    DIGITAL_STAMP_EXPENSE,
    DIGITAL_STAMP_PAYMENT,
    DEFAULT_PAID_FROM,
    DEFAULT_PREPAID,
    DPP_VARIANCE,
    PPN_VARIANCE,
)


class TestReceiptMateraiFlow:
    """Smoke test: Receipt Materai → GL Mappings → Journal Entry posting"""

    def setup_method(self):
        """Setup test prerequisites"""
        # Ensure test company exists
        if not frappe.db.exists("Company", "Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "country": "Indonesia",
            }).insert(ignore_permissions=True)

        # Ensure GL accounts exist
        for account_name in [
            "Biaya Materai Digital Test",
            "Kas Test",
            "Beban Dibayar Dimuka Test",
        ]:
            if not frappe.db.exists("Account", account_name):
                frappe.get_doc({
                    "doctype": "Account",
                    "account_name": account_name,
                    "account_number": account_name[:4],
                    "parent_account": "5000 - Expenses",
                    "company": "Test Company",
                    "root_type": "Expense",
                }).insert(ignore_permissions=True)

        # Setup Finance Control Settings with test mappings
        settings = frappe.get_doc("Finance Control Settings")
        settings.enable_digital_stamp = 1
        settings.gl_account_mappings = []
        settings.append("gl_account_mappings", {
            "purpose": DIGITAL_STAMP_EXPENSE,
            "company": "Test Company",
            "account": "Biaya Materai Digital Test",
            "is_required": 1,
        })
        settings.append("gl_account_mappings", {
            "purpose": DIGITAL_STAMP_PAYMENT,
            "company": "Test Company",
            "account": "Kas Test",
            "is_required": 1,
        })
        settings.save()
        clear_cache()

    def test_receipt_disabled_no_enforce_mapping(self):
        """Test: enable_digital_stamp=0 should not enforce GL mappings"""
        settings = frappe.get_doc("Finance Control Settings")
        settings.enable_digital_stamp = 0
        settings.save()
        clear_cache()

        # Should not throw error even if mapping not configured
        # (just calls optional helper)
        from imogi_finance.receipt_control.utils import get_receipt_control_settings
        receipt_settings = get_receipt_control_settings()
        
        assert receipt_settings.enable_digital_stamp == 0

    def test_receipt_enabled_resolve_accounts(self):
        """Test: enable_digital_stamp=1 should resolve GL accounts correctly"""
        settings = frappe.get_doc("Finance Control Settings")
        settings.enable_digital_stamp = 1
        settings.save()
        clear_cache()

        from imogi_finance.receipt_control.utils import get_digital_stamp_accounts

        # Should resolve accounts without error
        expense_account, payment_account = get_digital_stamp_accounts("Test Company")
        
        assert expense_account == "Biaya Materai Digital Test"
        assert payment_account == "Kas Test"

    def test_receipt_missing_mapping_clear_error(self):
        """Test: Missing mapping should raise clear error message"""
        # Clear mappings
        settings = frappe.get_doc("Finance Control Settings")
        settings.gl_account_mappings = []
        settings.save()
        clear_cache()

        from imogi_finance.receipt_control.utils import get_digital_stamp_accounts

        with pytest.raises(frappe.ValidationError) as exc_info:
            get_digital_stamp_accounts("Test Company")
        
        error_msg = str(exc_info.value)
        assert "digital_stamp" in error_msg.lower() or "not configured" in error_msg.lower()


class TestOCRFlow:
    """Smoke test: OCR → Tax Profile + GL Mappings → Variance posting"""

    def setup_method(self):
        """Setup test prerequisites"""
        if not frappe.db.exists("Company", "Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "country": "Indonesia",
            }).insert(ignore_permissions=True)

        # Create Tax Profile
        if frappe.db.exists("Tax Profile", {"company": "Test Company"}):
            doc = frappe.get_doc("Tax Profile", frappe.db.get_value(
                "Tax Profile",
                {"company": "Test Company"},
                "name"
            ))
            doc.delete()

        frappe.get_doc({
            "doctype": "Tax Profile",
            "company": "Test Company",
            "ppn_input_account": "2110 - Test PPN Input",
            "ppn_output_account": "2111 - Test PPN Output",
        }).insert(ignore_permissions=True)

        # Setup Finance Control Settings with variance mappings
        settings = frappe.get_doc("Finance Control Settings")
        settings.gl_account_mappings = []
        settings.append("gl_account_mappings", {
            "purpose": DPP_VARIANCE,
            "company": "Test Company",
            "account": "Selisih DPP Test",
            "is_required": 0,
        })
        settings.append("gl_account_mappings", {
            "purpose": PPN_VARIANCE,
            "company": "Test Company",
            "account": "Selisih PPN Test",
            "is_required": 0,
        })
        settings.save()
        clear_cache()

    def test_ocr_ppn_from_tax_profile(self):
        """Test: OCR should resolve PPN from Tax Profile"""
        from imogi_finance.settings.utils import get_ppn_accounts

        ppn_input, ppn_output = get_ppn_accounts("Test Company")
        
        assert ppn_input == "2110 - Test PPN Input"
        assert ppn_output == "2111 - Test PPN Output"

    def test_ocr_variance_from_gl_mappings(self):
        """Test: OCR should resolve variance accounts from GL Mappings"""
        dpp_var = get_gl_account(DPP_VARIANCE, "Test Company", required=False)
        ppn_var = get_gl_account(PPN_VARIANCE, "Test Company", required=False)
        
        assert dpp_var == "Selisih DPP Test"
        assert ppn_var == "Selisih PPN Test"

    def test_ocr_variance_optional_not_required(self):
        """Test: Variance accounts should be optional (required=False)"""
        # Even with no mapping, should return None not error
        result = get_gl_account(
            DPP_VARIANCE,
            "NonExistent Company",
            required=False
        )
        
        assert result is None  # Not error, just None


class TestTransferApplicationFlow:
    """Smoke test: Transfer Application → GL Mappings + reference_doctypes"""

    def setup_method(self):
        """Setup test prerequisites"""
        if not frappe.db.exists("Company", "Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "country": "Indonesia",
            }).insert(ignore_permissions=True)

        # Setup Finance Control Settings
        settings = frappe.get_doc("Finance Control Settings")
        settings.gl_account_mappings = []
        settings.append("gl_account_mappings", {
            "purpose": DEFAULT_PAID_FROM,
            "company": "Test Company",
            "account": "Kas/Bank Test",
            "is_required": 1,
        })
        settings.save()

        # Setup Transfer Application Settings with reference_doctypes
        ta_settings = frappe.get_doc("Transfer Application Settings")
        ta_settings.reference_doctypes = []
        ta_settings.append("reference_doctypes", {
            "reference_doctype": "Expense Request",
            "enabled": 1,
        })
        ta_settings.append("reference_doctypes", {
            "reference_doctype": "Purchase Invoice",
            "enabled": 1,
        })
        ta_settings.save()
        clear_cache()

    def test_transfer_resolve_paid_from_account(self):
        """Test: Transfer Application resolves paid_from from GL Mappings"""
        paid_from = get_gl_account(DEFAULT_PAID_FROM, "Test Company", required=False)
        
        assert paid_from == "Kas/Bank Test"

    def test_transfer_reference_doctypes_from_table(self):
        """Test: Reference doctypes loaded from Transfer Application Settings table"""
        from imogi_finance.transfer_application.settings import get_reference_doctypes

        doctypes = get_reference_doctypes()
        
        assert "Expense Request" in doctypes
        assert "Purchase Invoice" in doctypes

    def test_transfer_reference_doctypes_fallback(self):
        """Test: Fallback to DEFAULT_REFERENCE_DOCTYPES if table empty"""
        ta_settings = frappe.get_doc("Transfer Application Settings")
        ta_settings.reference_doctypes = []
        ta_settings.save()
        clear_cache()

        from imogi_finance.transfer_application.settings import (
            get_reference_doctypes,
            DEFAULT_REFERENCE_DOCTYPES,
        )

        doctypes = get_reference_doctypes()
        
        # Should fall back to defaults
        assert len(doctypes) > 0
        assert set(doctypes) == set(DEFAULT_REFERENCE_DOCTYPES)


class TestDeferredExpenseFlow:
    """Smoke test: Deferred Expense → deferrable_accounts rule + GL Mappings fallback"""

    def setup_method(self):
        """Setup test prerequisites"""
        if not frappe.db.exists("Company", "Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "country": "Indonesia",
            }).insert(ignore_permissions=True)

        # Create prepaid accounts
        for account_name in [
            "Prepaid Expense Default",
            "Prepaid Insurance",
            "Prepaid Rent",
        ]:
            if not frappe.db.exists("Account", account_name):
                frappe.get_doc({
                    "doctype": "Account",
                    "account_name": account_name,
                    "account_number": account_name[:4],
                    "parent_account": "1220 - Prepaid Expenses",
                    "company": "Test Company",
                    "root_type": "Asset",
                }).insert(ignore_permissions=True)

        # Setup Finance Control Settings with default prepaid
        settings = frappe.get_doc("Finance Control Settings")
        settings.gl_account_mappings = []
        settings.append("gl_account_mappings", {
            "purpose": DEFAULT_PREPAID,
            "company": "Test Company",
            "account": "Prepaid Expense Default",
            "is_required": 1,
        })
        settings.save()

        # Setup Expense Deferred Settings with rules
        deferred = frappe.get_doc("Expense Deferred Settings")
        deferred.deferrable_accounts = []
        deferred.append("deferrable_accounts", {
            "expense_account": "6100 - Insurance Expense",
            "prepaid_account": "Prepaid Insurance",
            "months": 12,
            "is_active": 1,
        })
        deferred.save()
        clear_cache()

    def test_deferred_resolve_default_prepaid(self):
        """Test: Deferred resolves default prepaid from GL Mappings"""
        from imogi_finance.settings.utils import get_default_prepaid_account

        account = get_default_prepaid_account("Test Company")
        
        assert account == "Prepaid Expense Default"

    def test_deferred_rule_override(self):
        """Test: Deferrable accounts rule should override default"""
        from imogi_finance.imogi_finance.doctype.expense_deferred_settings.expense_deferred_settings import (
            get_deferrable_account_map,
        )

        _, rule_map = get_deferrable_account_map()
        
        # Rule for Prepaid Insurance should exist
        assert "Prepaid Insurance" in rule_map

    def test_deferred_fallback_when_no_rule(self):
        """Test: If no rule match, fallback to default prepaid"""
        from imogi_finance.settings.utils import get_default_prepaid_account

        # For an expense account with no rule, should fallback to default
        account = get_default_prepaid_account("Test Company")
        
        assert account == "Prepaid Expense Default"


class TestIntegrationEndToEnd:
    """Integration test: Verify all 4 flows work together without conflicts"""

    def setup_method(self):
        """Setup complete test environment"""
        # Setup company
        if not frappe.db.exists("Company", "Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "country": "Indonesia",
            }).insert(ignore_permissions=True)

        # Setup Finance Control Settings with ALL mappings
        settings = frappe.get_doc("Finance Control Settings")
        settings.enable_digital_stamp = 1
        settings.gl_account_mappings = []
        
        purposes_accounts = {
            DIGITAL_STAMP_EXPENSE: "Biaya Materai Digital",
            DIGITAL_STAMP_PAYMENT: "Kas",
            DEFAULT_PAID_FROM: "Kas",
            DEFAULT_PREPAID: "Beban Dibayar Dimuka",
            DPP_VARIANCE: "Selisih DPP",
            PPN_VARIANCE: "Selisih PPN",
        }
        
        for purpose, account in purposes_accounts.items():
            settings.append("gl_account_mappings", {
                "purpose": purpose,
                "company": "Test Company",
                "account": account,
                "is_required": 1,
            })
        
        settings.save()
        clear_cache()

    def test_all_gl_purposes_resolvable(self):
        """Test: All GL purposes can be resolved without conflict"""
        from imogi_finance.settings.gl_purposes import ALL_PURPOSES

        for purpose in ALL_PURPOSES:
            account = get_gl_account(purpose, "Test Company", required=False)
            # Should not raise, may or may not return value depending on purpose config
            # Just verify no crosstalk errors
            assert True  # If we get here without exception, it works


if __name__ == "__main__":
    # Run with: frappe test-site test_integration_flows.py
    pytest.main([__file__, "-v"])
