"""Redesign tampilan Salary Structure Assignment (v2 - layout seimbang).

Perbaikan dari versi sebelumnya:
1. Blok atas SEIMBANG -> kiri: Employee + Employee Name, kanan: Salary
   Structure + Company. Tidak ada lagi field menumpuk / kolom kosong saat
   Employee dipilih.
2. Department & Designation (auto-fetch HRMS) disembunyikan -> tidak bikin
   tampilan "loncat" saat memilih Employee.
3. Komponen Gaji tetap LEBAR PENUH di section sendiri.
4. Income Tax Slab / Payroll Payable Account / Currency dikumpulkan rapi di
   section "Detail Payroll" di bawah tabel (tidak lagi terorphan).
5. SEMUA column/section break bawaan HRMS yang tidak dipakai disembunyikan,
   sehingga tata letak sepenuhnya ditentukan section break milik kita.

Idempotent. Jadi layout final yang menang (taruh paling akhir di patches.txt).
"""

import json

import frappe

PARENT = "Salary Structure Assignment"
CHILD = "Salary Structure Assignment Component"

# --- Custom break milik redesign (nama unik) ------------------------------- #
EMP_COL = "ssa_employee_col"            # column break blok atas
PERIODE_SECTION = "ssa_periode_section"
DATE_COL_1 = "ssa_date_col_1"
DATE_COL_2 = "ssa_date_col_2"
KOMP_SECTION = "ssa_komponen_section"
KOMP_SECTION_END = "ssa_komponen_section_end"
PAYROLL_SECTION = "ssa_payroll_section"
PAYROLL_COL_1 = "ssa_payroll_col_1"
PAYROLL_COL_2 = "ssa_payroll_col_2"

# --- Field eksisting -------------------------------------------------------- #
TABLE = "salary_component_amounts"
INTRO = "assignment_contract_intro"

KOMP_DESC = (
	"Klik Add Row, pilih Salary Component, lalu isi Nilai bulanan "
	"(per hari jika formula memakai payment_days)."
)

# Urutan field yang TAMPIL. Sisanya di-append & disembunyikan otomatis.
VISIBLE_ORDER = [
	"employee",
	"employee_name",
	EMP_COL,
	"salary_structure",
	"company",
	PERIODE_SECTION,
	"from_date",
	DATE_COL_1,
	"end_date",
	DATE_COL_2,
	"status",
	KOMP_SECTION,
	INTRO,
	TABLE,
	KOMP_SECTION_END,
	PAYROLL_SECTION,
	"income_tax_slab",
	PAYROLL_COL_1,
	"payroll_payable_account",
	PAYROLL_COL_2,
	"currency",
]

# Break milik kita -> jangan disembunyikan.
MY_BREAKS = {
	EMP_COL,
	PERIODE_SECTION,
	DATE_COL_1,
	DATE_COL_2,
	KOMP_SECTION,
	KOMP_SECTION_END,
	PAYROLL_SECTION,
	PAYROLL_COL_1,
	PAYROLL_COL_2,
}

# Break bawaan yang TETAP dipakai (dikontrol client script: riwayat & tracking).
KEEP_BREAKS = {
	"assignment_contract_tracking_section",
	"assignment_contract_tracking_column",
	"assignment_contract_history_section",
}

# Field non-break yang disembunyikan (clutter / tidak relevan di form ini).
HIDE_FIELDS = (
	"department",
	"designation",
	"base",
	"variable",
	"amended_from",
	"leave_encashment_amount_per_day",
	"taxable_earnings_till_date",
	"tax_deducted_till_date",
	"payroll_cost_centers",
	"meal_allowance",
	"transport_allowance",
)


def execute():
	_create_breaks()
	_apply_field_order()
	_hide_all_unused_breaks()
	_hide_clutter_fields()
	_style_sections_and_table()
	_set_grid_columns()
	frappe.clear_cache(doctype=PARENT)
	frappe.clear_cache(doctype=CHILD)


# --------------------------------------------------------------------------- #
# 1. Buat section / column break custom                                       #
# --------------------------------------------------------------------------- #
def _create_breaks():
	# Posisi insert_after di sini hanya placement awal; urutan final ditentukan
	# oleh field_order property setter di langkah berikutnya.
	_upsert(EMP_COL, "Column Break", insert_after="employee_name")
	_upsert(PERIODE_SECTION, "Section Break", insert_after="company", label="Periode Kontrak")
	_upsert(DATE_COL_1, "Column Break", insert_after="from_date")
	_upsert(DATE_COL_2, "Column Break", insert_after="end_date")
	_upsert(KOMP_SECTION_END, "Section Break", insert_after=TABLE, label="")
	_upsert(PAYROLL_SECTION, "Section Break", insert_after=TABLE, label="Detail Payroll")
	_upsert(PAYROLL_COL_1, "Column Break", insert_after=TABLE)
	_upsert(PAYROLL_COL_2, "Column Break", insert_after=TABLE)
	_upsert(
		KOMP_SECTION,
		"Section Break",
		insert_after="status",
		label="Komponen Gaji",
		description=KOMP_DESC,
	)



# --------------------------------------------------------------------------- #
# 2. Urutkan field                                                            #
# --------------------------------------------------------------------------- #
def _apply_field_order():
	frappe.clear_cache(doctype=PARENT)
	all_fields = [f.fieldname for f in frappe.get_meta(PARENT).fields]

	visible = [f for f in VISIBLE_ORDER if f in all_fields]
	remainder = [f for f in all_fields if f not in visible]
	_store_field_order(visible + remainder)


def _store_field_order(order):
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


# --------------------------------------------------------------------------- #
# 3. Sembunyikan semua break bawaan yang tidak dipakai                        #
# --------------------------------------------------------------------------- #
def _hide_all_unused_breaks():
	keep = MY_BREAKS | KEEP_BREAKS
	for df in frappe.get_meta(PARENT).fields:
		if df.fieldtype not in ("Section Break", "Column Break"):
			continue
		if df.fieldname in keep:
			_set_property(df.fieldname, "hidden", "0", "Check")
			continue
		_set_property(df.fieldname, "hidden", "1", "Check")


def _hide_clutter_fields():
	for fieldname in HIDE_FIELDS:
		_set_property(fieldname, "hidden", "1", "Check")


# --------------------------------------------------------------------------- #
# 4. Label, deskripsi, banner intro                                           #
# --------------------------------------------------------------------------- #
def _style_sections_and_table():
	_set_property(TABLE, "label", "", "Data")
	_set_property(TABLE, "description", "", "Text")
	_set_property(KOMP_SECTION, "label", "Komponen Gaji", "Data")
	_set_property(KOMP_SECTION, "description", KOMP_DESC, "Text")
	_set_property(PERIODE_SECTION, "label", "Periode Kontrak", "Data")
	_set_property(PAYROLL_SECTION, "label", "Detail Payroll", "Data")
	# Banner biru sudah dirender client script -> intro field disembunyikan.
	if _exists(INTRO):
		_set_property(INTRO, "hidden", "1", "Check")


def _set_grid_columns():
	_set_child_columns("salary_component", 7)
	_set_child_columns("amount", 3)


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _exists(fieldname):
	return bool(frappe.db.exists("Custom Field", {"dt": PARENT, "fieldname": fieldname}))


def _upsert(fieldname, fieldtype, insert_after, label="", description=""):
	if insert_after and not _field_in_meta(insert_after):
		insert_after = "salary_structure"  # fallback aman
	payload = {
		"fieldtype": fieldtype,
		"insert_after": insert_after,
		"label": label,
		"description": description,
		"collapsible": 0,
	}
	existing = frappe.db.get_value("Custom Field", {"dt": PARENT, "fieldname": fieldname}, "name")
	if existing:
		frappe.db.set_value("Custom Field", existing, payload, update_modified=False)
		return
	frappe.get_doc(
		{"doctype": "Custom Field", "dt": PARENT, "fieldname": fieldname, **payload}
	).insert(ignore_permissions=True)


def _field_in_meta(fieldname):
	return any(f.fieldname == fieldname for f in frappe.get_meta(PARENT).fields)


def _set_property(fieldname, prop, value, property_type):
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


def _set_child_columns(fieldname, columns):
	if frappe.db.exists("DocField", {"parent": CHILD, "fieldname": fieldname}):
		frappe.db.set_value(
			"DocField",
			{"parent": CHILD, "fieldname": fieldname},
			"columns",
			columns,
			update_modified=False,
		)