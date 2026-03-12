# Panduan: Kapan PPh dari Supplier vs Expense Request Digunakan?

## Ringkasan Cepat

| Skenario | Apply WHT di ER | PPh di Tab Tax | Hasil |
|----------|-----------------|-----------------|-------|
| **Skenario A** | ✅ Dicentang | PPh 23 terisi | Gunakan ER → Clear supplier's category |
| **Skenario B** | ❌ TIDAK | KOSONG | Gunakan Supplier's category (jika ada) |
| **Skenario C** | ❌ TIDAK | Terisi | Ambiguitas ⚠️ (lihat penjelasan) |
| **Skenario D** | ✅ Dicentang | KOSONG | Error ❌ (PPh Type wajib jika Apply WHT) |

---

## Detail Setiap Skenario

### 🟢 Skenario A: Apply WHT Dicentang, PPh Terisi (NORMAL - Rekomendasi)

**Setup di Expense Request:**
```
Apply WHT (is_pph_applicable): ✅ Dicentang
PPh Type (pph_type): PPh 23
Base Amount (pph_base_amount): Rp 300,000
```

**Setup di Supplier Master:**
```
Tax Withholding Category: PPh 23
```

**Behavior:**
- ✅ `apply_tds = 1` di PI
- ✅ `tax_withholding_category` di PI = **CLEARED** (jangan pakai supplier's)
- ✅ Gunakan `imogi_pph_type = PPh 23` dari ER
- ✅ **Hasil: Single PPh calculation** (Rp 9,000)

**Penjelasan:**
Ketika Anda explicitly set PPh di Expense Request dengan "Apply WHT" dicentang, sistem akan **menggunakan HANYA PPh dari ER dan mengabaikan supplier's category** untuk mencegah double calculation.

---

### 🟡 Skenario B: Apply WHT TIDAK Dicentang, PPh Kosong (FALLBACK ke Supplier)

**Setup di Expense Request:**
```
Apply WHT (is_pph_applicable): ❌ TIDAK dicentang
PPh Type (pph_type): KOSONG
Base Amount (pph_base_amount): KOSONG
```

**Setup di Supplier Master:**
```
Tax Withholding Category: PPh 23 ← ADA
```

**Behavior:**
```
if not apply_tds and not pph_type:
    # Logic di accounting.py line 293:
    # pi.tax_withholding_category = None  (karena apply_pph=False)
    # pi.apply_tds = 0
```

**Pertanyaan Anda yang Bagus:**
> "Kalau Apply WHT tidak dicentang dan PPh di Tab Tax tidak diisi, bagaimana cara mengaktifkan PPh dari supplier?"

**Jawaban:**
Saat ini, **Purchase Invoice dibuat dengan `tax_withholding_category = None` dan `apply_tds = 0`**, jadi PPh dari supplier **TIDAK akan otomatis digunakan**. 

Ini karena:
1. Di `accounting.py` line 293: `pi.tax_withholding_category = request.pph_type if apply_pph else None`
2. Kalau `apply_pph = False`, maka `tax_withholding_category` = `None`
3. Supplier's category tidak di-copy ke PI

**Untuk mengaktifkan PPh dari supplier jika Apply WHT tidak dicentang:**
Anda harus **MANUAL mengisi PPh di Purchase Invoice** setelah dibuat, atau ubah logika di `accounting.py` untuk auto-copy supplier's category.

---

### 🟠 Skenario C: Apply WHT TIDAK Dicentang, Tapi PPh Terisi (Ambiguitas)

**Setup di Expense Request:**
```
Apply WHT (is_pph_applicable): ❌ TIDAK dicentang (kontradiktif!)
PPh Type (pph_type): PPh 23 ← Tapi terisi
Base Amount (pph_base_amount): Rp 300,000
```

**Behavior (Current):**
Karena di `accounting.py`:
```python
is_pph_applicable = bool(getattr(request, "is_pph_applicable", 0) or pph_items)
# Ini akan FALSE karena is_pph_applicable=0 dan pph_items=[]

apply_pph = is_pph_applicable  # = FALSE
pi.tax_withholding_category = request.pph_type if apply_pph else None  # = None (ignored!)
pi.apply_tds = 1 if apply_pph else 0  # = 0
```

**Hasil:**
- PPh yang terisi di Tab Tax **AKAN DIABAIKAN** (tidak digunakan)
- PI akan dibuat dengan `apply_tds = 0` dan `tax_withholding_category = None`

**Rekomendasi:**
- ❌ Jangan gunakan skenario ini
- ✅ Jika ingin pakai PPh, **HARUS ceklist "Apply WHT"**

---

### 🔴 Skenario D: Apply WHT Dicentang, Tapi PPh Tab Tax Kosong (ERROR)

**Setup di Expense Request:**
```
Apply WHT (is_pph_applicable): ✅ Dicentang
PPh Type (pph_type): KOSONG ← ERROR!
Base Amount (pph_base_amount): KOSONG
```

**Behavior:**
```python
apply_pph = True  # karena is_pph_applicable = 1

if apply_pph:
    pph_type = getattr(request, "pph_type", None)  # = None
    if not pph_type:
        frappe.throw(
            _("PPh Type is required in Expense Request...")
        )  # ← THROW ERROR
```

**Hasil:**
- ❌ **ERROR** - Purchase Invoice tidak bisa dibuat
- Pesan: "PPh Type is required in Expense Request XYZ before creating Purchase Invoice"

**Solusi:**
- ✅ Isi "PPh Type" di Expense Request sebelum membuat PI

---

## Solusi: Bagaimana Mengaktifkan PPh dari Supplier?

### Opsi 1: Manual di Expense Request (Recommended)

Kalau Anda ingin supplier's PPh digunakan:
1. ✅ Ceklist "Apply WHT" di Expense Request
2. ✅ Pilih "PPh Type" = sama dengan Supplier's category
3. ✅ Isi "Base Amount" (bisa equal dengan item amount atau custom)
4. ✅ Buat PI → Otomatis gunakan PPh dari ER

**Keuntungan:**
- ✅ Explicit & controlled (tahu persis berapa PPh yang akan dihitung)
- ✅ Per-ER configuration (setiap ER bisa punya PPh berbeda)
- ✅ Tidak bergantung pada supplier master

### Opsi 2: Auto-copy dari Supplier (Modifikasi Diperlukan)

Jika Anda ingin **otomatis mengambil PPh dari supplier** ketika Apply WHT tidak dicentang, sekarang sudah ada feature built-in untuk ini!

**Fitur: Auto-copy Supplier's WHT**

**Cara mengaktifkan:**
1. Buka **IMOGI Finance → Settings**
2. Cari field: `Use Supplier's WHT if no ER PPh`
3. Ceklist untuk enable
4. Save

**Setelah enabled:**

```python
# Logika baru di accounting.py:
if apply_pph:
    # ER has Apply WHT - GUNAKAN ER (prevent double)
    pi.tax_withholding_category = request.pph_type
else:
    # ER tidak set Apply WHT
    if use_supplier_wht_if_no_er_pph_enabled:
        # Auto-copy supplier's category
        supplier_category = frappe.db.get_value("Supplier", supplier, "tax_withholding_category")
        if supplier_category:
            pi.tax_withholding_category = supplier_category  # ✅ Gunakan supplier's
            pi.apply_tds = 1
```

**Keuntungan:**
- ✅ Otomatis menggunakan supplier's PPh
- ✅ Minimize data entry
- ✅ Still safe (ER's Apply WHT tetap priority)

**Kekurangan:**
- ⚠️ Implicit behavior (sulit debug jika ada issue)
- ⚠️ Bergantung pada supplier master

**Lihat detail:** [Supplier WHT Auto-copy Feature](SUPPLIER_WHT_AUTO_COPY_FEATURE.md)

---

## Rekomendasi Best Practice

### ✅ Best Practice

**Untuk setiap Expense Request yang akan jadi Purchase Invoice:**

1. **Jika item memerlukan PPh:**
   ```
   ✅ Ceklist "Apply WHT"
   ✅ Isi "PPh Type" (sesuai supplier atau requirement)
   ✅ Isi "Base Amount"
   ```

2. **Jika item TIDAK memerlukan PPh:**
   ```
   ❌ Jangan ceklist "Apply WHT"
   ❌ Kosongkan "PPh Type"
   ❌ Kosongkan "Base Amount"
   ```

3. **Jangan gunakan Supplier's category secara implicit:**
   - Master supplier's category hanya sebagai reference
   - Selalu explicit di setiap ER yang membutuhkan PPh

### ✅ Update Dokumentasi UI

Rekomendasi untuk menambah guidance di Expense Request form:

**Di field "Apply WHT":**
```
Help Text: "Ceklist ini untuk mengaktifkan Withholding Tax (PPh). 
Jika dicentang, HARUS diisi PPh Type dan Base Amount. 
Supplier's Tax Withholding Category akan diabaikan untuk mencegah double calculation."
```

**Di field "PPh Type":**
```
Help Text: "Pilih kategori pajak yang dikenakan. 
Requirement: Wajib diisi jika 'Apply WHT' dicentang."
```

---

## Summary Tabel Teknis

| Kondisi | `apply_tds` | `tax_withholding_category` | Hasil |
|---------|------------|--------------------------|-------|
| Apply WHT ✅ + PPh ✅ | 1 | `pph_type` dari ER | ✅ Pakai ER |
| Apply WHT ✅ + PPh ❌ | (error) | - | ❌ ERROR |
| Apply WHT ❌ + PPh ❌ | 0 | `None` | ❌ Tidak ada PPh |
| Apply WHT ❌ + PPh ✅ | 0 | `None` (ignored) | ❌ PPh diabaikan |
| Supplier Category ✅ | - | - | Tidak digunakan (jika dari ER) |

---

## Implementation Note untuk User

**Pertanyaan Anda:**
> "Kalau Apply WHT tidak dicentang dan PPh di Tab Tax tidak diisi, bagaimana cara mengaktifkan PPh dari supplier?"

**Jawaban Teknis:**
Saat ini sistem **TIDAK otomatis mengambil supplier's category**. Untuk menggunakan supplier's PPh, Anda harus:

**Pilihan 1 (Current):** Manual di PI setelah dibuat
```
1. Buat PI dari ER
2. Di PI, isi manual "Tax Withholding Category" = Supplier's category
```

**Pilihan 2 (Rekomendasi):** Explicit di ER
```
1. Di ER, ceklist "Apply WHT"
2. Isi "PPh Type" = Supplier's category
3. Buat PI → Otomatis terkalkulasi
```

**Pilihan 3 (Kalau perlu auto-copy):** Perlu custom development
- Modifikasi `accounting.py` untuk auto-copy supplier's category
- Tapi ini menambah complexity dan potensial bug

Saya rekomendasikan **Pilihan 2** (Explicit di ER) karena:
- ✅ Lebih clear dan controlled
- ✅ Sesuai dengan design saat ini
- ✅ Mudah di-audit
- ✅ Fleksibel per-transaction
