# Payment Reconciliation User Guide - Auto-Unlink on Cancel

## 📋 Overview

Sistem Advance Payment menggunakan **Auto-Unlink on Cancel** untuk menangani pembatalan dokumen yang sudah di-reconcile. Payment reconciliation entries akan **otomatis di-unlink SEBELUM cancel** untuk mencegah blocking.

---

## 🔄 Apa yang Terjadi Saat Cancel Document?

### Automatic Actions (Fully Automated):
1. ✅ **Payment reconciliation entries** otomatis di-unlink (BEFORE cancel)
2. ✅ **Document cancellation** proceeds smoothly tanpa blocking
3. ✅ **Advance Payment Entry allocations** otomatis di-clear (AFTER cancel)
4. ✅ **Advance amount** kembali tersedia untuk allocate ke dokumen lain

### Manual Actions Required:
❌ **NONE!** - Semua otomatis ditangani system

---

## ⚙️ Technical Flow

### Hook Sequence:
```
User clicks "Cancel"
    ↓
BEFORE_CANCEL hook triggered
    → Auto-detect Payment Ledger Entries
    → Auto-unlink each payment
    → Show success message
    ↓
CANCEL proceeds
    ↓
ON_CANCEL hook triggered
    → Clear APE allocations
    → Update APE unallocated amounts
    ↓
✅ Complete!
```

---

## 📖 User Guide: Cancel Document yang Sudah Di-Reconcile

### Scenario: Cancel Purchase Invoice yang Sudah Di-Reconcile

**Starting Point:**
- Purchase Invoice: PI-001 (Submitted)
- Advance Payment Entry: APE-001 (allocated 10,000 to PI-001)
- Payment Reconciliation: Completed (PE-001 reconciled to PI-001)

**Steps to Cancel:**

#### Step 1: Click Cancel
```
1. Open Purchase Invoice PI-001
2. Click "Cancel" button
3. Confirm cancellation
```

#### Step 2: System Auto-Processes
```
✅ System automatically unlinks PE-001 from PI-001
✅ Blue message appears: "Payment Reconciliation Auto-Unlinked:
   Successfully unlinked 1 payment(s) before cancellation."
```

#### Step 3: Cancellation Completes
```
✅ PI-001 cancelled (docstatus = 2)
✅ APE-001 allocation cleared
✅ APE-001 unallocated_amount restored to 10,000
```

**That's it! No manual steps needed.**

---

## 🎯 Visual Indicators & Messages

### Success Message (Auto-Unlink):
```
┌────────────────────────────────────────────────┐
│ ℹ️ Payment Reconciliation Auto-Unlinked       │
│                                                │
│ Successfully unlinked 2 payment(s) before      │
│ cancellation.                                  │
│                                                │
│ Advance allocations will be cleared after      │
│ cancel completes.                              │
└────────────────────────────────────────────────┘
```

### Warning Message (Some Failed - Rare):
```
┌────────────────────────────────────────────────┐
│ ⚠️ Note                                        │
│                                                │
│ Some payments could not be auto-unlinked:      │
│ • PE-002: Payment already cancelled            │
│                                                │
│ This is usually OK. Cancellation will proceed. │
└────────────────────────────────────────────────┘
```

---

## 📊 Complete Flow Diagram

```
┌──BEFORE_CANCEL HOOK (Auto-Unlink):                     │
│  ✅ Detect Payment Ledger Entries                       │
│  ✅ Auto-unlink PE-001 from PI-001                      │
│  ✅ Auto-unlink PE-002 from PI-001                      │
│  ✅ Show success message                                │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  CANCEL PROCEEDS:                                       │
│  ✅ PI-001.docstatus = 2 (Cancelled)                    │
│  ✅ No blocking errors!                                 │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  ON_CANCEL HOOK (Clear Allocations):                   │
│  ✅ Clear APE-001 allocations                           │
│  ✅ APE-001.unallocated_amount += 10,000                │
│  ✅ APE-001 status updated (if needed)                  │
│  ✅ Advance available again                             │
└───────────────┬─────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────┐
│  COMPLETE:                                              │
│  ✅ Document cancelled                                  │
│  ✅ Payments unlinked                                   │
│  ✅ Allocations cleared                                 │
│  ✅ Advance available                                   │
│  ✅ Outstanding amounts restored        
┌─────────────────────────────────────────────────────────┐
│  RESULT:                                                │
│  ✅ APE allocations cleared                             │
│  ✅ Payment Ledger Entries unlinked                     │
│  ✅ Outstanding amounts restored                        │
│  ✅ Advance available for other invoices                │
└─────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technical Details

### Files Modified:

1. **api.py** - Added helper functions:
   - `check_and_warn_reconciled_payments()` - Detects reconciled payments
   - `get_reconciled_payments_for_cancelled_doc()` - Returns list of payments
   - `unlink_single_payment()` - Unlinks one payment
   - `unlink_payment_manual()` - Fallback manual unlink

2. **payment_reconciliation_helper.js** - User interface:
   - `add_unreconuto-unlink functions:
   - `on_reference_before_cancel()` - BEFORE_CANCEL hook entry point
   - `auto_unlink_reconciled_payments()` - Detects & unlinks payments
   - `on_reference_cancel()` - ON_CANCEL hook (clear allocations)
   - `unlink_single_payment()` - Unlinks one payment
   - `unlink_payment_manual()` - Fallback manual unlink

2. **hooks.py** - Hook registration:
   - Added `before_cancel` hooks for PI, SI, Expense Claim, Payroll Entry
   - Existing `on_cancel` hooks for clearing allocations

### Hook Sequence:
```python
"Purchase Invoice": {
    "before_cancel": [
        "imogi_finance.events.purchase_invoice.before_cancel",
        "imogi_finance.advance_payment.api.on_reference_before_cancel",  # AUTO-UNLINK
    ],
    "on_cancel": [Without Reconciliation
```
✅ Create PE-001 → APE-001 created
✅ Allocate APE-001 to PI-001
✅ Cancel PI-001
✅ No payments to unlink message
✅ APE allocation cleared instantly
✅ Advance available again
```

### Scenario 2: Cancel Invoice After Reconciliation
```
✅ Create PE-001 → APE-001 created
✅ Allocate APE-001 to PI-001
✅ Reconcile via Payment Reconciliation Tool
✅ Cancel PI-001
✅ Blue message: "Successfully unlinked 1 payment(s)"
✅ Cancellation completes without blocking
✅ APE allocation cleared
✅ Outstanding restored
```

### Scenario 3: Cancel with Multiple Payments
```
✅ Create PE-001, PE-002 → APE-001, APE-002
✅ Allocate both to PI-001
✅ Reconcile all payments
✅ Cancel PI-001
✅ Blue message: "Successfully unlinked 2 payment(s)"
✅ Both allocations cleared
✅ Both advances available
```

### Scenario 4: Cancel Payment Entry
```
✅ Create PE-001 → APE-001 created
✅ Allocate APE-001 to PI-001
✅ Reconcile payments
✅ Cancel PE-001
✅ APE-001 automatically cancelled
✅ All allocations cleared from PI-001
✅ No blocking errors
```

---

## 💡 Best Practices

### For Users:
1. **Just click Cancel** - System handles everything automatically
2. **Read success messages** - Confirms what was unlinked
3. **Check advance availability** - Verify amounts restored
4. **No manual steps needed** - Unless system shows orange warning

### For Administrators:
1. **Monitor logs** for auto-unlink success rates
2. **No special permissions needed** - Works for all users
3. **Review Payment Ledger** for data consistency
4. **Test cancellation flow** after ERPNext updates

---

## 🔍 Troubleshooting

### Issue: Cancellation still blocked?
**Cause:** Payment Entry might be from different source (not reconciliation)
**Solution:** Check Payment Entry references table manually

### Issue: Orange warning appears?
**Cause:** Some payments couldn't be unlinked (rare)
**Solution:** 
- Check if those Payment Entries are already cancelled (usually OK)
- Or manually unlink as instructed in warning

### Issue: Advance not available after cancel?
**Cause:** APE might be cancelled or another issue
**Solution:** 
- Check APE status (should be submitted, not cancelled)
- Verify APE.unallocated_amount increased
- Check allocations table is empty

---

## 📞 Support

For issues or questions:
1. **Check logs**: System logs auto-unlink attempts
2. **Verify hooks**: Ensure before_cancel hooks registered
3. **Test flow**: Follow testing checklist above
4. **Contact admin**: If auto-unlink consistently fails

**Implementation files:**
- `/imogi_finance/advance_payment/api.py`
- `/imogi_finance/hooks.py
✅ APE-001 automatically cancelled
✅ All allocations cleared
✅ No warning needed (PE cancellation handles everything)
```

---

## 💡 Best Practices

### For Users:
1. **Always check dashboard** after cancelling documents
2. **Follow the warning messages** - they contain step-by-step guidance
3. **Use "Unlink All Payments" button** for fastest resolution
4. **Verify outstanding amounts** after unlinking

### For Administrators:
1. **Train users** on the 3 unlink methods
2. **Grant Payment Entry write permission** to users who need "Unlink All" button
3. **Monitor Payment Ledger** for orphaned entries
4. **Review logs** for auto-unlink success/failure rates

---

## 🔍 Troubleshooting

### Warning doesn't appear?
- Check if document was actually reconciled (check Payment Ledger Entry)
- Verify hooks are properly registered in hooks.py
- Check browser console for JavaScript errors

### "Unlink All Payments" button missing?
- User needs write permission on Payment Entry
- Check frappe.boot.user.can_write array

### Unlink fails with error?
- Check Payment Entry status (must be submitted, not cancelled)
- Verify reference still exists in Payment Entry
- Try manual method (Method 3) instead

---

## 📞 Support

For issues or questions:
1. Check this guide first
2. Review system logs: `frappe.logger()`
3. Contact system administrator
4. Reference implementation in:
   - `/imogi_finance/advance_payment/api.py`
   - `/imogi_finance/public/js/payment_reconciliation_helper.js`
