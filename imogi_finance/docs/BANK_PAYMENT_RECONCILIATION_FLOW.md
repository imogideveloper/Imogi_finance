# Bank Payment Reconciliation Flow

## Overview

Fitur ini mengimplementasikan alur pembayaran yang berbeda untuk metode pembayaran **Bank** vs **Cash**:

- **Cash Payment**: Purchase Invoice langsung berstatus **Paid** saat Payment Entry di-submit
- **Bank Payment**: Purchase Invoice tetap berstatus **Unpaid** sampai Bank Transaction di-**reconcile**

## Business Logic

### Mengapa Diperlukan?

Dalam praktik akuntansi, pembayaran via bank memerlukan konfirmasi dari bank statement (Bank Transaction reconciliation) sebelum invoice dapat dianggap benar-benar lunas. Ini berbeda dengan pembayaran cash yang langsung dapat dikonfirmasi.

### Flow Diagram

```
┌─────────────────┐
│ Payment Entry   │
│ (Submit)        │
└────────┬────────┘
         │
         ├─────────── Check Account Type
         │
    ┌────▼────┐                    ┌────────────┐
    │  Bank?  │───Yes──────────────►│ ERPNext    │
    └────┬────┘                    │ Submit PE  │
         │                         └─────┬──────┘
         No (Cash)                       │
         │                         ┌─────▼──────────┐
    ┌────▼────────┐               │ ERPNext Updates│
    │ ERPNext     │               │ PI → Paid      │
    │ Submit PE   │               └─────┬──────────┘
    └────┬────────┘                     │
         │                         ┌─────▼──────────┐
    ┌────▼────────┐               │ Our Hook Runs  │
    │ PI → Paid   │               │ (on_update_    │
    │ immediately │               │ after_submit)  │
    └─────────────┘               └─────┬──────────┘
                                        │
                                  ┌─────▼──────────┐
                                  │ Force Revert   │
                                  │ PI → Unpaid    │
                                  └─────┬──────────┘
                                        │
                                  ┌─────▼──────────┐
                                  │ Set awaiting_  │
                                  │ bank_recon = 1 │
                                  └─────┬──────────┘
                                        │
                                  ┌─────▼──────────┐
                                  │ Bank Transaction│
                                  │ Reconciliation │
                                  └─────┬──────────┘
                                        │
                                  ┌─────▼──────────┐
                                  │ Update PI & ER │
                                  │ Status → Paid  │
                                  └────────────────┘
```

## Technical Implementation

### 1. Custom Field

**Payment Entry**:
- `awaiting_bank_reconciliation` (Check): Flag untuk menandai PE yang menunggu bank reconciliation

### 2. Modified Functions

#### `imogi_finance/events/payment_entry.py`

##### `_is_bank_payment(doc)` (New)
Helper function untuk check apakah payment menggunakan Bank account:
```python
def _is_bank_payment(doc) -> bool:
    """Check if Payment Entry is using Bank account (not Cash)."""
    # Check paid_from for "Pay" type, paid_to for "Receive" type
    # Return True if account_type == "Bank"
```

##### `_handle_expense_request_submit(doc, expense_request)` (Modified)
- Check `_is_bank_payment(doc)`
- Jika Bank: Set flag `awaiting_bank_reconciliation = 1`
- Jika Cash: Proceed normal (PI akan Paid oleh ERPNext)

##### `on_update_after_submit(doc, method)` (New)
Hook yang dipanggil **AFTER** ERPNext native code update PI status:
- Check jika `awaiting_bank_reconciliation = 1`
- Get linked PIs from references
- **Force revert** PI status dari Paid → Unpaid
- Update ER status kembali ke "PI Created"

**WHY THIS WORKS:**
1. Payment Entry submit dengan references normal → GL entries dibuat dengan benar ✅
2. ERPNext update PI status → Paid (native behavior)
3. Our hook runs AFTER ERPNext → Force revert status to Unpaid ✅
4. PI tetap Unpaid sampai bank reconciliation ✅

#### `imogi_finance/events/bank_transaction.py`

##### `on_update_after_submit(doc, method)` (New)
Hook yang dipanggil saat Bank Transaction di-update setelah submit:
- Check jika `status == "Reconciled"`
- Find linked Payment Entries via `_find_linked_payment_entries()`
- Update invoice status via `_update_invoice_status_after_bank_reconciliation()`

##### `_find_linked_payment_entries(bank_transaction)` (New)
Match Payment Entry dengan Bank Transaction berdasarkan:
- Account (paid_from/paid_to matches bank_account)
- Amount (deposit/withdrawal)
- Has `awaiting_bank_reconciliation = 1` flag
- Docstatus = 1 (submitted)

##### `_update_invoice_status_after_bank_reconciliation(pe_name, bt_name)` (New)
- Get Expense Request from PE
- Clear `awaiting_bank_reconciliation` flag
- Update PI status to "Paid"
- Update ER status to "Paid"
- Add comment to PE

### 3. Hooks Configuration

**`imogi_finance/hooks.py`**:
```python
"Payment Entry": {
    "on_submit": [...],
    "on_update_after_submit": [
        "imogi_finance.events.payment_entry.on_update_after_submit",
    ],
}

"Bank Transaction": {
    "on_update_after_submit": [
        "imogi_finance.events.bank_transaction.on_update_after_submit",
        # ... existing hooks
    ],
}
```

## Usage Examples

### Scenario 1: Cash Payment (Existing Behavior)

```python
# Create Payment Entry
pe = frappe.new_doc("Payment Entry")
pe.payment_type = "Pay"
pe.paid_from = "Cash - IDR"  # Cash account
pe.paid_to = "Creditors - IDR"
pe.paid_amount = 1000000
# ... set references to PI
pe.submit()

# Result: PI immediately marked as Paid
```

### Scenario 2: Bank Payment (New Behavior)

```python
# Create Payment Entry
pe = frappe.new_doc("Payment Entry")
pe.payment_type = "Pay"
pe.paid_from = "BCA Bank - IDR"  # Bank account
pe.paid_to = "Creditors - IDR"
pe.paid_amount = 1000000
# ... set references to PI
pe.submit()

# Result:
# - PI remains Unpaid
# - pe.awaiting_bank_reconciliation = 1

# Later... when Bank Transaction is reconciled
bt = frappe.get_doc("Bank Transaction", "BT-00123")
bt.status = "Reconciled"
bt.save()

# Result:
# - PI marked as Paid
# - pe.awaiting_bank_reconciliation = 0
# - Expense Request status = "Paid"
```

## Database Schema Changes

### Custom Field Addition

Run this after deploying:
```bash
bench --site [site-name] migrate
```

This will create the custom field `awaiting_bank_reconciliation` in Payment Entry.

## Testing Checklist

- [ ] Test Cash payment - PI should be Paid immediately
- [ ] Test Bank payment - PI should remain Unpaid
- [ ] Test Bank Transaction reconciliation - PI should become Paid
- [ ] Test with Expense Request workflow
- [ ] Verify custom field is created properly
- [ ] Check logs for proper tracking

## Migration Guide

### For Existing Installations

1. **Pull latest code**:
   ```bash
   cd ~/frappe-bench/apps/imogi_finance
   git pull
   ```

2. **Run migration**:
   ```bash
   bench --site [site-name] migrate
   ```

3. **Verify custom field**:
   - Open any Payment Entry form
   - Check if "Awaiting Bank Reconciliation" field appears in Reversal Information section

4. **No data migration needed**: Existing Payment Entries will have `awaiting_bank_reconciliation = 0` by default (correct behavior for already-submitted entries)

## Troubleshooting

### Issue: PI not marked as Paid after Bank Reconciliation

**Check**:
1. Payment Entry has `awaiting_bank_reconciliation = 1`?
2. Bank Transaction status is "Reconciled"?
3. Bank Transaction amount matches Payment Entry amount?
4. Bank Transaction account matches PE paid_from/paid_to?

**Logs to check**:
```
[Bank Transaction {name}] Reconciled but no linked Payment Entries found.
[Bank Reconciliation] PE {name} reconciled via Bank Transaction {bt_name}
```

### Issue: Cash payment not marking PI as Paid immediately

**Check**:
1. Account type is "Cash" (not "Bank")?
2. Check error logs in Payment Entry on_submit

## Future Enhancements

1. **UI Indicator**: Add indicator on Payment Entry form showing "Waiting for Bank Reconciliation"
2. **Bulk Reconciliation**: Support for matching multiple PEs to one Bank Transaction
3. **Tolerance Matching**: Allow small amount differences (e.g., bank fees)
4. **Email Notification**: Notify approvers when bank payment is reconciled
5. **Report**: List all payments awaiting bank reconciliation

## Related Documentation

- [Payment Entry Flow](./PAYMENT_ENTRY_FLOW.md)
- [Bank Transaction Reconciliation](./BANK_STATEMENT_FINAL.md)
- [Cash Bank Daily Report](./CASH_BANK_REPORT_REVERSAL_STRATEGY.md)
