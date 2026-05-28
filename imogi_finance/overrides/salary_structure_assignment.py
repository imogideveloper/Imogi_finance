"""Salary Structure Assignment contract workflow override."""

import frappe
from frappe import _
from frappe.utils import getdate

from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
	DuplicateAssignment,
	SalaryStructureAssignment,
)


class CustomSalaryStructureAssignment(SalaryStructureAssignment):
	"""Allow a replacement contract to share an effective date with its tracked predecessor."""

	def validate_dates(self):
		joining_date, relieving_date = frappe.db.get_value(
			"Employee", self.employee, ["date_of_joining", "relieving_date"]
		)

		if not self.from_date:
			return

		duplicate_name = frappe.db.get_value(
			"Salary Structure Assignment",
			{
				"employee": self.employee,
				"from_date": self.from_date,
				"docstatus": 1,
				"name": ("!=", self.name),
			},
			"name",
		)
		if duplicate_name and duplicate_name != self.get("previous_assignment_contract"):
			frappe.throw(
				_("Salary Structure Assignment for Employee already exists"), DuplicateAssignment
			)

		if joining_date and getdate(self.from_date) < joining_date:
			frappe.throw(
				_("From Date {0} cannot be before employee's joining Date {1}").format(
					self.from_date, joining_date
				)
			)

		if relieving_date and getdate(self.from_date) > relieving_date and not self.flags.old_employee:
			frappe.throw(
				_("From Date {0} cannot be after employee's relieving Date {1}").format(
					self.from_date, relieving_date
				)
			)
