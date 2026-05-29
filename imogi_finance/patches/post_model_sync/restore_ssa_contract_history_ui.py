"""Tampilkan kembali section Riwayat Assignment Contract + perbaiki urutan field."""

import json

import frappe

PARENT = "Salary Structure Assignment"
HISTORY_SECTION = "assignment_contract_history_section"
HISTORY_HTML = "assignment_contract_history"


def execute():
	_ensure_history_custom_fields()
	_unhide_history_fields()
	_fix_history_field_order()
	frappe.clear_cache(doctype=PARENT)


def _ensure_history_custom_fields():
	if not frappe.db.exists("Custom Field", {"dt": PARENT, "fieldname": HISTORY_SECTION}):
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": PARENT,
				"fieldname": HISTORY_SECTION,
				"label": "Riwayat Assignment Contract",
				"fieldtype": "Section Break",
				"insert_after": "renewed_by_assignment_contract",
			}
		).insert(ignore_permissions=True)

	if not frappe.db.exists("Custom Field", {"dt": PARENT, "fieldname": HISTORY_HTML}):
		frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": PARENT,
				"fieldname": HISTORY_HTML,
				"label": "Riwayat",
				"fieldtype": "HTML",
				"insert_after": HISTORY_SECTION,
				"read_only": 1,
			}
		).insert(ignore_permissions=True)


def _unhide_history_fields():
	for fieldname in (HISTORY_SECTION, HISTORY_HTML):
		ps_name = f"{PARENT}-{fieldname}-hidden"
		if frappe.db.exists("Property Setter", ps_name):
			frappe.delete_doc("Property Setter", ps_name, force=True)

	cf_html = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": HISTORY_HTML}, "name")
	if cf_html:
		frappe.db.set_value(
			"Custom Field", cf_html, "insert_after", HISTORY_SECTION, update_modified=False
		)


def _fix_history_field_order():
	meta = frappe.get_meta(PARENT)
	order = [f.fieldname for f in meta.fields]
	if HISTORY_SECTION not in order or HISTORY_HTML not in order:
		return

	_move_after(order, HISTORY_HTML, HISTORY_SECTION)
	_set_field_order(order)


def _move_after(order: list[str], fieldname: str, after: str) -> None:
	if fieldname not in order or after not in order:
		return
	order.remove(fieldname)
	order.insert(order.index(after) + 1, fieldname)


def _set_field_order(order: list[str]) -> None:
	value = json.dumps(order)
	ps_name = f"{PARENT}-main-field_order"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return
	frappe.make_property_setter(
		{
			"doctype": PARENT,
			"doctype_or_field": "DocType",
			"property": "field_order",
			"value": value,
			"property_type": "JSON",
		},
		ignore_validate=True,
		is_system_generated=0,
	)
