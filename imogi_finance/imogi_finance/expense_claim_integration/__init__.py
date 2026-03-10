"""
Native Payment Ledger Enhancement Module

This module provides enhancements to ERPNext's native Payment Ledger system
without duplicating functionality.

Features:
- Custom dashboard report for better UX
- Expense Claim advance allocation
- Enhanced UI components

Philosophy: Native First + Minimal Custom
- Use ERPNext native Payment Ledger Entry as source of truth
- Only add what native doesn't provide
- Minimize maintenance overhead
"""

__version__ = "1.0.0"

# Import main functions for easier access
from imogi_finance.expense_claim_integration.expense_claim_advances import (
    get_employee_advances,
    allocate_advance_to_expense_claim,
    link_employee_advances,
    set_approval_status
)

__all__ = [
    "get_employee_advances",
    "allocate_advance_to_expense_claim",
    "link_employee_advances",
    "set_approval_status"
]
