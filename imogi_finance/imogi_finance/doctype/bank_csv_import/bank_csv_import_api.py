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
            "opening_balance": result.get("opening_balance", 0),
            "closing_balance": result.get("closing_balance", 0),
            "statement_from_date": result.get("statement_from_date"),
            "statement_to_date": result.get("statement_to_date"),
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

    # Baca file (support CSV dan Excel .xlsx/.xls)
    file_path = get_file_path(doc.import_file)
    import os
    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".xlsx", ".xls"):
        # Baca Excel
        try:
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            ws = wb.active
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append([str(v).strip() if v is not None else "" for v in row])
            wb.close()
        except ImportError:
            frappe.throw(_("openpyxl tidak terinstall. Hubungi administrator."))
    else:
        # Baca CSV dengan auto-detect encoding
        with open(file_path, "rb") as f:
            raw_bytes = f.read()

        # Coba decode dengan berbagai encoding
        decoded = None
        for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252", "iso-8859-1"):
            try:
                decoded = raw_bytes.decode(encoding)
                break
            except Exception:
                continue

        if decoded is None:
            frappe.throw(_("Tidak dapat membaca file. Encoding tidak dikenali."))

        # Tentukan delimiter
        dialect_map = {
            "excel": ",",
            "excel-tab": "\t",
            "unix": ",",
        }
        delimiter = dialect_map.get(config.csv_dialect, ",")
        if config.csv_dialect == "semicolon":
            delimiter = ";"

        reader = csv.reader(io.StringIO(decoded), delimiter=delimiter)
        rows = list(reader)

    if not rows:
        frappe.throw(_("File kosong."))

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

    # Extract saldo awal & akhir dari data
    opening_balance, closing_balance, statement_from_date, statement_to_date = \
        _extract_balances_from_rows(data_rows, headers, field_map, config)

    # Buat Opening Balance Journal Entry jika belum ada GL Entry
    account = frappe.db.get_value("Bank Account", doc.bank_account, "account")
    je_name = None
    if opening_balance and account and statement_from_date:
        try:
            je_name = _ensure_opening_balance_je(
                doc.bank_account,
                account,
                doc.company,
                opening_balance,
                statement_from_date,
            )
            if je_name:
                log_lines.append(f"Opening Balance Journal Entry: {je_name}")
        except Exception as e:
            frappe.log_error(f"Opening Balance JE error: {str(e)}")
            log_lines.append(f"Warning: Gagal buat Opening Balance JE - {str(e)}")

    log = "\n".join(log_lines)
    return {
        "total": total,
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "log": log,
        "opening_balance": opening_balance,
        "closing_balance": closing_balance,
        "statement_from_date": statement_from_date,
        "statement_to_date": statement_to_date,
        "opening_balance_je": je_name,
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


def _extract_balances_from_rows(data_rows, headers, field_map, config):
    """Extract saldo awal dan akhir dari baris data CSV/Excel."""
    opening_balance = 0.0
    closing_balance = 0.0
    statement_from_date = None
    statement_to_date = None

    if "balance" not in field_map:
        return opening_balance, closing_balance, statement_from_date, statement_to_date

    valid_entries = []
    for row in data_rows:
        if not row or all(not str(v).strip() for v in row):
            continue
        row_dict = {}
        for i, header in enumerate(headers):
            row_dict[header] = row[i] if i < len(row) else ""

        bal_str = _clean(row_dict.get(field_map.get("balance", ""), ""))
        date_str = _clean(row_dict.get(field_map.get("posting_date", ""), ""))

        bal = _parse_amount(bal_str)
        date = _parse_date(date_str, config.date_format) if date_str else None

        if bal and date:
            valid_entries.append((date, bal))

    # Cari juga dari baris ringkasan "Saldo Awal" dan "Saldo Akhir"
    for row in data_rows:
        if not row:
            continue
        row_dict = {}
        for i, header in enumerate(headers):
            row_dict[header] = row[i] if i < len(row) else ""

        # Cek semua cell untuk pattern Saldo Awal/Akhir
        for cell_val in row_dict.values():
            cell_normalized = _normalize(str(cell_val))
            if "saldoawal" in cell_normalized or "openingbalance" in cell_normalized:
                amount = _parse_amount(str(cell_val))
                if amount:
                    opening_balance = amount
            elif "saldoakhir" in cell_normalized or "closingbalance" in cell_normalized:
                amount = _parse_amount(str(cell_val))
                if amount:
                    closing_balance = amount

    if valid_entries:
        valid_entries.sort(key=lambda x: x[0])
        statement_from_date = valid_entries[0][0]
        statement_to_date = valid_entries[-1][0]
        if not closing_balance:
            closing_balance = valid_entries[-1][1]
        if not opening_balance and len(valid_entries) > 1:
            opening_balance = valid_entries[0][1]

    # Fallback: jika balance tidak ada di file, hitung dari debit/kredit
    if not closing_balance and ("debit" in field_map or "credit" in field_map or "amount" in field_map):
        total_debit = 0.0
        total_credit = 0.0
        dates = []
        for row in data_rows:
            if not row or all(not str(v).strip() for v in row):
                continue
            row_dict = {}
            for i, header in enumerate(headers):
                row_dict[header] = row[i] if i < len(row) else ""

            date_str = _clean(row_dict.get(field_map.get("posting_date", ""), ""))
            date = _parse_date(date_str, config.date_format) if date_str else None

            debit_str = _clean(row_dict.get(field_map.get("debit", ""), "")) if "debit" in field_map else ""
            credit_str = _clean(row_dict.get(field_map.get("credit", ""), "")) if "credit" in field_map else ""
            amount_str = _clean(row_dict.get(field_map.get("amount", ""), "")) if "amount" in field_map else ""

            debit = _parse_amount(debit_str)
            credit = _parse_amount(credit_str)

            # Handle format BCA: kolom Jumlah tunggal dengan suffix DB/CR
            if debit == 0 and credit == 0 and amount_str:
                amount_val = _parse_amount(amount_str)
                amount_lower = amount_str.lower()
                if "db" in amount_lower or "dr" in amount_lower:
                    debit = amount_val
                elif "cr" in amount_lower:
                    credit = amount_val

            if (debit or credit) and date:
                total_debit += debit
                total_credit += credit
                dates.append(date)

        if dates:
            dates.sort()
            if not statement_from_date:
                statement_from_date = dates[0]
            if not statement_to_date:
                statement_to_date = dates[-1]
            # Closing = opening + kredit - debit
            closing_balance = opening_balance + total_credit - total_debit

    return opening_balance, closing_balance, statement_from_date, statement_to_date


def _ensure_opening_balance_je(bank_account_name, account, company, opening_balance, as_of_date):
    """Buat Opening Balance Journal Entry jika belum ada dan opening_balance > 0."""
    if not opening_balance or not account or not as_of_date:
        return None

    # Cek apakah sudah ada GL Entry untuk akun ini sebelum tanggal tersebut
    existing_gl = frappe.db.exists("GL Entry", {
        "account": account,
        "is_cancelled": 0,
    })

    if existing_gl:
        # Sudah ada GL Entry — skip, tidak perlu buat opening balance
        return None

    # Cek apakah sudah ada Opening Balance JE yang kita buat sebelumnya
    existing_je = frappe.db.exists("Journal Entry", {
        "user_remark": f"Opening Balance - {bank_account_name}",
        "docstatus": 1,
    })
    if existing_je:
        return existing_je

    # Cari temporary/opening account
    temp_account = frappe.db.get_value("Account", {
        "account_type": "Temporary",
        "company": company,
    }, "name")

    if not temp_account:
        # Pakai Retained Earnings atau equity account
        temp_account = frappe.db.get_value("Account", {
            "root_type": "Equity",
            "is_group": 0,
            "company": company,
        }, "name")

    if not temp_account:
        frappe.log_error("Opening Balance JE: Tidak ada temporary/equity account")
        return None

    # Buat Journal Entry
    je = frappe.get_doc({
        "doctype": "Journal Entry",
        "voucher_type": "Opening Entry",
        "company": company,
        "posting_date": as_of_date,
        "user_remark": f"Opening Balance - {bank_account_name}",
        "accounts": [
            {
                "account": account,
                "debit_in_account_currency": opening_balance,
                "credit_in_account_currency": 0,
            },
            {
                "account": temp_account,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": opening_balance,
            },
        ],
    })
    je.insert(ignore_permissions=True)
    je.submit()
    frappe.db.commit()

    return je.name
