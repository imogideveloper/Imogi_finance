"""Integrasi Payroll Entry ↔ Payroll Period (pola cutoff 25–24)."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

import frappe
from frappe import _
from frappe.utils import add_months, getdate


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
	if doc.get("payroll_period"):
		apply_sub_period_to_payroll_entry(doc)
		if not doc.get("payroll_sub_period"):
			frappe.throw(_("Pilih Periode Gaji (Bulan) dari Payroll Period."))


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
