# Expense Claim Integration Module

## Overview

Modul ini menyediakan fitur advance payment (uang muka) yang terintegrasi dengan ERPNext native Payment Ledger untuk Employee Expense Claims.

## Features

### 1. Advance Payment Dashboard
- **Report Location**: `FINANCE IMOGI > Advance Payment > Advance Payment Dashboard`
- **Purpose**: Monitoring uang muka karyawan yang belum dialokasikan
- **Features**:
  - Lihat semua advance payment untuk Employee
  - Filter berdasarkan Company, Date Range, Party Type, Party, Account
  - Menampilkan amount, allocated amount, dan outstanding amount
  - Total row untuk summary

### 2. Expense Claim Integration
- **Auto-linking**: Ketika Expense Claim di-submit, sistem otomatis menghubungkan dengan employee advances yang tersedia
- **Manual linking**: Button "Link Employee Advances" untuk manual allocation
- **View advances**: Button "View Employee Advances" untuk melihat advances karyawan

### 3. Employee Advance Management
- Tracking advance yang sudah dialokasi
- Menampilkan outstanding advance di form
- Alert notification untuk available advances

## Installation

Modul ini sudah terdaftar di hooks.py:

```python
# Doc Events
doc_events = {
    "Expense Claim": {
        "on_submit": "imogi_finance.expense_claim_integration.expense_claim_advances.link_employee_advances",
    }
}

# Doctype JS
doctype_js = {
    "Expense Claim": [
        "public/js/expense_claim.js",
        "public/js/payment_reconciliation_helper.js",
    ]
}
```

## Usage Guide

### Memberikan Advance ke Karyawan

1. Buat **Payment Entry** dengan:
   - Party Type: `Employee`
   - Party: Pilih karyawan
   - Payment Type: `Pay`
   - Paid Amount: Jumlah advance

2. Submit Payment Entry
   - Payment Ledger Entry akan otomatis dibuat
   - Status: Unallocated advance

### Mengalokasikan Advance ke Expense Claim

#### Otomatis (Recommended)
1. Buat dan Submit **Expense Claim**
2. Sistem akan otomatis mengalokasikan available advances ke expense claim
3. Payment Ledger Entry akan di-update

#### Manual
1. Buka submitted Expense Claim
2. Klik **Tools > Link Employee Advances**
3. Sistem akan mencari dan mengalokasikan advances

### Monitoring Advances

1. Buka **Advance Payment Dashboard**
2. Set filter:
   - Company (mandatory)
   - Date range (optional)
   - Party Type: Employee
   - Party: Pilih karyawan (optional)
3. View outstanding advances

## Technical Details

### File Structure
```
imogi_finance/
├── expense_claim_integration/
│   ├── __init__.py
│   ├── advance_dashboard_report.py
│   ├── expense_claim_advances.py
│   └── report/
│       ├── __init__.py
│       └── advance_payment_dashboard/
│           ├── __init__.py
│           ├── advance_payment_dashboard.json
│           └── advance_payment_dashboard.py
├── public/
│   └── js/
│       └── expense_claim.js
```

### Database Schema
Menggunakan ERPNext native **Payment Ledger Entry**:
- `voucher_type`: "Payment Entry" untuk advance
- `voucher_no`: Payment Entry name
- `party_type`: "Employee"
- `party`: Employee ID
- `against_voucher_type`: "" untuk unallocated, "Expense Claim" untuk allocated
- `against_voucher_no`: Expense Claim name setelah allocated
- `amount`: Amount advance

### Key Functions

#### `get_employee_advances(employee, company)`
Mendapatkan list advances yang tersedia untuk employee

#### `get_allocated_advances(expense_claim)`
Mendapatkan advances yang sudah dialokasi ke expense claim

#### `link_employee_advances(doc, method=None)`
Hook function untuk auto-allocate advances saat expense claim submit

## Testing

### Test Scenario 1: Basic Advance Payment
1. Create Payment Entry (Employee advance: Rp 1,000,000)
2. Verify in Advance Payment Dashboard
3. Create Expense Claim (Total: Rp 800,000)
4. Submit Expense Claim
5. Verify allocation in dashboard (Outstanding: Rp 200,000)

### Test Scenario 2: Multiple Advances
1. Create 2 Payment Entries (Rp 500,000 each)
2. Create Expense Claim (Total: Rp 1,200,000)
3. Submit - both advances should be fully allocated
4. Verify outstanding is 0

### Test Scenario 3: Partial Allocation
1. Create Payment Entry (Rp 1,000,000)
2. Create Expense Claim (Total: Rp 600,000)
3. Submit - partial allocation
4. Create another Expense Claim (Rp 400,000)
5. Submit - remaining should be fully allocated

## Troubleshooting

### Advance tidak muncul di dashboard
- Pastikan Payment Entry sudah submitted
- Pastikan Party Type = Employee
- Check filter Company

### Auto-allocation tidak bekerja
- Pastikan hook terdaftar di hooks.py
- Check bench restart sudah dilakukan
- Verify employee di Payment Entry sama dengan di Expense Claim

### Error saat allocate
- Check Payment Entry masih available (tidak fully allocated)
- Verify employee matches
- Check docstatus = 1 (submitted)

## API Reference

### Whitelisted Methods

```python
# Get employee advances
frappe.call({
    method: 'imogi_finance.expense_claim_integration.expense_claim_advances.get_employee_advances',
    args: {
        employee: 'EMP-00001',
        company: 'My Company'
    }
})

# Get allocated advances
frappe.call({
    method: 'imogi_finance.expense_claim_integration.expense_claim_advances.get_allocated_advances',
    args: {
        expense_claim: 'EXP-00001'
    }
})
```

## Future Enhancements

1. Multi-currency support
2. Advance request workflow
3. Budget integration
4. Email notifications
5. Mobile app support

## Support

For issues or questions:
- Create issue di GitHub repository
- Contact: imogi.indonesia@gmail.com

## License

MIT License - Copyright (c) 2026 Imogi
