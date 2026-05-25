"""Salary Structure Assignment: child table komponen gaji (Odoo-style)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

# Map nama komponen ke field standar/custom SSA (untuk formula slip gaji).
COMPONENT_FIELD_MAP = {
	"gaji pokok": "base",
	"tunjangan makan": "meal_allowance",
	"tunjangan transport": "transport_allowance",
	"tunjangan operational": "tunjangan_operational",
}


def sync_assignment_component_fields(doc):
	"""Salin baris child table ke field scalar agar formula HRMS/payroll_indonesia tetap jalan."""
	rows = doc.get("salary_component_amounts") or []
	if not rows:
		return

	# Reset field yang diisi dari tabel (hindari nilai lama tertinggal).
	for fieldname in set(COMPONENT_FIELD_MAP.values()):
		if doc.meta.has_field(fieldname):
			doc.set(fieldname, 0)

	seen_components = set()
	for row in rows:
		if not row.salary_component:
			continue
		if row.salary_component in seen_components:
			frappe.throw(
				_("Komponen {0} sudah ada di tabel. Satu komponen hanya sekali.").format(
					frappe.bold(row.salary_component)
				)
			)
		seen_components.add(row.salary_component)

		key = (row.salary_component or "").strip().lower()
		fieldname = COMPONENT_FIELD_MAP.get(key)
		if fieldname and doc.meta.has_field(fieldname):
			doc.set(fieldname, flt(row.amount))



def resolve_assignment_doc(assignment):
	"""Muat SSA lengkap (termasuk child table Komponen Gaji) untuk evaluasi formula."""
	if not assignment:
		return None
	if isinstance(assignment, str):
		return frappe.get_doc("Salary Structure Assignment", assignment)
	if hasattr(assignment, "get") and assignment.get("salary_component_amounts"):
		return assignment
	name = assignment.get("name") if isinstance(assignment, dict) else getattr(assignment, "name", None)
	if name and frappe.db.exists("Salary Structure Assignment", name):
		return frappe.get_doc("Salary Structure Assignment", name)
	return frappe._dict(assignment) if isinstance(assignment, dict) else assignment


def get_assignment_formula_context(assignment) -> dict:
	"""Bangun variabel formula dari child table (+ field scalar legacy)."""
	assignment = resolve_assignment_doc(assignment)
	if not assignment:
		return {}

	context: dict = {}
	rows = assignment.get("salary_component_amounts") or []

	if rows:
		for row in rows:
			if not row.salary_component:
				continue
			amount = flt(row.amount)
			key = (row.salary_component or "").strip().lower()
			fieldname = COMPONENT_FIELD_MAP.get(key)
			if fieldname:
				context[fieldname] = amount
			abbr = frappe.db.get_value(
				"Salary Component", row.salary_component, "salary_component_abbr"
			)
			if abbr:
				context[abbr] = amount
			# fallback: snake_case dari nama komponen
			context[key.replace(" ", "_")] = amount
	else:
		for fieldname in COMPONENT_FIELD_MAP.values():
			if assignment.get(fieldname) is not None:
				context[fieldname] = flt(assignment.get(fieldname))

	# Komponen yang tidak ada di SSA (mis. tanpa tunjangan operational) → 0 agar formula tidak error.
	for fieldname in set(COMPONENT_FIELD_MAP.values()):
		if fieldname not in context and assignment.get(fieldname) is not None:
			context[fieldname] = flt(assignment.get(fieldname))
		context.setdefault(fieldname, 0)

	return context


def validate_salary_structure_assignment(doc, method=None):
	sync_assignment_component_fields(doc)
