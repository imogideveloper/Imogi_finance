import csv
import json

import frappe
from frappe import _
from frappe.core.doctype.data_import.importer import Importer, ImportFile


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
	from erpnext.accounts.doctype.bank_statement_import.bank_statement_import import (
		parse_data_from_template,
		update_mapping_db,
		write_files,
	)

	update_mapping_db(bank, template_options)

	data_import = frappe.get_doc("Bank Statement Import", data_import)
	file = import_file_path if import_file_path else google_sheets_url

	import_file = ImportFile("Bank Transaction", file=file, import_type="Insert New Records")

	data = parse_data_from_template(import_file.raw_data)

	if not data_import.get("payload_count"):
		data_import.payload_count = len(data) - 1

	if import_file_path:
		add_bank_account(data, bank_account)  # use fixed version
		write_files(import_file, data)

	try:
		i = Importer(data_import.reference_doctype, data_import=data_import)
		i.import_data()
	except Exception:
		frappe.db.rollback()
		data_import.db_set("status", "Error")
		data_import.log_error("Bank Statement Import failed")
	finally:
		frappe.flags.in_import = False

	frappe.publish_realtime("data_import_refresh", {"data_import": data_import.name})