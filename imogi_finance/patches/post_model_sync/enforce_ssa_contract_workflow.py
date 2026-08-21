"""Enforce Assignment Contract workflow for Salary Structure Assignment."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


PARENT_DOCTYPE = "Salary Structure Assignment"
CHILD_DOCTYPE = "Salary Structure Assignment Component"
TABLE_FIELD = "salary_component_amounts"


def execute():
	_create_tracking_fields()
	_update_status_options()
	_unlock_component_table_on_submit()
	_refresh_contract_statuses()
	_clear_contract_types()
	frappe.clear_cache(doctype=PARENT_DOCTYPE)
	frappe.clear_cache(doctype=CHILD_DOCTYPE)


def _create_tracking_fields():
	create_custom_fields(
		{
			PARENT_DOCTYPE: [
				{
					"fieldname": "assignment_contract_type",
					"label": "Jenis Contract",
					"fieldtype": "Select",
					"options": "\nRenewal\nAmendment",
					"insert_after": "status",
					"read_only": 1,
					"hidden": 1,
					"in_list_view": 0,
					"in_standard_filter": 1,
					"depends_on": "eval:doc.previous_assignment_contract",
					"description": "Renewal jika komponen gaji sama, Amendment jika Komponen Gaji berubah.",
				},
				{
					"fieldname": "assignment_contract_tracking_section",
					"label": "Tracking Assignment Contract",
					"fieldtype": "Section Break",
					"insert_after": "currency",
					"depends_on": "eval:doc.previous_assignment_contract || doc.renewed_by_assignment_contract",
				},
				{
					"fieldname": "previous_assignment_contract",
					"label": "Previous Assignment Contract",
					"fieldtype": "Link",
					"options": PARENT_DOCTYPE,
					"insert_after": "assignment_contract_tracking_section",
					"read_only": 1,
					"in_standard_filter": 1,
					"description": "Contract lama yang menjadi sumber perubahan/perpanjangan.",
				},
				{
					"fieldname": "assignment_contract_tracking_column",
					"fieldtype": "Column Break",
					"insert_after": "previous_assignment_contract",
				},
				{
					"fieldname": "change_reason",
					"label": "Alasan Perubahan",
					"fieldtype": "Small Text",
					"insert_after": "assignment_contract_tracking_column",
					"depends_on": "eval:doc.previous_assignment_contract || doc.renewed_by_assignment_contract",
					"mandatory_depends_on": "eval:doc.previous_assignment_contract",
					"description": "Alasan perpanjangan/perubahan contract, mis. kenaikan gaji atau tambahan tunjangan.",
				},
				{
					"fieldname": "renewed_by_assignment_contract",
					"label": "Renewed By Assignment Contract",
					"fieldtype": "Link",
					"options": PARENT_DOCTYPE,
					"insert_after": "change_reason",
					"read_only": 1,
					"allow_on_submit": 1,
					"in_standard_filter": 1,
					"description": "Contract baru yang menggantikan contract ini.",
				},
				{
					"fieldname": "assignment_contract_history_section",
					"label": "Riwayat Assignment Contract",
					"fieldtype": "Section Break",
					"insert_after": "renewed_by_assignment_contract",
				},
				{
					"fieldname": "assignment_contract_history",
					"label": "Riwayat",
					"fieldtype": "HTML",
					"insert_after": "assignment_contract_history_section",
					"read_only": 1,
				},
			]
		},
		ignore_validate=True,
	)
	_reposition_existing_tracking_fields()


def _reposition_existing_tracking_fields():
	updates = {
		"assignment_contract_tracking_section": {
			"insert_after": "currency",
			"label": "Tracking Assignment Contract",
			"depends_on": "eval:doc.previous_assignment_contract || doc.renewed_by_assignment_contract",
		},
		"assignment_contract_type": {
			"insert_after": "status",
			"read_only": 1,
			"options": "\nRenewal\nAmendment",
			"hidden": 1,
			"in_list_view": 0,
			"depends_on": "eval:doc.previous_assignment_contract",
		},
		"previous_assignment_contract": {
			"insert_after": "assignment_contract_tracking_section",
			"read_only": 1,
		},
		"assignment_contract_tracking_column": {
			"insert_after": "previous_assignment_contract",
		},
		"change_reason": {
			"insert_after": "assignment_contract_tracking_column",
			"depends_on": "eval:doc.previous_assignment_contract || doc.renewed_by_assignment_contract",
			"mandatory_depends_on": "eval:doc.previous_assignment_contract",
		},
		"renewed_by_assignment_contract": {
			"insert_after": "change_reason",
			"read_only": 1,
			"allow_on_submit": 1,
		},
		"assignment_contract_history_section": {
			"insert_after": "renewed_by_assignment_contract",
			"label": "Riwayat Assignment Contract",
		},
		"assignment_contract_history": {
			"insert_after": "assignment_contract_history_section",
			"label": "Riwayat",
		},
	}
	for fieldname, values in updates.items():
		custom_field = frappe.db.get_value(
			"Custom Field",
			{"dt": PARENT_DOCTYPE, "fieldname": fieldname},
			"name",
		)
		if custom_field:
			frappe.db.set_value("Custom Field", custom_field, values, update_modified=False)


def _update_status_options():
	status_field = frappe.db.get_value(
		"Custom Field",
		{"dt": PARENT_DOCTYPE, "fieldname": "status"},
		"name",
	)
	options = "Activate\nExpired Soon\nExpired"
	if status_field:
		frappe.db.set_value("Custom Field", status_field, "options", options, update_modified=False)
	_set_property(PARENT_DOCTYPE, "status", "options", options, "Text")


def _unlock_component_table_on_submit():
	# Historically this locked the table (allow_on_submit=0) after submit for
	# audit-trail integrity. Explicit user request (2026-08-19): keep the
	# Komponen Gaji grid editable even on Submitted documents, prioritizing
	# editability over the audit lock. This runs on every after_migrate, so
	# it must keep re-asserting allow_on_submit=1 rather than 0, otherwise a
	# routine migrate silently re-locks the grid again.
	_set_custom_field_allow_on_submit(PARENT_DOCTYPE, TABLE_FIELD, 1)
	_set_property(PARENT_DOCTYPE, TABLE_FIELD, "allow_on_submit", "1", "Check")

	if frappe.db.exists("DocType", CHILD_DOCTYPE):
		for fieldname in ("salary_component", "amount"):
			_set_docfield_allow_on_submit(CHILD_DOCTYPE, fieldname, 1)
			_set_property(CHILD_DOCTYPE, fieldname, "allow_on_submit", "1", "Check")


def _refresh_contract_statuses():
	from imogi_finance.payroll.salary_structure_assignment import get_assignment_status

	meta = frappe.get_meta(PARENT_DOCTYPE)
	if not (meta.has_field("end_date") and meta.has_field("status")):
		return

	fields = ["name", "end_date", "status"]
	if meta.has_field("renewed_by_assignment_contract"):
		fields.append("renewed_by_assignment_contract")

	for row in frappe.get_all(
		PARENT_DOCTYPE,
		filters={"docstatus": ["!=", 2]},
		fields=fields,
	):
		status = get_assignment_status(
			row.get("end_date"),
			row.get("renewed_by_assignment_contract"),
		)
		if row.get("status") != status:
			frappe.db.set_value(PARENT_DOCTYPE, row.name, "status", status, update_modified=False)


def _clear_contract_types():
	meta = frappe.get_meta(PARENT_DOCTYPE)
	if not meta.has_field("assignment_contract_type"):
		return

	for row in frappe.get_all(
		PARENT_DOCTYPE,
		filters={"assignment_contract_type": ["is", "set"]},
		fields=["name"],
	):
		frappe.db.set_value(
			PARENT_DOCTYPE,
			row.name,
			"assignment_contract_type",
			"",
			update_modified=False,
		)


def _set_custom_field_allow_on_submit(doctype: str, fieldname: str, value: int):
	custom_field = frappe.db.get_value(
		"Custom Field",
		{"dt": doctype, "fieldname": fieldname},
		"name",
	)
	if custom_field:
		frappe.db.set_value("Custom Field", custom_field, "allow_on_submit", value, update_modified=False)


def _set_docfield_allow_on_submit(doctype: str, fieldname: str, value: int):
	docfield = frappe.db.get_value(
		"DocField",
		{"parent": doctype, "fieldname": fieldname},
		"name",
	)
	if docfield:
		frappe.db.set_value("DocField", docfield, "allow_on_submit", value, update_modified=False)


def _set_property(doctype: str, fieldname: str, prop: str, value: str, property_type: str):
	ps_name = f"{doctype}-{fieldname}-{prop}"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", value, update_modified=False)
		return

	frappe.make_property_setter(
		{
			"doctype": doctype,
			"doctype_or_field": "DocField",
			"fieldname": fieldname,
			"property": prop,
			"value": value,
			"property_type": property_type,
		},
		ignore_validate=True,
		is_system_generated=0,
	)
