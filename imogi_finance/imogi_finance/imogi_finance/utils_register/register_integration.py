"""
Register Integration Utilities - ERPNext v15+ Native-First

Provides unified interface to VAT and Withholding registers for Tax Period Closing.
Handles report execution, data aggregation, and batch GL retrieval optimization.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate
from typing import Dict, List, Any, Optional, Tuple
from datetime import date


class RegisterIntegrationError(Exception):
	"""Custom exception for register integration errors."""
	pass


def get_vat_input_from_register(
	company: str,
	from_date: date | str,
	to_date: date | str,
	verification_status: Optional[str] = None
) -> Dict[str, Any]:
	"""
	Get VAT Input totals from VAT Input Register Verified report.

	Args:
		company: Company name
		from_date: Period start date
		to_date: Period end date
		verification_status: Invoice verification status filter (default: "Verified")

	Returns:
		Dict with total_dpp, total_ppn, invoice_count, and invoices list

	Raises:
		RegisterIntegrationError: If report execution fails
	"""
	try:
		# Import report module
		from imogi_finance.imogi_finance.report.vat_input_register_verified.vat_input_register_verified import execute

		# Prepare filters
		filters = {
			"company": company,
			"from_date": getdate(from_date),
			"to_date": getdate(to_date),
			"verification_status": verification_status
		}

		# Execute report
		columns, data = execute(filters)

		# Aggregate totals
		total_dpp = 0.0
		total_ppn = 0.0
		invoice_count = len(data)

		for row in data:
			# Use GL Entry tax amount as source of truth
			# Input VAT is always a tax credit (positive from tax perspective)
			# regardless of GL debit/credit sign
			tax_amount = abs(flt(row.get("tax_amount_gl", 0)))
			dpp = flt(row.get("ti_fp_dpp", 0))

			total_ppn += tax_amount
			total_dpp += dpp

		return {
			"total_dpp": total_dpp,
			"total_ppn": total_ppn,
			"invoice_count": invoice_count,
			"invoices": data,
			"verification_status": verification_status
		}

	except Exception as e:
		error_msg = f"Failed to get VAT Input data from register: {str(e)}"
		frappe.log_error(error_msg, "Register Integration Error")
		raise RegisterIntegrationError(error_msg) from e


def get_vat_output_from_register(
	company: str,
	from_date: date | str,
	to_date: date | str,
	verification_status: Optional[str] = None
) -> Dict[str, Any]:
	"""
	Get VAT Output totals from VAT Output Register Verified report.

	Args:
		company: Company name
		from_date: Period start date
		to_date: Period end date
		verification_status: Invoice verification status filter (default: "Verified")

	Returns:
		Dict with total_dpp, total_ppn, invoice_count, and invoices list

	Raises:
		RegisterIntegrationError: If report execution fails
	"""
	try:
		# Import report module
		from imogi_finance.imogi_finance.report.vat_output_register_verified.vat_output_register_verified import execute

		# Prepare filters
		filters = {
			"company": company,
			"from_date": getdate(from_date),
			"to_date": getdate(to_date),
			"verification_status": verification_status
		}

		# Execute report
		columns, data = execute(filters)

		# Aggregate totals
		total_dpp = 0.0
		total_ppn = 0.0
		invoice_count = len(data)

		for row in data:
			# Use GL Entry tax amount as source of truth
			tax_amount = flt(row.get("tax_amount_gl", 0))
			dpp = flt(row.get("out_fp_dpp", 0))

			total_ppn += tax_amount
			total_dpp += dpp

		return {
			"total_dpp": total_dpp,
			"total_ppn": total_ppn,
			"invoice_count": invoice_count,
			"invoices": data,
			"verification_status": verification_status
		}

	except Exception as e:
		error_msg = f"Failed to get VAT Output data from register: {str(e)}"
		frappe.log_error(error_msg, "Register Integration Error")
		raise RegisterIntegrationError(error_msg) from e


def get_withholding_from_register(
	company: str,
	from_date: date | str,
	to_date: date | str,
	accounts: Optional[List[str]] = None
) -> Dict[str, Any]:
	"""
	Get Withholding Tax totals from Withholding Register report.

	Args:
		company: Company name
		from_date: Period start date
		to_date: Period end date
		accounts: List of PPh account names to filter (optional, uses Tax Profile if None)

	Returns:
		Dict with totals by account, total_amount, entry_count, and entries list

	Raises:
		RegisterIntegrationError: If report execution fails
	"""
	try:
		# Import report module
		from imogi_finance.imogi_finance.report.withholding_register.withholding_register import execute

		# Prepare filters
		filters = {
			"company": company,
			"from_date": getdate(from_date),
			"to_date": getdate(to_date)
		}

		if accounts:
			filters["accounts"] = accounts

		# Execute report
		columns, data = execute(filters)

		# Aggregate totals by account
		totals_by_account = {}
		total_amount = 0.0
		entry_count = len(data)

		for row in data:
			account = row.get("account")
			net_amount = flt(row.get("net_amount", 0))

			if account:
				if account not in totals_by_account:
					totals_by_account[account] = 0.0
				totals_by_account[account] += net_amount

			total_amount += net_amount

		return {
			"totals_by_account": totals_by_account,
			"total_amount": total_amount,
			"entry_count": entry_count,
			"entries": data
		}

	except Exception as e:
		error_msg = f"Failed to get Withholding data from register: {str(e)}"
		frappe.log_error(error_msg, "Register Integration Error")
		raise RegisterIntegrationError(error_msg) from e


def get_all_register_data(
	company: str,
	from_date: date | str,
	to_date: date | str,
	verification_status: Optional[str] = None,
	withholding_accounts: Optional[List[str]] = None
) -> Dict[str, Any]:
	"""
	Get all tax register data in a single call for Tax Period Closing.

	This is the main entry point for Tax Period Closing to retrieve
	register-based data with verification filtering.

	Args:
		company: Company name
		from_date: Period start date
		to_date: Period end date
		verification_status: VAT verification status (default: "Verified")
		withholding_accounts: PPh accounts list (uses Tax Profile if None)

	Returns:
		Dict with vat_input, vat_output, withholding, and summary sections

	Raises:
		RegisterIntegrationError: If any report execution fails
	"""
	try:
		# Get VAT Input data
		vat_input = get_vat_input_from_register(
			company=company,
			from_date=from_date,
			to_date=to_date,
			verification_status=verification_status
		)

		# Get VAT Output data
		vat_output = get_vat_output_from_register(
			company=company,
			from_date=from_date,
			to_date=to_date,
			verification_status=verification_status
		)

		# Get Withholding data
		withholding = get_withholding_from_register(
			company=company,
			from_date=from_date,
			to_date=to_date,
			accounts=withholding_accounts
		)

		# Calculate VAT netting
		vat_net = vat_output["total_ppn"] - vat_input["total_ppn"]

		# Build comprehensive result
		return {
			"vat_input": vat_input,
			"vat_output": vat_output,
			"withholding": withholding,
			"summary": {
				"input_vat_total": vat_input["total_ppn"],
				"input_vat_dpp": vat_input["total_dpp"],
				"input_invoice_count": vat_input["invoice_count"],
				"output_vat_total": vat_output["total_ppn"],
				"output_vat_dpp": vat_output["total_dpp"],
				"output_invoice_count": vat_output["invoice_count"],
				"vat_net": vat_net,
				"vat_net_direction": "payable" if vat_net > 0 else "receivable" if vat_net < 0 else "zero",
				"withholding_total": withholding["total_amount"],
				"withholding_entry_count": withholding["entry_count"],
				"verification_status": verification_status
			},
			"metadata": {
				"company": company,
				"from_date": getdate(from_date),
				"to_date": getdate(to_date),
				"generated_at": frappe.utils.now(),
				"generated_by": frappe.session.user
			}
		}

	except RegisterIntegrationError:
		# Re-raise our custom errors
		raise
	except Exception as e:
		error_msg = f"Failed to get complete register data: {str(e)}"
		frappe.log_error(error_msg, "Register Integration Error")
		raise RegisterIntegrationError(error_msg) from e


def validate_register_configuration(company: str) -> Dict[str, Any]:
	"""
	Validate that all required register configurations are in place.

	Args:
		company: Company name to validate

	Returns:
		Dict with validation results for each register type
	"""
	from imogi_finance.imogi_finance.utils.tax_report_utils import (
		validate_vat_input_configuration,
		validate_vat_output_configuration,
		validate_withholding_configuration
	)

	vat_input_validation = validate_vat_input_configuration(company)
	vat_output_validation = validate_vat_output_configuration(company)
	withholding_validation = validate_withholding_configuration(company)

	all_valid = (
		vat_input_validation.get("valid") and
		vat_output_validation.get("valid") and
		withholding_validation.get("valid")
	)

	return {
		"valid": all_valid,
		"vat_input": vat_input_validation,
		"vat_output": vat_output_validation,
		"withholding": withholding_validation,
		"message": _("All register configurations are valid.") if all_valid else _(
			"Some register configurations are invalid. Please check the details."
		)
	}
