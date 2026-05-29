"""Sembunyikan section Tunjangan Ditanggung Perusahaan + blok periode HRMS di Payroll Entry.

Periode gaji diatur lewat Payroll Period / Periode Gaji (Bulan) di atas form.
Start/End Date & Payroll Frequency tetap terisi otomatis di backend.
"""

import frappe

PARENT = "Payroll Entry"

EMPLOYER_FIELDS = (
	"employer_contributions_section",
	"total_employer_contribution",
	"employer_contributions_summary",
)

# Field HRMS redundant (periode sudah dari Payroll Period / Periode Gaji di atas).
# Jangan sembunyikan section_break_cypo — field setelahnya (Salary Slip Based, Run Payroll, Periode) ikut hilang.
PAYROLL_PERIOD_DETAIL_FIELDS = (
	"payroll_frequency",
	"start_date",
	"end_date",
	"column_break_13",
	"deduct_tax_for_unclaimed_employee_benefits",
	"deduct_tax_for_unsubmitted_tax_exemption_proof",
)

# Disembunyikan dari UI; nilai tetap diisi otomatis di backend (tahun dari posting date).
PAYROLL_PERIOD_LINK_FIELD = "payroll_period"


def execute():
	for fieldname in EMPLOYER_FIELDS + PAYROLL_PERIOD_DETAIL_FIELDS:
		_hide_field(fieldname)
	_hide_field(PAYROLL_PERIOD_LINK_FIELD)
	_reposition_periode_gaji_field()
	_unhide_field("section_break_cypo")
	_move_employer_fields_to_form_end()
	frappe.clear_cache(doctype=PARENT)


def _reposition_periode_gaji_field():
	"""Periode Gaji langsung di bawah Company jika Payroll Period disembunyikan."""
	cf_name = frappe.db.get_value(
		"Custom Field", {"dt": PARENT, "fieldname": "payroll_sub_period"}, "name"
	)
	if cf_name:
		frappe.db.set_value(
			"Custom Field", cf_name, "insert_after", "company", update_modified=False
		)


def _unhide_field(fieldname: str):
	ps_name = f"{PARENT}-{fieldname}-hidden"
	if frappe.db.exists("Property Setter", ps_name):
		frappe.db.set_value("Property Setter", ps_name, "value", "0", update_modified=False)


def _hide_field(fieldname: str):
	cf_name = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": fieldname}, "name")
	if cf_name:
		frappe.db.set_value("Custom Field", cf_name, "hidden", 1, update_modified=False)

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


def _move_employer_fields_to_form_end():
	"""Pindah ke akhir form agar tidak mengganggu section periode gaji jika ditampilkan lagi."""
	chain = [
		("employer_contributions_section", "error_message"),
		("total_employer_contribution", "employer_contributions_section"),
		("employer_contributions_summary", "total_employer_contribution"),
	]
	for fieldname, insert_after in chain:
		cf_name = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": fieldname}, "name")
		if cf_name:
			frappe.db.set_value(
				"Custom Field", cf_name, "insert_after", insert_after, update_modified=False
			)
