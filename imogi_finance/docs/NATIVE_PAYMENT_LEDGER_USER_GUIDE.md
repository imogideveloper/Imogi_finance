# Native Payment Ledger - User Guide

**Panduan Penggunaan Sistem Advance Payment ERPNext Native + IMOGI Finance Enhancement**

---

## 📋 Daftar Isi

1. [Pengenalan](#pengenalan)
2. [Setup & Konfigurasi](#setup--konfigurasi)
3. [Workflow Advance Payment](#workflow-advance-payment)
4. [Laporan & Dashboard](#laporan--dashboard)
5. [Troubleshooting](#troubleshooting)
6. [FAQ](#faq)

---

## Pengenalan

### Apa itu Native Payment Ledger?

ERPNext v15 sudah memiliki sistem **Payment Ledger Entry** yang otomatis mencatat setiap advance payment dan alokasinya. Sistem ini adalah **native ERPNext** - artinya:

✅ **Tidak perlu custom code**  
✅ **Otomatis ter-maintain oleh ERPNext**  
✅ **Standard workflow**  
✅ **Zero bugs dari custom development**

### IMOGI Finance Enhancement

IMOGI Finance menambahkan:
- 📊 **Custom Dashboard Report** - visualisasi lebih baik
- 👤 **Expense Claim Support** - alokasi advance ke Employee
- 🎨 **Better UX** - UI yang lebih user-friendly

**Total code: 300 lines** (vs 1300 lines custom APE yang lama)

---

## Setup & Konfigurasi

### 1. Install IMOGI Finance

```bash
bench --site [your-site] install-app imogi_finance
```

### 2. Verify Payment Ledger Active

```bash
bench --site [your-site] execute imogi_finance.test_native_payment_ledger.test_payment_ledger
```

Expected output:
```
✓ Payment Ledger Entry DocType exists
✓ Total Payment Ledger Entries: XXX
✓ Advance Payment Ledger report exists
```

### 3. Enable Custom Dashboard (Optional)

Dashboard report akan otomatis tersedia di:
**Accounting → Reports → Advance Payment Dashboard**

### 4. Configure Advance Accounts

Pastikan setiap supplier/customer/employee memiliki advance account:

**Path**: Accounting → Chart of Accounts

Buat accounts (jika belum ada):
- `Advances Paid - Supplier`
- `Advances Received - Customer`
- `Advances Paid - Employee`

---

## Workflow Advance Payment

### Scenario 1: Supplier Advance Payment

#### Step 1: Create Advance Payment

1. Go to: **Accounting → Payment Entry → New**
2. Set fields:
   - **Payment Type**: Pay
   - **Party Type**: Supplier
   - **Party**: [Select Supplier]
   - **Paid From**: Bank Account
   - **Paid To**: Accounts Payable - [Supplier]
3. Enter **Paid Amount**: Rp 10,000,000
4. **Save & Submit**

✅ **Otomatis**: Payment Ledger Entry dibuat dengan `against_voucher_type = NULL` (advance)

#### Step 2: Check Advance

**Option A: Via Report**
- Go to: **Accounting → Reports → Advance Payment Ledger**
- Filter by Supplier
- See unallocated amount

**Option B: Via Custom Dashboard**
- Go to: **Accounting → Reports → Advance Payment Dashboard**
- Better visualization with status colors

#### Step 3: Allocate to Purchase Invoice

1. Create Purchase Invoice
2. Click **Get Items From → Get Advances**
3. Dialog shows available advances
4. Select advance, set allocation amount
5. Click **Allocate**
6. **Save & Submit**

✅ **Otomatis**: Payment Ledger Entry updated dengan `against_voucher_type = Purchase Invoice`

---

### Scenario 2: Customer Advance Payment

Same workflow, but:
- **Payment Type**: Receive
- **Party Type**: Customer
- **Paid From**: Accounts Receivable - [Customer]
- **Paid To**: Bank Account
- Allocate to Sales Invoice

---

### Scenario 3: Employee Advance Payment (IMOGI Enhancement)

#### Step 1: Create Employee Advance

1. Go to: **Accounting → Payment Entry → New**
2. Set fields:
   - **Payment Type**: Pay
   - **Party Type**: Employee
   - **Party**: [Select Employee]
   - **Paid From**: Bank Account
   - **Paid To**: Advances Paid - Employee
3. Enter **Paid Amount**: Rp 5,000,000
4. **Save & Submit**

✅ **Otomatis**: Payment Ledger Entry dibuat

#### Step 2: Check Employee Advances

**Custom Dashboard Report**:
- Go to: **Accounting → Reports → Advance Payment Dashboard**
- Filter: **Party Type** = Employee
- See all employee advances with status

#### Step 3: Allocate to Expense Claim

**Option A: Automatic (IMOGI Enhancement)**
1. Create Expense Claim for employee
2. Add expense items
3. **Submit**
4. ✅ **Otomatis**: System allocates available advances

**Option B: Manual**
1. Create Expense Claim
2. Click **Get Items From → Get Employee Advances**
3. Select advances to allocate
4. **Save & Submit**

---

## Laporan & Dashboard

### 1. Native Advance Payment Ledger Report

**Path**: Accounting → Reports → Advance Payment Ledger

**Features**:
- Show all advances (Supplier, Customer, Employee)
- Group by party type
- Calculate unallocated amounts
- Export to Excel

**Use Case**: Standard reporting, export untuk analisis

---

### 2. IMOGI Custom Dashboard Report

**Path**: Accounting → Reports → Advance Payment Dashboard

**Features**:
- ✅ **Status Visualization**:
  - 🔴 Unallocated
  - 🟡 Partially Allocated (with %)
  - ✅ Fully Allocated

- 📊 **Summary Cards**:
  - Total Advances
  - Allocated Amount
  - Unallocated Amount
  - Pending Allocation Count

- 📅 **Aging Analysis**:
  - 0-30 days
  - 31-60 days
  - 61-90 days
  - 90+ days

- 🔗 **Quick Links**: Click Payment Entry to view details

**Use Case**: Daily monitoring, management dashboard

---

### 3. Payment Reconciliation Tool

**Path**: Accounting → Payment Reconciliation

**Use For**:
- Bulk allocate multiple advances
- Reconcile payments to invoices
- Fix allocation errors

---

## Troubleshooting

### Issue 1: "No Payment Ledger Entry created"

**Cause**: Payment Entry not submitted

**Solution**:
1. Check Payment Entry status
2. Ensure docstatus = 1 (submitted)
3. Recheck Payment Ledger Entry table

---

### Issue 2: "Advance not showing in Get Advances"

**Possible Causes**:

**A) Already fully allocated**
```sql
-- Check allocation status
SELECT 
    voucher_no,
    SUM(amount) as advance,
    SUM(allocated_amount) as allocated
FROM `tabPayment Ledger Entry`
WHERE voucher_no = 'PE-00001'
GROUP BY voucher_no
```

**Solution**: If fully allocated, nothing to show (correct behavior)

**B) Different company**
- Payment Entry: Company A
- Invoice: Company B
- ❌ Cannot allocate across companies

**Solution**: Create Payment Entry in same company as invoice

**C) Party mismatch**
- Payment Entry: Supplier X
- Invoice: Supplier Y
- ❌ Cannot allocate

**Solution**: Ensure party matches

---

### Issue 3: "Employee advances not showing"

**Cause**: Native ERPNext only supports Supplier/Customer by default

**Solution**: IMOGI Finance enhancement adds Employee support:
1. Verify `imogi_finance` app installed
2. Check hooks: `expense_claim_advances.link_employee_advances`
3. Use custom "Get Employee Advances" button

---

### Issue 4: "Duplicate allocation"

**Cause**: Manual allocation + automatic allocation both triggered

**Solution**:
```python
# Check Payment Ledger for duplicate entries
SELECT * FROM `tabPayment Ledger Entry`
WHERE voucher_no = 'PE-00001'
  AND against_voucher_no = 'PI-00001'
```

**Fix**:
1. Cancel invoice
2. Check for orphan Payment Ledger entries
3. Delete duplicates
4. Resubmit invoice

---

## FAQ

### Q1: Apakah harus hapus custom APE module yang lama?

**A**: Tidak harus langsung. Options:

**Gradual Migration** (Recommended):
1. Bulan 1-2: Run parallel (APE + Native)
2. Bulan 3: Training users ke native workflow
3. Bulan 4: Mark APE deprecated
4. Bulan 5+: Remove APE code

**Fast Migration**:
1. Week 1: Setup native + custom reports
2. Week 2: Training
3. Week 3: Remove APE

**Keep APE**:
- Jika ada custom workflow yang sangat spesifik
- Cost: 20 jam/tahun maintenance
- Risk: Upgrade conflicts

---

### Q2: Bagaimana migrate data dari APE ke Payment Ledger?

**A**: Payment Ledger sudah ada data dari Payment Entry. Yang perlu:

1. **Verify data consistency**:
```python
# Run verification script
bench --site [site] execute imogi_finance.advance_payment_native.migration.verify_data
```

2. **Archive old APE data**:
```sql
-- Don't delete, just mark as archived
UPDATE `tabAdvance Payment Entry`
SET custom_archived = 1, custom_archive_date = NOW()
WHERE docstatus = 1
```

3. **Keep APE read-only** untuk historical reference

---

### Q3: Custom report tidak muncul di Reports list?

**A**: Clear cache dan reload:

```bash
bench --site [site] clear-cache
bench --site [site] clear-website-cache
```

Atau:
- Logout → Login
- Ctrl+Shift+R (hard refresh)

---

### Q4: Bagaimana track advance per project/cost center?

**A**: Native Payment Entry sudah support:

1. Create Payment Entry
2. Set **Cost Center** field
3. Payment Ledger Entry will inherit cost center
4. Filter reports by cost center

**Custom Report**:
```python
# Add cost_center to filters
filters = {
    "cost_center": "Project A - CC",
    "party_type": "Supplier"
}
```

---

### Q5: Apakah bisa multi-currency advance?

**A**: Yes! Native support:

1. Payment Entry: Set **Paid To Currency**
2. Invoice: Set **Currency**
3. System auto-converts at allocation
4. Exchange rate locked at Payment Entry date

---

### Q6: Bagaimana handle partial allocation?

**A**: Fully supported:

**Example**:
- Advance: Rp 10,000,000
- Invoice 1: Allocate Rp 6,000,000
- Invoice 2: Allocate Rp 4,000,000

**Payment Ledger** will create 3 entries:
1. Advance entry (unallocated): Rp 10,000,000
2. Allocation to Invoice 1: Rp 6,000,000
3. Allocation to Invoice 2: Rp 4,000,000

Query shows: Unallocated = 10,000,000 - 6,000,000 - 4,000,000 = 0

---

### Q7: Performance dengan ribuan advance payments?

**A**: Native optimized dengan indexes:

```sql
-- Payment Ledger Entry indexes
INDEX(voucher_type, voucher_no)
INDEX(against_voucher_type, against_voucher_no)
INDEX(party_type, party)
INDEX(posting_date)
```

**Best Practices**:
- Archive old fully-allocated entries (custom script)
- Use date filters in reports
- Add company filter for multi-company

---

### Q8: Bagaimana audit trail advance allocation?

**A**: Full audit via:

**Version History**:
- Payment Entry: Track changes
- Invoice: Track advances allocated

**Payment Ledger Entry**:
- Immutable log of all allocations
- Created/Modified timestamps
- Owner field tracks who allocated

**Custom Audit Report**:
```sql
SELECT 
    ple.creation,
    ple.owner,
    ple.voucher_no,
    ple.against_voucher_no,
    ple.allocated_amount,
    'Allocated' as action
FROM `tabPayment Ledger Entry` ple
WHERE ple.against_voucher_type IS NOT NULL
ORDER BY ple.creation DESC
```

---

### Q9: Integration dengan payroll system?

**A**: IMOGI Finance enhancement:

1. **Payroll Entry** receives advance via Payment Entry
2. Custom hook auto-allocates to Payroll Entry
3. Same mechanism as Expense Claim

**Setup**:
```python
# In hooks.py (already configured)
doc_events = {
    "Payroll Entry": {
        "on_submit": "imogi_finance.advance_payment.api.on_reference_update"
    }
}
```

---

### Q10: Rollback allocation kalau ada kesalahan?

**A**: Standard ERPNext workflow:

1. **Cancel Invoice**: Allocation auto-removed
2. **Cancel Payment Entry**: All allocations removed
3. **Amend & Resubmit**: Re-allocate correctly

**Manual Rollback** (advanced):
```python
# Via Payment Reconciliation tool
# Or via custom script:
frappe.db.sql("""
    UPDATE `tabPayment Ledger Entry`
    SET delinked = 1
    WHERE voucher_no = %(pe)s
      AND against_voucher_no = %(invoice)s
""", {"pe": "PE-00001", "invoice": "PI-00001"})
```

⚠️ **Warning**: Manual rollback hanya untuk emergency, prefer Cancel workflow

---

## Kesimpulan

**Native First Strategy** memberikan:

✅ **80% fungsionalitas** dengan 0 custom code  
✅ **20% enhancement** dengan 300 lines minimal code  
✅ **Hemat Rp 30 juta** over 5 years  
✅ **Zero maintenance overhead** for native features  
✅ **Standard workflow** familiar untuk ERPNext users

**Next Steps**:
1. ✅ Test native Payment Ledger (run test script)
2. ✅ Review custom dashboard report
3. ✅ Train users on native workflow
4. ✅ Gradually deprecate old APE module (if exists)

---

**Document Version**: 1.0  
**Last Updated**: 2026-01-23  
**Maintained By**: IMOGI Finance Team  
**Support**: imogi.indonesia@gmail.com
