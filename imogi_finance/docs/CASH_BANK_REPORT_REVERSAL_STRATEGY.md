# Cash/Bank Report Reversal Strategy

## Overview

This document explains how to handle corrections when transactions need to be reversed after a Cash/Bank Daily Report has been printed (submitted).

## Workflow Configuration

The workflow is defined in **fixtures/workflow.json** and **fixtures/workflow_state.json** for easy deployment across instances.

## Workflow States

Cash Bank Daily Reports use Frappe native workflow with these states:

1. **Generated**: Report created, can be regenerated and modified
2. **Printed**: Report has been printed and locked (immutable for audit trail)

## Transaction Reversal Strategy

### ✅ Cash Account Mode (GL Entry)

**When to Use**: For cash ledger accounts without bank account setup

**Reversal Process**:
1. **DO NOT Cancel** original Payment Entry
2. Use **"Reverse Payment Entry"** button instead
3. System creates reversal entry at **today's date**
4. Original transaction remains in ledger (audit trail preserved)
5. Reversal posts as new transaction today

**Example**:
```
Original PE (Jan 10, 2026):
- Paid From: Cash - IDR
- Amount: 1,000,000
- Status: Submitted, Included in Printed Report Jan 10

Reversal PE (Created Jan 16, 2026):
- Paid To: Cash - IDR (reversed direction)
- Amount: 1,000,000
- Posting Date: Jan 16, 2026
- Remarks: "Reversal of PE-00123 (original date: Jan 10, 2026)"
- Status: Draft → needs review and submit
```

**Result**:
- Jan 10 report: Shows original transaction (locked, unchanged)
- Jan 16 report: Shows reversal transaction
- Net effect: Transaction reversed with full audit trail

### ✅ Bank Account Mode (Bank Transaction)

**When to Use**: For bank accounts with imported bank statements

**Important Notes**:
- Bank Transactions are **IMMUTABLE** (来自银行对账单导入)
- Cannot be cancelled or deleted (bank statement is source of truth)
- Errors require **reconciliation correction**

**Correction Process**:

#### Option 1: Reconciliation Adjustment (Preferred)
```
1. Original Bank Transaction remains unchanged
2. Create Manual Journal Entry for correction
3. Post JE at current date
4. Use "Bank Reconciliation Adjustment" account
5. Document reason in remarks
```

#### Option 2: GL Entry Correction
```
1. Bank Transaction stays as-is
2. Create correcting GL Entry
3. Adjust affected expense accounts
4. Post at current date with clear reference
```

**Example**:
```
Bank Transaction (Jan 10, 2026) - CANNOT CHANGE:
- Bank: BCA Main Account
- Withdrawal: 1,000,000
- Description: "Payment to Supplier XYZ"
- Status: Reconciled, Included in Printed Report Jan 10

Correction JE (Jan 16, 2026):
Entry 1:
  Dr. Supplier XYZ Payable: 1,000,000
  Cr. Bank Reconciliation Adjustment: 1,000,000
  
Entry 2: (if needed to reallocate)
  Dr. Correct Expense Account: 1,000,000
  Cr. Supplier XYZ Payable: 1,000,000

Remarks: "Correction for Bank Transaction dated Jan 10, 2026 - 
          Original payment to wrong account, reallocating to correct expense"
```

**Result**:
- Jan 10 bank report: Shows bank transaction (locked, reflects bank statement)
- Jan 16 GL: Shows correction entries
- Bank balance: Remains accurate (matches bank statement)
- Accounting: Corrected via GL entries

## Workflow Protection

### Cash Bank Report Locking

**When "Print & Lock" is clicked**:
```python
workflow_state: "Generated" → "Printed"
printed_at: Current datetime
printed_by: Current user
```

**Protection Applied**:
- ✅ Cannot regenerate snapshot
- ✅ Cannot modify report date or branches
- ✅ Cannot delete report
- ✅ Related Payment Entries cannot be cancelled

### Payment Entry Cancellation Block

**Validation on PE Cancel**:
```python
def on_cancel(payment_entry):
    if linked_to_printed_report(payment_entry):
        BLOCK with message:
        "Cannot cancel - use Reverse Payment Entry instead"
```

**Check Logic**:
1. Get PE posting date
2. Find Cash/Bank Daily Reports for that date
3. Check if any report is workflow_state = "Printed"
4. If yes → BLOCK cancellation
5. If no → Allow normal cancellation

## API Methods

### 1. Mark Report as Printed
```python
@frappe.whitelist()
def mark_as_printed(name: str):
    """Transition report from Generated to Printed state"""
    # Sets workflow_state, printed_at, printed_by
    # Locks report from modifications
```

### 2. Reverse Payment Entry
```python
@frappe.whitelist()
def reverse_payment_entry(
    payment_entry_name: str, 
    reversal_date: str | None = None
):
    """Create reversal PE at today's date (or specified date)
    
    - Flips accounts (paid_from ↔ paid_to)
    - Posts at reversal_date (default: today)
    - Links to original PE
    - Updates Expense Request status
    """
```

### 3. Check Printed Report Linkage
```python
def _check_linked_to_printed_report(payment_entry) -> bool:
    """Check if PE is in any printed daily report"""
    # Returns True if found
```

## UI Components

### Cash Bank Daily Report Form

**Buttons**:
- **"Regenerate Snapshot"**: Only shown if workflow_state = "Generated"
- **"Print & Lock"**: Primary button, marks as printed and opens print view
  - Shows confirmation dialog
  - Locks report after user confirms

**Indicators**:
- Green: "Report Printed & Locked: [datetime] by [user]"
- Orange: "Balance Mismatch Detected"
- Blue: "Opening Balance Source: [source]"

### Payment Entry Form

**Additional Buttons** (to be added):
- **"Reverse Entry"**: Creates reversal PE
  - Only shown if PE is submitted
  - Opens dialog to select reversal date
  - Default: today

**Validation Messages**:
- Error: "Cannot cancel - included in printed report"
- Success: "Reversal PE-XXXXX created for [date]"

## Best Practices

### For Cash Accounts
1. ✅ Always use reversal instead of cancellation after report is printed
2. ✅ Review reversal PE before submitting
3. ✅ Document reason in remarks field
4. ✅ Notify relevant parties about the reversal
5. ✅ Generate new daily report for reversal date

### For Bank Accounts
1. ✅ Never modify imported Bank Transactions
2. ✅ Use Journal Entries for corrections
3. ✅ Always reference original bank transaction in remarks
4. ✅ Keep bank reconciliation trail clear
5. ✅ Document correction reason thoroughly

### For Audit Trail
1. ✅ Never delete or regenerate printed reports
2. ✅ Keep original transactions visible
3. ✅ Use reversals/corrections at current date
4. ✅ Maintain clear documentation in remarks
5. ✅ Create correction reports for new transaction dates

## Compliance Notes

This reversal strategy ensures:
- ✅ **Audit Trail Integrity**: Original transactions remain unchanged
- ✅ **Temporal Accuracy**: Corrections post at actual correction date
- ✅ **Bank Statement Match**: Bank transactions always match statements
- ✅ **Accounting Standards**: Follows reversal entry best practices
- ✅ **Tax Compliance**: Clear documentation for auditors

## Migration Notes

### Existing Payment Entries
- No schema changes required for existing PEs
- Reversal validation only applies to NEW cancellations
- Existing cancelled PEs remain unchanged

### Existing Daily Reports
- Add workflow_state field (default: "Generated")
- Reports without printed_at are considered "Generated"
- Can manually mark old reports as "Printed" if needed

### Optional Fields for Payment Entry
Consider adding custom fields:
```json
{
  "fieldname": "is_reversal",
  "fieldtype": "Check",
  "label": "Is Reversal Entry"
},
{
  "fieldname": "reversed_entry",
  "fieldtype": "Link",
  "label": "Reversed Payment Entry",
  "options": "Payment Entry"
},
{
  "fieldname": "is_reversed",
  "fieldtype": "Check",
  "label": "Has Been Reversed"
},
{
  "fieldname": "reversal_entry",
  "fieldtype": "Link",
  "label": "Reversal Entry",
  "options": "Payment Entry"
}
```

## Summary

| Scenario | Solution | Posting Date | Audit Trail |
|----------|----------|--------------|-------------|
| **Cash PE after print** | Reverse Payment Entry | Today | ✅ Full |
| **Bank TX after print** | GL/JE Correction | Today | ✅ Full |
| **Report modification** | BLOCKED if printed | - | ✅ Locked |
| **PE cancellation** | BLOCKED if in printed report | - | ✅ Protected |

This approach maintains complete audit trail while allowing legitimate corrections through proper accounting reversal methods.
