"""Tunjangan / iuran ditanggung perusahaan (komponen Salary Component bertipe Employer)."""

from __future__ import annotations

import frappe
from frappe.utils import flt


def is_employer_salary_component(component_name: str | None) -> bool:
	"""True untuk komponen perusahaan (bukan Contra)."""
	if not component_name:
		return False
	name = (component_name or "").strip()
	if name.lower().startswith("contra "):
		return False
	lower = name.lower()
	return "employer" in lower or "perusahaan" in lower


def _row_component_and_amount(row) -> tuple[str | None, float]:
	if isinstance(row, dict):
		return row.get("salary_component"), flt(row.get("amount"))
	return getattr(row, "salary_component", None), flt(getattr(row, "amount", 0))


def collect_employer_contribution_rows(doc, source_tables: tuple[str, ...] = ("earnings", "deductions")) -> list[dict]:
	"""Kumpulkan baris employer dari child table slip/struktur."""
	rows: list[dict] = []
	seen: set[str] = set()
	for table in source_tables:
		for row in doc.get(table) or []:
			sc, amount = _row_component_and_amount(row)
			if not sc or sc in seen or not is_employer_salary_component(sc):
				continue
			seen.add(sc)
			rows.append({"salary_component": sc, "amount": amount})
	return rows


def _resolve_bpjs_base(doc) -> float:
	"""Gaji pokok / base untuk iuran BPJS (sama seperti formula komponen)."""
	base = flt(getattr(doc, "base", 0))
	if base > 0:
		return base
	ssa = getattr(doc, "_salary_structure_assignment", None) or {}
	if isinstance(ssa, dict):
		base = flt(ssa.get("base"))
	if base > 0:
		return base
	for row in doc.get("earnings") or []:
		sc, _ = _row_component_and_amount(row)
		if sc and sc.strip().lower() in ("gaji pokok", "basic", "base"):
			_, amount = _row_component_and_amount(row)
			return amount
	return base


def infer_employer_contribution_rows(doc) -> list[dict]:
	"""Hitung baris employer dari base bila belum ada di earnings slip."""
	base = _resolve_bpjs_base(doc)
	if base <= 0:
		return []

	try:
		from payroll_indonesia.config import get_bpjs_cap, get_bpjs_rate
	except ImportError:
		return []

	health_base = max(base, 5_396_761.0)
	jht_base = min(base, flt(get_bpjs_cap("bpjs_jht_employer_cap")) or base)
	jp_base = min(base, flt(get_bpjs_cap("bpjs_pension_employer_cap")) or base)

	return [
		{
			"salary_component": "BPJS Kesehatan Employer",
			"amount": health_base * flt(get_bpjs_rate("bpjs_health_employer_rate")) / 100,
		},
		{
			"salary_component": "BPJS JHT Employer",
			"amount": jht_base * flt(get_bpjs_rate("bpjs_jht_employer_rate")) / 100,
		},
		{
			"salary_component": "BPJS JP Employer",
			"amount": jp_base * flt(get_bpjs_rate("bpjs_pension_employer_rate")) / 100,
		},
		{
			"salary_component": "BPJS JKK Employer",
			"amount": base * flt(get_bpjs_rate("bpjs_jkk_rate")) / 100,
		},
		{
			"salary_component": "BPJS JKM Employer",
			"amount": base * flt(get_bpjs_rate("bpjs_jkm_rate")) / 100,
		},
	]


def sync_doc_employer_contributions(doc, target_field: str = "employer_contributions") -> None:
	"""Isi tabel employer_contributions dari earnings (+ deductions legacy)."""
	if not doc.meta.has_field(target_field):
		return

	rows = collect_employer_contribution_rows(doc)
	if not rows:
		rows = infer_employer_contribution_rows(doc)
	doc.set(target_field, [])
	for row in rows:
		doc.append(target_field, row)

	# Legacy: komponen employer yang salah masuk ke deductions dipindah ke tabel employer.
	if doc.meta.has_field("deductions"):
		new_deductions = []
		for d in doc.deductions:
			sc, _ = _row_component_and_amount(d)
			if is_employer_salary_component(sc):
				continue
			new_deductions.append(d)
		doc.set("deductions", new_deductions)


def sync_salary_structure_employer_display(doc, method=None) -> None:
	"""Salary Structure: tampilkan salinan komponen employer untuk referensi."""
	sync_doc_employer_contributions(doc, target_field="employer_contributions")


def sync_salary_slip_employer_display(doc, method=None) -> None:
	"""Salary Slip: pastikan tabel employer terisi setelah earnings dihitung."""
	sync_doc_employer_contributions(doc)


def _persist_payroll_entry_employer_summary(
	name: str, summary_rows: list[dict], total: float
) -> None:
	"""Tulis ringkasan employer tanpa memicu error update-after-submit pada PE."""
	docstatus = frappe.db.get_value("Payroll Entry", name, "docstatus")

	if frappe.get_meta("Payroll Entry").has_field("total_employer_contribution"):
		frappe.db.set_value(
			"Payroll Entry",
			name,
			"total_employer_contribution",
			total,
			update_modified=False,
		)

	frappe.db.delete(
		"Employer Contribution Detail",
		{
			"parent": name,
			"parenttype": "Payroll Entry",
			"parentfield": "employer_contributions_summary",
		},
	)
	for idx, row in enumerate(summary_rows, start=1):
		child = frappe.get_doc(
			{
				"doctype": "Employer Contribution Detail",
				"parent": name,
				"parenttype": "Payroll Entry",
				"parentfield": "employer_contributions_summary",
				"idx": idx,
				"salary_component": row["salary_component"],
				"amount": row["amount"],
			}
		)
		child.db_insert()

	if docstatus == 0:
		# Draft: sinkronkan ke doc jika sedang dibuka di memori
		return

	# Submitted: jangan panggil save() penuh pada form


def update_payroll_entry_employer_summary(
	payroll_entry, *, persist: bool = True
) -> list[dict]:
	"""Agregat kontribusi perusahaan dari slip gaji terkait Payroll Entry."""
	if not payroll_entry:
		return []

	name = payroll_entry if isinstance(payroll_entry, str) else payroll_entry.name
	meta = frappe.get_meta("Payroll Entry")
	if not name or not meta.has_field("employer_contributions_summary"):
		return []

	totals: dict[str, float] = {}
	slips = frappe.get_all(
		"Salary Slip",
		filters={"payroll_entry": name, "docstatus": ["!=", 2]},
		pluck="name",
	)
	for slip_name in slips:
		employer_rows = frappe.get_all(
			"Employer Contribution Detail",
			filters={
				"parent": slip_name,
				"parenttype": "Salary Slip",
				"parentfield": "employer_contributions",
			},
			fields=["salary_component", "amount"],
		)
		if not employer_rows:
			for row in frappe.get_all(
				"Salary Detail",
				filters={"parent": slip_name, "parentfield": "earnings"},
				fields=["salary_component", "amount"],
			):
				if is_employer_salary_component(row.salary_component):
					employer_rows.append(row)

		for row in employer_rows:
			sc = row.salary_component
			if not sc:
				continue
			totals[sc] = totals.get(sc, 0) + flt(row.amount)

	summary_rows = [
		{"salary_component": sc, "amount": amt} for sc, amt in sorted(totals.items())
	]
	total = sum(totals.values())

	if persist:
		_persist_payroll_entry_employer_summary(name, summary_rows, total)
	else:
		doc = payroll_entry if not isinstance(payroll_entry, str) else None
		if doc:
			doc.set("employer_contributions_summary", [])
			for row in summary_rows:
				doc.append("employer_contributions_summary", row)
			if meta.has_field("total_employer_contribution"):
				doc.total_employer_contribution = total

	return summary_rows


@frappe.whitelist()
def refresh_payroll_entry_employer_summary(payroll_entry: str) -> dict:
	"""Perbarui ringkasan employer di PE (dipanggil dari form jika total masih 0)."""
	rows = update_payroll_entry_employer_summary(payroll_entry, persist=True)
	total = sum(flt(r["amount"]) for r in rows)
	return {"total_employer_contribution": total, "rows": rows}
