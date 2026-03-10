"""
Tax Report Utilities - ERPNext v15+ Native-First

Modular utilities for tax registers with GL Entry validation.
This ensures only properly posted transactions with valid journal entries are shown.
"""

import frappe
from frappe import _
from frappe.query_builder import DocType, Criterion
from frappe.query_builder.functions import Sum, Coalesce
from frappe.utils import flt, getdate
from typing import Optional, Dict, List, Tuple, Any

from imogi_finance.settings.utils import (
	get_tax_profile as _get_tax_profile_helper,
	get_ppn_accounts,
	get_tax_invoice_ocr_settings as _get_tax_invoice_ocr_settings_helper,
)


def get_tax_profile(company: str) -> Optional[frappe._dict]:
	"""
	Get Tax Profile for company with caching.

	Args:
		company: Company name

	Returns:
		Tax Profile document as dict or None
	"""
	if not company:
		return None

	try:
		profile = _get_tax_profile_helper(company)
		return frappe._dict(profile.as_dict())
	except frappe.ValidationError:
		return None


def get_tax_invoice_ocr_settings() -> frappe._dict:
	"""
	Get Tax Invoice OCR Settings with caching.

	Returns:
		Settings as dict with default values
	"""
	try:
		settings = _get_tax_invoice_ocr_settings_helper()
		return frappe._dict(settings.as_dict())
	except frappe.ValidationError:
		return frappe._dict({})


def validate_vat_input_configuration(company: Optional[str] = None) -> Dict[str, Any]:
	"""
	Validate VAT Input Register configuration by checking Tax Profile.

	Args:
		company: Company name to validate

	Returns:
		Dict with validation result and messages
	"""
	if not company:
		return {
			"valid": False,
			"message": _("Company not specified."),
			"indicator": "red"
		}

	try:
		ppn_input_account, _unused = get_ppn_accounts(company)
	except frappe.ValidationError as e:
		return {
			"valid": False,
			"message": str(e),
			"action": _("Please configure Tax Profile for company '{0}'").format(company),
			"indicator": "red"
		}

	# Verify account exists
	if not frappe.db.exists("Account", ppn_input_account):
		return {
			"valid": False,
			"message": _("PPN Input Account '{0}' does not exist.").format(ppn_input_account),
			"action": _("Please update the Tax Profile."),
			"indicator": "red"
		}

	# Verify account is active
	is_disabled = frappe.db.get_value("Account", ppn_input_account, "disabled")
	if is_disabled:
		return {
			"valid": False,
			"message": _("PPN Input Account '{0}' is disabled.").format(ppn_input_account),
			"action": _("Please enable the account or update configuration."),
			"indicator": "orange"
		}

	return {
		"valid": True,
		"account": ppn_input_account,
		"message": _("Configuration is valid."),
		"indicator": "green"
	}


def validate_vat_output_configuration(company: Optional[str] = None) -> Dict[str, Any]:
	"""
	Validate VAT Output Register configuration by checking Tax Profile.

	Args:
		company: Company name to validate

	Returns:
		Dict with validation result and messages
	"""
	if not company:
		return {
			"valid": False,
			"message": _("Company not specified."),
			"indicator": "red"
		}

	try:
		_unused, ppn_output_account = get_ppn_accounts(company)
	except frappe.ValidationError as e:
		return {
			"valid": False,
			"message": str(e),
			"action": _("Please configure Tax Profile for company '{0}'").format(company),
			"indicator": "red"
		}

	# Verify account exists
	if not frappe.db.exists("Account", ppn_output_account):
		return {
			"valid": False,
			"message": _("PPN Output Account '{0}' does not exist.").format(ppn_output_account),
			"action": _("Please update the Tax Profile."),
			"indicator": "red"
		}

	# Verify account is active
	is_disabled = frappe.db.get_value("Account", ppn_output_account, "disabled")
	if is_disabled:
		return {
			"valid": False,
			"message": _("PPN Output Account '{0}' is disabled.").format(ppn_output_account),
			"action": _("Please enable the account or update configuration."),
			"indicator": "orange"
		}

	return {
		"valid": True,
		"account": ppn_output_account,
		"message": _("Configuration is valid."),
		"indicator": "green"
	}


def validate_withholding_configuration(company: str) -> Dict[str, Any]:
	"""
	Validate Withholding Register configuration.

	Args:
		company: Company name to validate

	Returns:
		Dict with validation result and messages
	"""
	if not company:
		return {
			"valid": False,
			"message": _("Company is required for Withholding Register."),
			"indicator": "red"
		}

	profile = get_tax_profile(company)

	if not profile:
		return {
			"valid": False,
			"message": _("Tax Profile not found for company '{0}'.").format(company),
			"action": _("Please create a Tax Profile for this company."),
			"indicator": "red"
		}

	pph_accounts = profile.get("pph_accounts") or []

	if not pph_accounts:
		return {
			"valid": False,
			"message": _("No PPh accounts configured in Tax Profile for '{0}'.").format(company),
			"action": _("Please configure PPh accounts at: <a href='/app/tax-profile/{0}'>Tax Profile</a>").format(profile.name),
			"indicator": "red"
		}

	# Verify at least one valid account exists
	valid_accounts = []
	for row in pph_accounts:
		account = row.get("payable_account")
		if account and frappe.db.exists("Account", account):
			is_disabled = frappe.db.get_value("Account", account, "disabled")
			if not is_disabled:
				valid_accounts.append(account)

	if not valid_accounts:
		return {
			"valid": False,
			"message": _("No valid PPh accounts found in Tax Profile."),
			"action": _("Please check account configuration at: <a href='/app/tax-profile/{0}'>Tax Profile</a>").format(profile.name),
			"indicator": "orange"
		}

	return {
		"valid": True,
		"accounts": valid_accounts,
		"message": _("Configuration is valid. {0} PPh account(s) configured.").format(len(valid_accounts)),
		"indicator": "green"
	}


def get_pph_accounts_for_company(company: str) -> List[str]:
	"""
	Get list of PPh payable accounts for a company.

	Args:
		company: Company name

	Returns:
		List of account names
	"""
	profile = get_tax_profile(company)

	if not profile:
		return []

	pph_accounts = profile.get("pph_accounts") or []
	accounts = []

	for row in pph_accounts:
		account = row.get("payable_account")
		if account:
			accounts.append(account)

	return accounts


def build_date_conditions(qb_table, filters: Dict[str, Any], date_field: str = "posting_date") -> Optional[Criterion]:
	"""
	Build date range conditions for Query Builder.

	Args:
		qb_table: Query Builder table object
		filters: Filter dictionary
		date_field: Name of the date field to filter

	Returns:
		Query Builder criterion or None
	"""
	conditions = []

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")

	if from_date:
		from_date = getdate(from_date)
		conditions.append(getattr(qb_table, date_field) >= from_date)

	if to_date:
		to_date = getdate(to_date)
		conditions.append(getattr(qb_table, date_field) <= to_date)

	if not conditions:
		return None

	criterion = conditions[0]
	for condition in conditions[1:]:
		criterion = criterion & condition

	return criterion


def has_valid_gl_entries(voucher_type: str, voucher_no: str, company: str) -> bool:
	"""
	Check if a voucher has valid GL entries (properly posted to ledger).
	This is critical for tax reporting - only show transactions that are in the books.

	Args:
		voucher_type: Type of voucher (Purchase Invoice, Sales Invoice, etc.)
		voucher_no: Voucher number/name
		company: Company name

	Returns:
		True if valid GL entries exist, False otherwise
	"""
	GLEntry = DocType("GL Entry")

	query = (
		frappe.qb.from_(GLEntry)
		.select(GLEntry.name)
		.where(GLEntry.voucher_type == voucher_type)
		.where(GLEntry.voucher_no == voucher_no)
		.where(GLEntry.company == company)
		.where(GLEntry.is_cancelled == 0)
		.limit(1)
	)

	result = query.run(as_dict=True)
	return len(result) > 0


def get_tax_amount_from_gl(
	voucher_type: str,
	voucher_no: str,
	tax_account: str,
	company: str
) -> float:
	"""
	Get tax amount from GL Entry for a specific voucher.
	This ensures we report the actual posted tax amount from the ledger.

	Args:
		voucher_type: Type of voucher
		voucher_no: Voucher number/name
		tax_account: Tax account name
		company: Company name

	Returns:
		Tax amount (credit - debit for liability, debit - credit for asset)
	"""
	GLEntry = DocType("GL Entry")

	# Determine if this is an asset or liability account using root_type
	# root_type is more reliable than account_type for Indonesian VAT accounts
	# where both Input and Output VAT may have account_type = "Tax"
	root_type = frappe.db.get_value("Account", tax_account, "root_type")

	query = (
		frappe.qb.from_(GLEntry)
		.select(
			Coalesce(Sum(GLEntry.debit), 0).as_("total_debit"),
			Coalesce(Sum(GLEntry.credit), 0).as_("total_credit")
		)
		.where(GLEntry.voucher_type == voucher_type)
		.where(GLEntry.voucher_no == voucher_no)
		.where(GLEntry.account == tax_account)
		.where(GLEntry.company == company)
		.where(GLEntry.is_cancelled == 0)
	)

	result = query.run(as_dict=True)

	if not result:
		return 0.0

	total_debit = flt(result[0].total_debit)
	total_credit = flt(result[0].total_credit)

	# For Input VAT (Asset root_type), use debit amount
	# For Output VAT (Liability root_type), use credit amount
	if root_type == "Liability":
		# Liability account - credit increases the liability
		return total_credit - total_debit
	else:
		# Asset account (including root_type "Asset") - debit increases the asset
		return total_debit - total_credit


def get_tax_amounts_batch(
	voucher_list: List[Tuple[str, str]],
	tax_account: str,
	company: str
) -> Dict[Tuple[str, str], float]:
	"""
	Get tax amounts from GL Entry for multiple vouchers in a single query.
	This solves the N+1 query problem when processing many invoices.

	Args:
		voucher_list: List of (voucher_type, voucher_no) tuples
		tax_account: Tax account name
		company: Company name

	Returns:
		Dict mapping (voucher_type, voucher_no) to tax amount

	Example:
		>>> vouchers = [("Purchase Invoice", "PI-001"), ("Purchase Invoice", "PI-002")]
		>>> amounts = get_tax_amounts_batch(vouchers, "PPN Masukan - IMOGI", "IMOGI")
		>>> amounts[("Purchase Invoice", "PI-001")]
		121000.0
	"""
	if not voucher_list:
		return {}

	GLEntry = DocType("GL Entry")

	# Determine if this is an asset or liability account using root_type
	# root_type is more reliable than account_type for Indonesian VAT accounts
	root_type = frappe.db.get_value("Account", tax_account, "root_type")
	is_liability = root_type == "Liability"

	# Build list of voucher_no values to filter
	voucher_nos = [voucher_no for _, voucher_no in voucher_list]

	# Single query to get all GL entries for these vouchers
	query = (
		frappe.qb.from_(GLEntry)
		.select(
			GLEntry.voucher_type,
			GLEntry.voucher_no,
			Coalesce(Sum(GLEntry.debit), 0).as_("total_debit"),
			Coalesce(Sum(GLEntry.credit), 0).as_("total_credit")
		)
		.where(GLEntry.voucher_no.isin(voucher_nos))
		.where(GLEntry.account == tax_account)
		.where(GLEntry.company == company)
		.where(GLEntry.is_cancelled == 0)
		.groupby(GLEntry.voucher_type, GLEntry.voucher_no)
	)

	results = query.run(as_dict=True)

	# Build result dictionary
	amounts = {}
	for row in results:
		voucher_key = (row.voucher_type, row.voucher_no)
		total_debit = flt(row.total_debit)
		total_credit = flt(row.total_credit)

		# Calculate net amount based on root_type
		if is_liability:
			amounts[voucher_key] = total_credit - total_debit
		else:
			amounts[voucher_key] = total_debit - total_credit

	# Ensure all requested vouchers have an entry (0.0 if not found)
	for voucher_key in voucher_list:
		if voucher_key not in amounts:
			amounts[voucher_key] = 0.0

	return amounts


def get_columns_with_width(columns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
	"""
	Ensure all columns have proper width settings for ERPNext v15+.

	Args:
		columns: List of column definitions

	Returns:
		Enhanced column list with proper widths
	"""
	for col in columns:
		if "width" not in col:
			fieldtype = col.get("fieldtype", "Data")

			# Default widths based on field type
			if fieldtype == "Currency":
				col["width"] = 120
			elif fieldtype == "Date":
				col["width"] = 100
			elif fieldtype == "Link":
				col["width"] = 150
			elif fieldtype == "Data":
				col["width"] = 140
			elif fieldtype == "Select":
				col["width"] = 110
			else:
				col["width"] = 120

	return columns


def format_status_indicator(status: str) -> str:
	"""
	Format status with HTML indicator for better UI.

	Args:
		status: Status value (Verified, Needs Review, Rejected, etc.)

	Returns:
		HTML formatted status
	"""
	color_map = {
		"Verified": "green",
		"Needs Review": "orange",
		"Rejected": "red",
		"Pending": "blue",
		"Draft": "gray"
	}

	color = color_map.get(status, "gray")

	return f'<span class="indicator-pill {color}">{status}</span>'


@frappe.whitelist()
def validate_tax_register_configuration(register_type: str, company: Optional[str] = None) -> Dict[str, Any]:
	"""
	Whitelisted method to validate tax register configuration from client.

	Args:
		register_type: Type of register (input, output, withholding)
		company: Company name (required for withholding)

	Returns:
		Validation result dictionary
	"""
	if register_type == "input":
		return validate_vat_input_configuration(company)
	elif register_type == "output":
		return validate_vat_output_configuration(company)
	elif register_type == "withholding":
		if not company:
			return {
				"valid": False,
				"message": _("Company is required for withholding register validation."),
				"indicator": "red"
			}
		return validate_withholding_configuration(company)
	else:
		return {
			"valid": False,
			"message": _("Invalid register type: {0}").format(register_type),
			"indicator": "red"
		}


def clear_tax_profile_cache(company: str):
	"""
	Clear Tax Profile cache when it's updated.
	Hook this to Tax Profile on_update event.

	Args:
		company: Company name
	"""
	cache_key = f"tax_profile:{company}"
	frappe.cache().delete_value(cache_key)


def clear_tax_settings_cache():
	"""
	Clear Tax Invoice OCR Settings cache when it's updated.
	Hook this to Tax Invoice OCR Settings on_update event.
	"""
	cache_key = "tax_invoice_ocr_settings"
	frappe.cache().delete_value(cache_key)
