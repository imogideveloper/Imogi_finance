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


def _get_previous_closing_balance(bank_account, current_docname):
    """
    Ambil closing_balance dari BCI sebelumnya untuk bank account yang sama.
    Urut berdasarkan statement_to_date descending, ambil yang pertama.
    """
    prev = frappe.db.sql("""
        SELECT closing_balance, statement_to_date
        FROM `tabBank CSV Import`
        WHERE bank_account = %s
          AND status = 'Completed'
          AND name != %s
          AND closing_balance IS NOT NULL
          AND closing_balance != 0
        ORDER BY statement_to_date DESC, creation DESC
        LIMIT 1
    """, (bank_account, current_docname), as_dict=True)

    if prev:
        return prev[0].get("closing_balance", 0)
    return None


def _process_import(doc):
    """Parse CSV dan buat Bank Transactions."""
    # Load konfigurasi bank
    config = frappe.get_doc("Bank Statement Bank List", doc.bank)

    if not config.enabled:
        # FIX 1: ganti _(f"...") dengan _("...").format(...)
        frappe.throw(_("Konfigurasi bank {0} dinonaktifkan.").format(doc.bank))

    # Build header map dari konfigurasi
    header_map = {}
    for alias_row in (config.header_aliases or []):
        aliases = [a.strip() for a in (alias_row.aliases or "").split(",") if a.strip()]
        if aliases:
            header_map[alias_row.fieldname] = aliases

    # Skip markers
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
        with open(file_path, "rb") as f:
            raw_bytes = f.read()

        decoded = None
        for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252", "iso-8859-1"):
            try:
                decoded = raw_bytes.decode(encoding)
                break
            except Exception:
                continue

        if decoded is None:
            frappe.throw(_("Tidak dapat membaca file. Encoding tidak dikenali."))

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

    # Cari baris header
    header_row_idx = _find_header_row(rows, header_map)
    if header_row_idx is None:
        frappe.throw(_("Tidak dapat menemukan baris header di CSV."))

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
        # FIX 2: ganti _(f"...") dengan _("...").format(...)
        frappe.throw(_("Field wajib tidak ditemukan di CSV: {0}.").format(", ".join(missing)))

    # Proses setiap row
    log_lines = []
    total = created = skipped = errors = 0
    all_dates = []
    total_debit = 0.0
    total_credit = 0.0

    for row_idx, row in enumerate(data_rows, start=1):
        if not row or all(not (v or "").strip() for v in row):
            continue

        row_dict = {}
        for i, header in enumerate(headers):
            if i < len(row):
                row_dict[header] = row[i]
            else:
                row_dict[header] = ""

        # Cek skip markers
        should_skip = False
        for check_field in ["posting_date", "description"]:
            if check_field in field_map:
                val = _normalize(row_dict.get(field_map[check_field], ""))
                if any(val.startswith(m) or m in val for m in skip_markers):
                    should_skip = True
                    break
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
            posting_date_str = _clean(row_dict.get(field_map.get("posting_date"), ""))
            description = _clean(row_dict.get(field_map.get("description"), ""))
            reference_number = _clean(row_dict.get(field_map.get("reference_number"), "")) if "reference_number" in field_map else ""
            debit_str = _clean(row_dict.get(field_map.get("debit"), "")) if "debit" in field_map else ""
            credit_str = _clean(row_dict.get(field_map.get("credit"), "")) if "credit" in field_map else ""

            if not posting_date_str:
                continue

            if skip_markers and any(
                _normalize(posting_date_str).startswith(m) or m in _normalize(posting_date_str)
                for m in skip_markers
            ):
                continue

            posting_date = _parse_date(posting_date_str, config.date_format)
            if not posting_date:
                row_text = _normalize(' '.join(str(v) for v in row_dict.values()))
                if skip_markers and any(m in row_text for m in skip_markers):
                    continue
                log_lines.append(f"Row {row_idx}: Tanggal tidak valid: '{posting_date_str}'")
                errors += 1
                continue

            debit = _parse_amount(debit_str)
            credit = _parse_amount(credit_str)

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

            # Akumulasi untuk kalkulasi balance
            all_dates.append(posting_date)
            total_debit += debit
            total_credit += credit

            # Cek duplikat — cek date + amount saja, description diabaikan
            existing_count = frappe.db.count('Bank Transaction', {
                'date': posting_date,
                'bank_account': doc.bank_account,
                'deposit': credit,
                'withdrawal': debit,
            })
            current_session_key = f'{posting_date}|{credit}|{debit}'
            if not hasattr(doc, '_import_session_counts'):
                doc._import_session_counts = {}
            session_count = doc._import_session_counts.get(current_session_key, 0)
            if existing_count > session_count:
                log_lines.append(f'Row {row_idx}: Duplikat - {posting_date} {description[:30]}')
                skipped += 1
                continue
            doc._import_session_counts[current_session_key] = session_count + 1

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
            frappe.log_error(f"Bank CSV Import Row {row_idx}: {str(e)}")

    # ── Kalkulasi From/To Date dari transaksi ──────────────────
    statement_from_date = None
    statement_to_date = None
    if all_dates:
        all_dates.sort()
        statement_from_date = all_dates[0]
        statement_to_date = all_dates[-1]

    # ── Kalkulasi Opening Balance ──────────────────────────────
    # FIX 3: ganti "_, _" dengan nama variabel yang tidak conflict dengan fungsi _()
    csv_opening, csv_closing, _from_date, _to_date = _extract_balances_from_rows(
        data_rows, headers, field_map, config
    )

    # Coba dari closing balance BCI sebelumnya (history)
    prev_closing = _get_previous_closing_balance(doc.bank_account, doc.name)

    # Tentukan opening balance
    if csv_opening:
        opening_balance = csv_opening
        log_lines.append(f"✅ Opening Balance dari CSV (Saldo Awal): Rp {opening_balance:,.2f}")
    elif prev_closing is not None:
        opening_balance = prev_closing
        log_lines.append(f"✅ Opening Balance dari history BCI sebelumnya: Rp {opening_balance:,.2f}")
    else:
        opening_balance = 0.0
        log_lines.append("ℹ️ Opening Balance: 0 (tidak ada history sebelumnya)")

    # ── Kalkulasi Closing Balance ──────────────────────────
    if csv_closing:
        closing_balance = csv_closing
        log_lines.append(f"✅ Closing Balance dari CSV (Saldo Akhir): Rp {closing_balance:,.2f}")
    else:
        closing_balance = opening_balance + total_credit - total_debit

    log_lines.append(
        f"📊 Summary: Opening={opening_balance:,.2f} | "
        f"+Credit={total_credit:,.2f} | -Debit={total_debit:,.2f} | "
        f"Closing={closing_balance:,.2f}"
    )

    # Notifikasi Opening Balance untuk import pertama
    account = frappe.db.get_value("Bank Account", doc.bank_account, "account")
    if opening_balance == 0 and account:
        existing_gl = frappe.db.exists("GL Entry", {
            "account": account,
            "is_cancelled": 0,
        })
        if not existing_gl:
            log_lines.append(
                f"⚠️ Ini adalah import pertama. Opening Balance = 0. "
                f"Jika perlu penyesuaian, buat Opening Entry manual di "
                f"Accounting → Journal Entry."
            )

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
    }


def _find_header_row(rows, header_map):
    all_aliases = set()
    for aliases in header_map.values():
        for alias in aliases:
            all_aliases.add(_normalize(alias))

    for idx, row in enumerate(rows):
        normalized_row = [_normalize(cell) for cell in row]
        matches = sum(1 for cell in normalized_row if cell in all_aliases)
        if matches >= 2:
            return idx

    return None


def _normalize(text):
    return (text or "").lower().strip().replace("_", "").replace(" ", "")


def _clean(text):
    return (text or "").strip()


def _parse_date(date_str, date_format=None):
    import re
    date_str = date_str.strip()

    formats = [
        "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y",
        "%d/%m/%y", "%Y/%m/%d", "%d %b %Y",
        "%d-%b-%Y", "%d %B %Y",
        "%d %B %Y %H:%M:%S",
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
    if not value:
        return 0.0

    cleaned = value.strip()

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts[-1]) == 3:
            cleaned = cleaned.replace(".", "")

    import re
    cleaned = re.sub(r"[^\d.\-]", "", cleaned)

    try:
        return abs(float(cleaned)) if cleaned else 0.0
    except Exception:
        return 0.0


def _extract_balances_from_rows(data_rows, headers, field_map, config):
    """Extract saldo dari CSV jika ada kolom balance atau label eksplisit."""
    opening_balance = 0.0
    closing_balance = 0.0
    statement_from_date = None
    statement_to_date = None

    valid_entries = []

    if "balance" in field_map:
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

    # Cek baris ringkasan Saldo Awal/Akhir
    for row in data_rows:
        if not row:
            continue
        row_dict = {}
        for i, header in enumerate(headers):
            row_dict[header] = row[i] if i < len(row) else ""

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

    return opening_balance, closing_balance, statement_from_date, statement_to_date


def _ensure_opening_balance_je(bank_account_name, account, company, opening_balance, as_of_date):
    if not opening_balance or not account or not as_of_date:
        return None

    existing_gl = frappe.db.exists("GL Entry", {
        "account": account,
        "is_cancelled": 0,
    })

    if existing_gl:
        return None

    existing_je = frappe.db.exists("Journal Entry", {
        "user_remark": f"Opening Balance - {bank_account_name}",
        "docstatus": 1,
    })
    if existing_je:
        return existing_je

    temp_account = frappe.db.get_value("Account", {
        "account_type": "Temporary",
        "company": company,
    }, "name")

    if not temp_account:
        temp_account = frappe.db.get_value("Account", {
            "root_type": "Equity",
            "is_group": 0,
            "company": company,
        }, "name")

    if not temp_account:
        frappe.log_error("Opening Balance JE: Tidak ada temporary/equity account")
        return None

    import datetime as dt
    if isinstance(as_of_date, str):
        as_of_date_obj = dt.date.fromisoformat(as_of_date)
    else:
        as_of_date_obj = as_of_date
    je_date = (as_of_date_obj - dt.timedelta(days=1)).strftime("%Y-%m-%d")

    je = frappe.get_doc({
        "doctype": "Journal Entry",
        "voucher_type": "Opening Entry",
        "company": company,
        "posting_date": je_date,
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