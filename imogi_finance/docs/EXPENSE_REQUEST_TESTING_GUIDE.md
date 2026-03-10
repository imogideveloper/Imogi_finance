# 📋 Expense Request Testing Guide

Dokumentasi lengkap untuk testing module **Expense Request** - mencakup semua skenario flow normal dan back flow (Cancel).

---

## 📑 Daftar Isi

1. [Prerequisites](#prerequisites)
2. [Test Data Setup](#test-data-setup)
3. [Flow Normal (Happy Path)](#flow-normal-happy-path)
4. [Flow Approval Multi-Level](#flow-approval-multi-level)
5. [Flow Rejection & Reopen](#flow-rejection--reopen)
6. [Flow Cancel (Back Flow)](#flow-cancel-back-flow)
7. [Tax Scenarios](#tax-scenarios)
8. [OCR Validation Scenarios](#ocr-validation-scenarios)
9. [Budget Control Testing](#budget-control-testing)
10. [Edge Cases & Error Handling](#edge-cases--error-handling)
11. [Internal Charge Testing](#internal-charge-testing)
12. [Deferred Expense Testing](#deferred-expense-testing)
13. [Multiple Items & Accounts Testing](#multiple-items--accounts-testing)
14. [Branch & Cost Allocation Testing](#branch--cost-allocation-testing)
15. [UI Actions Testing](#ui-actions-testing)
16. [Print Format Testing](#print-format-testing)
17. [PPnBM Testing](#ppnbm-testing-luxury-goods-tax)
18. [Data Integrity Testing](#data-integrity-testing)
19. [Attachment & Notes Testing](#attachment--notes-testing)
20. [Checklist Testing](#checklist-testing)
21. [Troubleshooting](#troubleshooting)
22. [Error Messages Reference](#-error-messages-reference)
23. [Error Message Testing Checklist](#-error-message-testing-checklist)

---

## Prerequisites

### Master Data yang Diperlukan

| Data | Deskripsi | Contoh |
|------|-----------|--------|
| **Company** | Perusahaan aktif | PT Test Company |
| **Supplier** | Vendor dengan NPWP | Supplier Test (NPWP: 01.234.567.8-901.000) |
| **Cost Center** | Pusat biaya | HO - Head Office |
| **Expense Account** | Akun biaya | 6100 - Biaya Operasional |
| **User Approvers** | User dengan role Expense Approver | approver1@test.com, approver2@test.com |
| **Expense Approval Setting** | Konfigurasi approval route | Per Cost Center |

### Konfigurasi Workflow

Pastikan workflow `Expense Request Workflow` aktif dengan states:
- Draft → Pending Review → Approved → PI Created → Paid
- Transitions: Submit, Approve, Reject

---

## Test Data Setup

### A. Setup Expense Approval Setting

```
1. Buka: Expense Approval Setting
2. Buat baru untuk Cost Center yang akan ditest
3. Set approvers:
   - Level 1: approver1@test.com (Amount: 0 - 5,000,000)
   - Level 2: approver2@test.com (Amount: 5,000,001 - 50,000,000)
   - Level 3: approver3@test.com (Amount: > 50,000,000)
```

### B. Setup Budget Control (Optional)

```
1. Buka: Budget Control Settings
2. Enable Budget Control: ✓
3. Set action on budget exceed: Stop / Warn
```

### C. Setup Tax Invoice OCR

#### 1. Prerequisites
- Tax Invoice OCR module terinstall dan aktif
- OCR service (e.g., Google Vision API, Tesseract) terkonfigurasi
- User memiliki permission untuk upload dan process tax invoices

#### 2. Tax Settings Configuration

**Path:** `Setup > Imogi Finance > Tax Settings`

| Setting | Value | Keterangan |
|---------|-------|------------|
| **Enable Tax Invoice OCR** | ✓ | Aktifkan fitur OCR |
| **DPP Variance Tolerance** | 2.0 | Toleransi selisih DPP (%) |
| **PPN Variance Tolerance** | 5.0 | Toleransi selisih PPN (%) |
| **Auto-Validate on Submit** | ✓ | Validasi otomatis saat submit ER |
| **Require NPWP Match** | ✓ | Wajib NPWP supplier sama dengan OCR |

#### 3. Supplier Master Setup

Pastikan supplier memiliki NPWP yang valid:

```
Supplier: PT ABC Vendor
NPWP: 01.234.567.8-901.000
Format: XX.XXX.XXX.X-XXX.XXX (15 digit dengan separator)
```

**Catatan Penting:**
- NPWP harus dalam format Indonesia yang benar
- OCR akan membaca NPWP dari faktur pajak dan compare dengan supplier NPWP
- Jika tidak match, submit akan error kecuali bypass validation

#### 4. Test Tax Invoice Files

Siapkan sample faktur pajak untuk testing:

| File | NPWP | DPP | PPN (11%) | Total | Keterangan |
|------|------|-----|-----------|-------|------------|
| `faktur_match.pdf` | 01.234.567.8-901.000 | 10,000,000 | 1,100,000 | 11,100,000 | NPWP match, perfect values |
| `faktur_dpp_variance.pdf` | 01.234.567.8-901.000 | 10,100,000 | 1,111,000 | 11,211,000 | DPP variance 1% (within tolerance) |
| `faktur_dpp_exceed.pdf` | 01.234.567.8-901.000 | 10,500,000 | 1,155,000 | 11,655,000 | DPP variance 5% (exceed tolerance) |
| `faktur_npwp_mismatch.pdf` | 99.888.777.6-543.000 | 10,000,000 | 1,100,000 | 11,100,000 | NPWP berbeda dari supplier |
| `faktur_ppn_1pct.pdf` | 01.234.567.8-901.000 | 10,000,000 | 100,000 | 10,100,000 | PPN 1% (non-standard, skip validation) |

#### 5. OCR Fields Mapping

Tax Invoice OCR akan populate fields berikut di Expense Request:

| ER Field | OCR Source | Validasi |
|----------|------------|----------|
| `ti_fp_no` | Nomor Faktur Pajak | Required |
| `ti_fp_date` | Tanggal Faktur | Required |
| `ti_fp_npwp` | NPWP dari Faktur | Match dengan Supplier NPWP |
| `ti_fp_dpp` | Dasar Pengenaan Pajak | Variance check ±2% |
| `ti_fp_ppn` | PPN Amount | Variance check ±5% |
| `ti_npwp_match` | Auto-set flag | 1 if NPWP match, 0 otherwise |

#### 6. Tolerance Calculation Examples

**DPP Variance (2% tolerance):**
```
ER Amount (before tax): 10,000,000
OCR DPP: 10,200,000
Variance: (10,200,000 - 10,000,000) / 10,000,000 = 2%
Result: ✅ PASS (exactly at tolerance)

OCR DPP: 10,300,000
Variance: 3%
Result: ❌ FAIL (exceed tolerance)
```

**PPN Variance (5% tolerance):**
```
ER PPN: 1,100,000
OCR PPN: 1,150,000
Variance: (1,150,000 - 1,100,000) / 1,100,000 = 4.5%
Result: ✅ PASS (within tolerance)

OCR PPN: 1,200,000
Variance: 9%
Result: ❌ FAIL (exceed tolerance)
```

#### 7. Non-Standard PPN Rates (Skip Validation)

PPN rates berikut akan **skip variance validation**:
- 1% (PP 23/2018 - UMKM)
- 2.5% (Reduced rate)
- Other non-11% rates

#### 8. Common Setup Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| OCR fields tidak populate | OCR service tidak aktif | Check API credentials, restart OCR service |
| NPWP always mismatch | Format NPWP salah | Pastikan format XX.XXX.XXX.X-XXX.XXX (dengan dots) |
| Variance selalu error | Tolerance terlalu ketat | Adjust tolerance di Tax Settings (2% DPP, 5% PPN recommended) |
| Cannot upload PDF | File size terlalu besar | Max 10MB per file, compress PDF |
| OCR read wrong values | Image quality rendah | Re-scan dengan resolution min 300 DPI |

#### 9. Testing Workflow

```
1. Setup master data (Supplier dengan NPWP valid)
2. Configure Tax Settings (tolerance 2% DPP, 5% PPN)
3. Prepare test tax invoice files
4. Create ER dengan PPN
5. Upload tax invoice via OCR
6. Verify OCR fields auto-populated
7. Verify validations:
   - NPWP Match → ti_npwp_match = 1
   - DPP Variance → within 2%
   - PPN Variance → within 5%
8. Submit ER
9. Check for validation errors
```

#### 10. Bypass Validation (For Testing)

Jika perlu bypass validation untuk testing edge cases:

```python
# Set flag di Expense Request
doc.skip_tax_validation = 1
doc.save()
```

**Catatan:** Flag ini hanya untuk testing/development, tidak untuk production.

---

### D. UI Display Reference

Dokumentasi tampilan UI yang seharusnya ada pada Expense Request form.

#### 1. Expense Request Form - Header Section

**Status Badges:**
```
┌─────────────────────────────────────────────────┐
│ Expense Request: ER-2026-00123                  │
│ Status: [Draft] / [Pending Review] / [Approved] │
│         [PI Created] / [Paid] / [Rejected]      │
│         [Cancelled]                              │
└─────────────────────────────────────────────────┘
```

**Basic Information:**
```
┌─────────────────────────────────────────────────┐
│ Company: *PT Test Company                       │
│ Supplier: *PT ABC Vendor                        │
│ NPWP: 01.234.567.8-901.000                     │
│ Cost Center: *HO - Head Office                  │
│ Posting Date: *24/01/2026                       │
│ Branch: HO (auto-filled from Cost Center)       │
└─────────────────────────────────────────────────┘
```

#### 2. Expense Items Table

```
┌───────────────────────────────────────────────────────────────────────┐
│ Expense Items                                           [+ Add Row]   │
├────┬──────────────┬─────────────┬──────────┬───────────┬─────────────┤
│ #  │ Account      │ Description │ Amount   │ Cost Ctr  │ Branch      │
├────┼──────────────┼─────────────┼──────────┼───────────┼─────────────┤
│ 1  │ 6100 - Biaya │ Consulting  │ 10.000.000│ HO       │ HO          │
│    │ Operasional  │ Fee         │          │           │             │
├────┼──────────────┼─────────────┼──────────┼───────────┼─────────────┤
│    │              │ Total:      │ 10.000.000│          │             │
└────┴──────────────┴─────────────┴──────────┴───────────┴─────────────┘
```

#### 3. Tax Section (PPN & PPh)

**Section A: PPN (Value Added Tax)**
```
┌─────────────────────────────────────────────────┐
│ □ Add PPN                                       │
│                                                 │
│ When checked:                                   │
│ ┌─────────────────────────────────────────────┐ │
│ │ PPN Rate: [11% ▼]                          │ │
│ │ PPN Amount: 1.100.000 (auto-calculated)    │ │
│ │ PPN Account: 2100 - PPN Masukan            │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**Section B: PPh (Withholding Tax)**
```
┌─────────────────────────────────────────────────┐
│ □ Apply Withholding Tax (PPh)                   │
│                                                 │
│ When checked:                                   │
│ ┌─────────────────────────────────────────────┐ │
│ │ WHT Category: [PPh 23 - Jasa ▼]           │ │
│ │ WHT Rate: 2%                                │ │
│ │ WHT Amount: 200.000 (auto-calculated)       │ │
│ │ WHT Account: 1510 - PPh 23 Dibayar Dimuka │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**Section C: PPnBM (Luxury Tax) - Optional**
```
┌─────────────────────────────────────────────────┐
│ □ Add PPnBM                                     │
│                                                 │
│ When checked:                                   │
│ ┌─────────────────────────────────────────────┐ │
│ │ PPnBM Rate: [20% ▼]                        │ │
│ │ PPnBM Amount: 2.000.000                     │ │
│ │ PPnBM Account: 2105 - PPnBM                │ │
│ └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

#### 4. Tax Invoice OCR Section

**Location:** Below tax section, collapsible

```
┌─────────────────────────────────────────────────────────────┐
│ 📄 Tax Invoice (Faktur Pajak)               [▼ Expand]     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ [📤 Upload Tax Invoice]  [Supported: PDF, JPG, PNG]        │
│                                                             │
│ OCR Extracted Data:                                         │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ Nomor Faktur: *010.000-26.12345678                   │  │
│ │ Tanggal Faktur: *15/01/2026                          │  │
│ │ NPWP Penjual: *01.234.567.8-901.000                  │  │
│ │               ✅ Match dengan Supplier                │  │
│ │                                                       │  │
│ │ DPP (OCR): 10.000.000                                │  │
│ │ DPP (ER):  10.000.000                                │  │
│ │ Variance: 0% ✅ (Tolerance: ±2%)                     │  │
│ │                                                       │  │
│ │ PPN (OCR): 1.100.000                                 │  │
│ │ PPN (ER):  1.100.000                                 │  │
│ │ Variance: 0% ✅ (Tolerance: ±5%)                     │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ Status Validasi:                                            │
│ • NPWP Match: ✅                                            │
│ • DPP Variance: ✅ Within tolerance                        │
│ • PPN Variance: ✅ Within tolerance                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Error State Example (NPWP Mismatch):**
```
┌─────────────────────────────────────────────────────────────┐
│ 📄 Tax Invoice (Faktur Pajak)                              │
├─────────────────────────────────────────────────────────────┤
│ NPWP Penjual: *99.888.777.6-543.000                        │
│               ❌ TIDAK MATCH dengan Supplier!               │
│                                                             │
│ Expected: 01.234.567.8-901.000 (Supplier NPWP)            │
│ Found:    99.888.777.6-543.000 (Tax Invoice NPWP)         │
│                                                             │
│ ⚠️ Submit akan gagal. Perbaiki NPWP atau ganti supplier.   │
└─────────────────────────────────────────────────────────────┘
```

#### 5. Totals Section (Summary)

```
┌─────────────────────────────────────────────────┐
│ Financial Summary                               │
├─────────────────────────────────────────────────┤
│ Base Amount:          10.000.000                │
│ + PPN (11%):           1.100.000                │
│ + PPnBM (20%):         2.000.000 (if applicable)│
│ ─────────────────────────────────              │
│ Gross Total:          13.100.000                │
│                                                 │
│ - WHT PPh 23 (2%):      (200.000)               │
│ ─────────────────────────────────              │
│ Net Payable:          12.900.000                │
└─────────────────────────────────────────────────┘
```

#### 6. Action Buttons (Status-Dependent)

**Draft Status:**
```
[💾 Save]  [📤 Submit]  [🔍 Check Approval Route]  [❌ Cancel]
```

**Pending Review Status:**
```
[✅ Approve (Level 1/2/3)]  [❌ Reject]  [🔙 Back to Draft]
```

**Approved Status:**
```
[📄 Create Purchase Invoice]  [❌ Cancel ER]  [🔍 View Approval Route]
```

**PI Created Status:**
```
[🔗 View Purchase Invoice]  [💳 Create Payment Entry]  [❌ Cancel ER]
(Cancel akan show guided message)
```

**Paid Status:**
```
[🔗 View Purchase Invoice]  [🔗 View Payment Entry]  [❌ Cancel ER]
(Cancel akan trigger full reversal)
```

#### 7. Linked Documents Section

```
┌─────────────────────────────────────────────────┐
│ 🔗 Linked Documents                             │
├─────────────────────────────────────────────────┤
│ • Purchase Invoice: PI-2026-00456 (Submitted)   │
│   Amount: 13.100.000                            │
│   [🔗 View]                                     │
│                                                 │
│ • Payment Entry: PE-2026-00789 (Submitted)      │
│   Amount: 12.900.000 (after WHT)                │
│   [🔗 View]                                     │
└─────────────────────────────────────────────────┘
```

#### 8. Approval Route Display

**When clicked "Check Approval Route":**
```
┌─────────────────────────────────────────────────────────────┐
│ Approval Route for ER-2026-00123                           │
├─────────────────────────────────────────────────────────────┤
│ Amount: 10.000.000                                          │
│ Cost Center: HO - Head Office                               │
│                                                             │
│ Approval Levels:                                            │
│ ┌───────────────────────────────────────────────────────┐  │
│ │ ✓ Level 1: approver1@test.com                        │  │
│ │   Threshold: 0 - 5.000.000                           │  │
│ │   Status: ✅ Approved (23/01/2026 14:30)             │  │
│ │                                                       │  │
│ │ ⏳ Level 2: approver2@test.com (CURRENT)             │  │
│ │   Threshold: 5.000.001 - 50.000.000                  │  │
│ │   Status: ⏳ Pending Approval                        │  │
│ │                                                       │  │
│ │ ⏸️ Level 3: approver3@test.com                       │  │
│ │   Threshold: > 50.000.000                            │  │
│ │   Status: ⏸️ Not Required (Amount below threshold)   │  │
│ └───────────────────────────────────────────────────────┘  │
│                                                             │
│ [✅ Close]                                                  │
└─────────────────────────────────────────────────────────────┘
```

#### 9. Internal Charge Section

**When "Generate Internal Charge" clicked:**
```
┌─────────────────────────────────────────────────┐
│ 📊 Internal Charge Request                      │
├─────────────────────────────────────────────────┤
│ From Branch: HO                                 │
│ To Branch: [Jakarta Branch ▼]                  │
│                                                 │
│ Items to Charge:                                │
│ ┌─────────────────────────────────────────────┐ │
│ │ ☑ Item 1: Consulting Fee - 10.000.000     │ │
│ │ ☐ Item 2: (if multiple items)              │ │
│ └─────────────────────────────────────────────┘ │
│                                                 │
│ Charge Amount: 10.000.000                       │
│                                                 │
│ [Generate ICR] [Cancel]                         │
└─────────────────────────────────────────────────┘
```

#### 10. Deferred Expense Item Display

**In Expense Items table when deferred:**
```
┌───────────────────────────────────────────────────────────────────┐
│ Expense Items                                                     │
├────┬──────────────┬─────────────┬──────────┬─────────────────────┤
│ #  │ Account      │ Description │ Amount   │ Deferred           │
├────┼──────────────┼─────────────┼──────────┼─────────────────────┤
│ 1  │ 6100 - Biaya │ Annual      │ 12.000.000│ ✓ Deferred        │
│    │ Operasional  │ License     │          │   Start: 01/01/2026│
│    │              │             │          │   End: 31/12/2026  │
│    │              │             │          │   Months: 12       │
│    │              │             │          │   Monthly: 1.000.000│
└────┴──────────────┴─────────────┴──────────┴─────────────────────┘
```

#### 11. Status Indicator Colors

```
Status Colors (untuk visual recognition):
┌─────────────────────┬─────────────┬──────────┐
│ Status              │ Color       │ Badge    │
├─────────────────────┼─────────────┼──────────┤
│ Draft               │ Gray        │ ⚪ Draft │
│ Pending Review      │ Orange      │ 🟠 Pending│
│ Approved            │ Green       │ 🟢 Approved│
│ PI Created          │ Blue        │ 🔵 PI Created│
│ Paid                │ Purple      │ 🟣 Paid  │
│ Rejected            │ Red         │ 🔴 Rejected│
│ Cancelled           │ Dark Gray   │ ⚫ Cancelled│
└─────────────────────┴─────────────┴──────────┘
```

#### 12. Validation Messages Location

**Inline validation errors (below field):**
```
NPWP: 01.234.567.8-901.000
❌ NPWP from OCR does not match Supplier NPWP
```

**Top banner errors (on Submit):**
```
┌─────────────────────────────────────────────────────────────┐
│ ❌ Validation Error                                          │
├─────────────────────────────────────────────────────────────┤
│ • DPP variance exceeds tolerance (3% > 2%)                  │
│ • Expected: 10.000.000, Found: 10.300.000                   │
│ • Please adjust ER amount or re-upload tax invoice          │
└─────────────────────────────────────────────────────────────┘
```

**Success message (on Submit):**
```
┌─────────────────────────────────────────────────────────────┐
│ ✅ Success                                                   │
├─────────────────────────────────────────────────────────────┤
│ Expense Request ER-2026-00123 submitted successfully        │
│ Sent to approver1@test.com for Level 1 approval             │
└─────────────────────────────────────────────────────────────┘
```

---

## Flow Normal (Happy Path)

### Skenario 1: ER Basic tanpa Pajak

**Tujuan:** Validasi flow dasar dari Draft hingga Paid dengan explicit status verification

| Step | Action | Expected Result | Status Check |
|------|--------|-----------------|--------------|
| 1 | Buat ER baru | Form terbuka | status = null/undefined |
| 2 | Isi mandatory fields: Supplier, Cost Center, Request Date | Fields terisi | - |
| 3 | Tambah Item: Account = Biaya Operasional, Amount = 1,000,000 | Total = 1,000,000 | - |
| 4 | Save | Document saved | ✅ `status` = "Draft" <br> ✅ `workflow_state` = "Draft" <br> ✅ `docstatus` = 0 |
| 5 | Submit | Document submitted | ✅ `status` = "Pending Review" <br> ✅ `workflow_state` = "Pending Review" <br> ✅ `docstatus` = 1 <br> ✅ `submitted_on` timestamp |
| 6 | Login sebagai Approver | - | - |
| 7 | Approve | Approval successful | ✅ `status` = "Approved" <br> ✅ `workflow_state` = "Approved" <br> ✅ `level_1_approved_on` timestamp |
| 8 | Click "Create Purchase Invoice" | PI created | ✅ ER `status` = "PI Created" <br> ✅ `linked_purchase_invoice` = PI name |
| 9 | Submit PI | PI submitted | ER status remains "PI Created" |
| 10 | Buat Payment Entry dari PI | PE created | - |
| 11 | Submit Payment Entry | PE submitted | ✅ ER `status` = "Paid" <br> ✅ `linked_payment_entry` = PE name |

**Verification Points:**
- [x] Status transitions correctly at each step
- [x] `status` always matches `workflow_state`
- [x] Timestamps recorded for key transitions
- [x] `linked_purchase_invoice` terisi dengan PI name
- [x] `linked_payment_entry` terisi dengan PE name
- [x] Status flow: Draft → Pending Review → Approved → PI Created → Paid

---

### Skenario 2: ER dengan PPN

**Test Data:**
- Amount: 10,000,000 (DPP)
- PPN: 11% = 1,100,000
- Total: 11,100,000

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER baru, isi mandatory fields | - |
| 2 | Tambah Item: Amount = 10,000,000 | Subtotal = 10,000,000 |
| 3 | Tab Taxes: Is PPN Applicable = ✓ | PPN section enabled |
| 4 | Pilih PPN Template (11%) | Total PPN = 1,100,000 |
| 5 | Save & Submit | Total Amount = 11,100,000 |
| 6 | Approve & Create PI | PI dengan PPN template |

**Verification Points:**
- [ ] PI memiliki tax template yang sama
- [ ] Tax amount di PI = 1,100,000
- [ ] DPP di PI = 10,000,000

---

### Skenario 3: ER dengan PPh (Withholding Tax)

**Test Data:**
- Amount: 10,000,000 (DPP)
- PPh 23: 2% = 200,000
- Total dibayar: 9,800,000

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER baru | - |
| 2 | Item Amount = 10,000,000 | - |
| 3 | Tab Taxes: Is PPh Applicable = ✓ | - |
| 4 | PPh Type = PPh 23 (2%) | - |
| 5 | PPh Base Amount = 10,000,000 | Total PPh = 200,000 (merah) |
| 6 | Total Amount = 9,800,000 | Net payable |
| 7 | Create PI | PI dengan WHT category |

**Verification Points:**
- [ ] PI memiliki `tax_withholding_category` = PPh 23
- [ ] Apply TDS = ✓ di PI
- [ ] WHT amount calculated correctly

---

### Skenario 4: ER dengan PPN + PPh

**Test Data:**
- DPP: 10,000,000
- PPN 11%: 1,100,000
- PPh 23 2%: 200,000
- Total: 10,900,000

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER, Amount = 10,000,000 | - |
| 2 | Enable PPN (11%) | PPN = 1,100,000 |
| 3 | Enable PPh 23 (2%) | PPh = 200,000 |
| 4 | Verify Total | 10,000,000 + 1,100,000 - 200,000 = 10,900,000 |
| 5 | Create PI | PI dengan PPN + WHT |

---

## Flow Approval Multi-Level

### Skenario 5: Level 1 Approval Only (Amount ≤ 5 juta)

| Step | Action | Expected Result | Status Check |
|------|--------|-----------------|--------------|
| 1 | Buat ER, Amount = 3,000,000 | - | - |
| 2 | Submit | Document submitted | ✅ `status` = "Pending Review" <br> ✅ `current_approval_level` = 1 |
| 3 | Login as Level 1 Approver | - | - |
| 4 | Approve | Directly approved | ✅ `status` = "Approved" <br> ✅ `level_1_approved_on` timestamp <br> ✅ No level 2/3 timestamps |

---

### Skenario 6: Level 2 Approval (Amount > 5 juta)

| Step | Action | Expected Result | Status Check |
|------|--------|-----------------|--------------|
| 1 | Buat ER, Amount = 15,000,000 | - | - |
| 2 | Submit | Document submitted | ✅ `status` = "Pending Review" <br> ✅ `current_approval_level` = 1 |
| 3 | Level 1 Approver: Approve | Level 1 approved | ✅ `status` = "Pending Review" (still) <br> ✅ `current_approval_level` = 2 <br> ✅ `level_1_approved_on` timestamp |
| 4 | Level 2 Approver: Approve | Fully approved | ✅ `status` = "Approved" <br> ✅ `level_2_approved_on` timestamp |

---

### Skenario 7: Level 3 Approval (Amount > 50 juta)

| Step | Action | Expected Result | Status Check |
|------|--------|-----------------|--------------|
| 1 | Buat ER, Amount = 75,000,000 | - | - |
| 2 | Submit | Document submitted | ✅ `status` = "Pending Review" <br> ✅ `current_approval_level` = 1 |
| 3 | Level 1 Approve | Level 1 approved | ✅ `status` = "Pending Review" <br> ✅ `current_approval_level` = 2 <br> ✅ `level_1_approved_on` timestamp |
| 4 | Level 2 Approve | Level 2 approved | ✅ `status` = "Pending Review" <br> ✅ `current_approval_level` = 3 <br> ✅ `level_2_approved_on` timestamp |
| 5 | Level 3 Approve | Fully approved | ✅ `status` = "Approved" <br> ✅ `level_3_approved_on` timestamp |

**Verification Points:**
- [x] `level_1_user`, `level_2_user`, `level_3_user` terisi
- [x] `level_1_approved_on`, `level_2_approved_on`, `level_3_approved_on` terisi
- [x] Approval route sesuai dengan Expense Approval Setting
- [x] Status remains "Pending Review" until final approval

---

## Flow Rejection & Reopen

### Skenario 8: Reject di Level 1

| Step | Action | Expected Result | Status Check |
|------|--------|-----------------|--------------|
| 1 | Buat & Submit ER | Document submitted | ✅ `status` = "Pending Review" <br> ✅ `current_approval_level` = 1 |
| 2 | Level 1 Approver: Reject | Rejection recorded | ✅ `status` = "Rejected" <br> ✅ `workflow_state` = "Rejected" <br> ✅ `level_1_rejected_on` timestamp <br> ✅ `docstatus` = 1 (still submitted) |
| 3 | Try to approve | Action not available | ER tidak bisa di-approve lagi |
| 4 | Check budget | Budget released | Budget lock di-release |

**Expected Behavior:**
- [x] Status changed to "Rejected"
- [x] Rejection timestamp recorded
- [x] Document remains submitted (docstatus = 1)
- [x] Cannot transition to other states except Reopen
- [x] Budget lock released

---

### Skenario 9: Reject di Level 2

| Step | Action | Expected Result | Status Check |
|------|--------|-----------------|--------------|
| 1 | Submit ER (Amount > 5 juta) | - | ✅ `status` = "Pending Review" |
| 2 | Level 1 Approve | Level 1 approved | ✅ `current_approval_level` = 2 |
| 3 | Level 2 Reject | Rejection at L2 | ✅ `status` = "Rejected" <br> ✅ `level_2_rejected_on` timestamp |

---

### Skenario 10: Reopen Rejected ER

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER dengan status "Rejected" | - |
| 2 | Click "Reopen" action | Status kembali ke "Draft" atau "Pending Review" |
| 3 | Edit jika perlu | - |
| 4 | Approve ulang | Normal flow |

---

## Flow Cancel (Back Flow)

### Skenario 11: Cancel ER di Status Draft

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER, Save (status = Draft) | - |
| 2 | Delete document | ER dihapus |

**Note:** Draft ER bisa langsung dihapus, tidak perlu Cancel.

---

### Skenario 12: Cancel ER di Status Pending Review

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Submit ER | Status = "Pending Review" |
| 2 | Menu > Cancel | ER cancelled |
| 3 | Amend jika perlu | New ER-XXXX-1 created |

**Permission Required:** System Manager atau Expense Approver

---

### Skenario 13: Cancel ER yang sudah Approved

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER dengan status "Approved" | - |
| 2 | Cancel | ER cancelled, Budget released |

**Verification Points:**
- [ ] Budget lock di-release (jika budget control enabled)
- [ ] Status = Cancelled (docstatus = 2)

---

### Skenario 14: Cancel ER dengan PI Created (GUIDED CANCELLATION) ✅

**⚠️ SMART VALIDATION: System provides clear guidance!**

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER status = "PI Created" | PI sudah ada (submitted) |
| 2 | Try to Cancel ER directly | **Error with guidance** |
| 3 | Error message shows 2 options | See below |

**Error Message (Helpful Guidance):**
```
❌ Linked Documents Exist:
Cannot cancel Expense Request - linked documents exist: Purchase Invoice PI-001.

Please either:
1. Cancel linked documents first in reverse order (PE → PI → ER), or
2. Use 'Cancel All Linked Documents' from the menu to cancel everything at once.
```

**Option A: Manual Cancellation**
| 4a | Cancel PI-001 first | PI cancelled |
| 5a | Cancel ER | ER cancelled ✅ |

**Option B: Bulk Cancellation (Recommended)**
| 4b | Menu > Cancel All Linked Documents | All cancelled together ✅ |

---

### Skenario 15: Cancel ER yang sudah Paid (FULL REVERSAL)

**⚠️ PALING KOMPLEKS - System provides clear guidance!**

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER status = "Paid" | PI + PE sudah ada |
| 2 | Try to Cancel ER directly | **Error with guidance** |

**Error Message:**
```
❌ Linked Documents Exist:
Cannot cancel Expense Request - linked documents exist: Payment Entry PE-001, Purchase Invoice PI-001.

Please either:
1. Cancel linked documents first in reverse order (PE → PI → ER), or
2. Use 'Cancel All Linked Documents' from the menu to cancel everything at once.
```

**Option A: Manual Cancellation (Reverse Order)**
| 3a | **Cancel Payment Entry** first | PE cancelled |
| 4a | **Cancel Purchase Invoice** | PI cancelled |
| 5a | **Cancel Expense Request** | ER cancelled ✅ |

**Option B: Bulk Cancellation (Recommended) ✅**
| 3b | Menu > **Cancel All Linked Documents** | All cancelled together ✅ |
| 4b | Confirm action | PE + PI + ER all cancelled in one go |

---

### Skenario 16: Amend Cancelled ER

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER yang sudah di-cancel | - |
| 2 | Click "Amend" | Copy ER dibuat: ER-2024-000001-1 |
| 3 | Edit sesuai kebutuhan | - |
| 4 | Submit ulang | Flow approval dari awal |

---

## Tax Scenarios

### Skenario 17: Tax Invoice OCR Integration

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enable PPN di ER | - |
| 2 | Upload Tax Invoice via OCR | OCR fields populated |
| 3 | Verify: ti_fp_no, ti_fp_date, ti_fp_dpp, ti_fp_ppn | Auto-filled from OCR |
| 4 | ti_verification_status = "Verified" | Ready to create PI |
| 5 | Create PI | PI uses verified tax data |

---

### Skenario 18: WHT Category Conflict

**Kondisi:** Supplier memiliki WHT Category berbeda dengan ER

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Supplier memiliki WHT Category = "PPh 21" | - |
| 2 | ER memiliki PPh Type = "PPh 23" | Conflict! |
| 3 | Click "Create Purchase Invoice" | Dialog muncul untuk pilih kategori |
| 4a | Pilih "Yes" | Gunakan PPh dari ER |
| 4b | Pilih "No" | Update ER ke WHT Supplier |

---

## OCR Validation Scenarios

### Skenario 19: Validasi NPWP Supplier

**Tujuan:** Memastikan NPWP dari OCR Faktur Pajak cocok dengan NPWP Supplier

**Test Data:**
- Supplier NPWP: `01.234.567.8-901.000`
- OCR NPWP (dari faktur): harus sama

#### Skenario 19a: NPWP Cocok ✅

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER dengan Supplier (NPWP: 01.234.567.8-901.000) | - |
| 2 | Enable PPN | - |
| 3 | Upload Tax Invoice OCR | OCR reads NPWP |
| 4 | OCR NPWP = 01.234.567.8-901.000 | NPWP Match ✅ |
| 5 | Submit | Validasi passed |
| 6 | Check `ti_npwp_match` field | Field automatically set to 1 |

**Verification Points:**
- [x] `ti_npwp_match` = 1 (true) - **IMPLEMENTED** ✅
- [x] Tidak ada error NPWP mismatch
- [x] Field di-set otomatis saat validation passes

#### Skenario 19b: NPWP Tidak Cocok ❌

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER dengan Supplier (NPWP: 01.234.567.8-901.000) | - |
| 2 | Enable PPN | - |
| 3 | Upload Tax Invoice OCR | OCR reads different NPWP |
| 4 | OCR NPWP = 99.888.777.6-543.000 | NPWP Mismatch! |
| 5 | Submit | **Error**: "NPWP from OCR (99.888.777.6-543.000) does not match Supplier NPWP (01.234.567.8-901.000)" |
| 6 | Check `ti_npwp_match` field | Field remains 0 or null (not set) |

**Expected Error Message:**
```
❌ Tax Invoice Validation Error:
NPWP from OCR (99.888.777.6-543.000) does not match Supplier NPWP (01.234.567.8-901.000)
```

---

### Skenario 20: Validasi DPP Variance (Selisih DPP)

**Tujuan:** Memastikan DPP dari OCR Faktur Pajak tidak berbeda signifikan dengan Total Expense

**Konfigurasi Toleransi (dari Settings):**
- Tolerance IDR: Rp 10,000 (default)
- Tolerance Percentage: 1% (default)

**Rule:** Error jika selisih melebihi **KEDUA** toleransi (IDR DAN %)

#### Skenario 20a: DPP Dalam Toleransi ✅

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER, Total Expense = 10,000,000 | DPP Expected = 10,000,000 |
| 2 | Upload Tax Invoice OCR | - |
| 3 | OCR DPP = 10,005,000 | Selisih = 5,000 (0.05%) |
| 4 | Submit | Validasi passed (dalam toleransi) |

**Verification Points:**
- [ ] `ti_dpp_variance` = 5,000
- [ ] Tidak ada error, mungkin ada warning

#### Skenario 20b: DPP Warning Zone ⚠️

**Kondisi:** Selisih melebihi SATU toleransi (IDR saja atau % saja)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER, Total Expense = 10,000,000 | - |
| 2 | OCR DPP = 10,015,000 | Selisih = 15,000 (0.15%) |
| 3 | Submit | **Warning** (bukan error) |

**Warning karena:**
- Selisih IDR = 15,000 > 10,000 (melebihi toleransi IDR)
- Selisih % = 0.15% < 1% (masih dalam toleransi %)
- Karena hanya salah satu yang melebihi → Warning saja

#### Skenario 20c: DPP Melebihi Toleransi ❌

**Kondisi:** Selisih melebihi KEDUA toleransi

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER, Total Expense = 1,000,000 | - |
| 2 | OCR DPP = 1,050,000 | Selisih = 50,000 (5%) |
| 3 | Submit | **Error**: DPP variance exceeded |

**Expected Error Message:**
```
❌ DPP dari OCR (Rp 1,050,000) berbeda dengan Total Expense (Rp 1,000,000). 
   Selisih: Rp 50,000 atau 5.00% (toleransi: Rp 10,000 atau 1%)
```

**Verification Points:**
- [ ] `ti_dpp_variance` = 50,000
- [ ] Submit blocked dengan error

---

### Skenario 21: Validasi PPN Variance (Selisih PPN)

**Tujuan:** Memastikan PPN dari OCR tidak berbeda signifikan dengan PPN yang dihitung

**Formula:** Expected PPN = DPP × PPN Rate (default 11%)

#### Skenario 21a: PPN Dalam Toleransi ✅

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER, DPP = 10,000,000 | Expected PPN = 1,100,000 |
| 2 | OCR PPN = 1,100,500 | Selisih = 500 (0.045%) |
| 3 | Submit | Validasi passed |

#### Skenario 21b: PPN Melebihi Toleransi ❌

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER, DPP = 1,000,000 | Expected PPN = 110,000 |
| 2 | OCR PPN = 125,000 | Selisih = 15,000 (13.6%) |
| 3 | Submit | **Error**: PPN variance exceeded |

**Expected Error Message:**
```
❌ PPN dari OCR (Rp 125,000) berbeda dengan PPN yang dihitung (Rp 110,000). 
   Selisih: Rp 15,000 atau 13.60% (toleransi: Rp 10,000 atau 1%)
```

---

### Skenario 22: Validasi DPP + PPN + NPWP Kombinasi

**Tujuan:** Test validasi lengkap semua field OCR

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER: Supplier NPWP = 01.234.567.8-901.000 | - |
| 2 | Total Expense = 10,000,000, Enable PPN 11% | Expected PPN = 1,100,000 |
| 3 | Upload Tax Invoice OCR dengan data: | - |
|   | - OCR NPWP = 01.234.567.8-901.000 | ✅ NPWP Match |
|   | - OCR DPP = 10,000,000 | ✅ DPP Match |
|   | - OCR PPN = 1,100,000 | ✅ PPN Match |
| 4 | Submit | Semua validasi passed ✅ |

**Verification Points:**
- [ ] `ti_npwp_match` = 1
- [ ] `ti_dpp_variance` = 0
- [ ] `ti_ppn_variance` = 0
- [ ] `ti_verification_status` = "Verified"

---

### Skenario 23: Skip Validasi untuk PPN Non-Standard

**Kondisi:** PPN Type = "Zero Rated" atau "Exempt"

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER dengan PPN Type = Zero Rated | - |
| 2 | OCR DPP berbeda dari Expected | - |
| 3 | Submit | DPP/PPN variance **tidak divalidasi** |
| 4 | Hanya NPWP yang divalidasi | NPWP check still applies |

**Note:** Untuk Zero Rated atau Exempt, hanya validasi NPWP yang berlaku.

---

### Tabel Ringkasan Toleransi Validasi

| Field | Toleransi IDR | Toleransi % | Rule |
|-------|---------------|-------------|------|
| DPP | Rp 10,000 | 1% | Error jika melebihi KEDUA |
| PPN | Rp 10,000 | 1% | Error jika melebihi KEDUA |
| NPWP | - | - | Harus exact match (normalized) |

**Normalisasi NPWP:** Format distandarkan (hapus tanda baca) sebelum dibandingkan
- `01.234.567.8-901.000` → `012345678901000`
- `01234567.8-901.000` → `012345678901000` (sama)

---

## Budget Control Testing

### Skenario 24: Budget Lock on Submit

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enable Budget Control | - |
| 2 | Set Budget untuk Cost Center | - |
| 3 | Submit ER | Budget locked/reserved |
| 4 | Check Budget Control Ledger | Entry created |

---

### Skenario 25: Budget Release on Cancel

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER dengan budget locked | - |
| 2 | Cancel ER | Budget released |
| 3 | Check Budget Control Ledger | Reversal entry created |

---

### Skenario 26: Budget Exceed Prevention

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Budget tersedia: 5,000,000 | - |
| 2 | Buat ER Amount: 7,000,000 | - |
| 3 | Submit | Error: "Budget exceeded" |

---

## Edge Cases & Error Handling

### Skenario 27: Submit tanpa Approval Route

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Cost Center tanpa Expense Approval Setting | - |
| 2 | Submit ER | Error: "Approval Route Not Found" |

---

### Skenario 28: Invalid Approver User

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Approver user di-disable | - |
| 2 | Submit ER | Error: "Approver user is disabled" |

---

### Skenario 29: Duplicate PI Prevention ✅

**Tujuan:** Prevent creating multiple PIs from one ER (with smart handling)

#### Skenario 29a: Active PI Exists (Button Hidden)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER dengan status "PI Created" | - |
| 2 | linked_purchase_invoice = "PI-001" | - |
| 3 | PI-001 docstatus = 1 (submitted) | - |
| 4 | Check for "Create Purchase Invoice" button | **Button HIDDEN** ✅ |
| 5 | Try to create via API/console | Backend error: "already linked" |

#### Skenario 29b: Cancelled PI (Button Shows Again) ✅

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER with linked_purchase_invoice = "PI-001" | - |
| 2 | PI-001 docstatus = 2 (cancelled) | - |
| 3 | Check for "Create Purchase Invoice" button | **Button VISIBLE** ✅ (can create new PI) |
| 4 | Click "Create Purchase Invoice" | PI-002 created successfully |
| 5 | linked_purchase_invoice updated | Now = "PI-002" |

#### Skenario 29c: Deleted PI (Button Shows)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER with linked_purchase_invoice = "PI-001" | - |
| 2 | PI-001 doesn't exist anymore (deleted) | - |
| 3 | Check for "Create Purchase Invoice" button | **Button VISIBLE** ✅ |
| 4 | Can create new PI | Success |

**Verification Points:**
- [x] Button hidden when active PI exists (docstatus = 1)
- [x] Button shows when PI cancelled (docstatus = 2) 
- [x] Button shows when PI deleted (not found)
- [x] Can create new PI after cancellation
- [x] Backend validation still prevents duplicates via API

---

## Internal Charge Testing

### Skenario 30: Generate Internal Charge Request

**Kondisi:** Allocation Mode = "Allocated via Internal Charge"

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER baru | - |
| 2 | Set Allocation Mode = "Allocated via Internal Charge" | Internal Charge field appears |
| 3 | Save & Submit | Status = Pending Review |
| 4 | Dashboard menunjukkan "Internal Charge not generated" | Orange indicator |
| 5 | Click "Generate Internal Charge" | ICR created |
| 6 | `internal_charge_request` terisi | Link to ICR |

**Verification Points:**
- [ ] Internal Charge Request created dengan items dari ER
- [ ] Dashboard indicator berubah menjadi green
- [ ] Button berubah menjadi "View Internal Charge"

---

### Skenario 31: View Internal Charge

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER dengan Internal Charge sudah ada | - |
| 2 | Click "View Internal Charge" | Navigate to ICR form |
| 3 | Verify ICR data | Items match ER items |

---

### Skenario 32: Internal Charge Approval Required

**Kondisi:** ICR harus Approved sebelum ER bisa create PI

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER dengan Allocation Mode = Internal Charge | - |
| 2 | Generate ICR (status = Draft) | - |
| 3 | Approve ER | ER status = Approved |
| 4 | Try Create PI (ICR not approved) | Blocked/Warning |
| 5 | Approve ICR | ICR status = Approved |
| 6 | Create PI | PI created successfully |

---

## Deferred Expense Testing

### Skenario 33: Basic Deferred Expense Item

**Tujuan:** Test amortisasi biaya ditangguhkan

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER dengan item | - |
| 2 | Centang "Deferred Expense" pada item | Deferred fields muncul |
| 3 | Isi Prepaid Account | Pilih dari daftar valid |
| 4 | Isi Deferred Start Date = 2026-01-01 | - |
| 5 | Isi Deferred Periods = 12 | 12 bulan amortisasi |
| 6 | Click "Show Amortization Schedule" | Schedule ditampilkan |
| 7 | Save | Validasi passed |

**Verification Points:**
- [ ] Amortization schedule menunjukkan 12 entries
- [ ] Amount per period = Total Amount / 12
- [ ] Start dari tanggal yang ditentukan

---

### Skenario 34: Deferred Expense Validation Errors

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Centang "Deferred Expense" tanpa Prepaid Account | Error: "Prepaid Account is required" |
| 2 | Isi Prepaid Account yang tidak valid | Error: "not in deferrable accounts" |
| 3 | Tidak isi Deferred Start Date | Error: "Deferred Start Date required" |
| 4 | Set Deferred Periods = 0 | Error: "Deferred Periods must be > 0" |

---

### Skenario 35: Deferred Expense Disabled

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Disable Deferred Expense di settings | - |
| 2 | Buat ER dengan item, centang Deferred | - |
| 3 | Save | Error: "Deferred Expense is disabled in settings" |

---

## Multiple Items & Accounts Testing

### Skenario 36: Multiple Expense Items

**Tujuan:** Test ER dengan beberapa line items

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER baru | - |
| 2 | Tambah Item 1: Account A, Amount = 500,000 | - |
| 3 | Tambah Item 2: Account B, Amount = 300,000 | - |
| 4 | Tambah Item 3: Account C, Amount = 200,000 | - |
| 5 | Verify Total | Total = 1,000,000 |
| 6 | Create PI | PI dengan 3 line items |

**Verification Points:**
- [ ] `amount` (subtotal) = 1,000,000
- [ ] `expense_accounts` contains all 3 accounts
- [ ] PI items match ER items

---

### Skenario 37: Item-Level PPh (Apply WHT per Item)

**Tujuan:** Test PPh per item, bukan per header

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER dengan 2 items | - |
| 2 | Item 1: Amount = 1,000,000, Apply WHT = ✓ | PPh base = 1,000,000 |
| 3 | Item 2: Amount = 500,000, Apply WHT = ❌ | No PPh |
| 4 | Set PPh Type = PPh 23 (2%) | - |
| 5 | Verify Total PPh | PPh = 1,000,000 × 2% = 20,000 |
| 6 | Total Amount = 1,500,000 - 20,000 = 1,480,000 | - |

**Verification Points:**
- [ ] PPh hanya dihitung dari item yang Apply WHT = ✓
- [ ] Header `pph_base_amount` = sum of item WHT bases
- [ ] `total_pph` calculated correctly

---

### Skenario 38: Mixed Mode - Header vs Item PPh

**Kondisi:** Jika ada item dengan Apply WHT, header PPh di-disable

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER tanpa item PPh | Header `pph_base_amount` editable |
| 2 | Centang Apply WHT pada salah satu item | Header `pph_base_amount` read-only |
| 3 | PPh base = sum dari item dengan Apply WHT | Auto-calculated |

---

## Branch & Cost Allocation Testing

### Skenario 39: Auto-Set Branch from Cost Center

**Tujuan:** Test branch defaults dari cost center

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER baru | - |
| 2 | Pilih Cost Center (yang punya branch mapping) | - |
| 3 | Branch auto-filled | Branch dari cost center |
| 4 | Save | Branch tersimpan |

**Verification Points:**
- [ ] Branch otomatis terisi dari Cost Center
- [ ] PI yang dibuat inherit branch yang sama

---

### Skenario 40: Manual Branch Override

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER, pilih Cost Center | Branch auto-filled |
| 2 | Manually change Branch | Branch dapat diubah |
| 3 | Save & Submit | Manual branch dipertahankan |

---

## UI Actions Testing

### Skenario 41: Check Approval Route Button

**Tujuan:** Test tombol untuk check approval route sebelum submit

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER (Draft), isi Cost Center & Items | - |
| 2 | Click "Check Approval Route" di Actions | Dialog muncul |
| 3 | Jika route ditemukan | Show route details (L1, L2, L3 users) |
| 4 | Jika route tidak ditemukan | Show error/warning |

**Verification Points:**
- [ ] Route ditampilkan dengan level dan approvers
- [ ] Amount thresholds ditampilkan
- [ ] Warning jika ada user tidak valid

---

### Skenario 42: Check Approval Route - No Setting

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Pilih Cost Center tanpa Approval Setting | - |
| 2 | Click "Check Approval Route" | Error: "Please configure Expense Approval Setting" |

---

## Print Format Testing

### Skenario 43: Print Expense Request

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buka ER yang sudah submitted | - |
| 2 | Click Print | Print preview muncul |
| 3 | Verify print content | Header, items, totals, approval info |
| 4 | Download PDF | PDF generated |

**Verification Points:**
- [ ] Company logo/header tercetak
- [ ] All items dengan account & amount
- [ ] Tax details (PPN, PPh)
- [ ] Approval status & timestamps
- [ ] Total amounts correct

---

## PPnBM Testing (Luxury Goods Tax)

### Skenario 44: ER dengan PPnBM

**Tujuan:** Test Pajak Penjualan Barang Mewah

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER, upload Tax Invoice dengan PPnBM | - |
| 2 | OCR reads `ti_fp_ppnbm` | PPnBM amount filled |
| 3 | Verify Total | DPP + PPN + PPnBM - PPh |
| 4 | Create PI | PI includes PPnBM |

**Formula:**
```
Total Amount = DPP + PPN + PPnBM - PPh
```

---

## Data Integrity Testing

### Skenario 45: Immutability After Approval

**Tujuan:** Prevent edit key fields setelah approved

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Approve ER | Status = Approved |
| 2 | Try edit `supplier` | Error: "Cannot modify after approval" |
| 3 | Try edit `amount` | Error: "Cannot modify after approval" |
| 4 | Try edit `cost_center` | Error: "Cannot modify after approval" |
| 5 | Try edit `branch` | Error: "Cannot modify after approval" |
| 6 | Try edit `project` | Error: "Cannot modify after approval" |
| 7 | Try edit `request_type` | Error: "Cannot modify after approval" |

**Protected Fields:**
- `request_type`
- `supplier`
- `amount`
- `cost_center`
- `branch`
- `project`

---

### Skenario 46A: Status Field Verification & Sync ✅

**Tujuan:** Verify status field accurately reflects workflow state and persists correctly

#### Sub-Test 1: Status-Workflow State Synchronization

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER baru | `status` = null/undefined (not yet saved) |
| 2 | Save as Draft | `status` = "Draft", `workflow_state` = "Draft" |
| 3 | Submit ER | `status` = "Pending Review", `workflow_state` = "Pending Review" |
| 4 | Verify DB | Both fields match in database |
| 5 | Level 1 Approve | `status` = "Pending L2" or "Approved", `workflow_state` matches |
| 6 | Refresh page | Status still correct (persisted) |
| 7 | Create PI | `status` = "PI Created", `workflow_state` = "PI Created" |
| 8 | Create PE | `status` = "Paid", `workflow_state` = "Paid" |

**Verification Points:**
- [x] `status` field always syncs with `workflow_state` after each transition
- [x] Status persists correctly after page refresh
- [x] Status visible in form header/indicator
- [x] Both fields updated via `db_set` (no modified timestamp change)

#### Sub-Test 2: Status Display & Filtering

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Go to Expense Request List | - |
| 2 | Check Status column | Shows current status for each ER |
| 3 | Filter by Status = "Pending Review" | Only pending ERs shown |
| 4 | Filter by Status = "Approved" | Only approved ERs shown |
| 5 | Filter by Status = "Paid" | Only paid ERs shown |
| 6 | Check status badge colors | Different colors for different states |

**Verification Points:**
- [ ] Status column displays correctly in list view
- [ ] Filter by status works accurately
- [ ] Status badge has appropriate color coding
- [ ] Status updates in real-time when changed

#### Sub-Test 3: Status Protection (Cannot Bypass Workflow)

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Create ER with Status = "Draft" | - |
| 2 | Try to manually set `status` = "Approved" via form | Field is read-only or change blocked |
| 3 | Try to set `workflow_state` = "Approved" via form | Field is read-only or change blocked |
| 4 | Try via API: `frappe.db.set_value()` manually | Changes blocked by `guard_status_changes` |
| 5 | Verify error message | "Status changes must be performed via workflow actions" |

**Verification Points:**
- [x] Status/workflow_state fields are read-only in form (unless via workflow action)
- [x] `guard_status_changes` prevents manual status bypass
- [x] Only workflow transitions can change status

#### Sub-Test 4: Status After Cancel

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER with Status = "Approved" | - |
| 2 | Cancel ER | `docstatus` = 2 (cancelled) |
| 3 | Check `status` field | Status remains "Approved" (preserved) |
| 4 | Check `workflow_state` | workflow_state remains "Approved" (preserved) |
| 5 | Check cancelled indicator | Red "Cancelled" badge shows |
| 6 | List view | Shows "Cancelled" status/indicator |

**Verification Points:**
- [ ] Status field preserved after cancellation (audit trail)
- [ ] Cancelled badge/indicator shows prominently
- [ ] Cannot change status of cancelled document

#### Sub-Test 5: Status Timestamp Recording

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Submit ER | `submitted_on` timestamp recorded |
| 2 | Level 1 Approve | `level_1_approved_on` timestamp recorded |
| 3 | Level 2 Approve | `level_2_approved_on` timestamp recorded |
| 4 | Reject at any level | `level_X_rejected_on` timestamp recorded |
| 5 | Check all timestamp fields | All populated with correct datetime |
| 6 | Verify timezone | Timestamps in correct timezone |

**Verification Points:**
- [ ] Timestamps recorded for each approval level
- [ ] Rejection timestamps recorded
- [ ] Timestamps are in correct format and timezone
- [ ] Timestamps visible in approval history

#### Sub-Test 6: Status Transition Validation

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | ER Status = "Draft" | Can transition to "Pending Review" via Submit |
| 2 | Status = "Pending Review" | Can transition to "Approved", "Rejected", or "Pending L2/L3" |
| 3 | Status = "Approved" | Can transition to "PI Created" only |
| 4 | Status = "PI Created" | Can transition to "Paid" only |
| 5 | Status = "Rejected" | Cannot transition (terminal state unless reopened) |
| 6 | Status = "Paid" | Cannot transition (terminal state) |

**Verification Points:**
- [ ] Only valid state transitions allowed
- [ ] Invalid transitions blocked with clear error
- [ ] State machine logic enforced

**Quick Reference: Valid Status Transitions**
```
Draft → Pending Review (via Submit)
Pending Review → Pending L2 (via Level 1 Approve)
Pending Review → Pending L3 (via Level 2 Approve) 
Pending Review → Approved (via Final Approve)
Pending Review → Rejected (via Reject)
Approved → PI Created (via Create PI)
PI Created → Paid (via Payment Entry submission)
Any State → Cancelled (via Cancel action)
Rejected → Draft (via Reopen)
```

---

## Attachment & Notes Testing

### Skenario 46: Upload Supporting Document

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Buat ER baru | - |
| 2 | Tab Documents > Upload Attachment | File uploaded |
| 3 | Isi Notes/Description | Notes saved |
| 4 | Save | Attachment & notes tersimpan |

---

### Skenario 47: Tax Invoice Attachment (Manual)

**Kondisi:** Tanpa OCR, upload manual tax invoice

| Step | Action | Expected Result |
|------|--------|-----------------|
| 1 | Enable PPN | - |
| 2 | Isi Tax Invoice Number manual | - |
| 3 | Isi Tax Invoice Date manual | - |
| 4 | Upload Tax Invoice Attachment | File attached |
| 5 | Save | All tax invoice fields saved |

---

## Checklist Testing

### Pre-Testing Checklist
- [ ] Expense Approval Setting sudah dikonfigurasi
- [ ] User approvers sudah dibuat dan aktif
- [ ] Workflow "Expense Request Workflow" aktif
- [ ] Budget Control Settings (jika test budget)
- [ ] Tax templates sudah ada (PPN, PPh)

### Flow Normal Checklist
- [ ] Create & Save ER (Draft)
- [ ] Submit → Pending Review
- [ ] Approve L1 (jika applicable)
- [ ] Approve L2 (jika applicable)
- [ ] Approve L3 (jika applicable)
- [ ] Status = Approved
- [ ] Create Purchase Invoice
- [ ] Status = PI Created
- [ ] Create Payment Entry
- [ ] Status = Paid

### Cancel Flow Checklist
- [ ] Cancel Draft ER (Delete)
- [ ] Cancel Pending Review ER
- [ ] Cancel Approved ER (Budget released)
- [ ] Cancel PI Created ER (Cancel PI first!)
- [ ] Cancel Paid ER (Cancel PE → PI → ER)
- [ ] Amend cancelled ER

### Tax Checklist
- [ ] PPN only
- [ ] PPh only
- [ ] PPN + PPh combined
- [ ] PPnBM (luxury goods tax)
- [ ] Tax Invoice OCR integration
- [ ] WHT category conflict handling

### OCR Validation Checklist
- [ ] NPWP Match (Supplier vs OCR)
- [ ] NPWP Mismatch → Error
- [ ] DPP dalam toleransi → Pass
- [ ] DPP warning zone → Warning only
- [ ] DPP melebihi toleransi → Error
- [ ] PPN dalam toleransi → Pass
- [ ] PPN melebihi toleransi → Error
- [ ] Skip validasi untuk Zero Rated/Exempt
- [ ] ti_dpp_variance tersimpan
- [ ] ti_ppn_variance tersimpan
- [ ] ti_npwp_match tersimpan

### Internal Charge Checklist
- [ ] Generate Internal Charge dari ER
- [ ] View Internal Charge button
- [ ] ICR items match ER items
- [ ] ICR approval required before PI

### Deferred Expense Checklist
- [ ] Enable deferred expense pada item
- [ ] Prepaid account selection
- [ ] Deferred start date
- [ ] Deferred periods
- [ ] Show amortization schedule
- [ ] Validation errors (missing fields)
- [ ] Disabled setting check

### Multiple Items Checklist
- [ ] Multiple line items
- [ ] Different expense accounts per item
- [ ] Item-level PPh (Apply WHT per item)
- [ ] Mixed mode (header vs item PPh)
- [ ] Total calculation correct

### Branch & Allocation Checklist
- [ ] Auto-set branch from cost center
- [ ] Manual branch override
- [ ] Allocation Mode = Direct
- [ ] Allocation Mode = Internal Charge

### UI Actions Checklist
- [ ] Check Approval Route button
- [ ] Create Purchase Invoice button
- [ ] Generate Internal Charge button
- [ ] View Internal Charge button
- [ ] Show Amortization Schedule button

### Print Format Checklist
- [ ] Print preview
- [ ] PDF download
- [ ] Header/logo
- [ ] Items table
- [ ] Tax details
- [ ] Approval info
- [ ] Totals

### Data Integrity Checklist
- [ ] Immutability after approval
- [ ] Protected fields enforcement
- [ ] Attachment upload
- [ ] Notes/description

### Status Field Verification Checklist
- [ ] Status-workflow_state sync (all transitions)
- [ ] Status persistence after page refresh
- [ ] Status display in list view
- [ ] Filter by status works correctly
- [ ] Status badge color coding
- [ ] Cannot manually bypass workflow
- [ ] guard_status_changes enforcement
- [ ] Status preserved after cancellation
- [ ] Timestamps recorded (submitted_on, level_X_approved_on)
- [ ] Rejection timestamps recorded
- [ ] Valid state transitions only
- [ ] Invalid transitions blocked with error
- [ ] Status read-only in form (except via workflow)
- [ ] Cancelled indicator shows correctly

### Budget Control Checklist
- [ ] Budget lock on submit
- [ ] Budget release on reject
- [ ] Budget release on cancel
- [ ] Budget exceed prevention

---

## Quick Reference: Total Calculation

### Formula

```
Subtotal (DPP)  = Sum of all item amounts
Total PPN       = DPP × PPN Rate (from template, default 11%)
Total PPnBM     = From OCR or manual (luxury goods tax)
Total PPh       = PPh Base × PPh Rate (WHT - reduces payable)
─────────────────────────────────────────────────────────────
Total Amount    = Subtotal + PPN + PPnBM - PPh
```

### Example Calculation

| Field | Amount | Notes |
|-------|--------|-------|
| Item 1 | 5,000,000 | |
| Item 2 | 3,000,000 | |
| Item 3 | 2,000,000 | |
| **Subtotal (DPP)** | **10,000,000** | Sum of items |
| PPN 11% | 1,100,000 | DPP × 11% |
| PPnBM | 0 | Not applicable |
| PPh 23 (2%) | (200,000) | WHT - deducted |
| **Total Amount** | **10,900,000** | Net payable |

---

## Quick Reference: Status Flow

```
┌─────────┐    Submit    ┌────────────────┐
│  Draft  │─────────────▶│ Pending Review │
└─────────┘              └───────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    │            │            │
                    ▼            ▼            ▼
              ┌──────────┐  ┌──────────┐  ┌──────────┐
              │ Pending  │  │ Pending  │  │ Rejected │
              │   L2     │  │   L3     │  └──────────┘
              └────┬─────┘  └────┬─────┘
                   │             │
                   ▼             ▼
              ┌──────────────────────┐
              │       Approved       │
              └──────────┬───────────┘
                         │ Create PI
                         ▼
              ┌──────────────────────┐
              │      PI Created      │
              └──────────┬───────────┘
                         │ Payment Entry
                         ▼
              ┌──────────────────────┐
              │         Paid         │
              └──────────────────────┘
```

---

## Quick Reference: Field Dependencies

### Tax Fields Visibility

| Condition | Visible Fields |
|-----------|---------------|
| `is_ppn_applicable` = ✓ | ppn_template, tax_invoice_*, ti_* (OCR fields) |
| `is_pph_applicable` = ✓ | pph_type, pph_base_amount |
| Item `is_deferred_expense` = ✓ | prepaid_account, deferred_start_date, deferred_periods |
| `allocation_mode` = "Allocated via Internal Charge" | internal_charge_request |

### Auto-Calculated Fields

| Field | Calculation |
|-------|-------------|
| `amount` | Sum of item amounts |
| `expense_accounts` | Unique accounts from items |
| `expense_account` | First account (if single) |
| `total_expense` | Same as amount |
| `total_ppn` | From OCR or template calculation |
| `total_pph` | PPh base × PPh rate |
| `total_amount` | DPP + PPN + PPnBM - PPh |
| `pph_base_amount` | Sum of item WHT bases (if item-level) |

---

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| "Approval Route Not Found" | No Expense Approval Setting | Create setting for Cost Center |
| "Only System Manager or Expense Approver can cancel" | Permission issue | Login with correct role |
| "Budget exceeded" | Amount > available budget | Reduce amount or request additional budget |
| "Cannot cancel - linked documents exist" | PI/PE not cancelled | Cancel downstream docs first |
| "NPWP dari OCR tidak sesuai dengan NPWP Supplier" | OCR NPWP ≠ Supplier NPWP | Verify correct supplier or re-upload correct tax invoice |
| "DPP dari OCR berbeda dengan Total Expense" | DPP variance exceeded tolerance | Check expense amount or verify tax invoice is correct |
| "PPN dari OCR berbeda dengan PPN yang dihitung" | PPN variance exceeded tolerance | Check PPN calculation or verify tax invoice |
| "Please verify Tax Invoice before creating PI" | OCR not verified | Verify Tax Invoice OCR Upload first |
| "Deferred Expense is disabled in settings" | Feature disabled | Enable in Expense Deferred Settings |
| "Prepaid Account is required for deferred expense items" | Missing prepaid account | Select valid prepaid account |
| "Prepaid Account {0} is not in deferrable accounts" | Invalid prepaid account | Use account from Expense Deferred Settings |
| "Deferred Start Date required for deferred expense items" | Missing start date | Fill deferred_start_date |
| "Deferred Periods must be > 0 for deferred expense items" | Invalid periods | Set periods > 0 |
| "Cannot modify after approval: {fields}" | Edit protected field after approved | Fields locked after approval |
| "Internal Charge not generated" | Missing ICR for allocation mode | Generate Internal Charge first |
| "No approver configured for level {0}" | Missing approver in setting | Update Expense Approval Setting |
| "You are not authorized to approve at level {0}" | Wrong user trying to approve | Login as correct approver |

---

## 📛 Error Messages Reference

Referensi lengkap semua error messages yang mungkin muncul dan kapan error tersebut di-trigger.

### Permission & Authorization Errors

| Error Message | Title | Trigger Condition | Test Scenario |
|---------------|-------|-------------------|---------------|
| `"Only the creator or an Expense Approver/System Manager can submit."` | - | User bukan creator dan bukan punya role yang diizinkan | Submit ER dengan user lain tanpa role |
| `"Only System Manager or Expense Approver can cancel."` | Not Allowed | User tidak punya role untuk cancel | Cancel ER dengan Accounts User |
| `"No approver configured for level {0}."` | Not Allowed | Approval level tidak punya user assigned | Submit ER dengan approval setting kosong di level tertentu |
| `"You are not authorized to approve at level {0}. Required: {1}."` | Not Allowed | User mencoba approve tapi bukan approver yang ditentukan | User berbeda mencoba approve |

### Approval Route Errors

| Error Message | Title | Trigger Condition | Test Scenario |
|---------------|-------|-------------------|---------------|
| `"Please configure Expense Approval Setting for cost center: {cost_center}"` | Approval Route Not Found | Tidak ada Expense Approval Setting untuk Cost Center | Submit ER tanpa approval setting |
| `"Invalid approvers: Users not found: Level {level}: {user}. Update Expense Approval Setting."` | - | Approver user tidak ditemukan di sistem | User di approval setting tidak exist |
| `"Invalid approvers: Users disabled: Level {level}: {user}. Update Expense Approval Setting."` | - | Approver user di-disable | User di approval setting status disabled |

### Budget Control Errors

| Error Message | Title | Trigger Condition | Test Scenario |
|---------------|-------|-------------------|---------------|
| `"Budget control operation failed during submission. Error: {0}"` | Budget Control Error | Error saat reservasi budget waktu submit | Submit ER dengan budget tidak cukup |
| `"Budget control operation failed. Workflow action cannot be completed. Error: {0}"` | Budget Control Error | Error saat update budget di workflow action | Error internal budget system |
| `"Failed to release budget. Cancel operation cannot proceed. Error: {0}"` | Budget Release Error | Error saat release budget waktu cancel | Cancel ER dengan error budget |
| `"Required document not found during budget control. Please check your setup. Error: {0}"` | Document Not Found | Document terkait tidak ditemukan | Budget setting tidak lengkap |
| `"Error in budget workflow: {0}"` | Budget Workflow Error | General budget workflow error | Budget calculation error |

### Tax Invoice OCR Validation Errors

| Error Message | Title | Trigger Condition | Test Scenario |
|---------------|-------|-------------------|---------------|
| `"NPWP from OCR ({ocr_npwp}) does not match Supplier NPWP ({supplier_npwp})"` | Tax Invoice Validation Error | NPWP dari OCR ≠ NPWP Supplier | Upload faktur dengan NPWP berbeda |
| `"DPP dari OCR ({ocr_dpp}) berbeda dengan Total Expense ({expected_dpp}). Selisih: {variance} atau {pct}% (toleransi: {tol_idr} atau {tol_pct}%)"` | Tax Invoice Validation Error | DPP variance > kedua toleransi | Upload faktur dengan DPP berbeda jauh |
| `"PPN dari OCR ({ocr_ppn}) berbeda dengan PPN yang dihitung ({expected_ppn}). Selisih: {variance} atau {pct}% (toleransi: {tol_idr} atau {tol_pct}%)"` | Tax Invoice Validation Error | PPN variance > kedua toleransi | Upload faktur dengan PPN berbeda jauh |
| `"PPN on Expense Request ({manual_ppn}) differs from OCR Faktur Pajak ({ti_ppn}) by more than {tolerance}."` | - | PPN manual vs OCR berbeda melebihi tolerance | Manual PPN ≠ OCR PPN |

### Deferred Expense Errors

| Error Message | Title | Trigger Condition | Test Scenario |
|---------------|-------|-------------------|---------------|
| `"Deferred Expense is disabled in settings."` | - | Item dengan is_deferred_expense=1 tapi setting disabled | Enable deferred pada item saat setting off |
| `"Prepaid Account is required for deferred expense items."` | - | Item deferred tanpa prepaid account | Centang deferred tanpa isi prepaid |
| `"Prepaid Account {0} is not in deferrable accounts. Valid accounts: {1}"` | - | Prepaid account tidak terdaftar | Pilih prepaid account yang tidak valid |
| `"Deferred Start Date required for deferred expense items."` | - | Item deferred tanpa start date | Tidak isi start date |
| `"Deferred Periods must be > 0 for deferred expense items."` | - | Periods ≤ 0 | Isi periods = 0 atau negatif |

### Data Integrity Errors

| Error Message | Title | Trigger Condition | Test Scenario |
|---------------|-------|-------------------|---------------|
| `"Cannot modify after approval: {fields}"` | - | Edit field kunci setelah status Approved/PI Created/Paid | Edit supplier setelah approved |

### Warning Messages (Non-Blocking)

| Warning Message | Title | Trigger Condition | Indicator |
|-----------------|-------|-------------------|-----------|
| `"⚠️ DPP dari OCR berbeda {variance} atau {pct}% (masih dalam toleransi)"` | Tax Invoice Validation Warning | DPP variance > salah satu toleransi tapi tidak kedua-duanya | Orange |
| `"⚠️ PPN dari OCR berbeda {variance} atau {pct}% (masih dalam toleransi)"` | Tax Invoice Validation Warning | PPN variance > salah satu toleransi tapi tidak kedua-duanya | Orange |

---

## 🧪 Error Message Testing Checklist

### Permission Errors Testing

| # | Error | Test Steps | Expected | ✓ |
|---|-------|------------|----------|---|
| E1 | Submit permission | 1. Login user tanpa role<br>2. Buka ER milik user lain<br>3. Submit | Error: "Only the creator..." | ☐ |
| E2 | Cancel permission | 1. Login Accounts User<br>2. Buka submitted ER<br>3. Cancel | Error: "Only System Manager..." | ☐ |
| E3 | Approve unauthorized | 1. Submit ER (approver: user_a)<br>2. Login sebagai user_b<br>3. Approve | Error: "You are not authorized..." | ☐ |

### Approval Route Errors Testing

| # | Error | Test Steps | Expected | ✓ |
|---|-------|------------|----------|---|
| E4 | No approval setting | 1. Buat Cost Center baru<br>2. Buat ER untuk CC tersebut<br>3. Submit | Error: "Approval Route Not Found" | ☐ |
| E5 | Approver not found | 1. Set approver = nonexistent@user.com<br>2. Submit ER | Error: "Users not found..." | ☐ |
| E6 | Approver disabled | 1. Disable user di approval setting<br>2. Submit ER | Error: "Users disabled..." | ☐ |
| E7 | No approver at level | 1. Set level_1_user = kosong di setting<br>2. Submit ER | Error: "No approver configured..." | ☐ |

### Tax Invoice OCR Errors Testing

| # | Error | Test Steps | Expected | ✓ |
|---|-------|------------|----------|---|
| E8 | NPWP mismatch | 1. Supplier NPWP: 01.234.567.8-901.000<br>2. Upload OCR dengan NPWP: 99.999.999.9-999.000<br>3. Submit | Error: "NPWP dari OCR...tidak sesuai" | ☐ |
| E9 | DPP variance exceeded | 1. ER amount = 1,000,000<br>2. OCR DPP = 1,100,000 (10% diff)<br>3. Submit | Error: "DPP dari OCR...berbeda" | ☐ |
| E10 | PPN variance exceeded | 1. Expected PPN = 110,000<br>2. OCR PPN = 150,000<br>3. Submit | Error: "PPN dari OCR...berbeda" | ☐ |

### Budget Errors Testing

| # | Error | Test Steps | Expected | ✓ |
|---|-------|------------|----------|---|
| E11 | Budget exceeded | 1. Set budget = 5,000,000<br>2. Buat ER = 7,000,000<br>3. Submit | Error: Budget control failed | ☐ |
| E12 | Budget release failed | 1. Corrupt budget ledger entry<br>2. Cancel ER | Error: "Failed to release budget" | ☐ |

### Deferred Expense Errors Testing

| # | Error | Test Steps | Expected | ✓ |
|---|-------|------------|----------|---|
| E13 | Deferred disabled | 1. Disable deferred di settings<br>2. Centang is_deferred di item<br>3. Save | Error: "Deferred Expense is disabled" | ☐ |
| E14 | No prepaid account | 1. Centang is_deferred<br>2. Tidak isi prepaid_account<br>3. Save | Error: "Prepaid Account is required" | ☐ |
| E15 | Invalid prepaid account | 1. Isi prepaid dengan akun yang tidak terdaftar<br>2. Save | Error: "not in deferrable accounts" | ☐ |
| E16 | No deferred start date | 1. Centang is_deferred, isi prepaid<br>2. Tidak isi start_date<br>3. Save | Error: "Deferred Start Date required" | ☐ |
| E17 | Invalid periods | 1. Isi semua deferred fields<br>2. Set periods = 0<br>3. Save | Error: "Deferred Periods must be > 0" | ☐ |

### Data Integrity Errors Testing

| # | Error | Test Steps | Expected | ✓ |
|---|-------|------------|----------|---|
| E18 | Modify after approval | 1. Approve ER sampai status = Approved<br>2. Edit supplier field<br>3. Save | Error: "Cannot modify after approval" | ☐ |

### Warning Messages Testing

| # | Warning | Test Steps | Expected | ✓ |
|---|---------|------------|----------|---|
| W1 | DPP warning zone | 1. ER amount = 10,000,000<br>2. OCR DPP = 10,015,000 (0.15%)<br>3. Submit | Warning (orange) + proceed | ☐ |
| W2 | PPN warning zone | 1. Expected PPN = 1,100,000<br>2. OCR PPN = 1,108,000 (0.7%)<br>3. Submit | Warning (orange) + proceed | ☐ |

---

## 🎉 Recent Implementation Updates (January 2026)

### ✅ Fix #1: NPWP Match Verification Flag
**File:** `imogi_finance/imogi_finance/doctype/expense_request/expense_request.py`

Implemented automatic setting of `ti_npwp_match` field when NPWP validation passes successfully.

- **Behavior:** Field `ti_npwp_match` automatically set to 1 when OCR NPWP matches Supplier NPWP
- **Purpose:** Proper tracking of verification status for audit trail
- **Test Scenario:** See [Skenario 19a](#skenario-19a-npwp-cocok-)

---

### ✅ Fix #2: Hybrid Cancel Validation (Smart Guidance)
**File:** `imogi_finance/imogi_finance/doctype/expense_request/expense_request.py`

Implemented intelligent cancel validation that prevents accidental cancellation while preserving flexibility.

**Features:**
- ✅ Checks for linked Purchase Invoice and Payment Entry before cancel
- ✅ Shows clear, helpful error message with 2 options:
  1. Manual cancellation in reverse order (PE → PI → ER)
  2. Use "Cancel All Linked Documents" feature (recommended)
- ✅ Best of both worlds: Safety + Flexibility

**Test Scenarios:**
- [Skenario 14](#skenario-14-cancel-er-dengan-pi-created-guided-cancellation-) - Cancel with PI
- [Skenario 15](#skenario-15-cancel-er-yang-sudah-paid-full-reversal) - Cancel with PE + PI

---

### ✅ Fix #3: Improved Duplicate PI Prevention
**File:** `imogi_finance/imogi_finance/doctype/expense_request/expense_request.js`

Enhanced "Create Purchase Invoice" button visibility logic to handle cancelled/deleted PI scenarios.

**Smart Behavior:**
- ❌ **Button HIDDEN** when active PI exists (docstatus = 1)
- ✅ **Button VISIBLE** when PI is cancelled (docstatus = 2) → Can create new PI
- ✅ **Button VISIBLE** when PI is deleted → Can create new PI
- ✅ Backend validation still prevents duplicates via API

**Test Scenario:** See [Skenario 29](#skenario-29-duplicate-pi-prevention-) (includes 3 sub-scenarios)

---

### 🔄 Error Messages Language Update
All new error messages are now in **English** for consistency:
- "NPWP from OCR does not match Supplier NPWP"
- "Cannot cancel Expense Request - linked documents exist..."
- "Linked Documents Exist" (title)

---

**Last Updated:** January 23, 2026  
**Module Version:** IMOGI Finance v1.x
**Implementation Status:** 3 Critical Fixes Completed ✅
