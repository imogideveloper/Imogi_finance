"""
Withholding Register - ERPNext v15+ Native-First

Shows GL Entry based withholding tax transactions.
Only includes valid, non-cancelled GL entries for configured PPh accounts.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Sum, Coalesce
from frappe.utils import flt, getdate
from typing import Optional, Dict, List, Any

from imogi_finance.imogi_finance.utils.tax_report_utils import (
	validate_withholding_configuration,
	get_pph_accounts_for_company,
	build_date_conditions,
	get_columns_with_width
)


def execute(filters: Optional[Dict[str, Any]] = None) -> tuple[List[Dict], List[Dict]]:
	"""
	Execute Withholding Register report.
	
	Args:
		filters: Report filters
		
	Returns:
		Tuple of (columns, data)
	"""
	filters = filters or {}
	
	# Company is required for this report
	company = filters.get("company")
	if not company:
		frappe.throw(_("Company is required for Withholding Register"))
	
	# Validate configuration
	validation = validate_withholding_configuration(company)
	if not validation.get("valid"):
		frappe.msgprint(
			f"{validation.get('message')}<br>{validation.get('action', '')}",
			title=_("Configuration Error"),
			indicator=validation.get("indicator", "red"),
			raise_exception=True
		)
	
	# Get accounts to filter - either from filter or from Tax Profile
	accounts = filters.get("accounts")
	if accounts and not isinstance(accounts, list):
		accounts = [accounts]
	
	if not accounts:
		accounts = validation.get("accounts", [])
	
	if not accounts:
		frappe.throw(_("No withholding tax accounts configured or selected"))
	
	columns = get_columns()
	data = get_data(filters, company, accounts)
	
	return columns, data


def get_columns() -> List[Dict[str, Any]]:
	"""Define report columns with ERPNext v15+ standards."""
	columns = [
		{
			"label": _("Posting Date"),
			"fieldname": "posting_date",
			"fieldtype": "Date",
			"width": 100
		},
		{
			"label": _("Account"),
			"fieldname": "account",
			"fieldtype": "Link",
			"options": "Account",
			"width": 200
		},
		{
			"label": _("Party Type"),
			"fieldname": "party_type",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("Party"),
			"fieldname": "party",
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 180
		},
		{
			"label": _("Voucher Type"),
			"fieldname": "voucher_type",
			"fieldtype": "Data",
			"width": 140
		},
		{
			"label": _("Voucher No"),
			"fieldname": "voucher_no",
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 160
		},
		{
			"label": _("Debit"),
			"fieldname": "debit",
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"label": _("Credit"),
			"fieldname": "credit",
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"label": _("Net Amount"),
			"fieldname": "net_amount",
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"label": _("Remarks"),
			"fieldname": "remarks",
			"fieldtype": "Small Text",
			"width": 220
		},
	]
	
	return get_columns_with_width(columns)


def get_data(filters: Dict[str, Any], company: str, accounts: List[str]) -> List[Dict[str, Any]]:
	"""
	Get Withholding Register data using frappe.qb.
	Returns only valid, non-cancelled GL entries.
	"""
	GL = DocType("GL Entry")
	
	# Build base query - only non-cancelled GL entries
	query = (
		frappe.qb.from_(GL)
		.select(
			GL.posting_date,
			GL.account,
			GL.party_type,
			GL.party,
			GL.voucher_type,
			GL.voucher_no,
			GL.debit,
			GL.credit,
			GL.remarks
		)
		.where(GL.company == company)
		.where(GL.is_cancelled == 0)
	)
	
	# Filter by accounts
	if accounts:
		query = query.where(GL.account.isin(accounts))
	
	# Apply date range
	date_condition = build_date_conditions(GL, filters, "posting_date")
	if date_condition is not None:
		query = query.where(date_condition)
	
	# Filter by party if specified
	if filters.get("party"):
		query = query.where(GL.party == filters.get("party"))
	
	# Filter by voucher type if specified
	if filters.get("voucher_type"):
		query = query.where(GL.voucher_type == filters.get("voucher_type"))
	
	# Order by posting date and account
	query = query.orderby(GL.posting_date).orderby(GL.account).orderby(GL.voucher_no)
	
	# Execute query
	entries = query.run(as_dict=True)
	
	# Calculate net amount (credit - debit for liability accounts)
	for entry in entries:
		entry["net_amount"] = flt(entry.get("credit", 0)) - flt(entry.get("debit", 0))
	
	return entries
