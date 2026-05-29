"""Payroll Entry: default payroll frequency + filter karyawan SSA aktif."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, getdate

from imogi_finance.payroll.payroll_period_integration import (
	_get_applicable_assignment_contract,
	apply_sub_period_to_payroll_entry,
)

from hrms.payroll.doctype.payroll_entry.payroll_entry import PayrollEntry as HRMSPayrollEntry


DEFAULT_PAYROLL_FREQUENCY = "Monthly"
ACTIVE_SSA_STATUSES = frozenset({"Activate", "Expired Soon"})


def ensure_payroll_entry_defaults(doc) -> None:
	"""Payroll Frequency wajib di HRMS meski field disembunyikan."""
	if not cint(doc.get("salary_slip_based_on_timesheet")) and not doc.get("payroll_frequency"):
		doc.payroll_frequency = DEFAULT_PAYROLL_FREQUENCY


def employee_has_active_assignment(employee: str, lookup_date) -> bool:
	if not employee or not lookup_date:
		return False
	if not frappe.db.has_column("Salary Structure Assignment", "end_date"):
		return True

	assignment = _get_applicable_assignment_contract(employee, getdate(lookup_date))
	if not assignment or assignment.get("is_expired"):
		return False

	if frappe.db.has_column("Salary Structure Assignment", "status"):
		status = frappe.db.get_value("Salary Structure Assignment", assignment.name, "status")
		if status and status not in ACTIVE_SSA_STATUSES:
			return False

	return True


def filter_employees_with_active_ssa(employees, lookup_date) -> list:
	if not employees:
		return []
	lookup = getdate(lookup_date) if lookup_date else None
	if not lookup:
		return list(employees)

	filtered = []
	for row in employees:
		employee = row.get("employee") if isinstance(row, dict) else getattr(row, "employee", None)
		if employee and employee_has_active_assignment(employee, lookup):
			filtered.append(row)
	return filtered


class CustomPayrollEntry(HRMSPayrollEntry):
	def validate(self):
		ensure_payroll_entry_defaults(self)
		if self.get("payroll_period"):
			apply_sub_period_to_payroll_entry(self)
		# Base = payroll_indonesia (jika ada) → HRMS PayrollEntry
		super().validate()

	@frappe.whitelist()
	def fill_employee_details(self):
		ensure_payroll_entry_defaults(self)
		super().fill_employee_details()

		if not self.get("end_date"):
			return self.get_employees_with_unmarked_attendance()

		active_employees = filter_employees_with_active_ssa(self.employees, self.end_date)
		if len(active_employees) < len(self.employees or []):
			self.set("employees", active_employees)
			self.number_of_employees = len(active_employees)

		if not active_employees:
			frappe.throw(
				_(
					"Tidak ada karyawan dengan Assignment Contract aktif untuk periode ini. "
					"Perbarui atau buat contract baru terlebih dahulu."
				),
				title=_("Tidak Ada Karyawan"),
			)

		return self.get_employees_with_unmarked_attendance()


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def employee_query(doctype, txt, searchfield, start, page_len, filters):
	"""Employee link query: default Monthly + hanya SSA aktif."""
	from hrms.payroll.doctype.payroll_entry.payroll_entry import get_employee_list

	filters = frappe._dict(filters or {})
	if not filters.get("payroll_frequency") and not cint(filters.get("salary_slip_based_on_timesheet")):
		filters.payroll_frequency = DEFAULT_PAYROLL_FREQUENCY

	employee_list = get_employee_list(
		filters,
		searchfield=searchfield,
		search_string=txt,
		fields=["name", "employee_name"],
		as_dict=False,
		limit=page_len,
		offset=start,
	)

	lookup_date = filters.get("end_date")
	if not lookup_date or not frappe.db.has_column("Salary Structure Assignment", "end_date"):
		return employee_list

	return [
		row
		for row in employee_list
		if row and employee_has_active_assignment(row[0], lookup_date)
	]
