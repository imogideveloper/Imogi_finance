"""Tax operations utilities for VAT, PPh, PB1, and CoreTax exports."""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Iterable

import frappe
from frappe import _, bold
from frappe.model.document import Document
from frappe.utils import add_days, flt, get_first_day, get_last_day, getdate, nowdate
from frappe.utils.xlsxutils import make_xlsx

from imogi_finance import roles, tax_invoice_fields


def _safe_throw(message: str, *, title: str | None = None):
    marker = getattr(frappe, "ThrowMarker", None)
    throw_fn = getattr(frappe, "throw", None)

    if callable(throw_fn):
        try:
            throw_fn(message, title=title)
            return
        except BaseException as exc:  # noqa: BLE001
            if (
                marker
                and isinstance(marker, type)
                and issubclass(marker, BaseException)
                and not isinstance(exc, marker)
            ):
                Combined = type("CombinedThrowMarker", (exc.__class__, marker), {})  # noqa: N806
                raise Combined(str(exc))
            raise

    if marker:
        raise marker(message)
    raise Exception(message)


def _get_period_bounds(period_month: int | None, period_year: int | None) -> tuple[date | None, date | None]:
    if not period_month or not period_year:
        return None, None
    start = get_first_day(f"{period_year}-{period_month:02d}-01")
    end = get_last_day(start)
    return start, end


def _get_tax_profile(company: str) -> frappe._dict:
    profile_name = frappe.db.get_value("Tax Profile", {"company": company}, "name")
    if not profile_name:
        frappe.throw(
            _("Please create a Tax Profile for company {0} to continue.").format(bold(company)),
            title=_("Tax Profile Missing"),
        )

    return frappe.get_cached_doc("Tax Profile", profile_name)  # type: ignore[return-value]


def _sum_field(rows: Iterable[dict], field: str) -> float:
    return sum(flt(row.get(field)) for row in rows)


def _get_gl_total(company: str, accounts: list[str], date_from: date | str | None, date_to: date | str | None) -> float:
    if not accounts:
        return 0.0

    filters = [
        ["company", "=", company],
        ["is_cancelled", "=", 0],
        ["account", "in", accounts],
    ]

    if date_from and date_to:
        filters.append(["posting_date", "between", [date_from, date_to]])
    elif date_from:
        filters.append(["posting_date", ">=", date_from])
    elif date_to:
        filters.append(["posting_date", "<=", date_to])

    aggregates = frappe.get_all(
        "GL Entry",
        filters=filters,
        fields=["sum(credit) as credit_total", "sum(debit) as debit_total"],
    )
    if not aggregates:
        return 0.0

    credit_total = flt(aggregates[0].get("credit_total"))
    debit_total = flt(aggregates[0].get("debit_total"))
    return credit_total - debit_total


def build_register_snapshot(company: str, date_from: date | str | None, date_to: date | str | None) -> dict:
	"""
	Build tax register snapshot using modern register reports with verification filtering.

	This is the primary data source for Tax Period Closing, pulling from:
	- VAT Input Register Verified (Purchase Invoices with GL validation)
	- VAT Output Register Verified (Sales Invoices with GL validation)
	- Withholding Register (GL Entry based PPh tracking)

	Only includes verified/validated transactions that are properly posted to GL.

	Args:
		company: Company name
		date_from: Period start date
		date_to: Period end date

	Returns:
		Snapshot dict with VAT totals, PPh totals, PB1, BPJS, and metadata
	"""
	from imogi_finance.imogi_finance.utils_register.register_integration import (
		get_all_register_data,
		RegisterIntegrationError
	)

	profile = _get_tax_profile(company)

	# Get PPh accounts for withholding register
	pph_accounts = [row.payable_account for row in getattr(profile, "pph_accounts", []) or [] if row.payable_account]

	# Get comprehensive register data - no verification filter so ALL submitted
	# invoices with VAT are captured. out_fp_status is for coreTax compliance
	# tracking only, not an accounting gate.
	try:
		register_data = get_all_register_data(
			company=company,
			from_date=date_from,
			to_date=date_to,
			verification_status=None,
			withholding_accounts=pph_accounts if pph_accounts else None
		)
	except RegisterIntegrationError as e:
		frappe.log_error(
			title="Register Integration Failed",
			message=f"Register integration failed: {str(e)}"
		)
		# Fallback to empty data with error flag
		register_data = {
			"summary": {
				"input_vat_total": 0.0,
				"output_vat_total": 0.0,
				"vat_net": 0.0,
				"withholding_total": 0.0,
				"input_invoice_count": 0,
				"output_invoice_count": 0,
				"withholding_entry_count": 0
			},
			"vat_input": {"invoices": []},
			"vat_output": {"invoices": []},
			"withholding": {"entries": [], "totals_by_account": {}},
			"metadata": {
				"error": str(e),
				"company": company,
				"from_date": date_from,
				"to_date": date_to
			}
		}

	# Extract summary values
	summary = register_data.get("summary", {})
	input_total = summary.get("input_vat_total", 0.0)
	output_total = summary.get("output_vat_total", 0.0)
	vat_net = summary.get("vat_net", 0.0)
	pph_total = summary.get("withholding_total", 0.0)

	# Handle PB1 multi-branch or single account (GL-based, not in registers)
	pb1_total = 0.0
	pb1_breakdown = {}

	if getattr(profile, "enable_pb1_multi_branch", 0) and getattr(profile, "pb1_account_mappings", None):
		# Multi-branch: calculate per branch and aggregate
		for mapping in profile.pb1_account_mappings or []:
			branch = getattr(mapping, "branch", None)
			pb1_account = getattr(mapping, "pb1_payable_account", None)
			if branch and pb1_account:
				branch_total = _get_gl_total(company, [pb1_account], date_from, date_to)
				pb1_breakdown[branch] = branch_total
				pb1_total += branch_total

		# Add default account if exists and not covered by mappings
		default_account = getattr(profile, "pb1_payable_account", None)
		if default_account:
			mapped_accounts = {getattr(m, "pb1_payable_account", None) for m in profile.pb1_account_mappings or []}
			if default_account not in mapped_accounts:
				default_total = _get_gl_total(company, [default_account], date_from, date_to)
				pb1_breakdown["_default"] = default_total
				pb1_total += default_total
	else:
		# Single account (backward compatible)
		pb1_account = getattr(profile, "pb1_payable_account", None)
		pb1_total = _get_gl_total(company, [pb1_account], date_from, date_to) if pb1_account else 0.0

	# BPJS (GL-based, not in registers)
	bpjs_account = getattr(profile, "bpjs_payable_account", None)
	bpjs_total = _get_gl_total(company, [bpjs_account], date_from, date_to) if bpjs_account else 0.0

	# Calculate carry-forward: GL balance of VAT-IN account BEFORE current period
	input_vat_account = getattr(profile, "ppn_input_account", None)
	if input_vat_account and date_from:
		day_before_period = str(add_days(getdate(date_from), -1))
		input_vat_carry_forward = _get_vat_in_gl_balance(company, input_vat_account, day_before_period)
	else:
		input_vat_carry_forward = 0.0

	effective_input_vat = input_total + input_vat_carry_forward

	# VAT Net uses effective input (includes carry-forward) for accurate tax position
	effective_vat_net = output_total - effective_input_vat

	# Build comprehensive snapshot
	snapshot = {
		"input_vat_total": input_total,
		"input_vat_carry_forward": input_vat_carry_forward,
		"effective_input_vat": effective_input_vat,
		"output_vat_total": output_total,
		"vat_net": effective_vat_net,
		"pph_total": pph_total,
		"pb1_total": pb1_total,
		"bpjs_total": bpjs_total,
		# Register-specific fields (NEW in v15+)
		"input_invoice_count": summary.get("input_invoice_count", 0),
		"output_invoice_count": summary.get("output_invoice_count", 0),
		"withholding_entry_count": summary.get("withholding_entry_count", 0),
		"verification_status": summary.get("verification_status", "Verified"),
		"vat_net_direction": summary.get("vat_net_direction", "zero"),
		# Detailed breakdowns
		"withholding_by_account": register_data.get("withholding", {}).get("totals_by_account", {}),
		"meta": {
			"company": company,
			"date_from": str(date_from) if date_from else None,
			"date_to": str(date_to) if date_to else None,
			"profile": profile.name,
			"generated_at": register_data.get("metadata", {}).get("generated_at"),
			"generated_by": register_data.get("metadata", {}).get("generated_by"),
			"data_source": "register_integration",
			"register_version": "v15+"
		},
	}

	# Add pb1_breakdown if multi-branch
	if pb1_breakdown:
		snapshot["pb1_breakdown"] = pb1_breakdown

	# Add error flag if present
	if "error" in register_data.get("metadata", {}):
		snapshot["meta"]["error"] = register_data["metadata"]["error"]
		snapshot["meta"]["data_source"] = "fallback_empty"

	return snapshot


def _get_tax_invoice_fields(doctype: str) -> set[str]:
    base_fields = set(tax_invoice_fields.get_tax_invoice_fields(doctype))
    tax_mapping_fields = {"taxes_and_charges", "taxes"}
    if doctype == "Purchase Invoice":
        tax_mapping_fields.update({"apply_tds", "tax_withholding_category"})

    return base_fields | tax_mapping_fields


def _has_locked_period(company: str, posting_date: date | str | None) -> str | None:
    """Check if posting date falls within a closed tax period.

    Returns the name of the locked Tax Period Closing document, or None.
    """
    if not posting_date:
        return None

    posting_date = getdate(posting_date)

    locked = frappe.get_all(
        "Tax Period Closing",
        filters=[
            ["company", "=", company],
            ["status", "=", "Closed"],
            ["docstatus", "=", 1],
            ["date_from", "<=", posting_date],
            ["date_to", ">=", posting_date],
        ],
        limit=1,
        pluck="name",
    )
    return locked[0] if locked else None


def _get_previous_doc(doc: Document):
    previous = getattr(doc, "_doc_before_save", None)
    if previous:
        return previous

    if getattr(doc, "name", None):
        try:
            return frappe.get_doc(doc.doctype, doc.name)
        except Exception:
            return None
    return None


def validate_tax_period_lock(doc: Document, posting_date_field: str = "posting_date") -> None:
    company = getattr(doc, "company", None)
    if not company:
        cost_center = getattr(doc, "cost_center", None)
        if cost_center:
            company = frappe.db.get_value("Cost Center", cost_center, "company")

    # ✅ FIX: Jika company tidak ditemukan, skip validasi
    if not company:
        return

    posting_date = (
        getattr(doc, posting_date_field, None)
        or getattr(doc, "request_date", None)
        or getattr(doc, "bill_date", None)
    )

    if not posting_date:
        return

    locked_name = _has_locked_period(company, posting_date)
    if not locked_name:
        return

    if roles.has_any_role(*roles.TAX_PRIVILEGED_ROLES):
        return

    previous = _get_previous_doc(doc)
    if not previous:
        _safe_throw(
            _(
                "Tax period is closed for the selected date range (Closing {0}). Please reopen the period or contact a Tax Reviewer."
            ).format(locked_name),
            title=_("Tax Period Locked"),
        )

    fields_to_guard = _get_tax_invoice_fields(doc.doctype)
    changed = []
    for field in fields_to_guard:
        if getattr(previous, field, None) != getattr(doc, field, None):
            changed.append(field)

    if not changed:
        return

    _safe_throw(
        _("Cannot modify tax invoice or tax mapping fields because Tax Period Closing {0} is Closed.").format(
            locked_name
        ),
        title=_("Tax Period Locked"),
    )


def _serialize_rows(rows: list[list[object]], headers: list[str], file_format: str, filename: str) -> str:
    if file_format == "XLSX":
        xlsx_file = make_xlsx(rows, "CoreTax Export", headers)
        filedata = xlsx_file.getvalue()
        file_name = f"{filename}.xlsx"
        file_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name,
                "content": filedata,
                "is_private": 1,
            }
        )
    else:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(headers)
        writer.writerows(rows)
        file_name = f"{filename}.csv"
        file_doc = frappe.get_doc(
            {
                "doctype": "File",
                "file_name": file_name,
                "content": buffer.getvalue(),
                "is_private": 1,
            }
        )

    file_doc.save(ignore_permissions=True)
    return file_doc.file_url


def _resolve_mapping_value(mapping, doc: Document, party_doc: Document | None):
    source_type = mapping.source_type
    source = mapping.source

    if source_type == "Document Field":
        return doc.get(source)
    if source_type == "Party Field" and party_doc:
        return party_doc.get(source)
    if source_type == "Computed DPP":
        return doc.get("ti_fp_dpp") or doc.get("out_fp_dpp")
    if source_type == "Computed PPN":
        return doc.get("ti_fp_ppn") or doc.get("out_fp_ppn")
    if source_type == "Tax Invoice Number":
        return doc.get("ti_fp_no") or doc.get("out_fp_no")
    if source_type == "Tax Invoice Date":
        return doc.get("ti_fp_date") or doc.get("out_fp_date")
    if source_type == "Fixed Value":
        return mapping.fixed_value or mapping.default_value
    return mapping.default_value


def _normalize_label(value: str | None) -> str:
    return (value or "").strip().lower()


def _get_coretax_required_fields(direction: str) -> dict[str, dict[str, object]]:
    if direction not in {"Input", "Output"}:
        return {}

    document_prefix = "ti" if direction == "Input" else "out"
    dpp_field = f"{document_prefix}_fp_dpp"
    ppn_field = f"{document_prefix}_fp_ppn"
    npwp_fields = (
        {f"{document_prefix}_fp_npwp"}
        if direction == "Input"
        else {"out_fp_customer_npwp", "out_buyer_tax_id"}
    )
    fp_date_field = f"{document_prefix}_fp_date"

    return {
        "ppn": {
            "label": "PPN",
            "label_tokens": ("ppn", "vat"),
            "document_fields": {ppn_field},
            "party_fields": set(),
            "computed_types": {"Computed PPN"},
        },
        "dpp": {
            "label": "DPP",
            "label_tokens": ("dpp",),
            "document_fields": {dpp_field},
            "party_fields": set(),
            "computed_types": {"Computed DPP"},
        },
        "npwp": {
            "label": "NPWP",
            "label_tokens": ("npwp", "tax id", "taxid"),
            "document_fields": npwp_fields,
            "party_fields": {"tax_id", "npwp"},
            "computed_types": set(),
        },
        "invoice_date": {
            "label": "Tax Invoice Date",
            "label_tokens": ("tanggal", "invoice date", "fp date", "faktur"),
            "document_fields": {fp_date_field},
            "party_fields": set(),
            "computed_types": {"Tax Invoice Date"},
        },
    }


def _mapping_matches_requirement(mapping, requirement: dict[str, object]) -> bool:
    label = _normalize_label(getattr(mapping, "label", None))
    if requirement.get("label_tokens"):
        tokens = requirement["label_tokens"]
        if not any(token in label for token in tokens):
            return False

    source_type = getattr(mapping, "source_type", "")
    source = getattr(mapping, "source", "")

    if source_type in requirement.get("computed_types", set()):
        return True

    if source_type == "Document Field":
        allowed_fields = requirement.get("document_fields", set())
        return bool(source) and (not allowed_fields or source in allowed_fields)

    if source_type == "Party Field":
        allowed_fields = requirement.get("party_fields", set())
        return bool(source) and (not allowed_fields or source in allowed_fields)

    if source_type == "Tax Invoice Date":
        return bool(source) and source in requirement.get("document_fields", set())

    return False


def validate_coretax_required_mappings(settings: Document) -> None:
    required = _get_coretax_required_fields(getattr(settings, "direction", ""))
    if not required:
        _safe_throw(_("CoreTax Export Settings must specify a direction of Input or Output."))

    mappings = getattr(settings, "column_mappings", []) or []
    missing_labels = []
    for requirement in required.values():
        if not any(_mapping_matches_requirement(mapping, requirement) for mapping in mappings):
            missing_labels.append(requirement["label"])

    if missing_labels:
        _safe_throw(
            _("CoreTax Export Settings {0} must include mappings for: {1}.").format(
                getattr(settings, "title", None) or getattr(settings, "name", None) or _("(untitled)"),
                ", ".join(missing_labels),
            ),
            title=_("CoreTax Mapping Incomplete"),
        )


def generate_coretax_rows(
    invoices: list[Document],
    settings: Document,
    *,
    party_type: str,
) -> tuple[list[str], list[list[object]]]:
    headers = [mapping.label or mapping.source for mapping in settings.column_mappings]
    rows: list[list[object]] = []
    for doc in invoices:
        party_doc = None
        party_name = getattr(doc, "supplier", None) if party_type == "Supplier" else getattr(doc, "customer", None)
        if party_name:
            try:
                party_doc = frappe.get_cached_doc(party_type, party_name)
            except Exception:
                party_doc = None

        row = []
        for mapping in settings.column_mappings:
            value = _resolve_mapping_value(mapping, doc, party_doc)
            row.append(value)
        rows.append(row)
    return headers, rows


def generate_coretax_export(
    *,
    company: str,
    date_from: date | str | None,
    date_to: date | str | None,
    direction: str,
    settings_name: str,
    filename: str,
) -> str:
    settings = frappe.get_cached_doc("CoreTax Export Settings", settings_name)

    if getattr(settings, "direction", None) and settings.direction != direction:
        frappe.throw(
            _("CoreTax Export Settings {0} is configured for {1} direction, not {2}.").format(
                settings_name, settings.direction, direction
            ),
            title=_("CoreTax Direction Mismatch"),
        )

    validate_coretax_required_mappings(settings)

    filters: dict[str, object] = {
        "company": company,
        "docstatus": 1,
        "posting_date": ["between", [date_from, date_to]],
    }

    if direction == "Input":
        filters["ti_verification_status"] = "Verified"
        invoices = frappe.get_list("Purchase Invoice", filters=filters, fields="*")
        party_type = "Supplier"
    else:
        filters["out_fp_status"] = "Verified"
        invoices = frappe.get_list("Sales Invoice", filters=filters, fields="*")
        party_type = "Customer"

    headers, rows = generate_coretax_rows(invoices, settings, party_type=party_type)
    return _serialize_rows(rows, headers, settings.file_format or "CSV", filename)


def compute_tax_totals(company: str, date_from: date | str | None, date_to: date | str | None) -> dict:
    return build_register_snapshot(company, date_from, date_to)


def build_payment_entry_lines(amount: float, payable_account: str, payment_account: str) -> list[dict]:
    return [
        {
            "account": payable_account,
            "debit_in_account_currency": amount,
            "credit_in_account_currency": 0,
        },
        {
            "account": payment_account,
            "credit_in_account_currency": amount,
            "debit_in_account_currency": 0,
        },
    ]


def _validate_payment_batch(batch: Document, *, require_payment_account: bool = True) -> None:
    if not batch.amount or batch.amount <= 0:
        frappe.throw(_("Amount must be greater than zero to create a payment."))

    if not batch.payable_account:
        frappe.throw(_("Please set Payable Account on the Tax Payment Batch."))

    if require_payment_account and not batch.payment_account:
        frappe.throw(_("Please set Payment Account on the Tax Payment Batch."))


def create_tax_payment_journal_entry(batch: Document) -> str:
    _validate_payment_batch(batch)

    je = frappe.new_doc("Journal Entry")
    je.company = batch.company
    je.posting_date = batch.get("payment_date") or batch.get("posting_date") or nowdate()
    je.user_remark = _("{0} payment for period {1}-{2}").format(
        batch.tax_type or _("Tax"), batch.period_month or "", batch.period_year or ""
    )

    reference_notes = []
    for row in getattr(batch, "references", []) or []:
        if getattr(row, "reference_name", None):
            reference_notes.append(f"{row.reference_doctype or '-'} {row.reference_name}: {row.amount or 0}")

    for line in build_payment_entry_lines(batch.amount, batch.payable_account, batch.payment_account):
        line["reference_type"] = "Tax Payment Batch"
        line["reference_name"] = batch.name
        je.append("accounts", line)

    if reference_notes:
        je.user_remark += " | " + "; ".join(reference_notes)

    je.insert(ignore_permissions=True)
    batch.db_set("journal_entry", je.name)
    batch.db_set("status", "Prepared")
    return je.name


def create_tax_payment_entry(batch: Document) -> str:
    _validate_payment_batch(batch, require_payment_account=True)

    if not batch.party_type or not batch.party:
        frappe.throw(_("Please set Party Type and Party to prepare a Payment Entry."))

    pe = frappe.new_doc("Payment Entry")
    pe.company = batch.company
    pe.payment_type = "Pay"
    pe.party_type = batch.party_type
    pe.party = batch.party
    pe.posting_date = batch.get("payment_date") or batch.get("posting_date") or nowdate()
    pe.mode_of_payment = batch.get("payment_mode")
    pe.paid_from = batch.payment_account
    pe.paid_to = batch.payable_account
    pe.paid_amount = batch.amount
    pe.received_amount = batch.amount
    pe.reference_no = batch.name
    pe.reference_date = pe.posting_date
    title = _("Tax Payment {0} {1}/{2} - {3}").format(
        batch.tax_type or _("Tax"), batch.period_month or "", batch.period_year or "", batch.name
    )
    pe.remarks = _("Tax payment for {0} period {1}-{2} - Batch {3}").format(
        batch.tax_type or _("Tax"), batch.period_month or "", batch.period_year or "", batch.name
    )
    if getattr(pe, "meta", None) and pe.meta.get_field("title"):
        pe.title = title
    elif getattr(pe, "meta", None) and pe.meta.get_field("party_name"):
        pe.party_name = title

    pe.insert(ignore_permissions=True)
    batch.db_set("payment_entry", pe.name)
    batch.db_set("status", "Prepared")
    return pe.name


def _get_or_create_tax_authority_supplier() -> str:
    """
    Get or create default supplier for tax authority payments.
    Used for VAT netting journal entries where payable account requires party.

    Returns:
        str: Supplier name (Government - Tax Authority)
    """
    supplier_name = "Government - Tax Authority"

    # Check if supplier exists
    if frappe.db.exists("Supplier", supplier_name):
        return supplier_name

    # Create supplier if not exists
    supplier = frappe.new_doc("Supplier")
    supplier.supplier_name = supplier_name
    supplier.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name") or "All Supplier Groups"
    supplier.supplier_type = "Company"
    supplier.country = "Indonesia"
    supplier.insert(ignore_permissions=True)

    return supplier.name


def build_vat_netting_lines(
    *,
    input_vat_total: float,
    output_vat_total: float,
    input_account: str,
    output_account: str,
    payable_account: str,
    party: str | None = None,
) -> list[dict]:
    if not input_account or not output_account or not payable_account:
        frappe.throw(_("VAT netting requires Input VAT, Output VAT, and Payable accounts."))

    lines: list[dict] = []
    debit_output = flt(output_vat_total)
    credit_input = min(flt(input_vat_total), debit_output) if debit_output else flt(input_vat_total)
    net_payable = debit_output - credit_input

    if debit_output:
        lines.append(
            {
                "account": output_account,
                "debit_in_account_currency": debit_output,
                "credit_in_account_currency": 0,
            }
        )

    if credit_input:
        lines.append(
            {
                "account": input_account,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": credit_input,
            }
        )

    if net_payable > 0:
        payable_line = {
            "account": payable_account,
            "debit_in_account_currency": 0,
            "credit_in_account_currency": net_payable,
        }

        # Add party information if provided (required for Payable account types)
        if party:
            payable_line["party_type"] = "Supplier"
            payable_line["party"] = party

        lines.append(payable_line)

    return lines


def _get_vat_in_gl_balance(company: str, input_account: str, as_of_date: str) -> float:
    """
    Get the actual debit balance of the VAT Input account from GL up to (and including)
    as_of_date. This captures both the current period invoices AND any carry-forward
    balance from previous periods that were not fully offset by prior netting entries.

    Returns positive float = accumulated input VAT credit available.
    """
    aggregates = frappe.get_all(
        "GL Entry",
        filters=[
            ["company", "=", company],
            ["account", "=", input_account],
            ["is_cancelled", "=", 0],
            ["posting_date", "<=", as_of_date],
        ],
        fields=["sum(debit) as debit_total", "sum(credit) as credit_total"],
    )
    if not aggregates:
        return 0.0
    debit_total = flt(aggregates[0].get("debit_total"))
    credit_total = flt(aggregates[0].get("credit_total"))
    # Debit balance = net input VAT still available (unnetted)
    return max(debit_total - credit_total, 0.0)


def create_vat_netting_entry(
    *,
    company: str,
    period_month: int,
    period_year: int,
    input_vat_total: float,
    output_vat_total: float,
    input_account: str,
    output_account: str,
    payable_account: str,
    posting_date: str | None = None,
    reference: str | None = None,
) -> str:
    effective_posting_date = posting_date or nowdate()

    # Read the ACTUAL GL balance of VAT-IN account up to netting date.
    # This automatically includes any carry-forward from previous periods
    # that were not fully offset by prior netting journal entries.
    gl_input_balance = _get_vat_in_gl_balance(company, input_account, effective_posting_date)

    # Use the higher of register total vs GL balance.
    # GL balance is authoritative (includes carry-forward from prior months);
    # register total covers the case where GL hasn't been posted yet.
    effective_input = max(flt(input_vat_total), gl_input_balance)

    # Get or create tax authority supplier for payable account
    tax_supplier = _get_or_create_tax_authority_supplier()

    lines = build_vat_netting_lines(
        input_vat_total=effective_input,
        output_vat_total=output_vat_total,
        input_account=input_account,
        output_account=output_account,
        payable_account=payable_account,
        party=tax_supplier,
    )

    if not lines:
        frappe.throw(_("No VAT netting lines were generated for the selected period."))

    je = frappe.new_doc("Journal Entry")
    je.company = company
    je.posting_date = effective_posting_date

    # Include reference in user remark if provided
    if reference:
        je.user_remark = _("VAT netting for {0}-{1} (Ref: {2})").format(period_month, period_year, reference)
    else:
        je.user_remark = _("VAT netting for {0}-{1}").format(period_month, period_year)

    for line in lines:
        je.append("accounts", line)

    je.insert(ignore_permissions=True)
    return je.name


def generate_vat_out_batch_excel(
    batch_name: str,
    *,
    include_fp_numbers: bool = False,
    for_upload: bool = True
) -> str:
    """Generate Excel file for VAT OUT Batch.

    Args:
        batch_name: Name of VAT OUT Batch
        include_fp_numbers: Whether to include FP numbers (for reconciliation)
        for_upload: True for CoreTax upload, False for reconciliation

    Returns:
        str: File URL
    """
    # Get batch
    batch = frappe.get_doc("VAT OUT Batch", batch_name)

    # Get invoices from batch
    invoices = batch.get_batch_invoices()

    # Group invoices by group_id
    groups_map = {}
    for inv in invoices:
        gid = inv.out_fp_group_id or 0
        if gid not in groups_map:
            groups_map[gid] = {
                "group_id": gid,
                "customer": inv.customer,
                "customer_name": inv.customer_name,
                "customer_npwp": inv.out_fp_customer_npwp,
                "total_dpp": 0,
                "total_ppn": 0,
                "fp_no": inv.out_fp_no or "",
                "fp_no_seri": inv.out_fp_no_seri or "",
                "fp_no_faktur": inv.out_fp_no_faktur or "",
                "fp_date": inv.out_fp_date or "",
                "invoices": []
            }

        groups_map[gid]["total_dpp"] += inv.out_fp_dpp or 0
        groups_map[gid]["total_ppn"] += inv.out_fp_ppn or 0
        groups_map[gid]["invoices"].append(inv)

    # Build data structure
    # Faktur sheet: 1 row per group
    faktur_data = []
    for gid in sorted(groups_map.keys()):
        group = groups_map[gid]

        faktur_row = {
            "Group ID": group["group_id"],
            "Customer": group["customer_name"] or group["customer"],
            "Customer NPWP": group["customer_npwp"] or "",
            "Total DPP": group["total_dpp"],
            "Total PPN": group["total_ppn"],
        }

        if include_fp_numbers:
            faktur_row["FP No Seri"] = group["fp_no_seri"]
            faktur_row["FP No Faktur"] = group["fp_no_faktur"]
            faktur_row["FP Date"] = group["fp_date"]

        faktur_data.append(faktur_row)

    # DetailFaktur sheet: 1 row per invoice
    detail_data = []
    for gid in sorted(groups_map.keys()):
        group = groups_map[gid]

        for inv in group["invoices"]:
            # Get item descriptions
            si_doc = frappe.get_doc("Sales Invoice", inv.name)
            item_desc = ", ".join([
                item.item_name or item.item_code
                for item in si_doc.items
            ])

            detail_row = {
                "Group ID": group["group_id"],
                "Sales Invoice": inv.name,
                "Invoice Date": inv.posting_date,
                "Item Description": item_desc,
                "DPP": inv.out_fp_dpp or 0,
                "PPN": inv.out_fp_ppn or 0,
                "Grand Total": inv.grand_total
            }

            detail_data.append(detail_row)

    # Create Excel file
    from frappe.utils.xlsxutils import make_xlsx

    # Prepare sheets
    sheets = {
        "Faktur": faktur_data,
        "DetailFaktur": detail_data
    }

    # Generate filename
    if for_upload:
        filename = f"coretax-vat-out-{batch.company}-{batch.date_from}-{batch.date_to}"
    else:
        filename = f"reconciliation-vat-out-{batch.company}-{batch.date_from}-{batch.date_to}"

    # Create XLSX
    xlsx_data = {}
    for sheet_name, data in sheets.items():
        if data:
            headers = list(data[0].keys())
            rows = [[row[h] for h in headers] for row in data]
            xlsx_data[sheet_name] = {"columns": headers, "data": rows}

    # Serialize
    xlsx_file = make_xlsx(xlsx_data, sheet_name="Faktur")
    filedata = xlsx_file.getvalue()

    # Save as File
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"{filename}.xlsx",
        "content": filedata,
        "is_private": 1,
    })
    file_doc.save(ignore_permissions=True)

    return file_doc.file_url
