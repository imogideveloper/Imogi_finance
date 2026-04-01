"""
API untuk Bank CSV Import
Mendukung semua bank via konfigurasi Bank Statement Bank List
"""

import frappe
import csv
import io
from frappe.utils.file_manager import get_file_path
from frappe import _


@frappe.whitelist()
def run_import(docname):
    """Jalankan import CSV dan buat Bank Transactions."""
    doc = frappe.get_doc("Bank CSV Import", docname)

    if doc.status == "Processing":
        frappe.throw(_("Import sudah berjalan."))

    # Update status
    frappe.db.set_value("Bank CSV Import", docname, "status", "Processing")
    frappe.db.commit()

    try:
        result = _process_import(doc)

        frappe.db.set_value("Bank CSV Import", docname, {
            "status": "Completed",
            "total_rows": result["total"],
            "created_rows": result["created"],
            "skipped_rows": result["skipped"],
            "error_rows": result["errors"],
            "import_log": result["log"],
        })
        frappe.db.commit()

        return result

    except Exception as e:
        frappe.db.set_value("Bank CSV Import", docname, {
            "status": "Failed",
            "import_log": str(e),
        })
        frappe.db.commit()
        frappe.throw(str(e))


def _process_import(doc):
    """Parse CSV dan buat Bank Transactions."""
    # Load konfigurasi bank
    config = frappe.get_doc("Bank Statement Bank List", doc.bank)

    if not config.enabled:
        frappe.throw(_(f"Konfigurasi bank {doc.bank} dinonaktifkan."))

    # Build header map dari konfigurasi
    header_map = {}
    for alias_row in (config.header_aliases or []):
        aliases = [a.strip() for a in (alias_row.aliases or "").split(",") if a.strip()]
        if aliases:
            header_map[alias_row.fieldname] = aliases

    # Skip markers - normalize juga supaya cocok dengan normalized text
    skip_markers = tuple(
        _normalize(m)
        for m in (config.skip_markers or "").split(",")
        if m.strip()
    ) if config.skip_markers else ()

    # Baca CSV
    file_path = get_file_path(doc.import_file)
    with open(file_path, "rb") as f:
        raw = f.read().decode("utf-8-sig")

    # Tentukan delimiter
    dialect_map = {
        "excel": ",",
        "excel-tab": "\t",
        "unix": ",",
    }
    delimiter = dialect_map.get(config.csv_dialect, ",")
    if config.csv_dialect == "semicolon":
        delimiter = ";"

    # Parse CSV
    reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
    rows = list(reader)

    if not rows:
        frappe.throw(_("File CSV kosong."))

    # Cari baris header (skip baris info rekening di atas)
    header_row_idx = _find_header_row(rows, header_map)
    if header_row_idx is None:
        frappe.throw(_("Tidak dapat menemukan baris header di CSV. Pastikan konfigurasi Bank Statement Bank List sudah benar."))

    headers = rows[header_row_idx]
    data_rows = rows[header_row_idx + 1:]

    # Normalize headers
    normalized_headers = {_normalize(h): h for h in headers}

    # Build field map
    field_map = {}
    for fieldname, aliases in header_map.items():
        for alias in aliases:
            if _normalize(alias) in normalized_headers:
                field_map[fieldname] = normalized_headers[_normalize(alias)]
                break

    # Validasi field wajib
    required = ["posting_date", "description"]
    missing = [f for f in required if f not in field_map]
    if missing:
        frappe.throw(_(f"Field wajib tidak ditemukan di CSV: {', '.join(missing)}. Cek konfigurasi header_aliases di Bank Statement Bank List."))

    # Proses setiap row
    log_lines = []
    total = created = skipped = errors = 0

    for row_idx, row in enumerate(data_rows, start=1):
        if not row or all(not (v or "").strip() for v in row):
            continue

        # Buat dict dari row
        row_dict = {}
        for i, header in enumerate(headers):
            if i < len(row):
                row_dict[header] = row[i]
            else:
                row_dict[header] = ""

        # Cek skip markers - cek semua cell di row
        should_skip = False
        # Cek di field posting_date dan description
        for check_field in ["posting_date", "description"]:
            if check_field in field_map:
                val = _normalize(row_dict.get(field_map[check_field], ""))
                if any(val.startswith(m) or m in val for m in skip_markers):
                    should_skip = True
                    break
        # Cek juga di semua cell jika skip_markers ditemukan
        if not should_skip and skip_markers:
            for cell_val in row_dict.values():
                normalized_cell = _normalize(cell_val)
                if any(normalized_cell.startswith(m) for m in skip_markers):
                    should_skip = True
                    break

        if should_skip:
            continue

        total += 1

        try:
            # Ambil nilai
            posting_date_str = _clean(row_dict.get(field_map.get("posting_date"), ""))
            description = _clean(row_dict.get(field_map.get("description"), ""))
            reference_number = _clean(row_dict.get(field_map.get("reference_number"), "")) if "reference_number" in field_map else ""
            debit_str = _clean(row_dict.get(field_map.get("debit"), "")) if "debit" in field_map else ""
            credit_str = _clean(row_dict.get(field_map.get("credit"), "")) if "credit" in field_map else ""
            balance_str = _clean(row_dict.get(field_map.get("balance"), "")) if "balance" in field_map else ""

            if not posting_date_str:
                continue

            # Cek apakah baris ini adalah baris ringkasan (skip markers)
            if skip_markers and any(
                _normalize(posting_date_str).startswith(m) or m in _normalize(posting_date_str)
                for m in skip_markers
            ):
                continue

            # Parse tanggal
            posting_date = _parse_date(posting_date_str, config.date_format)
            if not posting_date:
                # Cek apakah baris ini adalah ringkasan - skip tanpa error
                row_text = _normalize(' '.join(str(v) for v in row_dict.values()))
                if skip_markers and any(m in row_text for m in skip_markers):
                    continue
                # Cek juga di posting_date_str sendiri
                if skip_markers and any(m in _normalize(posting_date_str) for m in skip_markers):
                    continue
                log_lines.append(f"Row {row_idx}: Tanggal tidak valid: '{posting_date_str}'")
                errors += 1
                continue

            # Parse amounts
            debit = _parse_amount(debit_str)
            credit = _parse_amount(credit_str)
            balance = _parse_amount(balance_str)

            # Handle format BCA: kolom "Jumlah" tunggal dengan suffix DB/CR
            if debit == 0 and credit == 0 and "amount" in field_map:
                amount_str = _clean(row_dict.get(field_map.get("amount"), ""))
                if amount_str:
                    amount_val = _parse_amount(amount_str)
                    amount_lower = amount_str.lower()
                    if "db" in amount_lower or "dr" in amount_lower or "debet" in amount_lower:
                        debit = amount_val
                    elif "cr" in amount_lower or "kredit" in amount_lower:
                        credit = amount_val

            if debit == 0 and credit == 0:
                skipped += 1
                continue

            # Cek duplikat berdasarkan tanggal + deskripsi + amount
            duplicate = frappe.db.exists("Bank Transaction", {
                "date": posting_date,
                "bank_account": doc.bank_account,
                "description": description,
                "deposit": credit,
                "withdrawal": debit,
            })

            if duplicate:
                log_lines.append(f"Row {row_idx}: Duplikat - {posting_date} {description[:30]}")
                skipped += 1
                continue

            # Buat Bank Transaction
            bt = frappe.get_doc({
                "doctype": "Bank Transaction",
                "date": posting_date,
                "bank_account": doc.bank_account,
                "company": doc.company,
                "description": description,
                "reference_number": reference_number,
                "deposit": credit,
                "withdrawal": debit,
                "currency": (
                        frappe.db.get_value("Account",
                            frappe.db.get_value("Bank Account", doc.bank_account, "account"),
                            "account_currency"
                        ) or "IDR"
                ),
            })
            bt.insert(ignore_permissions=True)
            bt.submit()

            created += 1
            log_lines.append(f"Row {row_idx}: OK - {posting_date} | {description[:40]} | D:{debit} C:{credit}")

        except Exception as e:
            errors += 1
            log_lines.append(f"Row {row_idx}: ERROR - {str(e)}")
            frappe.log_error(f"BCA Import Row {row_idx}: {str(e)}")

    log = "\n".join(log_lines)
    return {
        "total": total,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "log": log,
    }


def _find_header_row(rows, header_map):
    """Cari baris header di CSV (skip baris info rekening di atas)."""
    all_aliases = set()
    for aliases in header_map.values():
        for alias in aliases:
            all_aliases.add(_normalize(alias))

    for idx, row in enumerate(rows):
        normalized_row = [_normalize(cell) for cell in row]
        matches = sum(1 for cell in normalized_row if cell in all_aliases)
        if matches >= 2:  # minimal 2 kolom cocok = baris header
            return idx

    return None


def _normalize(text):
    return (text or "").lower().strip().replace("_", "").replace(" ", "")


def _clean(text):
    return (text or "").strip()


def _parse_date(date_str, date_format=None):
    """Parse tanggal dari berbagai format."""
    import re
    date_str = date_str.strip()

    formats = [
        "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
        "%d/%m/%y", "%Y/%m/%d", "%d %b %Y",
        "%d-%b-%Y", "%d %B %Y",
        "%d %B %Y %H:%M:%S",  # Mandiri: 29 March 2026 04:13:47
        "%d %b %Y %H:%M:%S",
    ]

    if date_format:
        fmt_map = {
            "DD/MM/YYYY": "%d/%m/%Y",
            "YYYY-MM-DD": "%Y-%m-%d",
            "DD-MM-YYYY": "%d-%m-%Y",
            "MM/DD/YYYY": "%m/%d/%Y",
        }
        if date_format in fmt_map:
            formats.insert(0, fmt_map[date_format])

    from datetime import datetime
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue

    return None


def _parse_amount(value):
    """Parse amount dari string dengan format Indonesia."""
    if not value:
        return 0.0

    cleaned = value.strip()

    # Handle format Indonesia: 1.234.567,89
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        # Cek apakah titik sebagai ribuan atau desimal
        parts = cleaned.split(".")
        if len(parts[-1]) == 3:
            cleaned = cleaned.replace(".", "")

    # Hapus karakter non-numerik selain titik dan minus
    import re
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)

    try:
        return abs(float(cleaned)) if cleaned else 0.0
    except Exception:
        return 0.0
