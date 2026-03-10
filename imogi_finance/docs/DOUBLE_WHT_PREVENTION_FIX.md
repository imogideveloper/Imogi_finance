# Fix: Double WHT Prevention when Apply WHT is Set in Expense Request

## Problem

Ketika "Apply WHT" (Withholding Tax) dicentang di Expense Request dengan template WHT yang sudah dikonfigurasi, terjadi **double calculation PPh (WithHolding Tax)** di Purchase Invoice:

1. **PPh dari Supplier**: PT Makmur memiliki `Tax Withholding Category: PPh 23` yang ditetapkan di supplier master
2. **PPh dari Apply WHT**: Expense Request memiliki `Apply WHT` dicentang dengan `PPh Type: PPh 23` dan `Base Amount: Rp 300,000.00`
3. **Hasil**: Keduanya ter-kalkulasi di Purchase Invoice, menyebabkan double PPh

### Contoh Kasus
- **Expense Request**: Apply WHT ✓, PPh Type = PPh 23, Base = Rp 300,000
- **Supplier**: Tax Withholding Category = PPh 23
- **Purchase Invoice**: PPh dihitung 2x
  - Dari supplier category
  - Dari Apply WHT
  - **Total = Double!**

## Root Cause

ERPNext's default behavior untuk Purchase Invoice:
1. Ketika `supplier` field diisi, ERPNext otomatis membaca `Tax Withholding Category` dari supplier master
2. Ini terjadi melalui Frappe's standard field behavior atau TDS (Tax Deducted at Source) controller
3. Bahkan jika `pph_type` sudah ditetapkan dari ER, supplier's category akan override atau ditambahkan
4. Hasilnya: **Double WHT calculation**

## Solution

Tambahkan logic untuk **prevent supplier's tax withholding category** ketika Apply WHT sudah di-set secara explicit dari Expense Request:

### Files Modified

#### 1. `/imogi_finance/events/purchase_invoice.py`

**Tambah function baru:**
```python
def prevent_double_wht_validate(doc, method=None):
    """Prevent double WHT on validate hook - called before other validations.
    
    When a Purchase Invoice is created from an Expense Request with Apply WHT,
    we need to clear the supplier's tax withholding category early to prevent
    Frappe from auto-populating it and causing double calculations.
    """
    _prevent_double_wht(doc)


def _prevent_double_wht(doc):
    """Prevent double WHT calculation when Apply WHT is set from Expense Request.
    
    When a Purchase Invoice is created from an Expense Request with Apply WHT (apply_tds=1),
    we should NOT use the supplier's tax withholding category because it will cause double
    WHT calculation - once from the supplier's category and once from the explicit pph_type.
    
    This function clears the tax_withholding_category if:
    1. PI is linked to an Expense Request (imogi_expense_request is set)
    2. Apply TDS is enabled (apply_tds = 1)
    3. PPh Type is explicitly set from ER (imogi_pph_type is set)
    """
    expense_request = doc.get("imogi_expense_request")
    apply_tds = cint(doc.get("apply_tds", 0))
    pph_type = doc.get("imogi_pph_type")
    supplier_tax_category = doc.get("tax_withholding_category")
    
    # Only apply logic to PI created from ER with explicit Apply WHT
    if expense_request and apply_tds and pph_type:
        # If supplier's tax category is set, it will cause double calculation
        # Clear it to use only the explicit pph_type from ER
        if supplier_tax_category:
            frappe.logger().info(
                f"[WHT Prevention] PI {doc.name}: Clearing supplier's tax_withholding_category "
                f"'{supplier_tax_category}' to prevent double WHT. Using pph_type '{pph_type}' from ER instead."
            )
            doc.tax_withholding_category = None
            
            # Log this action for audit
            frappe.msgprint(
                _("WHT Configuration: Using PPh Type '{0}' from Expense Request. "
                  "Supplier's Tax Withholding Category was cleared to prevent double calculation.").format(pph_type),
                indicator="blue",
                alert=False
            )
```

**Update `validate_before_submit`:**
```python
def validate_before_submit(doc, method=None):
    # Prevent double WHT: clear supplier's tax category if Apply WHT already set from ER
    _prevent_double_wht(doc)
    
    # Sync OCR fields but don't save - document will be saved automatically after this hook
    sync_tax_invoice_upload(doc, "Purchase Invoice", save=False)
    validate_tax_invoice_upload_link(doc, "Purchase Invoice")
    
    # Validate NPWP match between OCR and Supplier
    _validate_npwp_match(doc)
    # ... rest of function
```

#### 2. `/imogi_finance/hooks.py`

**Update Purchase Invoice validate hook:**
```python
"Purchase Invoice": {
    "validate": [
        "imogi_finance.events.purchase_invoice.prevent_double_wht_validate",  # Add this
        "imogi_finance.tax_operations.validate_tax_period_lock",
        "imogi_finance.validators.finance_validator.validate_document_tax_fields",
        "imogi_finance.advance_payment.api.on_reference_update",
    ],
    # ... rest of hooks
},
```

## How It Works

### Flow

1. **Validate Hook** (earliest):
   - Function: `prevent_double_wht_validate()` dipanggil
   - Action: Clear `tax_withholding_category` jika Apply WHT dari ER sudah ditetapkan
   - Purpose: Prevent Frappe from auto-reading supplier's category

2. **Before Submit Hook**:
   - Function: `_prevent_double_wht()` dipanggil lagi
   - Action: Double-check dan clear supplier category jika masih ada
   - Purpose: Safeguard sebelum PI di-submit

3. **Tax Calculation**:
   - Hanya menggunakan `pph_type` dari Expense Request
   - Supplier's category diabaikan
   - Result: **NO DOUBLE WHT**

### Configuration Hierarchy

**Priority**: Expense Request (Apply WHT) > Supplier's Tax Category

```
Purchase Invoice Created from ER:
  ├─ If Apply WHT ✓ in ER:
  │  ├─ Use: pph_type from ER
  │  └─ Clear: supplier's tax_withholding_category (to prevent double)
  └─ If Apply WHT ✗ in ER:
     └─ Use: supplier's tax_withholding_category (standard behavior)
```

## Testing

Run test script:
```bash
bench --site [site-name] execute imogi_finance.test_double_wht_prevention.test_double_wht_prevention
```

**Test akan verify:**
- ✅ `tax_withholding_category` is cleared when Apply WHT is set
- ✅ Only ONE PPh entry exists (no double)
- ✅ `apply_tds` is set correctly
- ✅ `imogi_pph_type` matches ER's pph_type

## Behavior After Fix

### Before Fix
```
Expense Request:
  - Apply WHT: ✓ PPh 23, Base = Rp 300,000

Supplier:
  - Tax Withholding Category: PPh 23

Purchase Invoice:
  - PPh 23 from ER: Rp 9,000 (Rp 300,000 × 3%)
  - PPh 23 from Supplier: Rp 9,000 (calculated again!)
  - ❌ TOTAL PPh: Rp 18,000 (DOUBLE!)
```

### After Fix
```
Expense Request:
  - Apply WHT: ✓ PPh 23, Base = Rp 300,000

Supplier:
  - Tax Withholding Category: PPh 23

Purchase Invoice:
  - tax_withholding_category: [CLEARED - to prevent supplier auto-calc]
  - apply_tds: 1 (from ER)
  - imogi_pph_type: PPh 23 (from ER)
  - PPh 23 calculation: Rp 9,000 (Rp 300,000 × 3%)
  - ✅ TOTAL PPh: Rp 9,000 (CORRECT - NO DOUBLE!)
```

## Impact

- ✅ **Fixes**: Double WHT calculation issue
- ✅ **Maintains**: Apply WHT functionality from ER
- ✅ **Simplifies**: Tax configuration (ER takes priority)
- ✅ **Auditable**: Logs action in system logs and shows message to user
- ✅ **Non-breaking**: Only affects PI from ER with Apply WHT enabled

## Notes

- Logic hanya berlaku untuk PI yang dibuat dari Expense Request (`imogi_expense_request` is set)
- Supplier's Tax Withholding Category masih bisa digunakan untuk PI yang dibuat manual (tanpa ER)
- Solusi diterapkan di **2 hooks** (validate + before_submit) untuk extra safety
- User akan melihat notifikasi bahwa supplier's category dihapus untuk Apply WHT
