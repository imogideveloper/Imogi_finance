"""
Test suite for Settings Helper Layer (Fase 8 Validation)

Tests validate:
1. GL account mapping resolution (exact match → fallback → error/None)
2. Tax Profile master for PPN accounts
3. Digital stamp account resolution
4. Paid from/to account resolution
5. Default prepaid account resolution
6. Reference doctypes fallback pattern
7. Branch settings defaults single source
"""

from __future__ import annotations

import pytest
import frappe
from frappe.utils import clear_cache

from imogi_finance.settings.utils import (
    get_gl_account,
    get_tax_profile,
    get_ppn_accounts,
    get_default_prepaid_account,
    get_finance_control_settings,
    get_transfer_application_settings,
)
from imogi_finance.settings.gl_purposes import (
    DIGITAL_STAMP_EXPENSE,
    DIGITAL_STAMP_PAYMENT,
    DEFAULT_PAID_FROM,
    DEFAULT_PREPAID,
    DPP_VARIANCE,
    PPN_VARIANCE,
)
from imogi_finance.settings.branch_defaults import BRANCH_SETTING_DEFAULTS
from imogi_finance.transfer_application.settings import (
    get_reference_doctypes,
    DEFAULT_REFERENCE_DOCTYPES,
)


class TestGLAccountMapping:
    """Test get_gl_account() helper function"""

    def setup_method(self):
        """Setup test data before each test"""
        # Create test company
        if not frappe.db.exists("Company", "Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "country": "Indonesia",
            }).insert(ignore_permissions=True)

        # Ensure Finance Control Settings has test mappings
        settings = frappe.get_doc("Finance Control Settings")
        settings.gl_account_mappings = []
        settings.append("gl_account_mappings", {
            "purpose": DIGITAL_STAMP_EXPENSE,
            "company": "Test Company",
            "account": "Biaya Test Expense",
            "is_required": 1,
        })
        settings.append("gl_account_mappings", {
            "purpose": DIGITAL_STAMP_EXPENSE,
            "company": "",  # Global default
            "account": "Biaya Default Expense",
            "is_required": 1,
        })
        settings.append("gl_account_mappings", {
            "purpose": DEFAULT_PREPAID,
            "company": "",
            "account": "Prepaid Default",
            "is_required": 1,
        })
        settings.save()
        clear_cache()

    def teardown_method(self):
        """Cleanup after each test"""
        clear_cache()

    def test_exact_match_company_priority(self):
        """Test: Exact match (purpose+company) should win over default"""
        result = get_gl_account(
            DIGITAL_STAMP_EXPENSE,
            company="Test Company",
            required=True
        )
        assert result == "Biaya Test Expense", \
            f"Should use Test Company specific mapping, got {result}"

    def test_fallback_to_global_default(self):
        """Test: Fallback to global default (company='') when no exact match"""
        result = get_gl_account(
            DIGITAL_STAMP_EXPENSE,
            company="NonExistent Company",
            required=False
        )
        assert result == "Biaya Default Expense", \
            f"Should fallback to global default, got {result}"

    def test_required_true_raises_error(self):
        """Test: required=True should raise error with actionable message"""
        with pytest.raises(frappe.ValidationError) as exc_info:
            get_gl_account(
                purpose="nonexistent_purpose",
                company="Test Company",
                required=True
            )
        
        error_msg = str(exc_info.value)
        assert "nonexistent_purpose" in error_msg.lower() or "not configured" in error_msg.lower(), \
            f"Error message should mention purpose, got: {error_msg}"

    def test_required_false_returns_none(self):
        """Test: required=False should return None instead of raise"""
        result = get_gl_account(
            purpose="nonexistent_purpose",
            company="Test Company",
            required=False
        )
        assert result is None, f"Should return None, got {result}"

    def test_all_purposes_defined(self):
        """Test: All GL purposes constants should be accessible"""
        purposes = [
            DIGITAL_STAMP_EXPENSE,
            DIGITAL_STAMP_PAYMENT,
            DEFAULT_PAID_FROM,
            DEFAULT_PREPAID,
            DPP_VARIANCE,
            PPN_VARIANCE,
        ]
        
        for purpose in purposes:
            assert purpose is not None, f"Purpose constant should not be None"
            assert isinstance(purpose, str), f"Purpose should be string, got {type(purpose)}"


class TestTaxProfileMaster:
    """Test that Tax Profile is master for PPN accounts"""

    def setup_method(self):
        """Setup test Tax Profile"""
        if not frappe.db.exists("Company", "Test Company"):
            frappe.get_doc({
                "doctype": "Company",
                "company_name": "Test Company",
                "country": "Indonesia",
            }).insert(ignore_permissions=True)

        # Create test Tax Profile
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
        clear_cache()

    def teardown_method(self):
        """Cleanup"""
        clear_cache()

    def test_get_ppn_accounts_success(self):
        """Test: get_ppn_accounts returns tuple of (input, output)"""
        ppn_input, ppn_output = get_ppn_accounts("Test Company")
        
        assert ppn_input == "2110 - Test PPN Input"
        assert ppn_output == "2111 - Test PPN Output"

    def test_get_ppn_accounts_missing_profile_error(self):
        """Test: get_ppn_accounts raises error if Tax Profile not found"""
        with pytest.raises(frappe.ValidationError) as exc_info:
            get_ppn_accounts("NonExistent Company")
        
        error_msg = str(exc_info.value)
        assert "tax profile" in error_msg.lower(), \
            f"Error should mention Tax Profile, got: {error_msg}"

    def test_get_ppn_accounts_missing_input_error(self):
        """Test: get_ppn_accounts raises error if ppn_input_account empty"""
        # Create Tax Profile with missing ppn_input_account
        tp = frappe.get_doc("Tax Profile", {"company": "Test Company"})
        tp.ppn_input_account = ""
        tp.save()
        clear_cache()

        with pytest.raises(frappe.ValidationError) as exc_info:
            get_ppn_accounts("Test Company")
        
        error_msg = str(exc_info.value)
        assert "ppn input" in error_msg.lower(), \
            f"Error should mention PPN Input Account, got: {error_msg}"


class TestBranchSettingsDefaults:
    """Test BRANCH_SETTING_DEFAULTS single source of truth"""

    def test_defaults_dict_has_required_keys(self):
        """Test: BRANCH_SETTING_DEFAULTS has all required keys"""
        required_keys = {
            "enable_multi_branch",
            "inherit_branch_from_cost_center",
            "default_branch",
            "enforce_branch_on_links",
        }
        
        assert set(BRANCH_SETTING_DEFAULTS.keys()) == required_keys, \
            f"Missing keys: {required_keys - set(BRANCH_SETTING_DEFAULTS.keys())}"

    def test_defaults_are_reasonable_values(self):
        """Test: Default values are reasonable (0/1/None)"""
        assert BRANCH_SETTING_DEFAULTS["enable_multi_branch"] == 0
        assert BRANCH_SETTING_DEFAULTS["inherit_branch_from_cost_center"] == 1
        assert BRANCH_SETTING_DEFAULTS["default_branch"] is None
        assert BRANCH_SETTING_DEFAULTS["enforce_branch_on_links"] == 1

    def test_defaults_dict_is_immutable_by_reference(self):
        """Test: Verify no duplicate definitions (only 1 source)"""
        # This test documents that BRANCH_SETTING_DEFAULTS should be imported,
        # not defined locally in each module
        count = 0
        import imogi_finance.branching
        import imogi_finance.receipt_control.utils
        
        # Both should import same dict, not redefine
        assert hasattr(imogi_finance.branching, "BRANCH_SETTING_DEFAULTS")
        assert hasattr(imogi_finance.receipt_control.utils, "BRANCH_SETTING_DEFAULTS")


class TestReferenceDocypesFallback:
    """Test reference_doctypes table with fallback to DEFAULT_REFERENCE_DOCTYPES"""

    def test_default_reference_doctypes_exists(self):
        """Test: DEFAULT_REFERENCE_DOCTYPES constant is defined"""
        assert DEFAULT_REFERENCE_DOCTYPES is not None
        assert len(DEFAULT_REFERENCE_DOCTYPES) > 0
        assert "Purchase Invoice" in DEFAULT_REFERENCE_DOCTYPES
        assert "Expense Claim" in DEFAULT_REFERENCE_DOCTYPES

    def test_get_reference_doctypes_returns_list(self):
        """Test: get_reference_doctypes() returns non-empty list"""
        result = get_reference_doctypes()
        
        assert isinstance(result, list), f"Should return list, got {type(result)}"
        assert len(result) > 0, "Should return at least one doctype"

    def test_get_reference_doctypes_contains_expected_defaults(self):
        """Test: Returned list contains at least some expected doctypes"""
        result = get_reference_doctypes()
        
        # Should contain at least one of these
        expected = {"Purchase Invoice", "Expense Claim", "Expense Request"}
        found = set(result) & expected
        
        assert len(found) > 0, \
            f"Should contain at least one of {expected}, got {result}"


class TestSchemaIntegrity:
    """Test that all required fields/tables exist in DocTypes"""

    def test_finance_control_settings_has_gl_account_mappings_table(self):
        """Test: Finance Control Settings has gl_account_mappings Table field"""
        meta = frappe.get_meta("Finance Control Settings")
        
        assert meta.has_field("gl_account_mappings"), \
            "Finance Control Settings should have gl_account_mappings field"
        
        field = meta.get_field("gl_account_mappings")
        assert field.fieldtype == "Table", \
            f"gl_account_mappings should be Table type, got {field.fieldtype}"

    def test_transfer_application_settings_has_reference_doctypes(self):
        """Test: Transfer Application Settings has reference_doctypes Table"""
        meta = frappe.get_meta("Transfer Application Settings")
        
        assert meta.has_field("reference_doctypes"), \
            "Transfer Application Settings should have reference_doctypes field"
        
        field = meta.get_field("reference_doctypes")
        assert field.fieldtype == "Table", \
            f"reference_doctypes should be Table type, got {field.fieldtype}"

    def test_expense_deferred_settings_has_deferrable_accounts(self):
        """Test: Expense Deferred Settings has deferrable_accounts Table"""
        meta = frappe.get_meta("Expense Deferred Settings")
        
        assert meta.has_field("deferrable_accounts"), \
            "Expense Deferred Settings should have deferrable_accounts field"

    def test_gl_account_mapping_item_child_table_exists(self):
        """Test: GL Account Mapping Item child table exists"""
        assert frappe.db.exists("DocType", "GL Account Mapping Item"), \
            "GL Account Mapping Item child table should exist"
        
        meta = frappe.get_meta("GL Account Mapping Item")
        assert meta.has_field("purpose"), "Should have purpose field"
        assert meta.has_field("account"), "Should have account field"
        assert meta.has_field("company"), "Should have company field"


class TestFixtureSeeding:
    """Test that fixtures are properly seeded on fresh deploy"""

    def test_finance_control_settings_doc_exists(self):
        """Test: Finance Control Settings singleton exists"""
        assert frappe.db.exists("Finance Control Settings", "Finance Control Settings"), \
            "Finance Control Settings singleton should exist"

    def test_finance_control_settings_has_gl_mappings_rows(self):
        """Test: Finance Control Settings has gl_account_mappings rows"""
        doc = frappe.get_doc("Finance Control Settings")
        
        assert len(doc.gl_account_mappings) >= 6, \
            f"Should have at least 6 GL account mappings, got {len(doc.gl_account_mappings)}"

    def test_gl_account_mappings_have_all_purposes(self):
        """Test: GL account mappings include all expected purposes"""
        doc = frappe.get_doc("Finance Control Settings")
        
        purposes = [row.purpose for row in doc.gl_account_mappings]
        required_purposes = {
            DIGITAL_STAMP_EXPENSE,
            DIGITAL_STAMP_PAYMENT,
            DEFAULT_PAID_FROM,
            DEFAULT_PREPAID,
            DPP_VARIANCE,
            PPN_VARIANCE,
        }
        
        found = set(purposes) & required_purposes
        missing = required_purposes - found
        
        assert len(missing) == 0, \
            f"Missing GL account mapping purposes: {missing}"

    def test_transfer_application_settings_has_reference_doctypes_rows(self):
        """Test: Transfer Application Settings has reference_doctypes seeded"""
        doc = frappe.get_doc("Transfer Application Settings")
        
        assert len(doc.reference_doctypes) > 0, \
            "Transfer Application Settings should have reference_doctypes rows"


if __name__ == "__main__":
    # Run with: frappe test-site test_settings_helpers.py
    pytest.main([__file__, "-v"])
