"""Batalkan full-width Komponen Gaji — kembalikan layout section HRMS."""

import frappe

PARENT = "Salary Structure Assignment"
KOMPONEN_SECTION = "ssa_komponen_gaji_section"
TABLE_FIELD = "salary_component_amounts"
INTRO_FIELD = "assignment_contract_intro"
OLD_SECTION = "section_break_7"

TABLE_DESCRIPTION = (
	"Klik Add Row, pilih Salary Component, isi nilai bulanan "
	"(per hari jika pakai payment_days di formula)."
)

KOMPONEN_PATCH_HIDDEN = (
	"column_break_9",
	"variable",
	"amended_from",
	"column_break_kjvm",
	"leave_encashment_amount_per_day",
)


def execute():
	_remove_komponen_section()
	_restore_table_layout()
	_undo_komponen_hidden_fields()
	_keep_base_hidden()
	frappe.clear_cache(doctype=PARENT)


def _remove_komponen_section():
	cf_name = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": KOMPONEN_SECTION})
	if cf_name:
		frappe.delete_doc("Custom Field", cf_name, force=True)

	for fieldname in (KOMPONEN_SECTION, OLD_SECTION, TABLE_FIELD):
		_delete_property_setter(fieldname, "label")
		_delete_property_setter(fieldname, "description")
		_delete_property_setter(fieldname, "hidden")


def _restore_table_layout():
	cf_intro = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": INTRO_FIELD}, "name")
	if cf_intro:
		frappe.db.set_value(
			"Custom Field", cf_intro, "insert_after", OLD_SECTION, update_modified=False
		)

	cf_table = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": TABLE_FIELD}, "name")
	if cf_table:
		insert_after = INTRO_FIELD if cf_intro else OLD_SECTION
		frappe.db.set_value(
			"Custom Field",
			cf_table,
			{
				"insert_after": insert_after,
				"label": "Komponen Gaji",
				"description": TABLE_DESCRIPTION,
			},
			update_modified=False,
		)

	if not frappe.db.exists("Property Setter", f"{PARENT}-section_break_7-label"):
		frappe.make_property_setter(
			{
				"doctype": PARENT,
				"doctype_or_field": "DocField",
				"fieldname": OLD_SECTION,
				"property": "label",
				"value": "Komponen Gaji",
				"property_type": "Data",
			},
			ignore_validate=True,
		)
	else:
		frappe.db.set_value(
			"Property Setter",
			f"{PARENT}-section_break_7-label",
			"value",
			"Komponen Gaji",
			update_modified=False,
		)


def _undo_komponen_hidden_fields():
	for fieldname in KOMPONEN_PATCH_HIDDEN:
		_delete_property_setter(fieldname, "hidden")


def _keep_base_hidden():
	for fieldname in ("base", "meal_allowance", "transport_allowance"):
		ps_name = f"{PARENT}-{fieldname}-hidden"
		if frappe.db.exists("Property Setter", ps_name):
			frappe.db.set_value("Property Setter", ps_name, "value", "1", update_modified=False)
		else:
			frappe.make_property_setter(
				{
					"doctype": PARENT,
					"doctype_or_field": "DocField",
					"fieldname": fieldname,
					"property": "hidden",
					"value": "1",
					"property_type": "Check",
				},
				ignore_validate=True,
				is_system_generated=0,
			)


def _delete_property_setter(fieldname: str, prop: str):
	ps_name = f"{PARENT}-{fieldname}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.delete_doc("Property Setter", ps_name, force=True)
