"""SSA form: From/End Date sejajar, satu label Komponen Gaji, grid lebar penuh."""

import frappe

PARENT = "Salary Structure Assignment"
TABLE_FIELD = "salary_component_amounts"
DATE_COLUMN_BREAK = "ssa_date_column_break"
CHILD_DOCTYPE = "Salary Structure Assignment Component"


def execute():
	_fix_status_field_default()
	_add_date_column_break()
	_move_end_date_beside_from_date()
	_single_komponen_gaji_label()
	_widen_component_grid_columns()
	frappe.clear_cache(doctype=PARENT)
	frappe.clear_cache(doctype=CHILD_DOCTYPE)


def _fix_status_field_default():
	"""Default status harus cocok dengan opsi (Activate, bukan Active)."""
	cf_name = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": "status"}, "name")
	if cf_name:
		frappe.db.set_value("Custom Field", cf_name, "default", "Activate", update_modified=False)
	ps = f"{PARENT}-status-default"
	if frappe.db.exists("Property Setter", ps):
		frappe.db.set_value("Property Setter", ps, "value", "Activate", update_modified=False)


def _add_date_column_break():
	if frappe.db.exists("Custom Field", {"dt": PARENT, "fieldname": DATE_COLUMN_BREAK}):
		return
	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": PARENT,
			"fieldname": DATE_COLUMN_BREAK,
			"fieldtype": "Column Break",
			"insert_after": "from_date",
		}
	).insert(ignore_permissions=True)


def _move_end_date_beside_from_date():
	cf_end = frappe.db.get_value(
		"Custom Field", {"dt": PARENT, "fieldname": "end_date"}, "name"
	)
	if cf_end:
		frappe.db.set_value(
			"Custom Field", cf_end, "insert_after", DATE_COLUMN_BREAK, update_modified=False
		)

	cf_status = frappe.db.get_value(
		"Custom Field", {"dt": PARENT, "fieldname": "status"}, "name"
	)
	if cf_status:
		frappe.db.set_value(
			"Custom Field", cf_status, "insert_after", "end_date", update_modified=False
		)


def _single_komponen_gaji_label():
	"""Section break = judul; field Table tanpa label duplikat."""
	_set_property("section_break_7", "label", "Komponen Gaji", "Data")

	cf_table = frappe.db.get_value(
		"Custom Field", {"dt": PARENT, "fieldname": TABLE_FIELD}, "name"
	)
	if cf_table:
		frappe.db.set_value("Custom Field", cf_table, "label", "", update_modified=False)

	_set_property(TABLE_FIELD, "label", "", "Data")


def _widen_component_grid_columns():
	"""Hanya Name + Nilai; lebar kolom mengisi grid."""
	for fieldname, columns in (("salary_component", 7), ("amount", 3)):
		_set_child_field_columns(fieldname, columns)
		_hide_extra_child_list_columns()


def _hide_extra_child_list_columns():
	meta = frappe.get_meta(CHILD_DOCTYPE)
	for df in meta.fields:
		if df.fieldname in ("salary_component", "amount"):
			continue
		if df.in_list_view:
			_set_child_property(df.fieldname, "in_list_view", "0", "Check")


def _set_child_field_columns(fieldname: str, columns: int):
	if frappe.db.exists("DocField", {"parent": CHILD_DOCTYPE, "fieldname": fieldname}):
		frappe.db.set_value(
			"DocField",
			{"parent": CHILD_DOCTYPE, "fieldname": fieldname},
			"columns",
			columns,
			update_modified=False,
		)


def _set_child_property(fieldname: str, prop: str, value: str, property_type: str):
	ps_name = f"{CHILD_DOCTYPE}-{fieldname}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return
	frappe.make_property_setter(
		{
			"doctype": CHILD_DOCTYPE,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		ignore_validate=True,
	)


def _set_property(fieldname: str, prop: str, value: str, property_type: str):
	ps_name = f"{PARENT}-{fieldname}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return
	frappe.make_property_setter(
		{
			"doctype": PARENT,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		ignore_validate=True,
		is_system_generated=0,
	)
