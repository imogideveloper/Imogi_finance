"""SSA: grid Komponen Gaji lebar penuh (section terpisah, tanpa column break HRMS)."""

import frappe

PARENT = "Salary Structure Assignment"
KOMPONEN_SECTION = "ssa_komponen_gaji_section"
TABLE_FIELD = "salary_component_amounts"
INTRO_FIELD = "assignment_contract_intro"
OLD_SECTION = "section_break_7"

SECTION_DESCRIPTION = (
	"Klik Add Row, pilih Salary Component, isi nilai bulanan "
	"(per hari jika pakai payment_days di formula)."
)

# Column break / field HRMS di section yang sama membuat grid hanya ~50% lebar.
LEGACY_SPLIT_FIELDS = (
	"base",
	"column_break_9",
	"variable",
	"amended_from",
	"column_break_kjvm",
	"leave_encashment_amount_per_day",
)


def execute():
	_ensure_komponen_section()
	_reposition_table_and_intro()
	_hide_legacy_split_fields()
	_adjust_section_labels()
	frappe.clear_cache(doctype=PARENT)


def _ensure_komponen_section():
	if frappe.db.exists("Custom Field", {"dt": PARENT, "fieldname": KOMPONEN_SECTION}):
		frappe.db.set_value(
			"Custom Field",
			frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": KOMPONEN_SECTION}),
			{
				"label": "Komponen Gaji",
				"description": SECTION_DESCRIPTION,
				"insert_after": OLD_SECTION,
			},
			update_modified=False,
		)
		return

	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": PARENT,
			"fieldname": KOMPONEN_SECTION,
			"fieldtype": "Section Break",
			"label": "Komponen Gaji",
			"description": SECTION_DESCRIPTION,
			"insert_after": OLD_SECTION,
		}
	).insert(ignore_permissions=True)


def _reposition_table_and_intro():
	cf_table = frappe.db.get_value(
		"Custom Field", {"dt": PARENT, "fieldname": TABLE_FIELD}, "name"
	)
	if cf_table:
		frappe.db.set_value(
			"Custom Field",
			cf_table,
			{
				"insert_after": KOMPONEN_SECTION,
				"label": "",
				"description": "",
			},
			update_modified=False,
		)

	cf_intro = frappe.db.get_value(
		"Custom Field", {"dt": PARENT, "fieldname": INTRO_FIELD}, "name"
	)
	if cf_intro:
		frappe.db.set_value(
			"Custom Field", cf_intro, "insert_after", TABLE_FIELD, update_modified=False
		)

	_set_property(TABLE_FIELD, "label", "", "Data")
	_set_property(TABLE_FIELD, "description", "", "Text")


def _hide_legacy_split_fields():
	for fieldname in LEGACY_SPLIT_FIELDS:
		_set_property(fieldname, "hidden", "1", "Check")


def _adjust_section_labels():
	_set_property(OLD_SECTION, "label", "", "Data")
	_set_property(KOMPONEN_SECTION, "label", "Komponen Gaji", "Data")
	_set_property(KOMPONEN_SECTION, "description", SECTION_DESCRIPTION, "Text")


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
