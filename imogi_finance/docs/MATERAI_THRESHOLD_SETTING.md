# Materai (Stamp Duty) Threshold Setting

## Overview

Tidak semua kuitansi/customer receipt memerlukan materai. Berdasarkan peraturan Indonesia, materai hanya diperlukan untuk dokumen dengan nilai tertentu. Setting ini memungkinkan konfigurasi threshold materai secara global.

## Konfigurasi

### Global Setting

Buka **Finance Control Settings** dan atur:

- **Materai Minimum Amount**: Jumlah minimum untuk kuitansi yang memerlukan materai (default: Rp 10.000.000)

### Cara Menggunakan di Print Format

Di template Customer Receipt (Jinja), Anda dapat menggunakan fungsi `requires_materai()` untuk mengecek apakah receipt perlu materai:

```jinja
{%- set needs_stamp = frappe.utils.call("imogi_finance.receipt_control.utils.requires_materai", doc.grand_total) -%}

{% if needs_stamp %}
  {#- Tampilkan area materai -#}
  {% if doc.stamp_mode and doc.stamp_mode != "None" %}
    <div class="cr-stamp-box">
      {% if doc.stamp_mode == "Physical" %}
        <div>Materai</div>
      {% elif stamp_image %}
        <img src="{{ stamp_image }}">
      {% else %}
        <div>e-Materai</div>
      {% endif %}
    </div>
  {% endif %}
{% else %}
  {#- Optional: tampilkan note bahwa tidak perlu materai -#}
  <div class="cr-no-stamp-note">
    <small>Tidak memerlukan materai (dibawah threshold)</small>
  </div>
{% endif %}
```

### Contoh Logika Conditional

```jinja
{%- set needs_stamp = frappe.utils.call("imogi_finance.receipt_control.utils.requires_materai", doc.grand_total) -%}

{#- Hanya render stamp section jika diperlukan -#}
{% if needs_stamp %}
  {% if doc.stamp_mode and doc.stamp_mode != "None" %}
    {#- Render stamp area -#}
    <div class="cr-stamp-section">
      <div class="cr-stamp-box" style="width:35mm;height:40mm;">
        {% if doc.stamp_mode == "Physical" %}
          <div style="margin-top:40%">Materai</div>
        {% elif stamp_image %}
          <img src="{{ stamp_image }}" style="width:100%;height:100%;object-fit:contain;">
        {% else %}
          <div style="margin-top:35%">e-Materai</div>
        {% endif %}
      </div>
    </div>
  {% endif %}
{% endif %}
```

## Technical Details

### Fungsi Helper

**File**: `imogi_finance/receipt_control/utils.py`

```python
def requires_materai(receipt_amount: float | Decimal) -> bool:
    """Check if the receipt amount requires materai (stamp duty).
    
    Args:
        receipt_amount: The total amount on the customer receipt.
        
    Returns:
        True if the amount meets or exceeds the minimum threshold for materai.
    """
    settings = get_receipt_control_settings()
    min_amount = float(settings.get("materai_minimum_amount", 10000000))
    
    return float(receipt_amount or 0) >= min_amount
```

### Default Values

| Setting | Default Value | Description |
|---------|--------------|-------------|
| `materai_minimum_amount` | 10,000,000 | Minimum amount (IDR) that requires materai |

### Peraturan Materai Indonesia

Sesuai peraturan terbaru:
- **Di bawah Rp 10.000.000**: Tidak memerlukan materai
- **Rp 10.000.000 ke atas**: Memerlukan materai Rp 10.000

> **Note**: Threshold dapat diubah sewaktu-waktu sesuai peraturan pemerintah. Update nilai di Finance Control Settings sesuai kebutuhan.

## Migration Notes

### Perubahan yang Dilakukan

1. **Finance Control Settings** - Menambahkan field baru:
   - `materai_minimum_amount` (Currency, default: 10000000)

2. **Receipt Control Utils** - Menambahkan:
   - Function `requires_materai()` untuk checking threshold
   - Default value di `get_receipt_control_settings()`

3. **Hooks** - Register Jinja method:
   - `imogi_finance.receipt_control.utils.requires_materai`

### Cara Reload

```bash
# Reload doctype untuk apply field baru
bench --site [site-name] reload-doc imogi_finance "DocType" "Finance Control Settings"

# Restart untuk apply Jinja method
bench --site [site-name] restart
```

## Example Usage in Production

### Basic Implementation

```jinja
{%- set needs_stamp = frappe.utils.call("imogi_finance.receipt_control.utils.requires_materai", doc.grand_total) -%}

<div class="receipt-footer">
  <div class="signature-section">
    <div>Tanda Tangan</div>
    <div>_________________</div>
    <div>{{ design.signer_name }}</div>
  </div>
  
  {% if needs_stamp %}
    <div class="stamp-section">
      {% if doc.stamp_mode == "Physical" %}
        <div class="stamp-placeholder">
          <p>Tempat<br>Materai<br>Rp 10.000</p>
        </div>
      {% elif doc.digital_stamp_serial %}
        <div class="digital-stamp">
          <img src="{{ stamp_image }}" alt="e-Materai">
          <small>{{ doc.digital_stamp_serial }}</small>
        </div>
      {% endif %}
    </div>
  {% endif %}
</div>
```

### Advanced: Show Warning When Near Threshold

```jinja
{%- set min_amount = frappe.db.get_single_value("Finance Control Settings", "materai_minimum_amount") or 10000000 -%}
{%- set needs_stamp = frappe.utils.call("imogi_finance.receipt_control.utils.requires_materai", doc.grand_total) -%}

{% if not needs_stamp and doc.grand_total >= (min_amount * 0.9) %}
  <div class="threshold-warning" style="color: orange; font-size: 10px;">
    ⚠ Mendekati threshold materai (Rp {{ frappe.utils.fmt_money(min_amount, currency="IDR") }})
  </div>
{% endif %}
```

## Testing

### Test Cases

1. **Receipt < Rp 10.000.000**: Tidak perlu materai
   - Buat customer receipt dengan total Rp 5.000.000
   - Verify: `requires_materai()` returns `False`

2. **Receipt = Rp 10.000.000**: Perlu materai
   - Buat customer receipt dengan total Rp 10.000.000
   - Verify: `requires_materai()` returns `True`

3. **Receipt > Rp 10.000.000**: Perlu materai
   - Buat customer receipt dengan total Rp 25.000.000
   - Verify: `requires_materai()` returns `True`

4. **Custom Threshold**: Setting dapat diubah
   - Set `materai_minimum_amount` = 5.000.000
   - Buat receipt Rp 7.000.000
   - Verify: `requires_materai()` returns `True`

### Python Test Example

```python
import frappe
from imogi_finance.receipt_control.utils import requires_materai

# Test dengan default threshold (10 juta)
assert requires_materai(5000000) == False
assert requires_materai(10000000) == True
assert requires_materai(15000000) == True

# Test dengan custom threshold
frappe.db.set_value("Finance Control Settings", None, "materai_minimum_amount", 5000000)
assert requires_materai(7000000) == True
```

## Troubleshooting

### Function tidak tersedia di Jinja

**Gejala**: Error `Unknown function 'requires_materai'`

**Solusi**:
```bash
# Pastikan hooks sudah terdaftar
bench --site [site-name] restart
```

### Threshold tidak berubah setelah update setting

**Gejala**: Setting diubah tapi function masih pakai nilai lama

**Solusi**:
```bash
# Clear cache
bench --site [site-name] clear-cache
```

## Future Enhancements

Fitur yang bisa ditambahkan di masa depan:

1. **Multi-tier Materai**: Support berbagai nilai materai berdasarkan range amount
2. **Materai Log**: Track kapan materai diperlukan vs tidak diperlukan
3. **Auto-warning**: Notifikasi otomatis saat mendekati threshold
4. **Historical Threshold**: Simpan history perubahan threshold untuk audit

## Related Documentation

- [CUSTOMER_RECEIPT_MODULE_FIX.md](CUSTOMER_RECEIPT_MODULE_FIX.md) - Receipt module overview
- [CUSTOMER_RECEIPT_WORKFLOW_TRACKING.md](CUSTOMER_RECEIPT_WORKFLOW_TRACKING.md) - Workflow implementation
