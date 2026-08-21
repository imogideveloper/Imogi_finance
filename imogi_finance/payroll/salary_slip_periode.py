"""Label periode (Hari/Bulan/Tahun) untuk grouping Salary Slip di list view.

Frappe's list view "Group By" hanya bisa mengelompokkan berdasarkan NILAI
field bertipe Select/Link/Data/Int/Check - tidak ada dukungan native untuk
bucket per hari/bulan/tahun dari sebuah field Date. Makanya field label
pre-formatted ini dibuat & disinkronkan setiap validate, mirip pola yang
sudah dipakai Payroll Entry ("periode" - lihat payroll_entry_summary.py).
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate

BULAN_ID_FULL = (
	"Januari", "Februari", "Maret", "April", "Mei", "Juni",
	"Juli", "Agustus", "September", "Oktober", "November", "Desember",
)

PERIODE_FIELDS = ("periode_hari", "periode_bulan", "periode_tahun")


def compute_periode_labels(reference_date) -> dict:
	d = getdate(reference_date) if reference_date else None
	if not d:
		return {}
	bulan = BULAN_ID_FULL[d.month - 1]
	return {
		"periode_hari": f"{d.day} {bulan} {d.year}",
		"periode_bulan": f"{bulan} {d.year}",
		"periode_tahun": str(d.year),
	}


def sync_periode_fields(doc, method=None):
	"""Hook validate - isi periode_hari/bulan/tahun dari end_date slip."""
	reference_date = doc.get("end_date") or doc.get("start_date") or doc.get("posting_date")
	labels = compute_periode_labels(reference_date)
	for fieldname, value in labels.items():
		doc.set(fieldname, value)
