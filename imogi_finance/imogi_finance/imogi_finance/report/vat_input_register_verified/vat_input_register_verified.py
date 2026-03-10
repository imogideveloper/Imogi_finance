"""
VAT Input Register Verified - ERPNext v15+ Native-First

Shows verified Purchase Invoices with Input VAT details.
Only includes transactions with valid GL entries (properly posted to ledger).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Sum, Coalesce
from frappe.utils import flt, getdate
from typing import Optional, Dict, List, Any

from imogi_finance.imogi_finance.utils.tax_report_utils import (
	validate_vat_input_configuration,
	build_date_conditions,
	get_columns_with_width,
	get_tax_amount_from_gl
)


def execute(filters: Optional[Dict[str, Any]] = None) -> tuple[List[Dict], List[Dict]]:
	"""
	Execute VAT Input Register report.
	
	Args:
		filters: Report filters
		
	Returns:
		Tuple of (columns, data)
	"""
	filters = filters or {}
	
	# Validate configuration first
	validation = validate_vat_input_configuration(filters.get("company"))
	if not validation.get("valid"):
		frappe.msgprint(
			f"{validation.get('message')}<br>{validation.get('action', '')}",
			title=_("Configuration Error"),
			indicator=validation.get("indicator", "red"),
			raise_exception=True
		)
	
	ppn_input_account = validation.get("account")
	columns = get_columns()
	data = get_data(filters, ppn_input_account)
	
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
			"label": _("Reference"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 140
		},
		{
			"label": _("Supplier"),
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 180
		},
		{
			"label": _("Supplier NPWP"),
			"fieldname": "ti_fp_npwp",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Tax Invoice No"),
			"fieldname": "ti_fp_no",
			"fieldtype": "Data",
			"width": 180
		},
		{
			"label": _("Tax Invoice Date"),
			"fieldname": "ti_fp_date",
			"fieldtype": "Date",
			"width": 110
		},
		{
			"label": _("Verification Status"),
			"fieldname": "ti_verification_status",
			"fieldtype": "Data",
			"width": 130
		},
		{
			"label": _("DPP"),
			"fieldname": "ti_fp_dpp",
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"label": _("PPN (Invoice)"),
			"fieldname": "ti_fp_ppn",
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"label": _("PPN (GL Entry)"),
			"fieldname": "tax_amount_gl",
			"fieldtype": "Currency",
			"width": 140
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 150
		},
	]
	
	return get_columns_with_width(columns)


def get_data(filters: Dict[str, Any], ppn_input_account: str) -> List[Dict[str, Any]]:
	"""
	Get VAT Input Register data using frappe.qb with GL Entry validation.
	Only shows invoices that have been properly posted to the ledger.
	"""
	PI = DocType("Purchase Invoice")
	GL = DocType("GL Entry")
	
	# Build base query - JOIN with GL Entry to ensure only posted invoices are shown
	query = (
		frappe.qb.from_(PI)
		.inner_join(GL)
		.on(
			(GL.voucher_type == "Purchase Invoice") &
			(GL.voucher_no == PI.name) &
			(GL.company == PI.company) &
			(GL.is_cancelled == 0)
		)
		.select(
			PI.name,
			PI.posting_date,
			PI.supplier,
			PI.company,
			PI.ti_fp_npwp,
			PI.ti_fp_no,
			PI.ti_fp_date,
			PI.ti_fp_dpp,
			PI.ti_fp_ppn,
			PI.ti_verification_status
		)
		.where(PI.docstatus == 1)
		.distinct()
	)
	
	# Apply filters
	if filters.get("company"):
		query = query.where(PI.company == filters.get("company"))
	
	if filters.get("supplier"):
		query = query.where(PI.supplier == filters.get("supplier"))
	
	# Verification status filter - default to "Verified" if not specified
	verification_status = filters.get("verification_status", "Verified")
	if verification_status:
		query = query.where(PI.ti_verification_status == verification_status)
	
	# Date range conditions
	date_condition = build_date_conditions(PI, filters, "posting_date")
	if date_condition is not None:
		query = query.where(date_condition)
	
	# Order by posting date
	query = query.orderby(PI.posting_date).orderby(PI.name)
	
	# Execute query
	invoices = query.run(as_dict=True)
	
	# Get GL-based tax amounts for each invoice
	data = []
	for invoice in invoices:
		# Get actual tax amount from GL Entry (most reliable source)
		tax_amount_gl = get_tax_amount_from_gl(
			voucher_type="Purchase Invoice",
			voucher_no=invoice.name,
			tax_account=ppn_input_account,
			company=invoice.company
		)
		
		data.append({
			**invoice,
			"tax_amount_gl": tax_amount_gl
		})
	
	return data
