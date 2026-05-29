"""SSA form v2: tanggal sejajar (section baru), grid Komponen Gaji lebar penuh."""

import json

import frappe

PARENT = "Salary Structure Assignment"
DATE_SECTION = "ssa_contract_dates_section"
DATE_COLUMN_BREAK = "ssa_date_column_break"
STATUS_COLUMN_BREAK = "ssa_status_column_break"
KOMPONEN_SECTION = "ssa_komponen_gaji_section"
OLD_SECTION = "section_break_7"
TABLE_FIELD = "salary_component_amounts"
INTRO_FIELD = "assignment_contract_intro"
CHILD_DOCTYPE = "Salary Structure Assignment Component"

KOMPONEN_DESCRIPTION = (
	"Klik Add Row, pilih Salary Component, isi nilai bulanan "
	"(per hari jika pakai payment_days di formula)."
)

# Field HRMS lama di section_break_7 — column break tetap memecah lebar grid.
LEGACY_FIELDS_IN_OLD_SECTION = (
	"base",
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
	OLD_SECTION,
	INTRO_FIELD,
)


def execute():
	_setup_contract_dates_section()
	_setup_komponen_gaji_section()
	_apply_field_order()
	_hide_legacy_section_clutter()
	_single_komponen_gaji_label()
	_widen_component_grid_columns()
	frappe.clear_cache(doctype=PARENT)
	frappe.clear_cache(doctype=CHILD_DOCTYPE)


def _setup_contract_dates_section():
	_ensure_custom_field(
		{
			"fieldname": DATE_SECTION,
			"fieldtype": "Section Break",
			"label": "",
			"insert_after": "salary_structure",
			"collapsible": 0,
		}
	)

	_ensure_custom_field(
		{
			"fieldname": DATE_COLUMN_BREAK,
			"fieldtype": "Column Break",
			"insert_after": "from_date",
		}
	)

	cf_end = frappe.db.get_value(
		"Custom Field", {"dt": PARENT, "fieldname": "end_date"}, "name"
	)
	if cf_end:
		frappe.db.set_value(
			"Custom Field", cf_end, "insert_after", DATE_COLUMN_BREAK, update_modified=False
		)

	_ensure_custom_field(
		{
			"fieldname": STATUS_COLUMN_BREAK,
			"fieldtype": "Column Break",
			"insert_after": "end_date",
		}
	)

	cf_status = frappe.db.get_value(
		"Custom Field", {"dt": PARENT, "fieldname": "status"}, "name"
	)
	if cf_status:
		frappe.db.set_value(
			"Custom Field", cf_status, "insert_after", STATUS_COLUMN_BREAK, update_modified=False
		)


def _setup_komponen_gaji_section():
	_ensure_custom_field(
		{
			"fieldname": KOMPONEN_SECTION,
			"fieldtype": "Section Break",
			"label": "Komponen Gaji",
			"insert_after": "status",
			"description": KOMPONEN_DESCRIPTION,
		}
	)

	cf_table = frappe.db.get_value(
		"Custom Field", {"dt": PARENT, "fieldname": TABLE_FIELD}, "name"
	)
	if cf_table:
		frappe.db.set_value(
			"Custom Field",
			cf_table,
			{"insert_after": KOMPONEN_SECTION, "label": "", "description": ""},
			update_modified=False,
		)

	_set_property(TABLE_FIELD, "label", "", "Data")
	_set_property(TABLE_FIELD, "description", "", "Text")
	_set_property(KOMPONEN_SECTION, "label", "Komponen Gaji", "Data")
	_set_property(KOMPONEN_SECTION, "description", KOMPONEN_DESCRIPTION, "Text")


def _apply_field_order():
	"""Urutkan field agar section tanggal + komponen gaji tampil benar."""
	frappe.clear_cache(doctype=PARENT)
	meta = frappe.get_meta(PARENT)
	order = [f.fieldname for f in meta.fields]

	_move_field_after(order, DATE_SECTION, "salary_structure")
	_move_field_after(order, "income_tax_slab", "salary_structure")
	_move_field_after(order, "column_break_11", "income_tax_slab")
	_move_field_after(order, "company", "column_break_11")
	_move_field_after(order, "from_date", DATE_SECTION)
	_move_field_after(order, DATE_COLUMN_BREAK, "from_date")
	_move_field_after(order, "end_date", DATE_COLUMN_BREAK)
	_move_field_after(order, STATUS_COLUMN_BREAK, "end_date")
	_move_field_after(order, "status", STATUS_COLUMN_BREAK)
	_move_field_after(order, KOMPONEN_SECTION, "status")
	_move_field_after(order, TABLE_FIELD, KOMPONEN_SECTION)

	_set_field_order(order)


def _move_field_after(order: list[str], fieldname: str, after: str) -> None:
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


def _hide_legacy_section_clutter():
	for fieldname in LEGACY_FIELDS_IN_OLD_SECTION:
		_set_property(fieldname, "hidden", "1", "Check")
	_set_property("meal_allowance", "hidden", "1", "Check")
	_set_property("transport_allowance", "hidden", "1", "Check")


def _single_komponen_gaji_label():
	_set_property(OLD_SECTION, "label", "", "Data")
	_set_property(OLD_SECTION, "hidden", "1", "Check")


def _widen_component_grid_columns():
	for fieldname, columns in (("salary_component", 5), ("amount", 5)):
		_set_child_field_columns(fieldname, columns)
	_hide_extra_child_list_columns()


def _hide_extra_child_list_columns():
	meta = frappe.get_meta(CHILD_DOCTYPE)
	for df in meta.fields:
		if df.fieldname in ("salary_component", "amount"):
			continue
		if df.in_list_view:
			_set_child_property(df.fieldname, "in_list_view", "0", "Check")


def _ensure_custom_field(fielddef: dict):
	fieldname = fielddef["fieldname"]
	if frappe.db.exists("Custom Field", {"dt": PARENT, "fieldname": fieldname}):
		name = frappe.db.get_value(
			"Custom Field", {"dt": PARENT, "fieldname": fieldname}, "name"
		)
		updates = {k: v for k, v in fielddef.items() if k not in ("fieldname",)}
		if updates:
			frappe.db.set_value("Custom Field", name, updates, update_modified=False)
		return

	frappe.get_doc({"doctype": "Custom Field", "dt": PARENT, **fielddef}).insert(
		ignore_permissions=True
	)


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
