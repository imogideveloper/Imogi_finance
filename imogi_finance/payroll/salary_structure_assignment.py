"""Salary Structure Assignment: child table komponen gaji (Odoo-style)."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate, strip_html, today

# Map nama komponen ke field standar/custom SSA (untuk formula slip gaji).
COMPONENT_FIELD_MAP = {
	"gaji pokok": "base",
	"tunjangan makan": "meal_allowance",
	"tunjangan transport": "transport_allowance",
	"tunjangan operational": "tunjangan_operational",
}

BPJS_BASE_EXCLUDED_COMPONENTS = {
	"bonus",
	"thr",
	"lembur",
	"piket",
}

COMPONENT_TABLE_FIELD = "salary_component_amounts"
TRACKING_PREVIOUS_FIELD = "previous_assignment_contract"
TRACKING_RENEWED_BY_FIELD = "renewed_by_assignment_contract"
CONTRACT_TYPE_FIELD = "assignment_contract_type"
HR_NOTIFICATION_ROLES = ("HR Manager", "HR User")
EXPIRING_SOON_DAYS = 30
LEGACY_EXPIRY_REMINDER_KEYS = ("h-30", "h-14", "h-7")


def sync_assignment_component_fields(doc):
	"""Salin baris child table ke field scalar agar formula HRMS/payroll_indonesia tetap jalan."""
	rows = doc.get(COMPONENT_TABLE_FIELD) or []
	if not rows:
		return

	# Reset field yang diisi dari tabel (hindari nilai lama tertinggal).
	for fieldname in set(COMPONENT_FIELD_MAP.values()):
		if doc.meta.has_field(fieldname):
			doc.set(fieldname, 0)

	seen_components = set()
	for row in rows:
		if not row.salary_component:
			continue
		if row.salary_component in seen_components:
			frappe.throw(
				_("Komponen {0} sudah ada di tabel. Satu komponen hanya sekali.").format(
					frappe.bold(row.salary_component)
				)
			)
		seen_components.add(row.salary_component)

		key = (row.salary_component or "").strip().lower()
		fieldname = COMPONENT_FIELD_MAP.get(key)
		if fieldname and doc.meta.has_field(fieldname):
			doc.set(fieldname, flt(row.amount))



def resolve_assignment_doc(assignment):
	"""Muat SSA lengkap (termasuk child table Komponen Gaji) untuk evaluasi formula."""
	if not assignment:
		return None
	if isinstance(assignment, str):
		return frappe.get_doc("Salary Structure Assignment", assignment)
	if hasattr(assignment, "get") and assignment.get("salary_component_amounts"):
		return assignment
	name = assignment.get("name") if isinstance(assignment, dict) else getattr(assignment, "name", None)
	if name and frappe.db.exists("Salary Structure Assignment", name):
		return frappe.get_doc("Salary Structure Assignment", name)
	return frappe._dict(assignment) if isinstance(assignment, dict) else assignment


def get_assignment_formula_context(assignment) -> dict:
	"""Bangun variabel formula dari child table (+ field scalar legacy)."""
	assignment = resolve_assignment_doc(assignment)
	if not assignment:
		return {}

	context: dict = {}
	rows = assignment.get("salary_component_amounts") or []
	bpjs_base = 0.0

	if rows:
		for row in rows:
			if not row.salary_component:
				continue
			amount = flt(row.amount)
			key = (row.salary_component or "").strip().lower()
			if key not in BPJS_BASE_EXCLUDED_COMPONENTS:
				bpjs_base += amount
			fieldname = COMPONENT_FIELD_MAP.get(key)
			if fieldname:
				context[fieldname] = amount
			abbr = frappe.db.get_value(
				"Salary Component", row.salary_component, "salary_component_abbr"
			)
			if abbr:
				context[abbr] = amount
			# fallback: snake_case dari nama komponen
			context[key.replace(" ", "_")] = amount
	else:
		for fieldname in COMPONENT_FIELD_MAP.values():
			if assignment.get(fieldname) is not None:
				context[fieldname] = flt(assignment.get(fieldname))

	# Komponen yang tidak ada di SSA (mis. tanpa tunjangan operational) → 0 agar formula tidak error.
	for fieldname in set(COMPONENT_FIELD_MAP.values()):
		if fieldname not in context and assignment.get(fieldname) is not None:
			context[fieldname] = flt(assignment.get(fieldname))
		context.setdefault(fieldname, 0)

	if not bpjs_base:
		bpjs_base = (
			flt(context.get("base"))
			+ flt(context.get("meal_allowance"))
			+ flt(context.get("transport_allowance"))
			+ flt(context.get("tunjangan_operational"))
		)
	context["bpjs_base"] = bpjs_base or flt(context.get("base"))

	return context


CONTRACT_PERIOD_FIELDS = ("from_date", "end_date")


def validate_salary_structure_assignment(doc, method=None):
	validate_submitted_component_contract_unchanged(doc)
	validate_submitted_contract_period_unchanged(doc)
	validate_assignment_contract_chain(doc)
	validate_change_reason_for_contract_change(doc)
	sync_assignment_component_fields(doc)
	validate_assignment_end_date(doc)
	validate_assignment_period_overlap(doc)
	sync_assignment_status(doc)


def update_submitted_salary_structure_assignment(doc, method=None):
	validate_submitted_component_contract_unchanged(doc)
	validate_submitted_contract_period_unchanged(doc)
	validate_change_reason_for_contract_change(doc)
	validate_assignment_end_date(doc)
	validate_assignment_period_overlap(doc)
	if not doc.meta.has_field("status"):
		return

	status = get_assignment_status(doc.get("end_date"), doc.get(TRACKING_RENEWED_BY_FIELD))
	if doc.get("status") != status:
		frappe.db.set_value(
			"Salary Structure Assignment",
			doc.name,
			"status",
			status,
			update_modified=False,
		)


def handle_salary_structure_assignment_submit(doc, method=None):
	"""Hubungkan contract baru ke contract lama setelah submit."""
	close_previous_assignment_contract(doc)


def validate_submitted_contract_period_unchanged(doc):
	"""From/End Date pada contract submitted tidak bisa diubah manual."""
	if doc.get("docstatus") != 1 or doc.is_new():
		return

	old_doc = doc.get_doc_before_save()
	if not old_doc or old_doc.get("docstatus") != 1:
		return

	for fieldname in CONTRACT_PERIOD_FIELDS:
		if not doc.meta.has_field(fieldname):
			continue
		if _assignment_date_value(doc.get(fieldname)) == _assignment_date_value(old_doc.get(fieldname)):
			continue
		frappe.throw(
			_(
				"{0} pada Assignment Contract yang sudah Submitted tidak bisa diubah. "
				"Gunakan <b>Buat Contract Baru</b> atau <b>Perpanjang Contract</b> untuk perubahan periode."
			).format(frappe.bold(doc.meta.get_label(fieldname)))
		)


def _assignment_date_value(value):
	if not value:
		return None
	return getdate(value)


def validate_submitted_component_contract_unchanged(doc):
	"""Komponen gaji di contract submitted immutable; perubahan harus lewat contract baru."""
	if doc.get("docstatus") != 1 or doc.is_new():
		return

	old_doc = doc.get_doc_before_save()
	if not old_doc or old_doc.get("docstatus") != 1:
		return

	if _component_rows_signature(doc) != _component_rows_signature(old_doc):
		frappe.throw(
			_(
				"Komponen Gaji pada Assignment Contract yang sudah Submitted tidak bisa diubah. "
				"Buat Assignment Contract baru untuk perubahan komponen gaji."
			)
		)

	for fieldname in COMPONENT_FIELD_MAP.values():
		if not doc.meta.has_field(fieldname):
			continue
		if flt(doc.get(fieldname)) != flt(old_doc.get(fieldname)):
			frappe.throw(
				_(
					"Field {0} berasal dari Komponen Gaji dan tidak bisa diubah pada contract submitted. "
					"Buat Assignment Contract baru untuk perubahan gaji."
				).format(frappe.bold(doc.meta.get_label(fieldname)))
			)


def validate_assignment_contract_chain(doc):
	if not (doc.meta.has_field(TRACKING_PREVIOUS_FIELD) and doc.get(TRACKING_PREVIOUS_FIELD)):
		return

	previous_name = doc.get(TRACKING_PREVIOUS_FIELD)
	if previous_name == doc.name:
		frappe.throw(_("Previous Assignment Contract tidak boleh sama dengan contract saat ini."))
	if not frappe.db.exists("Salary Structure Assignment", previous_name):
		frappe.throw(_("Previous Assignment Contract {0} tidak ditemukan.").format(previous_name))

	previous = frappe.get_doc("Salary Structure Assignment", previous_name)
	if previous.employee != doc.employee:
		frappe.throw(_("Previous Assignment Contract harus untuk employee yang sama."))
	if previous.salary_structure != doc.salary_structure:
		frappe.throw(_("Previous Assignment Contract harus memakai Salary Structure yang sama."))
	if doc.from_date and previous.from_date and getdate(doc.from_date) <= getdate(previous.from_date):
		frappe.throw(_("From Date contract baru harus lebih besar dari From Date contract lama."))


def validate_change_reason_for_contract_change(doc):
	if not doc.meta.has_field("change_reason"):
		return
	if doc.meta.has_field(TRACKING_PREVIOUS_FIELD) and doc.get(TRACKING_PREVIOUS_FIELD) and not doc.get("change_reason"):
		frappe.throw(_("Alasan Perubahan wajib diisi untuk perpanjangan/perubahan contract."))


def validate_assignment_end_date(doc):
	if not (doc.meta.has_field("end_date") and doc.get("end_date") and doc.get("from_date")):
		return
	if getdate(doc.end_date) < getdate(doc.from_date):
		frappe.throw(_("End Date tidak boleh lebih kecil dari From Date."))


def validate_assignment_period_overlap(doc):
	if not (doc.get("employee") and doc.get("from_date")):
		return
	if not doc.meta.has_field("end_date"):
		return

	current_start = getdate(doc.from_date)
	current_end = getdate(doc.end_date) if doc.get("end_date") else getdate("9999-12-31")
	excluded_names = [doc.name]
	if doc.meta.has_field(TRACKING_PREVIOUS_FIELD) and doc.get(TRACKING_PREVIOUS_FIELD):
		excluded_names.append(doc.get(TRACKING_PREVIOUS_FIELD))

	overlaps = frappe.db.sql(
		"""
		select name, from_date, end_date
		from `tabSalary Structure Assignment`
		where employee = %(employee)s
			and docstatus != 2
			and name not in %(excluded_names)s
			and (renewed_by_assignment_contract is null or renewed_by_assignment_contract = '')
			and from_date <= %(current_end)s
			and (end_date is null or end_date = '' or end_date >= %(current_start)s)
		order by from_date desc
		limit 1
		""",
		{
			"employee": doc.employee,
			"excluded_names": tuple(excluded_names),
			"current_start": current_start,
			"current_end": current_end,
		},
		as_dict=True,
	)
	if not overlaps:
		return

	overlap = overlaps[0]
	frappe.throw(
		_(
			"Periode Assignment Contract overlap dengan contract {0} ({1} s/d {2}). "
			"Gunakan tombol Buat Contract Baru dari contract lama, atau sesuaikan From/End Date."
		).format(
			frappe.bold(overlap.name),
			frappe.bold(overlap.from_date),
			frappe.bold(overlap.end_date or _("Tanpa End Date")),
		)
	)


def get_assignment_status(end_date=None, renewed_by=None) -> str:
	if renewed_by:
		return "Expired"
	if end_date and getdate(end_date) < getdate(today()):
		return "Expired"
	if end_date and 0 <= date_diff(getdate(end_date), getdate(today())) <= EXPIRING_SOON_DAYS:
		return "Expired Soon"
	return "Activate"


def sync_assignment_status(doc):
	if not doc.meta.has_field("status"):
		return
	doc.status = get_assignment_status(doc.get("end_date"), doc.get(TRACKING_RENEWED_BY_FIELD))


def sync_expired_salary_structure_assignments():
	"""Refresh status SSA dan buat ToDo HR untuk contract expired yang belum diperpanjang."""
	meta = frappe.get_meta("Salary Structure Assignment")
	if not (meta.has_field("end_date") and meta.has_field("status")):
		return

	fields = ["name", "employee", "salary_structure", "from_date", "end_date", "status", "docstatus"]
	if meta.has_field(TRACKING_RENEWED_BY_FIELD):
		fields.append(TRACKING_RENEWED_BY_FIELD)

	for row in frappe.get_all(
		"Salary Structure Assignment",
		filters={"docstatus": ["!=", 2]},
		fields=fields,
	):
		status = get_assignment_status(row.end_date, row.get(TRACKING_RENEWED_BY_FIELD))
		if row.status != status:
			frappe.db.set_value(
				"Salary Structure Assignment",
				row.name,
				"status",
				status,
				update_modified=False,
			)

		if row.docstatus == 1:
			notify_hr_for_assignment_contract(row, status, meta)


@frappe.whitelist()
def get_assignment_contract_renewal_defaults(source_name: str) -> dict:
	"""Data awal untuk draft Assignment Contract baru dari contract existing."""
	if not source_name:
		frappe.throw(_("Assignment Contract sumber wajib diisi."))

	source = frappe.get_doc("Salary Structure Assignment", source_name)
	if source.docstatus != 1:
		frappe.throw(_("Contract baru hanya bisa dibuat dari Assignment Contract yang sudah Submitted."))

	fields = {}
	for fieldname in _renewal_copy_fields(source):
		if source.meta.has_field(fieldname):
			fields[fieldname] = source.get(fieldname)

	fields["from_date"] = _get_next_contract_from_date(source)
	if source.meta.has_field("end_date"):
		fields["end_date"] = None
	if source.meta.has_field("status"):
		fields["status"] = "Activate"
	if source.meta.has_field(TRACKING_PREVIOUS_FIELD):
		fields[TRACKING_PREVIOUS_FIELD] = source.name
	if source.meta.has_field(CONTRACT_TYPE_FIELD):
		fields[CONTRACT_TYPE_FIELD] = ""
	if source.meta.has_field("change_reason"):
		fields["change_reason"] = ""

	return {
		"fields": fields,
		COMPONENT_TABLE_FIELD: [
			{
				"salary_component": row.salary_component,
				"amount": flt(row.amount),
			}
			for row in source.get(COMPONENT_TABLE_FIELD) or []
			if row.salary_component
		],
	}


def close_previous_assignment_contract(doc):
	if not (doc.meta.has_field(TRACKING_PREVIOUS_FIELD) and doc.get(TRACKING_PREVIOUS_FIELD)):
		return

	previous_name = doc.get(TRACKING_PREVIOUS_FIELD)
	if not frappe.db.exists("Salary Structure Assignment", previous_name):
		return

	previous = frappe.get_doc("Salary Structure Assignment", previous_name)
	updates = {}
	if previous.meta.has_field(TRACKING_RENEWED_BY_FIELD):
		updates[TRACKING_RENEWED_BY_FIELD] = doc.name
	if previous.meta.has_field("status"):
		updates["status"] = "Expired"

	if previous.meta.has_field("end_date") and doc.get("from_date"):
		new_previous_end_date = add_days(getdate(doc.from_date), -1)
		if (
			previous.get("from_date")
			and new_previous_end_date >= getdate(previous.from_date)
			and (not previous.get("end_date") or getdate(previous.end_date) >= getdate(doc.from_date))
		):
			updates["end_date"] = new_previous_end_date
			if previous.meta.has_field("status"):
				updates["status"] = "Expired"

	if updates:
		frappe.db.set_value(
			"Salary Structure Assignment",
			previous.name,
			updates,
			update_modified=False,
		)

	_add_contract_link_comment(previous.name, doc.name, is_previous=True)
	_add_contract_link_comment(doc.name, previous.name, is_previous=False)


def notify_hr_for_assignment_contract(row, status: str, meta=None):
	meta = meta or frappe.get_meta("Salary Structure Assignment")
	if _has_replacement_contract(row, meta):
		return

	days_until = date_diff(getdate(row.end_date), getdate(today())) if row.get("end_date") else None
	if status == "Expired":
		notification_key = "expired"
		priority = "High"
		description = _(
			"Assignment Contract {0} sudah Expired. "
			"Silakan perpanjang dengan membuat Assignment Contract baru."
		).format(frappe.bold(row.name))
	elif status == "Expired Soon" and days_until is not None and 0 <= days_until <= EXPIRING_SOON_DAYS:
		notification_key = "expired-soon"
		priority = "Medium"
		description = _(
			"Assignment Contract {0} akan Expired Soon dalam {1} hari. "
			"Siapkan perpanjangan dengan membuat Assignment Contract baru."
		).format(frappe.bold(row.name), frappe.bold(days_until))
	else:
		return

	for user in _get_users_with_roles(HR_NOTIFICATION_ROLES):
		if _open_contract_todo_exists(row.name, user, notification_key):
			continue
		if notification_key == "expired-soon" and _open_contract_todo_exists(
			row.name, user, LEGACY_EXPIRY_REMINDER_KEYS
		):
			continue
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"owner": user,
				"allocated_to": user,
				"assigned_by": _get_assigner_user(),
				"priority": priority,
				"status": "Open",
				"date": today(),
				"reference_type": "Salary Structure Assignment",
				"reference_name": row.name,
				"description": f"{description}<br><small>SSA Reminder: {notification_key}</small>",
			}
		).insert(ignore_permissions=True)


def _component_rows_signature(doc) -> tuple:
	return tuple(
		(row.salary_component or "", flt(row.amount))
		for row in sorted(doc.get(COMPONENT_TABLE_FIELD) or [], key=lambda item: item.idx or 0)
	)


def _renewal_copy_fields(source) -> tuple[str, ...]:
	return (
		"employee",
		"salary_structure",
		"company",
		"currency",
		"payroll_payable_account",
		"income_tax_slab",
		"base",
		"meal_allowance",
		"transport_allowance",
		"tunjangan_operational",
	)


def _get_next_contract_from_date(source):
	if source.meta.has_field("end_date") and source.get("end_date"):
		return add_days(getdate(source.end_date), 1)
	return today()


def _has_replacement_contract(row, meta) -> bool:
	if meta.has_field(TRACKING_RENEWED_BY_FIELD) and row.get(TRACKING_RENEWED_BY_FIELD):
		replacement = row.get(TRACKING_RENEWED_BY_FIELD)
		if frappe.db.exists("Salary Structure Assignment", {"name": replacement, "docstatus": 1}):
			return True

	if not (row.get("employee") and row.get("salary_structure") and row.get("from_date")):
		return False

	return bool(
		frappe.db.exists(
			"Salary Structure Assignment",
			{
				"employee": row.employee,
				"salary_structure": row.salary_structure,
				"docstatus": 1,
				"from_date": (">", row.from_date),
				"name": ("!=", row.name),
			},
		)
	)


def _get_users_with_roles(roles: tuple[str, ...]) -> list[str]:
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", roles], "parenttype": "User"},
		fields=["parent as user"],
		distinct=True,
	)
	user_names = [row.user for row in users]
	if not user_names:
		return []
	return frappe.get_all(
		"User",
		filters={"name": ["in", user_names], "enabled": 1},
		pluck="name",
	)


def _open_contract_todo_exists(contract_name: str, user: str, notification_key) -> bool:
	if not isinstance(notification_key, str):
		return any(
			_open_contract_todo_exists(contract_name, user, key)
			for key in tuple(notification_key or ())
		)

	return bool(
		frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "Salary Structure Assignment",
				"reference_name": contract_name,
				"allocated_to": user,
				"status": "Open",
				"description": ("like", f"%SSA Reminder: {notification_key}%"),
			},
			limit=1,
		)
	)


@frappe.whitelist()
def get_current_user_assignment_contract_reminders(limit: int = 5) -> list[dict]:
	user = frappe.session.user
	if not user or user == "Guest":
		return []
	if not set(frappe.get_roles(user)).intersection(HR_NOTIFICATION_ROLES):
		return []

	rows = frappe.get_all(
		"ToDo",
		filters={
			"allocated_to": user,
			"status": "Open",
			"reference_type": "Salary Structure Assignment",
			"description": ("like", "%SSA Reminder:%"),
		},
		fields=["name", "reference_name", "priority", "description", "creation"],
		order_by="creation desc",
		limit=int(limit or 5),
	)
	for row in rows:
		row.message = strip_html((row.description or "").split("SSA Reminder:", 1)[0]).strip()
	return rows


@frappe.whitelist()
def get_assignment_contract_history(employee: str, salary_structure: str | None = None) -> list[dict]:
	if not employee:
		return []

	filters = {"employee": employee, "docstatus": ["!=", 2]}

	fields = [
		"name",
		"salary_structure",
		"from_date",
		"end_date",
		"status",
		"previous_assignment_contract",
		"renewed_by_assignment_contract",
		"change_reason",
	]
	available_fields = {"name"}
	meta = frappe.get_meta("Salary Structure Assignment")
	for fieldname in fields:
		if fieldname == "name" or meta.has_field(fieldname):
			available_fields.add(fieldname)

	return frappe.get_all(
		"Salary Structure Assignment",
		filters=filters,
		fields=sorted(available_fields),
		order_by="from_date desc, creation desc",
	)


def _get_assigner_user() -> str:
	user = getattr(frappe.session, "user", None)
	return user if user and user != "Guest" else "Administrator"


def _add_contract_link_comment(reference_name: str, linked_name: str, is_previous: bool):
	try:
		if is_previous:
			content = _("Contract ini ditutup/diteruskan oleh Assignment Contract {0}.").format(
				frappe.bold(linked_name)
			)
		else:
			content = _("Contract ini dibuat sebagai perpanjangan/perubahan dari {0}.").format(
				frappe.bold(linked_name)
			)
		doc = frappe.get_doc("Salary Structure Assignment", reference_name)
		doc.add_comment("Info", content)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"Salary Structure Assignment Contract Comment Failed",
		)
