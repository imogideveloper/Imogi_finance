"""Child table komponen gaji di Salary Structure Assignment (Add a line + Link Salary Component)."""

import frappe

CHILD_DOCTYPE = "Salary Structure Assignment Component"
TABLE_FIELD = "salary_component_amounts"
HIDE_FIELDS = ("base", "meal_allowance", "transport_allowance")


def execute():
	_ensure_child_doctype()
	_add_table_field()
	_hide_legacy_allowance_fields()
	_backfill_child_table_from_legacy_fields()
	frappe.clear_cache(doctype="Salary Structure Assignment")


def _ensure_child_doctype():
	if frappe.db.exists("DocType", CHILD_DOCTYPE):
		return
	frappe.reload_doc("Imogi Finance", "doctype", "salary_structure_assignment_component")


def _add_table_field():
	if frappe.db.exists(
		"Custom Field",
		{"dt": "Salary Structure Assignment", "fieldname": TABLE_FIELD},
	):
		return

	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Salary Structure Assignment",
			"fieldname": TABLE_FIELD,
			"label": "Komponen Gaji",
			"fieldtype": "Table",
			"options": CHILD_DOCTYPE,
			"insert_after": "section_break_7",
			"description": "Klik Add Row, pilih Salary Component, isi nilai bulanan (per hari jika pakai payment_days di formula).",
		}
	).insert(ignore_permissions=True)

	# Judul section area komponen gaji.
	SECTION_LABEL = "Komponen Gaji"
	if frappe.db.exists("Property Setter", "Salary Structure Assignment-section_break_7-label"):
		frappe.db.set_value(
			"Property Setter",
			"Salary Structure Assignment-section_break_7-label",
			"value",
			SECTION_LABEL,
			update_modified=False,
		)
	else:
		frappe.make_property_setter(
			{
				"doctype": "Salary Structure Assignment",
				"doctype_or_field": "DocField",
				"fieldname": "section_break_7",
				"property": "label",
				"value": SECTION_LABEL,
				"property_type": "Data",
			},
			ignore_validate=True,
		)


def _hide_legacy_allowance_fields():
	for fieldname in HIDE_FIELDS:
		ps_name = f"Salary Structure Assignment-{fieldname}-hidden"
		if frappe.db.exists("Property Setter", ps_name):
			frappe.db.set_value("Property Setter", ps_name, "value", "1", update_modified=False)
			continue
		frappe.make_property_setter(
			{
				"doctype": "Salary Structure Assignment",
				"doctype_or_field": "DocField",
				"fieldname": fieldname,
				"property": "hidden",
				"value": "1",
				"property_type": "Check",
			},
			ignore_validate=True,
			is_system_generated=0,
		)


# Urutan baris saat migrasi data lama (field tersembunyi → child table).
LEGACY_ROW_MAP = (
	("Gaji Pokok", "base"),
	("Tunjangan Makan", "meal_allowance"),
	("Tunjangan Transport", "transport_allowance"),
)


def _backfill_child_table_from_legacy_fields():
	"""Isi child table dari nilai base / uang makan / transport yang sudah ada."""
	if not frappe.db.exists("DocType", "Salary Structure Assignment Component"):
		return
	if not frappe.get_meta("Salary Structure Assignment").has_field("salary_component_amounts"):
		return

	for row in frappe.db.sql(
		"""
		SELECT name, base, meal_allowance, transport_allowance
		FROM `tabSalary Structure Assignment`
		WHERE docstatus < 2
		""",
		as_dict=True,
	):
		if frappe.db.count(
			"Salary Structure Assignment Component",
			{"parent": row.name, "parenttype": "Salary Structure Assignment"},
		):
			continue

		ssa = frappe.get_doc("Salary Structure Assignment", row.name)
		added = False
		for component_name, fieldname in LEGACY_ROW_MAP:
			amount = row.get(fieldname) or 0
			if not amount:
				continue
			if not frappe.db.exists("Salary Component", component_name):
				continue
			ssa.append(
				"salary_component_amounts",
				{"salary_component": component_name, "amount": amount},
			)
			added = True

		if added:
			ssa.flags.ignore_validate = True
			ssa.save(ignore_permissions=True)
