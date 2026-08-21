"""Simplify Salary Slip's List View columns per explicit user request
(2026-08-20): show Net Pay (missing by default) and drop the busier
Employee/Company/Salary Structure columns, matching the plain-list look
the user compared against - final column set: ID, Employee Name, Net Pay,
Posting Date, Status (ID and Status are always shown by Frappe itself).
"""

import frappe


def execute():
	doctype = "Salary Slip"

	_set_in_list_view(doctype, "net_pay", 1)
	_set_in_list_view(doctype, "employee", 0)
	_set_in_list_view(doctype, "company", 0)
	_set_in_list_view(doctype, "salary_structure", 0)

	frappe.clear_cache(doctype=doctype)


def _set_in_list_view(doctype: str, fieldname: str, value: int):
	ps_name = f"{doctype}-{fieldname}-in_list_view"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", str(value), update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": doctype,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": "in_list_view",
			"value": str(value),
			"property_type": "Check",
		},
		ignore_validate=True,
		is_system_generated=0,
	)
