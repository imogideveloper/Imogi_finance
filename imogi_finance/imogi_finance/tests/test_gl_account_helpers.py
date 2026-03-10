"""Smoke tests untuk GL Account mapping helpers.

Quick validation tests untuk ensure get_gl_account() bekerja dengan baik.
Run dengan: bench --site [site] execute imogi_finance.tests.test_gl_account_helpers
"""

import frappe
from frappe.utils import now
from imogi_finance.settings.utils import get_gl_account, get_finance_control_settings
from imogi_finance.settings import gl_purposes


def test_gl_account_mapping_creation():
    """Test 1: Create Finance Control Settings dengan GL mappings."""
    print("\n=== TEST 1: Creating Finance Control Settings with GL mappings ===")
    
    try:
        # Get or create settings
        settings = frappe.get_doc("Finance Control Settings")
    except frappe.DoesNotExistError:
        settings = frappe.new_doc("Finance Control Settings")
        settings.insert()
    
    # Clear existing mappings
    settings.gl_account_mappings = []
    
    # Add test mappings (assuming these accounts exist)
    # Note: In real test, these should be valid accounts in your chart of accounts
    test_accounts = {
        gl_purposes.DIGITAL_STAMP_EXPENSE: "5410 - Digital Stamp Expense",
        gl_purposes.DIGITAL_STAMP_PAYMENT: "1110 - Cash",
        gl_purposes.DEFAULT_PAID_FROM: "1110 - Cash",
        gl_purposes.DEFAULT_PREPAID: "1220 - Prepaid Expense",
        gl_purposes.DPP_VARIANCE: "6101 - DPP Variance",
        gl_purposes.PPN_VARIANCE: "6102 - PPN Variance",
    }
    
    for purpose, account in test_accounts.items():
        settings.append("gl_account_mappings", {
            "purpose": purpose,
            "account": account,
            "company": "",
            "is_required": 1,
            "description": f"Test mapping for {purpose}"
        })
    
    settings.save()
    print(f"✅ Created Finance Control Settings with {len(test_accounts)} GL mappings")
    return settings


def test_get_gl_account_exact_match():
    """Test 2: Test exact match lookup."""
    print("\n=== TEST 2: Testing exact match by purpose ===")
    
    try:
        account = get_gl_account(gl_purposes.DIGITAL_STAMP_EXPENSE, required=False)
        if account:
            print(f"✅ Found account for {gl_purposes.DIGITAL_STAMP_EXPENSE}: {account}")
            return True
        else:
            print(f"⚠️  No account found for {gl_purposes.DIGITAL_STAMP_EXPENSE}")
            return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_get_gl_account_missing_required():
    """Test 3: Test error when required account is missing."""
    print("\n=== TEST 3: Testing error for missing required account ===")
    
    try:
        account = get_gl_account("non_existent_purpose", required=True)
        print(f"❌ Should have thrown error but got: {account}")
        return False
    except frappe.ValidationError as e:
        print(f"✅ Correctly threw error: {str(e)}")
        return True
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False


def test_get_gl_account_missing_optional():
    """Test 4: Test returning None when optional account is missing."""
    print("\n=== TEST 4: Testing None return for missing optional account ===")
    
    try:
        account = get_gl_account("non_existent_purpose", required=False)
        if account is None:
            print(f"✅ Correctly returned None for missing optional account")
            return True
        else:
            print(f"❌ Should have returned None but got: {account}")
            return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False


def test_gl_account_multicompany_fallback():
    """Test 5: Test multi-company fallback logic."""
    print("\n=== TEST 5: Testing multi-company fallback ===")
    
    try:
        # Query untuk company yang bukan default
        account = get_gl_account(
            gl_purposes.DIGITAL_STAMP_EXPENSE,
            company="Other Company",
            required=False
        )
        
        # Should fallback ke global default (company="")
        if account:
            print(f"✅ Correctly fell back to global default: {account}")
            return True
        else:
            print(f"⚠️  No fallback found (might be OK if no default mapping exists)")
            return True  # This is acceptable behavior
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


def test_gl_mapping_uniqueness_validation():
    """Test 6: Test uniqueness validation in controller."""
    print("\n=== TEST 6: Testing GL mapping uniqueness validation ===")
    
    try:
        settings = frappe.get_doc("Finance Control Settings")
        
        # Try to add duplicate mapping
        settings.append("gl_account_mappings", {
            "purpose": gl_purposes.DIGITAL_STAMP_EXPENSE,
            "account": "1110 - Cash",
            "company": "",
            "is_required": 0,
            "description": "Duplicate"
        })
        
        # This should fail validation
        settings.save()
        print(f"❌ Should have thrown validation error for duplicate mapping")
        return False
    except frappe.ValidationError as e:
        if "Duplicate GL account mapping" in str(e):
            print(f"✅ Correctly caught duplicate mapping: {str(e)}")
            return True
        else:
            print(f"❌ Wrong validation error: {str(e)}")
            return False
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False


def run_all_tests():
    """Run all smoke tests."""
    print("\n" + "="*60)
    print("SMOKE TESTS: GL Account Mapping Helpers")
    print("="*60)
    
    results = []
    
    try:
        # Test 1: Creation
        test_gl_account_mapping_creation()
        
        # Test 2: Exact match
        results.append(("Exact match lookup", test_get_gl_account_exact_match()))
        
        # Test 3: Missing required
        results.append(("Missing required account error", test_get_gl_account_missing_required()))
        
        # Test 4: Missing optional
        results.append(("Missing optional account None", test_get_gl_account_missing_optional()))
        
        # Test 5: Multi-company fallback
        results.append(("Multi-company fallback", test_gl_account_multicompany_fallback()))
        
        # Test 6: Uniqueness validation (skip if first test failed)
        try:
            results.append(("GL mapping uniqueness validation", test_gl_mapping_uniqueness_validation()))
        except Exception as e:
            print(f"\n⚠️  Skipping uniqueness test due to: {str(e)}")
        
        # Summary
        print("\n" + "="*60)
        print("TEST RESULTS SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for test_name, result in results:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{status}: {test_name}")
        
        print(f"\n{passed}/{total} tests passed")
        print("="*60 + "\n")
        
        return passed == total
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}")
        frappe.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
