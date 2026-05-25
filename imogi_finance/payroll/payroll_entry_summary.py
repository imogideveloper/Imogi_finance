"""Auto-update ringkasan Payroll Entry (periode, total karyawan, total amount)."""

from __future__ import annotations

import frappe
from frappe.utils import flt, getdate

BULAN_ID = (
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


def format_periode_label(start_date=None, end_date=None) -> str:
	"""Label periode list view — bulan gaji dari end_date (pola 25–24)."""
	d = getdate(end_date or start_date) if (end_date or start_date) else None
	if not d:
		return ""
	return f"{BULAN_ID[d.month - 1]} {d.year}"


def update_payroll_entry_summary(payroll_entry, *, persist=True) -> dict:
	"""Hitung ulang periode + agregat slip gaji yang sudah submit."""
	if not payroll_entry:
		return {}

	name = payroll_entry if isinstance(payroll_entry, str) else payroll_entry.name
	if not name or not frappe.db.exists("Payroll Entry", name):
		return {}

	start_date, end_date = frappe.db.get_value(
		"Payroll Entry", name, ["start_date", "end_date"]
	)
	periode = format_periode_label(start_date, end_date)

	slips = frappe.get_all(
		"Salary Slip",
		filters={"payroll_entry": name, "docstatus": 1},
		fields=["net_pay"],
	)
	total_karyawan = len(slips)
	total_amount = sum(flt(s.net_pay) for s in slips)

	summary = {
		"periode": periode,
		"total_karyawan": total_karyawan,
		"total_amount": total_amount,
	}

	if persist:
		frappe.db.set_value("Payroll Entry", name, summary, update_modified=False)
		try:
			from imogi_finance.payroll.employer_contributions import (
				update_payroll_entry_employer_summary,
			)

			update_payroll_entry_employer_summary(name, persist=True)
		except Exception:
			pass
	else:
		doc = payroll_entry if not isinstance(payroll_entry, str) else None
		if doc:
			doc.periode = periode
			doc.total_karyawan = total_karyawan
			doc.total_amount = total_amount

	return summary


def sync_summary_on_validate(doc, method=None):
	"""Isi field ringkasan saat save Payroll Entry."""
	if not doc.get("name") or doc.get("__islocal"):
		doc.periode = format_periode_label(doc.get("start_date"), doc.get("end_date"))
		return

	summary = update_payroll_entry_summary(doc.name, persist=True)
	doc.periode = summary.get("periode", doc.get("periode"))
	doc.total_karyawan = summary.get("total_karyawan", 0)
	doc.total_amount = summary.get("total_amount", 0)


def refresh_summary_from_salary_slip(doc, method=None):
	"""Dipanggil saat Salary Slip submit/cancel."""
	if doc.get("payroll_entry"):
		update_payroll_entry_summary(doc.payroll_entry, persist=True)
		try:
			from imogi_finance.payroll.employer_contributions import (
				update_payroll_entry_employer_summary,
			)

			update_payroll_entry_employer_summary(doc.payroll_entry, persist=True)
		except Exception:
			pass
