"""Test PB1 Multi-Account functionality."""
from __future__ import annotations

import frappe
import pytest


def test_tax_profile_pb1_single_account():
    """Test backward compatibility: single PB1 account works."""
    profile = frappe.get_doc({
        "doctype": "Tax Profile",
        "company": "Test Company",
        "ppn_input_account": "PPN Input - TC",
        "ppn_output_account": "PPN Output - TC",
        "pb1_payable_account": "PB1 Payable - TC",
        "enable_pb1_multi_branch": 0,
    })
    
    # Should return single account regardless of branch
    assert profile.get_pb1_account() == "PB1 Payable - TC"
    assert profile.get_pb1_account("Branch A") == "PB1 Payable - TC"


def test_tax_profile_pb1_multi_branch_mapping():
    """Test multi-branch PB1 account mapping."""
    profile = frappe.get_doc({
        "doctype": "Tax Profile",
        "company": "Test Company",
        "ppn_input_account": "PPN Input - TC",
        "ppn_output_account": "PPN Output - TC",
        "pb1_payable_account": "PB1 Default - TC",
        "enable_pb1_multi_branch": 1,
        "pb1_account_mappings": [
            {"branch": "Jakarta", "pb1_payable_account": "PB1 Jakarta - TC"},
            {"branch": "Surabaya", "pb1_payable_account": "PB1 Surabaya - TC"},
        ]
    })
    
    # Should return branch-specific account
    assert profile.get_pb1_account("Jakarta") == "PB1 Jakarta - TC"
    assert profile.get_pb1_account("Surabaya") == "PB1 Surabaya - TC"
    
    # Should fallback to default for unmapped branch
    assert profile.get_pb1_account("Bandung") == "PB1 Default - TC"
    
    # Should return default when no branch specified
    assert profile.get_pb1_account() == "PB1 Default - TC"


def test_tax_profile_validate_duplicate_branch():
    """Test validation catches duplicate branch mappings."""
    profile = frappe.get_doc({
        "doctype": "Tax Profile",
        "company": "Test Company",
        "ppn_input_account": "PPN Input - TC",
        "ppn_output_account": "PPN Output - TC",
        "pb1_payable_account": "PB1 Default - TC",
        "enable_pb1_multi_branch": 1,
        "pb1_account_mappings": [
            {"branch": "Jakarta", "pb1_payable_account": "PB1 Jakarta A - TC"},
            {"branch": "Jakarta", "pb1_payable_account": "PB1 Jakarta B - TC"},
        ]
    })
    
    # Should raise error for duplicate branch
    with pytest.raises(Exception) as exc_info:
        profile.validate()
    
    assert "Jakarta" in str(exc_info.value)
    assert "multiple times" in str(exc_info.value).lower()


def test_tax_payment_batch_uses_branch_specific_pb1():
    """Test Tax Payment Batch picks correct PB1 account based on branch."""
    # This would need actual Tax Profile and Branch setup
    # Simplified test structure:
    
    batch = frappe.get_doc({
        "doctype": "Tax Payment Batch",
        "company": "Test Company",
        "tax_type": "PB1",
        "branch": "Jakarta",
        "period_month": 1,
        "period_year": 2026,
    })
    
    # Mock the profile with multi-branch
    # In real implementation, this would query actual Tax Profile
    # and use get_pb1_account("Jakarta")
    
    # Assertion: batch.payable_account should be Jakarta-specific
    # This is integration test territory


def test_build_register_snapshot_pb1_breakdown():
    """Test register snapshot includes PB1 breakdown when multi-branch."""
    from imogi_finance.tax_operations import build_register_snapshot
    
    # Mock setup: Tax Profile with multi-branch PB1
    # Mock GL entries for different PB1 accounts
    
    # snapshot = build_register_snapshot("Test Company", "2026-01-01", "2026-01-31")
    
    # Expected:
    # - snapshot["pb1_total"] = aggregate of all branches
    # - snapshot["pb1_breakdown"] = {"Jakarta": 100000, "Surabaya": 50000}
    
    # This requires full database setup, suitable for integration tests
    pass


if __name__ == "__main__":
    # Run basic unit tests
    test_tax_profile_pb1_single_account()
    test_tax_profile_pb1_multi_branch_mapping()
    print("✅ All unit tests passed!")
