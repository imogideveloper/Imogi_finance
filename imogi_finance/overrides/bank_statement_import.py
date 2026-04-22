import csv
import json

import frappe
from frappe import _
from frappe.core.doctype.data_import.importer import Importer, ImportFile


def patch_start_import():
    """Monkey patch ERPNext's start_import with fixed version"""
    import erpnext.accounts.doctype.bank_statement_import.bank_statement_import as bsi_module
    bsi_module.start_import = start_import

def add_bank_account(data, bank_account):
	bank_account_loc = None
	if "Bank Account" not in data[0]:
		data[0].append("Bank Account")
	else:
		for loc, header in enumerate(data[0]):
			if header == "Bank Account":
				bank_account_loc = loc

	for row in data[1:]:
		if bank_account_loc is not None:  # FIX: was just 'if bank_account_loc'
			row[bank_account_loc] = bank_account
		else:
			row.append(bank_account)

def start_import(data_import, bank_account, import_file_path, google_sheets_url, bank, template_options):
    """Patched version of erpnext bank statement import to fix UnboundLocalError"""
    import traceback as tb  # tambah ini
    
    from erpnext.accounts.doctype.bank_statement_import.bank_statement_import import (
        parse_data_from_template,
        update_mapping_db,
        write_files,
    )

    try:  # wrap semua dalam try
        update_mapping_db(bank, template_options)
        frappe.log_error("Step 1: update_mapping_db OK", "BSI Debug")

        data_import_doc = frappe.get_doc("Bank Statement Import", data_import)
        frappe.log_error("Step 2: get_doc OK", "BSI Debug")
        
        file = import_file_path if import_file_path else google_sheets_url
        import_file = ImportFile("Bank Transaction", file=file, import_type="Insert New Records")
        frappe.log_error("Step 3: ImportFile OK", "BSI Debug")

        data = parse_data_from_template(import_file.raw_data)
        frappe.log_error(f"Step 4: parse_data OK rows={len(data)}", "BSI Debug")

        if not data_import_doc.get("payload_count"):
            data_import_doc.payload_count = len(data) - 1

        if import_file_path:
            add_bank_account(data, bank_account)
            frappe.log_error("Step 5: add_bank_account OK", "BSI Debug")
            write_files(import_file, data)
            frappe.log_error("Step 6: write_files OK", "BSI Debug")

        i = Importer(data_import_doc.reference_doctype, data_import=data_import_doc)
        frappe.log_error("Step 7: Importer OK", "BSI Debug")
        i.import_data()
        frappe.log_error("Step 8: import_data OK", "BSI Debug")

    except Exception:
        frappe.log_error(tb.format_exc(), "BSI Full Error")  # log full traceback
        frappe.db.rollback()
        frappe.get_doc("Bank Statement Import", data_import).db_set("status", "Error")
    finally:
        frappe.flags.in_import = False

    frappe.publish_realtime("data_import_refresh", {"data_import": data_import})
	
from erpnext.accounts.doctype.bank_statement_import.bank_statement_import import BankStatementImport
from frappe.utils.background_jobs import enqueue

class CustomBankStatementImport(BankStatementImport):
    def start_import(self):
        preview = frappe.get_doc("Bank Statement Import", self.name).get_preview_from_template(
            self.import_file, self.google_sheets_url
        )

        if "Bank Account" not in frappe.as_json(preview["columns"]):
            frappe.throw(_("Please add the Bank Account column"))

        from frappe.utils.background_jobs import is_job_enqueued
        from frappe.utils.scheduler import is_scheduler_inactive

        if is_scheduler_inactive() and not frappe.flags.in_test:
            frappe.throw(_("Scheduler is inactive. Cannot import data."), title=_("Scheduler Inactive"))

        job_id = f"bank_statement_import::{self.name}"
        if not is_job_enqueued(job_id):
            enqueue(
                start_import,  # ← ini sekarang pakai versi fix kita
                queue="default",
                timeout=6000,
                event="data_import",
                job_id=job_id,
                data_import=self.name,
                bank_account=self.bank_account,
                import_file_path=self.import_file,
                google_sheets_url=self.google_sheets_url,
                bank=self.bank,
                template_options=self.template_options,
                now=frappe.conf.developer_mode or frappe.flags.in_test,
            )
            return True

        return False