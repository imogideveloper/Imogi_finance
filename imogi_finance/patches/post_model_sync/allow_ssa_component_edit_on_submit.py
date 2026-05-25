"""Komponen Gaji SSA: boleh add/delete baris meski dokumen sudah submit."""

import frappe

TABLE_FIELD = "salary_component_amounts"
CHILD_DOCTYPE = "Salary Structure Assignment Component"


def execute():
	_set_allow_on_submit("Salary Structure Assignment", TABLE_FIELD)
	for fieldname in ("salary_component", "amount"):
		_set_allow_on_submit(CHILD_DOCTYPE, fieldname, is_child=True)
	frappe.clear_cache(doctype="Salary Structure Assignment")


def _set_allow_on_submit(doctype: str, fieldname: str, is_child: bool = False):
	ps_name = f"{doctype}-{fieldname}-allow_on_submit"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", "1", update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": doctype,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": "allow_on_submit",
			"value": "1",
			"property_type": "Check",
		},
		ignore_validate=True,
		is_system_generated=0,
	)
