import frappe
from frappe.model.document import Document
from frappe.utils import now

from imogi_finance.imogi_finance.doctype.bank_csv_import.bank_csv_import_api import (
    get_bank_statement_doc,
)


class BankStatement(Document):
    pass


@frappe.whitelist()
def auto_reconcile_statement_details(docname: str):
    """Auto-match Statement Detail rows against GL Entry on bank account."""
    doc = get_bank_statement_doc(docname)
    account = frappe.db.get_value("Bank Account", doc.bank_account, "account")
    if not account:
        frappe.throw("Akun GL untuk Bank Account tidak ditemukan.")

    gl_rows = frappe.get_all(
        "GL Entry",
        filters={
            "account": account,
            "posting_date": ["between", [doc.statement_from_date, doc.statement_to_date]],
            "is_cancelled": 0,
        },
        fields=["name", "posting_date", "debit", "credit", "voucher_type", "voucher_no"],
        order_by="posting_date asc, creation asc",
    )

    gl_map = {}
    for gl in gl_rows:
        key = _build_match_key(gl.posting_date, gl.debit, gl.credit)
        gl_map.setdefault(key, []).append(gl)

    reconciled = 0
    unmatched = 0
    for row in doc.statement_details or []:
        if row.import_status != "Created":
            continue
        if row.is_reconciled:
            continue

        key = _build_match_key(row.posting_date, row.deposit, row.withdrawal)
        candidates = gl_map.get(key, [])
        if not candidates:
            unmatched += 1
            row.reconciliation_note = "Tidak ada GL Entry yang match (tanggal + nominal)."
            continue

        matched = candidates.pop(0)
        row.is_reconciled = 1
        row.reconciled_on = now()
        row.reconciled_voucher_type = matched.voucher_type
        row.reconciled_voucher_no = matched.voucher_no
        row.reconciliation_note = "Auto-reconciled dari GL Entry."
        reconciled += 1

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {
        "reconciled": reconciled,
        "unmatched": unmatched,
        "total": len(doc.statement_details or []),
    }


@frappe.whitelist()
def reset_reconcile_statement_details(docname: str):
    doc = get_bank_statement_doc(docname)
    reset_count = 0
    for row in doc.statement_details or []:
        if row.is_reconciled:
            reset_count += 1
        row.is_reconciled = 0
        row.reconciled_on = None
        row.reconciled_voucher_type = None
        row.reconciled_voucher_no = None
        row.reconciliation_note = None

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"reset": reset_count}


def _build_match_key(posting_date, deposit, withdrawal):
    return f"{posting_date}|{float(deposit or 0):.2f}|{float(withdrawal or 0):.2f}"
