# Jawaban: Bagaimana Mengaktifkan PPh dari Supplier jika Apply WHT Tidak Dicentang?

## Pertanyaan Anda

> "Semisal Apply WHT-nya tidak dicentang dan di bagian Tab Tax-nya tidak diisi PPh-nya, nanti untuk mengaktifkan PPh ternayata dia pakai PPh dari supplier gimana?"

## Jawaban Singkat

Ada **3 pilihan** untuk mengaktifkan PPh dari supplier:

### ✅ Pilihan 1: EXPLICIT - Ceklist Apply WHT + Isi PPh di ER (RECOMMENDED)

**Setup Expense Request:**
```
Apply WHT: ✅ Ceklist
PPh Type: PPh 23 ← Isi sesuai supplier atau requirement
Base Amount: Rp 300,000 ← Isi jumlah yang akan dikena PPh
```

**Hasil:**
- ✅ PPh otomatis dihitung
- ✅ Clear dan controlled
- ✅ Tidak ada double calculation
- ✅ Audit trail jelas

**Kelebihan:** Explicit, controlled, mudah di-audit

---

### 🟡 Pilihan 2: AUTO-COPY - Enable Setting + Supplier punya Tax Category (BARU)

**Step 1: Enable setting**
```
IMOGI Finance → Settings
Cari field: "Use Supplier's WHT if no ER PPh"
Ceklist untuk enable ✅
```

**Step 2: Setup Supplier**
```
Supplier: PT Makmur
Tax Withholding Category: PPh 23
```

**Step 3: Create ER tanpa Apply WHT**
```
Apply WHT: ❌ TIDAK dicentang
PPh Type: (kosongkan)
Supplier: PT Makmur
```

**Step 4: Create PI**
```
Otomatis menggunakan supplier's PPh 23! ✅
```

**Bagaimana Cara Kerjanya:**
```python
# Di accounting.py, logic baru:

if apply_pph:
    # ER punya Apply WHT → GUNAKAN ER
    pi.tax_withholding_category = request.pph_type
else:
    # ER tidak punya Apply WHT
    if use_supplier_wht_if_no_er_pph_enabled:
        # Auto-copy dari supplier
        supplier_wht = db.get_value("Supplier", supplier, "tax_withholding_category")
        if supplier_wht:
            pi.tax_withholding_category = supplier_wht  # ✅ Pakai supplier's
```

**Kelebihan:**
- ✅ Otomatis, minimal data entry
- ✅ Fallback ke supplier master
- ✅ Still safe (ER priority tetap tertinggi)

**Kekurangan:**
- ⚠️ Implicit (perlu tahu settingnya enable)
- ⚠️ Perlu supplier master selalu updated

---

### 🔴 Pilihan 3: MANUAL DI PI - Edit PI setelah dibuat (WORKAROUND)

**Step 1: Create PI dari ER (tanpa Apply WHT)**
```
Hasil PI: apply_tds = 0 (belum ada PPh)
```

**Step 2: Edit PI manual**
```
Buka PI
Tax Withholding Category: Isi manual = PPh 23
Apply TDS: Check ✅
Save
```

**Kelebihan:**
- ✅ Flexible per transaction
- ✅ Tidak perlu setting

**Kekurangan:**
- ❌ Manual, tidak efisien
- ❌ Mudah lupa
- ❌ Audit trail tidak clear

---

## Perbandingan 3 Pilihan

| Aspek | Pilihan 1: Explicit ER | Pilihan 2: Auto-copy | Pilihan 3: Manual PI |
|-------|------------------------|-------------------|-------------------|
| **Cara Kerja** | Isi Apply WHT + PPh di ER | Enable setting, supplier punya category | Edit PI manual |
| **Data Entry** | Setiap ER harus isi | Minimal (supplier master only) | Setiap PI edit manual |
| **Fleksibilitas** | Tinggi (per ER) | Rendah (tergantung supplier) | Tinggi tapi risky |
| **Audit Trail** | ✅ Clear | ✅ Logged | ❌ Tidak clear |
| **Rekomendasi** | ⭐⭐⭐ TERBAIK | ⭐⭐ BAIK | ⭐ HINDARI |
| **Setup Complexity** | Simple | Medium (butuh enable setting) | None (manual) |

---

## Skenario Penggunaan

### Kapan Gunakan Pilihan 1 (Explicit ER)?

✅ **GUNAKAN JIKA:**
- PPh bisa berbeda untuk supplier yang sama
- Ingin explicit control per transaction
- Audit & compliance adalah prioritas
- Ada edge cases yang perlu manual override

**Contoh:**
```
PT Makmur (supplier sama):
  - ER 1: PPh 23 (jasa konsultasi)
  - ER 2: PPh 2 (barang)
  - ER 3: Tidak ada PPh (exempted)
```

### Kapan Gunakan Pilihan 2 (Auto-copy)?

✅ **GUNAKAN JIKA:**
- Setiap supplier punya PPh yang FIXED
- Ingin minimize data entry
- Supplier master selalu up-to-date
- Tidak ada exception per transaction

**Contoh:**
```
PT Makmur: Always PPh 23
PT Konstruksi: Always PPh 3  
PT Teknis: Always PPh 2
(tidak pernah berubah per transaksi)
```

---

## Step-by-Step Mengaktifkan Pilihan 2 (Auto-copy)

Kalau Anda ingin menggunakan fitur auto-copy:

### 1. Enable Setting
```
Buka: IMOGI Finance → Settings → Expense Request Settings
Cari: "Use Supplier's WHT if no ER PPh"
Action: ✅ Ceklist
Klik: Save
```

### 2. Verify Supplier Master
```
Buka: Buying → Supplier (PT Makmur)
Tab: Buying
Cari: "Tax Withholding Category"
Value: PPh 23 ← Harus di-set
Klik: Save
```

### 3. Test
```
Create Expense Request:
  - Supplier: PT Makmur
  - Apply WHT: ❌ JANGAN dicentang
  - Items: Isikan normal
  - Save & Submit

Create PI dari ER:
  - Check di PI: tax_withholding_category harus terisi "PPh 23"
  - Check: apply_tds harus = 1
  - Check logs untuk "Auto-copy WHT" message
```

### 4. Verify

```
Buka PI, lihat:
✅ tax_withholding_category: PPh 23 (otomatis dari supplier)
✅ apply_tds: 1 (otomatis enabled)
✅ Di taxes table, ada PPh 23 entry
```

---

## Priority Rules (PENTING!)

**Hierarchy untuk determine PPh mana yang digunakan:**

```
PRIORITY 1 (TERTINGGI):
Expense Request dengan Apply WHT ✅
├─ Jika dicentang → SELALU gunakan ER's pph_type
├─ Supplier's category akan DIABAIKAN (prevent double!)
└─ Contoh: ER set PPh 23 + Supplier set PPh 2 = GUNAKAN PPh 23

        ↓

PRIORITY 2 (MENENGAH):
Supplier's Tax Withholding Category (jika enabled auto-copy)
├─ Jika ER tidak set Apply WHT
├─ Dan setting "use_supplier_wht_if_no_er_pph" = 1
├─ Dan supplier punya category
└─ Maka GUNAKAN supplier's category
  
        ↓

PRIORITY 3 (TERENDAH):
No PPh
└─ Jika semua kosong = No PPh di PI
```

---

## Checklist: Mana yang Pilihan Anda?

### Checklist Pilihan 1: Explicit ER

- [ ] Setiap ER akan isi Apply WHT + PPh Type + Base Amount
- [ ] Tim akan trained untuk selalu isi PPh data
- [ ] Audit trail per transaction penting
- [ ] OK dengan data entry overhead

**→ Gunakan Pilihan 1**

### Checklist Pilihan 2: Auto-copy

- [ ] Supplier PPh sudah fixed & tidak berubah
- [ ] Supplier master sudah updated
- [ ] Ingin minimize data entry
- [ ] Enable setting sudah done

**→ Gunakan Pilihan 2**

### Checklist Pilihan 3: Manual PI

- [ ] Tidak ada preference/plan terstruktur
- [ ] Akan edit manual jika terlupakan
- [ ] Okay dengan risky approach

**→ JANGAN gunakan, risky!**

---

## FAQ

### Q: Kalau saya pakai Pilihan 2, apa yang terjadi kalau supplier tidak punya Tax Category?

**A:** Otomatis tidak ada PPh di PI (apply_tds = 0). Tidak ada error.

### Q: Kalau saya pakai Pilihan 1, apa terjadi double calculation?

**A:** **Tidak!** Supplier's category akan di-clear otomatis (fitur prevent double WHT).

### Q: Kalau saya set Apply WHT di ER tapi PPh Type kosong?

**A:** **ERROR** - Sistem akan throw error: "PPh Type is required".

Solusi: Isi PPh Type jika Apply WHT dicentang.

### Q: Kalau saya disable Pilihan 2 nanti?

**A:** Uncheck setting "use_supplier_wht_if_no_er_pph". PI yang sudah dibuat tidak terpengaruh.

### Q: Mana yang lebih baik?

**A:** **Pilihan 1 (Explicit ER)** adalah TERBAIK karena:
- ✅ Clear & explicit
- ✅ Flexible
- ✅ Audit trail jelas
- ✅ Prevent double di automatic

Pilihan 2 adalah optional untuk mengurangi data entry jika supplier PPh fixed.

---

## Dokumentasi Lengkap

Lihat file dokumentasi untuk detail lebih:
- [PPH_SUPPLIER_VS_ER_GUIDE.md](PPH_SUPPLIER_VS_ER_GUIDE.md) - Panduan lengkap scenario
- [SUPPLIER_WHT_AUTO_COPY_FEATURE.md](SUPPLIER_WHT_AUTO_COPY_FEATURE.md) - Detail fitur auto-copy
- [DOUBLE_WHT_PREVENTION_FIX.md](DOUBLE_WHT_PREVENTION_FIX.md) - Cara prevent double PPh
