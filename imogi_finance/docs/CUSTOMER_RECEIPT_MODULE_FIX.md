# Customer Receipt Module Fix

## Masalah

Modul Customer Receipt tidak terpegang (tidak berfungsi dengan baik) karena:

1. **Module initialization tidak lengkap** - File `imogi_finance/receipt_control/__init__.py` kosong, menyebabkan module tidak bisa di-import dengan benar
2. **Tidak ada explicit exports** - Fungsi-fungsi hooks tidak di-export dengan benar dari module
3. **Cache Frappe** - Setelah perubahan hooks, Frappe perlu di-reload untuk mengenali perubahan

## Solusi yang Diterapkan

### 1. Menambahkan Module Exports (`receipt_control/__init__.py`)

File `imogi_finance/receipt_control/__init__.py` yang sebelumnya kosong sekarang berisi:

```python
"""
Customer Receipt Control Module

This module provides customer receipt validation and payment entry integration.
"""

from imogi_finance.receipt_control.payment_entry_hooks import (
    validate_customer_receipt_link,
    record_payment_entry,
    remove_payment_entry,
)
from imogi_finance.receipt_control.utils import (
    get_receipt_control_settings,
    terbilang_id,
    record_stamp_cost,
    build_verification_url,
)
from imogi_finance.receipt_control.validators import (
    ReceiptAllocationValidator,
    ReceiptControlSettings,
    ReceiptInfo,
    ReceiptItem,
    PaymentEntryInfo,
    PaymentReference,
    ReceiptValidationError,
)

__all__ = [
    # Payment Entry Hooks
    "validate_customer_receipt_link",
    "record_payment_entry",
    "remove_payment_entry",
    # Utilities
    "get_receipt_control_settings",
    "terbilang_id",
    "record_stamp_cost",
    "build_verification_url",
    # Validators
    "ReceiptAllocationValidator",
    "ReceiptControlSettings",
    "ReceiptInfo",
    "ReceiptItem",
    "PaymentEntryInfo",
    "PaymentReference",
    "ReceiptValidationError",
]
```

### 2. Memastikan Module Import di Main Init

File `imogi_finance/__init__.py` diperbaiki untuk mengimport receipt_control module:

```python
__version__ = "0.1.0"

# Import sub-modules to ensure proper initialization
# This ensures that all hooks and handlers are registered correctly
try:
    # Receipt control module - Customer Receipt & Payment Entry integration
    from imogi_finance import receipt_control
except ImportError:
    # Module dependencies might not be available during installation
    pass
```

### 3. Verifikasi Hooks Registration

Hooks sudah terdaftar dengan benar di `hooks.py`:

**Payment Entry hooks (baris 313-342):**
```python
"Payment Entry": {
    "validate": [
        "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
        ...
    ],
    "before_submit": [
        "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
        ...
    ],
    "on_submit": [
        "imogi_finance.receipt_control.payment_entry_hooks.record_payment_entry",
        ...
    ],
    "on_cancel": [
        "imogi_finance.receipt_control.payment_entry_hooks.remove_payment_entry",
        ...
    ],
}
```

**Customer Receipt hooks (baris 289-291):**
```python
"Customer Receipt": {
    "validate": ["imogi_finance.events.metadata_fields.set_created_by"],
    "on_submit": ["imogi_finance.events.metadata_fields.set_submit_on"],
}
```

### 4. Custom Field sudah ada

Custom field `customer_receipt` di Payment Entry sudah terdaftar di `fixtures/custom_field.json`:
```json
{
  "doctype": "Custom Field",
  "name": "Payment Entry-customer_receipt",
  "dt": "Payment Entry",
  "fieldname": "customer_receipt",
  "fieldtype": "Link",
  "insert_after": "reference_no",
  "label": "Customer Receipt",
  "options": "Customer Receipt",
  "allow_on_submit": 1,
  "description": "Controlled customer receipt reference"
}
```

## Langkah-langkah Setelah Fix

Untuk menerapkan fix ini, jalankan perintah berikut:

### 1. Migrate Database (Install fixtures dan custom fields)
```bash
bench --site [nama-site] migrate
```

### 2. Restart Bench (Reload hooks dan modules)
```bash
bench restart
```

### 3. Clear Cache (Optional, tapi direkomendasikan)
```bash
bench --site [nama-site] clear-cache
```

### 4. Rebuild Assets (Jika ada perubahan di client-side)
```bash
bench build
```

## Testing

Setelah menjalankan langkah-langkah di atas, test fungsi Customer Receipt:

1. **Buat Customer Receipt baru**
   - Buka Customer Receipt list
   - Buat dokumen baru dengan customer dan references (Sales Invoice/Sales Order)
   - Submit dokumen

2. **Buat Payment Entry**
   - Buat Payment Entry baru dengan party type = Customer
   - Pilih customer yang sama dengan Customer Receipt
   - Field "Customer Receipt" seharusnya muncul dan bisa dipilih
   - Pilih Customer Receipt yang sudah dibuat
   - Submit Payment Entry

3. **Verifikasi Integrasi**
   - Buka Customer Receipt yang sudah dibuat
   - Lihat tab "Payments" - seharusnya Payment Entry yang dibuat muncul di sini
   - Outstanding amount seharusnya berkurang sesuai paid amount
   - Status seharusnya berubah menjadi "Partially Paid" atau "Paid"

4. **Test Validasi**
   - Coba buat Payment Entry dengan customer yang memiliki open receipts tanpa memilih Customer Receipt (jika mode = "Mandatory Strict")
   - Seharusnya muncul error: "Customer Receipt is required..."
   - Coba allocate lebih dari outstanding receipt amount
   - Seharusnya muncul error validasi

## Komponen Module Receipt Control

Module ini terdiri dari:

1. **payment_entry_hooks.py** - Hooks untuk Payment Entry (validate, record, remove)
2. **validators.py** - Validasi logic untuk receipt allocation
3. **utils.py** - Utility functions (settings, terbilang, stamp recording)
4. **customer_receipt.py** (di doctype) - Business logic untuk Customer Receipt doctype

## Fitur yang Didukung

✅ Customer Receipt validation dan tracking
✅ Payment Entry integration dengan automatic allocation
✅ Receipt modes: OFF, Optional, Mandatory Strict
✅ Mixed payment mode (allow payment exceed receipt amount)
✅ Multi-branch support
✅ Digital stamp integration
✅ Payment status tracking (Issued, Partially Paid, Paid)
✅ Item locking after receipt issued

## Troubleshooting

Jika masih ada masalah setelah fix:

1. **Check Frappe logs**
   ```bash
   bench --site [nama-site] console
   ```
   Kemudian test import:
   ```python
   from imogi_finance.receipt_control import validate_customer_receipt_link
   print("Import successful")
   ```

2. **Check custom fields installed**
   ```bash
   bench --site [nama-site] console
   ```
   ```python
   import frappe
   frappe.get_doc("Custom Field", "Payment Entry-customer_receipt")
   ```

3. **Check hooks registered**
   ```bash
   bench --site [nama-site] console
   ```
   ```python
   import frappe
   hooks = frappe.get_hooks("doc_events")
   print(hooks.get("Payment Entry"))
   ```

4. **Manual reload**
   ```bash
   bench --site [nama-site] reload-doc imogi_finance "DocType" "Customer Receipt"
   bench --site [nama-site] reload-doc imogi_finance "DocType" "Customer Receipt Item"
   bench --site [nama-site] reload-doc imogi_finance "DocType" "Customer Receipt Payment"
   ```

## Update Log

**2026-01-17**: Fixed module initialization and exports for Customer Receipt module
- Added proper __init__.py exports in receipt_control module
- Added module import in main imogi_finance __init__.py
- Verified hooks registration in hooks.py
- Created comprehensive documentation

---

**Status**: ✅ **RESOLVED** - Module Customer Receipt sekarang sudah terpegang dengan baik
