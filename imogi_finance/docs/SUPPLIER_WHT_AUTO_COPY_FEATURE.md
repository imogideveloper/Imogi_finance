# Fitur: Auto-copy Supplier's WHT Category

## Penjelasan Singkat

Jika Anda ingin **otomatis menggunakan PPh dari Supplier** ketika Apply WHT TIDAK dicentang di Expense Request, ada opsi baru untuk mengaktifkan behavior ini.

## Bagaimana Menggunakannya?

### Step 1: Enable Setting di IMOGI Finance Settings

Buka **IMOGI Finance → Settings → Expense Request Settings**

Cari field:
```
Use Supplier's WHT if no ER PPh
```

Jika field tidak ada, hubungi admin untuk menambahkannya. Atau buat via API:

```python
frappe.db.set_value("IMOGI Finance Settings", None, "use_supplier_wht_if_no_er_pph", 1)
```

### Step 2: Set Supplier's Tax Withholding Category

Di Supplier Master (misalnya PT Makmur):
```
Buying Tab → Tax Withholding Category: PPh 23
```

### Step 3: Create Expense Request TANPA Apply WHT

```
Apply WHT: ❌ TIDAK dicentang
PPh Type: (kosongkan)
Base Amount: (kosongkan)
Supplier: PT Makmur
```

### Step 4: Create Purchase Invoice

Otomatis akan menggunakan supplier's Tax Withholding Category (PPh 23).

## Behavior Perbandingan

### Default (use_supplier_wht_if_no_er_pph = 0 atau tidak dienable)

```
Expense Request:
  - Apply WHT: ❌ TIDAK
  - Supplier: PT Makmur (Tax Category: PPh 23)

Purchase Invoice:
  - tax_withholding_category: NONE
  - apply_tds: 0
  - PPh: ❌ TIDAK dihitung
```

### Dengan Feature Enabled (use_supplier_wht_if_no_er_pph = 1)

```
Expense Request:
  - Apply WHT: ❌ TIDAK
  - Supplier: PT Makmur (Tax Category: PPh 23)

Purchase Invoice:
  - tax_withholding_category: PPh 23 ✅ (auto-copied)
  - apply_tds: 1
  - PPh: ✅ Otomatis dihitung dari supplier
```

## Priority Rules (Hierarchy)

```
1. Expense Request Apply WHT (HIGHEST PRIORITY)
   ↓ Jika Apply WHT dicentang, gunakan ER's pph_type
   ↓ Supplier's category akan diabaikan (prevent double)

2. Supplier's Tax Withholding Category (jika enabled)
   ↓ Jika ER tidak set Apply WHT
   ↓ Dan setting "use_supplier_wht_if_no_er_pph" = 1
   ↓ Auto-copy supplier's category

3. No PPh (LOWEST PRIORITY)
   ↓ Jika keduanya tidak ada
```

## Kapan Menggunakan Feature Ini?

### ✅ GUNAKAN feature ini jika:

- Semua supplier punya Tax Withholding Category yang sudah fixed
- Ingin minimize data entry (jangan perlu input PPh di setiap ER)
- Supplier's PPh calculation sudah pasti sesuai requirement

**Contoh Use Case:**
```
PT Makanan Bersama → Always PPh 23
PT Konstruksi → Always PPh 3
PT Teknis → Always PPh 2
```

### ❌ JANGAN GUNAKAN jika:

- PPh bisa berbeda per transaction (even untuk supplier yang sama)
- Ingin explicit control setiap transaction
- Ada edge cases yang perlu manual override

**Contoh Use Case:**
```
Supplier sama (PT Makmur) tapi:
  - Transaksi 1: PPh 23 (services)
  - Transaksi 2: PPh 2 (goods)
  - Transaksi 3: Tidak ada PPh (exempted)
```

## Technical Details

### Setting Configuration

Field name: `use_supplier_wht_if_no_er_pph`

**Type:** Check (Boolean)

**Location:** IMOGI Finance Settings

**Default:** 0 (Disabled)

### Code Logic

File: `imogi_finance/accounting.py` (line 288-318)

```python
if apply_pph:
    # ER has explicit Apply WHT set - ALWAYS USE ER
    pi.tax_withholding_category = request.pph_type
    pi.apply_tds = 1
else:
    # ER doesn't have Apply WHT - check setting
    settings = get_settings() if callable(get_settings) else {}
    use_supplier_wht = cint(settings.get("use_supplier_wht_if_no_er_pph", 0))
    
    if use_supplier_wht:
        # AUTO-COPY supplier's category
        supplier_wht = frappe.db.get_value("Supplier", request.supplier, "tax_withholding_category")
        if supplier_wht:
            pi.tax_withholding_category = supplier_wht
            pi.apply_tds = 1
            # Log action
        else:
            pi.apply_tds = 0
    else:
        # DEFAULT: Don't use supplier's category
        pi.apply_tds = 0
```

### Logging

Ketika auto-copy terjadi, akan di-log:

```
[Auto-copy WHT] PI ACC-PINV-2026-00001: Using supplier's Tax Withholding Category 'PPh 23' 
because Apply WHT not set in ER and auto-copy is enabled
```

## Frequently Asked Questions

### Q: Kalau supplier tidak punya Tax Withholding Category?

**A:** Otomatis tidak ada PPh di PI (apply_tds = 0). Tidak error.

### Q: Kalau Apply WHT di ER dan Supplier juga punya category?

**A:** Always gunakan ER's pph_type. Supplier's category akan diabaikan untuk prevent double.

### Q: Apakah ini mempengaruhi PI yang dibuat manual (tidak dari ER)?

**A:** Tidak. Feature ini hanya berlaku untuk PI yang dibuat dari ER via `create_purchase_invoice_from_request()`.

### Q: Bagaimana jika saya mau disable ini nanti?

**A:** Cukup uncheck field "use_supplier_wht_if_no_er_pph" di settings. PI yang sudah dibuat tidak terpengaruh.

---

## Setup Checklist

- [ ] Enable setting: `use_supplier_wht_if_no_er_pph` = 1
- [ ] Ensure semua supplier memiliki Tax Withholding Category yang correct
- [ ] Test dengan sample ER tanpa Apply WHT
- [ ] Verify PI dibuat dengan supplier's category
- [ ] Check logs untuk audit trail

---

## Related Settings

Lihat juga field yang related:
- `IMOGI Finance → Settings → Expense Request Settings → use_supplier_wht_if_no_er_pph` (NEW)
- `Purchase Invoice → apply_tds` (standard Frappe field)
- `Purchase Invoice → tax_withholding_category` (standard Frappe field)
- `Supplier → tax_withholding_category` (standard Frappe field)
