"""Integrasi Payroll Entry ↔ Payroll Period (pola cutoff 25–24)."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_months, getdate, today


DEFAULT_CUTOFF_START_DAY = 25
DEFAULT_CUTOFF_END_DAY = 24


def get_sub_periods(payroll_period: str) -> list[dict[str, Any]]:
	"""Daftar baris periode gaji dari child table Payroll Period."""
	if not payroll_period or not frappe.db.exists("Payroll Period", payroll_period):
		return []

	rows = frappe.get_all(
		"Payroll Period Date",
		filters={"parent": payroll_period, "parenttype": "Payroll Period"},
		fields=["name", "start_date", "end_date", "period_label"],
		order_by="start_date asc",
	)
	if not rows:
		ensure_payroll_period_sub_periods(payroll_period)
		rows = frappe.get_all(
			"Payroll Period Date",
			filters={"parent": payroll_period, "parenttype": "Payroll Period"},
			fields=["name", "start_date", "end_date"],
			order_by="start_date asc",
		)

	result = []
	for row in rows:
		start = getdate(row.start_date)
		end = getdate(row.end_date)
		label = row.get("period_label") or _format_sub_period_label(start, end)
		result.append(
			{
				"name": row.name,
				"start_date": start,
				"end_date": end,
				"label": label,
			}
		)
	return result


def _format_sub_period_label(start: date, end: date) -> str:
	"""Label bulan gaji berdasarkan tanggal akhir (24 Mei → gaji Mei)."""
	months_id = (
		"Jan",
		"Feb",
		"Mar",
		"Apr",
		"Mei",
		"Jun",
		"Jul",
		"Agu",
		"Sep",
		"Okt",
		"Nov",
		"Des",
	)
	m = end.month - 1
	return f"{months_id[m]} {end.year} ({start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')})"


def apply_sub_period_to_payroll_entry(doc) -> None:
	"""Set start_date / end_date PE dari baris Payroll Period Date."""
	if not doc.get("payroll_period") or not doc.get("payroll_sub_period"):
		return

	sub_period = doc.payroll_sub_period
	row = None

	# Field Select menyimpan label; cari baris by label atau by name (legacy)
	if frappe.db.exists("Payroll Period Date", sub_period):
		row = frappe.db.get_value(
			"Payroll Period Date",
			sub_period,
			["name", "start_date", "end_date", "parent"],
			as_dict=True,
		)
	else:
		row = frappe.db.get_value(
			"Payroll Period Date",
			{
				"parent": doc.payroll_period,
				"parenttype": "Payroll Period",
				"period_label": sub_period,
			},
			["name", "start_date", "end_date", "parent"],
			as_dict=True,
		)
		if row:
			label = frappe.db.get_value("Payroll Period Date", row.name, "period_label")
			if label:
				doc.payroll_sub_period = label

	if not row:
		# Cocokkan label format lama dari API
		for candidate in get_sub_periods(doc.payroll_period):
			if candidate.get("label") == sub_period or candidate.get("name") == sub_period:
				row = frappe._dict(
					name=candidate["name"],
					start_date=candidate["start_date"],
					end_date=candidate["end_date"],
					parent=doc.payroll_period,
				)
				doc.payroll_sub_period = candidate.get("label") or candidate["name"]
				break

	if not row:
		frappe.throw(_("Periode gaji tidak ditemukan: {0}").format(frappe.bold(sub_period)))

	if row.parent != doc.payroll_period:
		frappe.throw(_("Periode gaji tidak sesuai dengan Payroll Period yang dipilih."))

	doc.start_date = row.start_date
	doc.end_date = row.end_date

	if doc.company:
		pp_company = frappe.db.get_value("Payroll Period", doc.payroll_period, "company")
		if pp_company and pp_company != doc.company:
			frappe.throw(
				_("Payroll Period {0} milik company {1}, berbeda dengan Payroll Entry.").format(
					frappe.bold(doc.payroll_period),
					frappe.bold(pp_company),
				)
			)


def validate_payroll_entry(doc, method=None):
	from imogi_finance.payroll.payroll_entry import ensure_payroll_entry_defaults

	ensure_payroll_entry_defaults(doc)
	if doc.get("payroll_period"):
		apply_sub_period_to_payroll_entry(doc)
		if not doc.get("payroll_sub_period"):
			frappe.throw(_("Pilih Periode Gaji (Bulan) dari Payroll Period."))
		if doc.get("end_date") and not doc.get("posting_date"):
			doc.posting_date = doc.end_date
	validate_active_assignment_contracts(doc)


def validate_active_assignment_contracts(doc) -> None:
	"""Stop Payroll Entry if selected employees only have expired SSA for the salary month."""
	if not doc.get("end_date") or not doc.get("employees"):
		return
	if not frappe.db.has_column("Salary Structure Assignment", "end_date"):
		return

	lookup_date = getdate(doc.get("end_date"))
	expired = []
	for row in doc.get("employees") or []:
		employee = row.get("employee")
		if not employee:
			continue
		assignment = _get_applicable_assignment_contract(employee, lookup_date)
		if assignment and assignment.get("is_expired"):
			expired.append(assignment)

	if not expired:
		return

	lines = []
	for item in expired:
		lines.append(
			_("{0} - {1} (End Date: {2})").format(
				frappe.bold(item.employee),
				frappe.bold(item.employee_name or item.employee),
				frappe.bold(item.end_date),
			)
		)

	frappe.throw(
		_(
			"Assignment Contract ini sudah habis, silahkan Perbarui kontrak terlebih dahulu."
		)
		+ "<br><br>"
		+ "<br>".join(lines),
		title=_("Assignment Contract Expired"),
	)


def _get_applicable_assignment_contract(employee: str, lookup_date):
	fields = ["name", "employee", "from_date", "end_date", "salary_structure"]
	if frappe.db.has_column("Salary Structure Assignment", "renewed_by_assignment_contract"):
		fields.append("renewed_by_assignment_contract")

	rows = frappe.get_all(
		"Salary Structure Assignment",
		filters={
			"employee": employee,
			"from_date": ("<=", lookup_date),
			"docstatus": 1,
		},
		fields=fields,
		order_by="from_date desc, creation desc",
	)
	for row in rows:
		replacement = row.get("renewed_by_assignment_contract")
		if replacement and _replacement_assignment_applies(replacement, lookup_date):
			continue

		row.employee_name = frappe.db.get_value("Employee", employee, "employee_name") or employee
		if row.get("end_date") and getdate(row.end_date) < lookup_date:
			row.is_expired = True
		else:
			row.is_expired = False
		return row

	return None


def _replacement_assignment_applies(replacement_name: str, lookup_date) -> bool:
	if not replacement_name or not frappe.db.exists("Salary Structure Assignment", replacement_name):
		return False
	replacement = frappe.db.get_value(
		"Salary Structure Assignment",
		replacement_name,
		["from_date", "end_date", "docstatus"],
		as_dict=True,
	)
	if not replacement or replacement.get("docstatus") != 1:
		return False
	if replacement.get("from_date") and getdate(replacement.from_date) > getdate(lookup_date):
		return False
	if replacement.get("end_date") and getdate(replacement.end_date) < getdate(lookup_date):
		return False
	return True


def validate_payroll_period(doc, method=None):
	"""Auto-generate baris 25–24 jika child table kosong."""
	_sync_period_row_labels(doc)
	if doc.get("periods"):
		return
	if not doc.get("start_date") or not doc.get("end_date"):
		return
	generated = build_cutoff_sub_periods(
		getdate(doc.start_date),
		getdate(doc.end_date),
	)
	for item in generated:
		row = {"start_date": item["start_date"], "end_date": item["end_date"]}
		if frappe.get_meta("Payroll Period Date").has_field("period_label"):
			row["period_label"] = _format_sub_period_label(
				item["start_date"], item["end_date"]
			)
		doc.append("periods", row)


def _sync_period_row_labels(doc) -> None:
	"""Isi period_label agar Link/Select menampilkan nama bulan, bukan hash ID."""
	if not frappe.get_meta("Payroll Period Date").has_field("period_label"):
		return
	for row in doc.get("periods") or []:
		if not row.start_date or not row.end_date:
			continue
		row.period_label = _format_sub_period_label(
			getdate(row.start_date), getdate(row.end_date)
		)


def ensure_payroll_period_sub_periods(payroll_period: str) -> None:
	"""Generate & simpan sub-period jika belum ada (untuk site yang sudah punya PP lama)."""
	doc = frappe.get_doc("Payroll Period", payroll_period)
	if doc.periods:
		return
	validate_payroll_period(doc)
	doc.flags.ignore_validate = True
	doc.save(ignore_permissions=True)


def build_cutoff_sub_periods(
	period_start: date,
	period_end: date,
	cutoff_start_day: int = DEFAULT_CUTOFF_START_DAY,
	cutoff_end_day: int = DEFAULT_CUTOFF_END_DAY,
) -> list[dict[str, date]]:
	"""
	Bangun rentang bulanan pola cutoff (default: 25 s/d 24 bulan berikutnya).
	Bulan gaji = bulan dari tanggal akhir (end).
	"""
	result: list[dict[str, date]] = []
	# Iterasi per bulan kalender yang tercakup dalam payroll period tahunan.
	cursor = date(period_start.year, period_start.month, 1)
	last_month = date(period_end.year, period_end.month, 1)

	while cursor <= last_month:
		end_month = cursor
		start_month = add_months(end_month, -1)
		end_day = min(cutoff_end_day, monthrange(end_month.year, end_month.month)[1])
		start_day = min(cutoff_start_day, monthrange(start_month.year, start_month.month)[1])
		sub_start = date(start_month.year, start_month.month, start_day)
		sub_end = date(end_month.year, end_month.month, end_day)

		# Masukkan jika rentang 25–24 overlap payroll period tahunan.
		# Jangan clip start/end: gaji Jan tetap 25 Des tahun lalu – 24 Jan.
		if sub_end >= period_start and sub_start <= period_end:
			result.append({"start_date": sub_start, "end_date": sub_end})

		cursor = add_months(cursor, 1)

	return result


def find_sub_period_for_posting_date(
	payroll_period: str, posting_date: str | date | None
) -> dict[str, Any] | None:
	"""Cocokkan bulan gaji dari posting date ke baris cutoff 25–24."""
	if not payroll_period or not posting_date:
		return None

	ref = getdate(posting_date)

	# Prioritas: bulan gaji = bulan posting (mis. posting 30 Apr → gaji Apr = 25 Mar–24 Apr)
	for row in get_sub_periods(payroll_period):
		end = getdate(row["end_date"])
		if end.year == ref.year and end.month == ref.month:
			return row

	for row in get_sub_periods(payroll_period):
		start = getdate(row["start_date"])
		end = getdate(row["end_date"])
		if start <= ref <= end:
			return row

	return None


@frappe.whitelist()
def get_payroll_sub_periods(payroll_period: str) -> list[dict[str, Any]]:
	frappe.has_permission("Payroll Entry", "read", throw=True)
	periods = get_sub_periods(payroll_period)
	# JSON-serializable dates
	for p in periods:
		p["start_date"] = str(p["start_date"])
		p["end_date"] = str(p["end_date"])
	return periods


@frappe.whitelist()
def get_sub_period_for_posting_date(payroll_period: str, posting_date: str) -> dict[str, Any] | None:
	"""API: sub-periode cutoff untuk posting date (pola Odoo Cutoff Periode)."""
	frappe.has_permission("Payroll Entry", "read", throw=True)
	row = find_sub_period_for_posting_date(payroll_period, posting_date)
	if not row:
		return None
	return {
		"name": row["name"],
		"label": row["label"],
		"start_date": str(row["start_date"]),
		"end_date": str(row["end_date"]),
	}


def find_payroll_period_for_date(company: str, reference_date: str | date | None) -> str | None:
	"""Payroll Period tahunan yang mencakup tanggal due/posting (mis. 2026 → Period Slip)."""
	if not company:
		return None

	ref = getdate(reference_date or today())
	periods = frappe.get_all(
		"Payroll Period",
		filters={"company": company},
		fields=["name", "start_date", "end_date"],
		order_by="start_date desc",
	)
	if not periods:
		return None

	for row in periods:
		if getdate(row.start_date) <= ref <= getdate(row.end_date):
			return row.name

	year = ref.year
	for row in periods:
		if getdate(row.start_date).year <= year <= getdate(row.end_date).year:
			return row.name

	return periods[0].name


@frappe.whitelist()
def auto_fill_payroll_entry_period(company: str, posting_date: str | None = None) -> dict[str, Any] | None:
	"""Isi Payroll Period + Periode Gaji (Bulan) dari due date (posting / hari ini)."""
	frappe.has_permission("Payroll Entry", "read", throw=True)

	ref_date = posting_date or today()
	payroll_period = find_payroll_period_for_date(company, ref_date)
	if not payroll_period:
		return None

	sub_row = find_sub_period_for_posting_date(payroll_period, ref_date)
	if not sub_row:
		return {"payroll_period": payroll_period, "sub_period": None}

	return {
		"payroll_period": payroll_period,
		"sub_period": {
			"name": sub_row["name"],
			"label": sub_row["label"],
			"start_date": str(sub_row["start_date"]),
			"end_date": str(sub_row["end_date"]),
		},
		"periode_label": get_payroll_month_label(str(sub_row["end_date"])),
	}


@frappe.whitelist()
def get_payroll_month_label(end_date: str) -> str:
	"""Label periode untuk field `periode` (bulan dari tanggal akhir)."""
	end = getdate(end_date)
	months_id = (
		"Jan",
		"Feb",
		"Mar",
		"Apr",
		"Mei",
		"Jun",
		"Jul",
		"Agu",
		"Sep",
		"Okt",
		"Nov",
		"Des",
	)
	return f"{months_id[end.month - 1]} {end.year}"
