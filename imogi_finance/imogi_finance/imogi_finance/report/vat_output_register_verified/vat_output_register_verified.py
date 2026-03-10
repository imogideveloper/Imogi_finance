"""
VAT Output Register Verified - ERPNext v15+ Native-First

Shows verified Sales Invoices with Output VAT details.
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
	validate_vat_output_configuration,
	build_date_conditions,
	get_columns_with_width,
	get_tax_amount_from_gl
)


def execute(filters: Optional[Dict[str, Any]] = None) -> tuple[List[Dict], List[Dict]]:
	"""
	Execute VAT Output Register report.

	Args:
		filters: Report filters

	Returns:
		Tuple of (columns, data)
	"""
	filters = filters or {}

	# Validate configuration first
	validation = validate_vat_output_configuration(filters.get("company"))
	if not validation.get("valid"):
		frappe.msgprint(
			f"{validation.get('message')}<br>{validation.get('action', '')}",
			title=_("Configuration Error"),
			indicator=validation.get("indicator", "red"),
			raise_exception=True
		)

	ppn_output_account = validation.get("account")
	columns = get_columns()
	data = get_data(filters, ppn_output_account)

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
			"options": "Sales Invoice",
			"width": 140
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 180
		},
		{
			"label": _("Buyer NPWP"),
			"fieldname": "out_fp_customer_npwp",
			"fieldtype": "Data",
			"width": 150
		},
		{
			"label": _("Tax Invoice No"),
			"fieldname": "out_fp_no",
			"fieldtype": "Data",
			"width": 180
		},
		{
			"label": _("Tax Invoice Date"),
			"fieldname": "out_fp_date",
			"fieldtype": "Date",
			"width": 110
		},
		{
			"label": _("Verification Status"),
			"fieldname": "out_fp_status",
			"fieldtype": "Data",
			"width": 130
		},
		{
			"label": _("DPP"),
			"fieldname": "out_fp_dpp",
			"fieldtype": "Currency",
			"width": 130
		},
		{
			"label": _("PPN (Invoice)"),
			"fieldname": "out_fp_ppn",
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


def get_data(filters: Dict[str, Any], ppn_output_account: str) -> List[Dict[str, Any]]:
	"""
	Get VAT Output Register data using frappe.qb with GL Entry validation.
	Only shows invoices that have been properly posted to the ledger.
	"""
	SI = DocType("Sales Invoice")
	GL = DocType("GL Entry")

	# Build base query - JOIN with GL Entry to ensure only posted invoices are shown
	query = (
		frappe.qb.from_(SI)
		.inner_join(GL)
		.on(
			(GL.voucher_type == "Sales Invoice") &
			(GL.voucher_no == SI.name) &
			(GL.company == SI.company) &
			(GL.is_cancelled == 0)
		)
		.select(
			SI.name,
			SI.posting_date,
			SI.customer,
			SI.company,
			SI.out_buyer_tax_id,
			SI.out_fp_no,
			SI.out_fp_date,
			SI.out_fp_dpp,
			SI.out_fp_ppn,
			SI.out_fp_status
		)
		.where(SI.docstatus == 1)
		.distinct()
	)

	# Apply filters
	if filters.get("company"):
		query = query.where(SI.company == filters.get("company"))

	if filters.get("customer"):
		query = query.where(SI.customer == filters.get("customer"))

	# Verification status filter - default to "Verified" if not specified
	verification_status = filters.get("verification_status", "Verified")
	if verification_status:
		query = query.where(SI.out_fp_status == verification_status)

	# Date range conditions
	date_condition = build_date_conditions(SI, filters, "posting_date")
	if date_condition is not None:
		query = query.where(date_condition)

	# Order by posting date
	query = query.orderby(SI.posting_date).orderby(SI.name)

	# Execute query
	invoices = query.run(as_dict=True)

	# Get GL-based tax amounts for each invoice
	data = []
	for invoice in invoices:
		# Get actual tax amount from GL Entry (most reliable source)
		tax_amount_gl = get_tax_amount_from_gl(
			voucher_type="Sales Invoice",
			voucher_no=invoice.name,
			tax_account=ppn_output_account,
			company=invoice.company
		)

		# Use out_buyer_tax_id as the buyer NPWP field
		npwp = invoice.get("out_buyer_tax_id")

		data.append({
			**invoice,
			"out_fp_customer_npwp": npwp,
			"tax_amount_gl": tax_amount_gl
		})

	return data
