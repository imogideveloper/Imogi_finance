"""Kembalikan layout form SSA seperti sebelum patch fix_ssa_form_layout / v2."""

import frappe

PARENT = "Salary Structure Assignment"
CHILD = "Salary Structure Assignment Component"
TABLE_FIELD = "salary_component_amounts"

LAYOUT_CUSTOM_FIELDS = (
	"ssa_contract_dates_section",
	"ssa_date_column_break",
	"ssa_status_column_break",
	"ssa_komponen_gaji_section",
)

# Property setter hidden dari layout v2 — jangan hapus yang dari migrasi child table.
KEEP_HIDDEN = frozenset({"base", "meal_allowance", "transport_allowance"})

UNHIDE_FIELDS = (
	"column_break_9",
	"variable",
	"amended_from",
	"column_break_kjvm",
	"leave_encashment_amount_per_day",
	"opening_balances_section",
	"taxable_earnings_till_date",
	"column_break_20",
	"tax_deducted_till_date",
	"section_break_17",
	"payroll_cost_centers",
	"section_break_7",
	"assignment_contract_intro",
)

TABLE_DESCRIPTION = (
	"Klik Add Row, pilih Salary Component, isi nilai bulanan "
	"(per hari jika pakai payment_days di formula)."
)


def execute():
	_delete_field_order()
	_delete_layout_custom_fields()
	_restore_custom_field_positions()
	_restore_komponen_labels()
	_unhide_layout_hidden_fields()
	_restore_child_grid_columns()
	frappe.clear_cache(doctype=PARENT)
	frappe.clear_cache(doctype=CHILD)


def _delete_field_order():
	name = f"{PARENT}-main-field_order"
	if frappe.db.exists("Property Setter", name):
		frappe.delete_doc("Property Setter", name, force=True)


def _delete_layout_custom_fields():
	for fieldname in LAYOUT_CUSTOM_FIELDS:
		cf_name = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": fieldname})
		if cf_name:
			frappe.delete_doc("Custom Field", cf_name, force=True)


def _restore_custom_field_positions():
	updates = {
		"end_date": {"insert_after": "from_date"},
		"status": {"insert_after": "end_date"},
		TABLE_FIELD: {
			"insert_after": "section_break_7",
			"label": "Komponen Gaji",
			"description": TABLE_DESCRIPTION,
		},
	}
	for fieldname, values in updates.items():
		cf_name = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": fieldname})
		if cf_name:
			frappe.db.set_value("Custom Field", cf_name, values, update_modified=False)


def _restore_komponen_labels():
	_delete_property_setter(PARENT, "section_break_7", "label")
	_delete_property_setter(PARENT, "section_break_7", "hidden")
	_delete_property_setter(PARENT, TABLE_FIELD, "label")
	_delete_property_setter(PARENT, TABLE_FIELD, "description")

	# Judul section seperti sebelum eksperimen layout (patch child table).
	if not frappe.db.exists("Property Setter", f"{PARENT}-section_break_7-label"):
		frappe.make_property_setter(
			{
				"doctype": PARENT,
				"doctype_or_field": "DocField",
				"fieldname": "section_break_7",
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


def _unhide_layout_hidden_fields():
	for fieldname in UNHIDE_FIELDS:
		_delete_property_setter(PARENT, fieldname, "hidden")


def _restore_child_grid_columns():
	for fieldname, columns in (("salary_component", 7), ("amount", 3)):
		if frappe.db.exists("DocField", {"parent": CHILD, "fieldname": fieldname}):
			frappe.db.set_value(
				"DocField",
				{"parent": CHILD, "fieldname": fieldname},
				"columns",
				columns,
				update_modified=False,
			)


def _delete_property_setter(doctype: str, fieldname: str, property_name: str) -> None:
	ps_name = f"{doctype}-{fieldname}-{property_name}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.delete_doc("Property Setter", ps_name, force=True)
