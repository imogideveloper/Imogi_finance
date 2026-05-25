"""Banner Assignment Contract (kotak biru) + kembalikan label section Komponen Gaji."""

import frappe

SECTION_FIELD = "section_break_7"
SECTION_LABEL = "Komponen Gaji"
HTML_FIELD = "assignment_contract_intro"


def execute():
	_revert_section_label()
	_add_intro_banner()
	frappe.clear_cache(doctype="Salary Structure Assignment")


def _revert_section_label():
	ps_name = f"Salary Structure Assignment-{SECTION_FIELD}-label"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", SECTION_LABEL, update_modified=False)
	else:
		frappe.make_property_setter(
			{
				"doctype": "Salary Structure Assignment",
				"doctype_or_field": "DocField",
				"fieldname": SECTION_FIELD,
				"property": "label",
				"value": SECTION_LABEL,
				"property_type": "Data",
			},
			ignore_validate=True,
		)


def _add_intro_banner():
	html = (
		'<motion class="alert alert-info" style="margin-bottom: 12px;">'
		"<strong>Assignment Contract</strong><br>"
		'<span class="text-muted">'
		"Kontrak penugasan gaji karyawan. Tambah baris komponen (Add Row), "
		"pilih <b>Salary Component</b>, lalu isi <b>Nilai</b> bulanan. "
		"Tombol <b>Muat Komponen dari Struktur</b> mengisi otomatis dari Salary Structure."
		"</span></motion>"
	)
	html = html.replace("<motion", "<div").replace("</motion>", "</div>")

	cf_name = f"Salary Structure Assignment-{HTML_FIELD}"
	if frappe.db.exists("Custom Field", cf_name):
		frappe.db.set_value("Custom Field", cf_name, "options", html, update_modified=False)
		return

	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Salary Structure Assignment",
			"fieldname": HTML_FIELD,
			"label": "Assignment Contract",
			"fieldtype": "HTML",
			"options": html,
			"insert_after": "section_break_7",
		}
	).insert(ignore_permissions=True)

	_hide_legacy_list_columns()


def _hide_legacy_list_columns():
	for fieldname in ("meal_allowance", "transport_allowance"):
		ps_name = f"Salary Structure Assignment-{fieldname}-in_list_view"
		if frappe.db.exists("Property Setter", ps_name):
			frappe.db.set_value("Property Setter", ps_name, "value", "0", update_modified=False)
			continue
		frappe.make_property_setter(
			{
				"doctype": "Salary Structure Assignment",
				"doctype_or_field": "DocField",
				"fieldname": fieldname,
				"property": "in_list_view",
				"value": "0",
				"property_type": "Check",
			},
			ignore_validate=True,
		)
