# Fix: PPN & PPh Conflict in Expense Request

## 🔴 Masalah yang Ditemukan

Ketika user mengonfigurasi **PPN dan PPh secara bersamaan** di Expense Request, terjadi **konflik validasi** yang membingungkan:

### Scenario Masalah:

1. User centang **PPN Applicable** ✅
2. User pilih **PPN Template** ✅  
3. User centang **Apply WHT di salah satu item** ✅
4. User **LUPA** pilih PPh Type di header ❌

**Hasil:**
```
Error: "Please select a PPh Type when PPh is applicable."
```

**Problem:** User bingung karena:
- Fokus ke konfigurasi PPN, tapi error PPh muncul duluan
- Error message tidak jelas mana yang kurang (PPN atau PPh)
- Tidak bisa save meskipun PPN sudah benar

### Root Cause:

File: `imogi_finance/validators/finance_validator.py`

**Kode Lama:**
```python
def validate_tax_fields(doc):
    # Validasi PPN
    if is_ppn_applicable and not ppn_template:
        throw("Please select PPN Template")  # ❌ Langsung throw
    
    # Validasi PPh
    if is_pph_applicable and not pph_type:
        throw("Please select PPh Type")  # ❌ Langsung throw
```

**Masalah:**
- Setiap error langsung throw exception
- User hanya lihat error pertama, tidak tahu ada error lain
- Harus fix satu-satu, baru bisa lihat error berikutnya

---

## ✅ Solusi yang Diimplementasikan

### 1. **Collect All Errors First**

Kumpulkan semua error validasi dulu, baru throw di akhir dengan semua error sekaligus.

### 2. **Categorize Errors by Tax Type**

Pisahkan error PPN dan PPh untuk clarity:

```python
def validate_tax_fields(doc):
    errors = []
    
    # ============================================================================
    # Validate PPN Configuration
    # ============================================================================
    if is_ppn_applicable and not ppn_template:
        errors.append("PPN is applicable but PPN Template is not selected...")
    
    # ============================================================================
    # Validate PPh Configuration
    # ============================================================================
    if item_pph_applicable or header_pph_applicable:
        if not pph_type:
            if item_pph_applicable and not header_pph_applicable:
                errors.append("Found X item(s) with 'Apply WHT' checked but PPh Type is not selected...")
            else:
                errors.append("PPh is applicable but PPh Type is not selected...")
        
        # Validate PPh Base Amount
        if header_pph_applicable and not item_pph_applicable:
            if not pph_base_amount or pph_base_amount <= 0:
                errors.append("PPh is applicable at header level but PPh Base Amount is not entered...")
        
        # Validate item-level PPh
        for item in item_pph_applicable:
            if not item.pph_base_amount or item.pph_base_amount <= 0:
                errors.append(f"PPh is applicable for {item_desc} but PPh Base Amount is not entered...")
    
    # ============================================================================
    # Show All Errors at Once (Better UX)
    # ============================================================================
    if errors:
        # Separate PPN and PPh errors for clarity
        ppn_errors = [e for e in errors if "PPN" in str(e)]
        pph_errors = [e for e in errors if "PPh" in str(e)]
        
        error_msg = []
        if ppn_errors:
            error_msg.append("<b>PPN Configuration Issues:</b>")
            error_msg.extend([f"• {e}" for e in ppn_errors])
        
        if pph_errors:
            if ppn_errors:
                error_msg.append("<br>")
            error_msg.append("<b>PPh Configuration Issues:</b>")
            error_msg.extend([f"• {e}" for e in pph_errors])
        
        throw("<br>".join(error_msg))
```

### 3. **Improved Error Messages**

**Before:**
```
Please select a PPh Type when PPh is applicable.
```

**After:**
```
PPN Configuration Issues:
• PPN is applicable but PPN Template is not selected. Please select a PPN Template in Tab Tax.

PPh Configuration Issues:
• Found 2 item(s) with 'Apply WHT' checked but PPh Type is not selected. Please select PPh Type in Tab Tax.
• PPh is applicable for Row 1 but PPh Base Amount is not entered. Please enter PPh Base Amount.
```

---

## 📊 Benefits

### 1. **Better User Experience**
- User melihat **semua error sekaligus**, tidak perlu fix satu-satu
- Error message **lebih jelas** dan spesifik
- **Kategorisasi** PPN vs PPh memudahkan troubleshooting

### 2. **Clear Guidance**
- Setiap error message memberitahu **dimana letak masalahnya**
- **Action yang harus dilakukan** dijelaskan dengan jelas
- Mendukung **item-level dan header-level** PPh configuration

### 3. **No More Conflicts**
- PPN dan PPh validation **tidak saling ganggu**
- User bisa configure keduanya **secara independen**
- Error tidak blocking konfigurasi tax lainnya

---

## 🧪 Test Cases

### Case 1: Only PPN - Correct Config ✅
```python
{
    "is_ppn_applicable": 1,
    "ppn_template": "ID - PPN 11% Input",
    "is_pph_applicable": 0,
}
```
**Result:** PASS - No errors

### Case 2: Only PPh - Correct Config ✅
```python
{
    "is_pph_applicable": 1,
    "pph_type": "PPh 23 - 2%",
    "pph_base_amount": 1000000,
}
```
**Result:** PASS - No errors

### Case 3: Both PPN & PPh - Correct Config ✅
```python
{
    "is_ppn_applicable": 1,
    "ppn_template": "ID - PPN 11% Input",
    "is_pph_applicable": 1,
    "pph_type": "PPh 23 - 2%",
    "pph_base_amount": 1000000,
}
```
**Result:** PASS - No errors

### Case 4: PPN Applicable but No Template ❌
```python
{
    "is_ppn_applicable": 1,
    "ppn_template": None,
}
```
**Result:** FAIL with error:
```
PPN Configuration Issues:
• PPN is applicable but PPN Template is not selected. Please select a PPN Template in Tab Tax.
```

### Case 5: PPh Applicable but No Type ❌
```python
{
    "is_pph_applicable": 1,
    "pph_type": None,
    "pph_base_amount": 1000000,
}
```
**Result:** FAIL with error:
```
PPh Configuration Issues:
• PPh is applicable but PPh Type is not selected. Please select a PPh Type in Tab Tax.
```

### Case 6: Both Applicable but Missing Configs ❌
```python
{
    "is_ppn_applicable": 1,
    "ppn_template": None,
    "is_pph_applicable": 1,
    "pph_type": None,
}
```
**Result:** FAIL with error:
```
PPN Configuration Issues:
• PPN is applicable but PPN Template is not selected. Please select a PPN Template in Tab Tax.

PPh Configuration Issues:
• PPh is applicable but PPh Type is not selected. Please select a PPh Type in Tab Tax.
• PPh is applicable at header level but PPh Base Amount is not entered. Please enter PPh Base Amount in Tab Tax.
```

### Case 7: Item-level PPh but No Header Type ❌
```python
{
    "is_ppn_applicable": 0,
    "is_pph_applicable": 0,
    "pph_type": None,
    "items": [
        {"is_pph_applicable": 1, "pph_base_amount": 0}
    ]
}
```
**Result:** FAIL with error:
```
PPh Configuration Issues:
• Found 1 item(s) with 'Apply WHT' checked but PPh Type is not selected. Please select PPh Type in Tab Tax.
• PPh is applicable for Row 1 but PPh Base Amount is not entered. Please enter PPh Base Amount.
```

---

## 📝 Implementation Details

### Files Modified:

1. **`imogi_finance/validators/finance_validator.py`**
   - Method: `validate_tax_fields()`
   - Changed: Error collection and categorization logic
   - Lines: ~60-120

### Backward Compatibility:

✅ **Fully backward compatible**
- No changes to field names or data structure
- No changes to API signatures
- Only improved error messages and validation flow
- Existing documents will continue to work

### Migration Required:

❌ **No migration needed**
- Pure logic improvement
- No database changes
- No field additions/removals

---

## 🎯 Key Improvements Summary

| Aspect | Before | After |
|--------|--------|-------|
| Error Display | One at a time | All errors at once |
| Error Clarity | Generic message | Specific with location |
| PPN/PPh Conflict | Blocks each other | Independent validation |
| User Experience | Frustrating (trial & error) | Clear guidance |
| Debug Time | High (multiple saves) | Low (see all issues) |

---

## 🚀 Next Steps

### For Users:
1. Update to latest version
2. Configure PPN and PPh as usual
3. Enjoy clearer error messages

### For Developers:
1. Review validation logic in `finance_validator.py`
2. Test with various PPN/PPh configurations
3. Monitor user feedback on error messages

---

## 📞 Support

Jika masih ada konflik atau error yang tidak jelas:

1. Check **Tab Tax** di Expense Request
2. Pastikan **PPN Template** dipilih jika PPN Applicable
3. Pastikan **PPh Type** dipilih jika ada item dengan Apply WHT
4. Pastikan **PPh Base Amount** diisi untuk setiap item dengan Apply WHT

---

**Last Updated:** January 21, 2026  
**Version:** 1.0.0  
**Status:** ✅ Implemented & Ready
