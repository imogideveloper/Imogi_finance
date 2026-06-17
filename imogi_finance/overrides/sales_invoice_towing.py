import json

import frappe
from erpnext.accounts.party import get_due_date
from erpnext.controllers.accounts_controller import get_payment_terms
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate, today

DEFAULT_TOWING_ITEM = "JASA-TOWING-001"
BILLABLE_DO_STATUSES = ("Done",)


def is_billable_do_status(status: str | None) -> bool:
	return status in BILLABLE_DO_STATUSES


def _billable_status_sql() -> str:
	return ", ".join(f"'{status}'" for status in BILLABLE_DO_STATUSES)


def _get_income_account(company: str) -> str | None:
	return (
		frappe.db.get_value(
			"Account",
			{"account_name": "Sales", "company": company, "root_type": "Income"},
			"name",
		)
		or frappe.get_cached_value("Company", company, "default_income_account")
	)


def _get_cost_center(company: str) -> str | None:
	return frappe.get_cached_value("Company", company, "cost_center")


def _resolve_payment_terms_template(
	sales_orders: list[str] | None = None,
	*,
	current_template: str | None = None,
) -> str | None:
	if current_template:
		return current_template

	for so_name in sales_orders or []:
		template_name = frappe.db.get_value("Sales Order", so_name, "payment_terms_template")
		if template_name:
			return template_name

	return None


def _build_payment_schedule(
	template_name: str,
	*,
	posting_date,
	grand_total=0,
	base_grand_total=0,
) -> list[dict]:
	schedule = get_payment_terms(
		template_name,
		posting_date=posting_date,
		grand_total=flt(grand_total),
		base_grand_total=flt(base_grand_total),
	)
	return schedule or []


def _due_date_from_schedule(schedule: list[dict], fallback=None):
	due_dates = [row.get("due_date") for row in schedule or [] if row.get("due_date")]
	if due_dates:
		return max(getdate(d) for d in due_dates)
	return fallback


def _resolve_payment_terms(
	customer: str,
	company: str,
	sales_orders: list[str],
	*,
	posting_date=None,
	payment_terms_template: str | None = None,
	grand_total=0,
	base_grand_total=0,
) -> dict:
	"""Ambil payment terms dari SO / SI dan hitung due date + payment schedule."""
	posting_date = getdate(posting_date or today())
	template_name = _resolve_payment_terms_template(
		sales_orders,
		current_template=payment_terms_template,
	)

	schedule: list[dict] = []
	if template_name:
		schedule = _build_payment_schedule(
			template_name,
			posting_date=posting_date,
			grand_total=grand_total,
			base_grand_total=base_grand_total,
		)

	due_date = _due_date_from_schedule(schedule)
	if not due_date and customer and company:
		due_date = get_due_date(
			posting_date,
			"Customer",
			customer,
			company=company,
			template_name=template_name,
		)

	return {
		"payment_terms_template": template_name,
		"due_date": due_date,
		"payment_schedule": schedule,
	}


def _apply_payment_terms_to_doc(doc, sales_orders: list[str]) -> None:
	if not doc.customer or not doc.company or not sales_orders:
		return

	terms = _resolve_payment_terms(
		doc.customer,
		doc.company,
		sales_orders,
		posting_date=doc.posting_date,
		payment_terms_template=doc.get("payment_terms_template"),
		grand_total=doc.get("rounded_total") or doc.get("grand_total"),
		base_grand_total=doc.get("base_rounded_total") or doc.get("base_grand_total"),
	)

	if terms.get("payment_terms_template"):
		doc.payment_terms_template = terms["payment_terms_template"]

	if terms.get("payment_schedule"):
		doc.set("payment_schedule", [])
		for row in terms["payment_schedule"]:
			doc.append("payment_schedule", row)

	if terms.get("due_date"):
		doc.due_date = terms["due_date"]


def get_towing_print_payment_info(doc) -> dict:
	"""Resolve payment terms and due date for towing invoice print/PDF."""
	sales_orders = list(
		dict.fromkeys(
			item.sales_order for item in (doc.get("items") or []) if item.get("sales_order")
		)
	)

	if doc.get("payment_schedule"):
		due_dates = [row.due_date for row in doc.payment_schedule if row.get("due_date")]
		if due_dates:
			return {
				"payment_terms_template": doc.get("payment_terms_template"),
				"due_date": max(getdate(d) for d in due_dates),
			}

	terms = _resolve_payment_terms(
		doc.customer,
		doc.company,
		sales_orders,
		posting_date=doc.get("posting_date"),
		payment_terms_template=doc.get("payment_terms_template"),
		grand_total=doc.get("rounded_total") or doc.get("grand_total"),
		base_grand_total=doc.get("base_rounded_total") or doc.get("base_grand_total"),
	)
	return {
		"payment_terms_template": terms.get("payment_terms_template"),
		"due_date": terms.get("due_date"),
	}


@frappe.whitelist()
def get_towing_payment_info(
	customer,
	company,
	sales_orders,
	posting_date=None,
	payment_terms_template=None,
	grand_total=None,
	base_grand_total=None,
):
	"""Return payment terms, schedule, and due date for towing SI."""
	if isinstance(sales_orders, str):
		sales_orders = json.loads(sales_orders)

	return _resolve_payment_terms(
		customer,
		company,
		[so for so in dict.fromkeys(sales_orders or []) if so],
		posting_date=posting_date,
		payment_terms_template=payment_terms_template,
		grand_total=grand_total,
		base_grand_total=base_grand_total,
	)


def _build_do_item_map(sales_order: str) -> dict[str, str]:
	rows = frappe.get_all(
		"SO Towing Kendaraan",
		filters={"parent": sales_order},
		fields=["delivery_order", "so_item_code"],
		order_by="idx asc",
	)
	return {row.delivery_order: row.so_item_code for row in rows if row.delivery_order}


def _get_billable_dos_for_so(sales_order: str, *, exclude_invoiced: bool = True) -> list[frappe._dict]:
	do_list = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"sales_order": sales_order,
			"status": ["in", list(BILLABLE_DO_STATUSES)],
			"docstatus": 1,
		},
		fields=_delivery_order_fields(),
		order_by="tanggal_do asc, name asc",
	)
	if exclude_invoiced:
		do_list = [do for do in do_list if not do.get("sales_invoice")]
	return do_list


def _delivery_order_fields() -> list[str]:
	return [
		"name",
		"docstatus",
		"nomor_rangka",
		"nomor_mesin",
		"nomor_polisi",
		"tipe_kendaraan",
		"merk_kendaraan",
		"lokasi_pickup",
		"lokasi_tujuan",
		"harga_jasa",
		"sales_order",
		"sales_invoice",
		"customer",
		"customer_name",
		"status",
		"tanggal_do",
	]


def _get_delivery_order(do_name: str) -> frappe._dict | None:
	return frappe.db.get_value(
		"Delivery Order Towing",
		do_name,
		_delivery_order_fields(),
		as_dict=True,
	)


def extract_delivery_order_from_item(item) -> str | None:
	description = (item.get("description") if isinstance(item, dict) else item.description) or ""
	lines = [line.strip() for line in description.strip().split("\n") if line.strip()]
	if lines and lines[-1].startswith("DO-TOW"):
		return lines[-1]
	return None


def extract_delivery_orders_from_doc(doc) -> list[str]:
	do_names = []
	for item in doc.get("items") or []:
		do_name = extract_delivery_order_from_item(item)
		if do_name:
			do_names.append(do_name)
	return list(dict.fromkeys(do_names))


def _build_si_item_from_do(
	do: frappe._dict,
	*,
	sales_order: str,
	do_item_map: dict[str, str],
	income_account: str | None,
	cost_center: str | None,
) -> dict:
	nomor_rangka = do.get("nomor_rangka") or do.get("nomor_polisi") or "N/A"
	tipe = do.get("tipe_kendaraan") or ""
	merk = do.get("merk_kendaraan") or ""
	kendaraan = f"{merk} {tipe}".strip() or "Kendaraan"
	rute = f"{do.get('lokasi_pickup') or '-'} → {do.get('lokasi_tujuan') or '-'}"
	item_code = do_item_map.get(do.name) or DEFAULT_TOWING_ITEM
	description = f"Jasa Towing - {nomor_rangka}\n{kendaraan} | {rute}\n{do.name}"

	return {
		"item_code": item_code,
		"item_name": f"Jasa Towing - {nomor_rangka}",
		"description": description,
		"qty": 1,
		"rate": flt(do.get("harga_jasa") or 0),
		"uom": "Nos",
		"income_account": income_account,
		"cost_center": cost_center,
		"conversion_factor": 1,
		"sales_order": sales_order,
	}


def build_towing_invoice_items(
	sales_orders: list[str],
	company: str,
	*,
	exclude_invoiced: bool = True,
) -> dict:
	"""Build Sales Invoice item rows from Done DO Towing across one or more SO."""
	if isinstance(sales_orders, str):
		sales_orders = json.loads(sales_orders)

	sales_orders = [so for so in dict.fromkeys(sales_orders or []) if so]
	if not sales_orders:
		frappe.throw(_("Pilih minimal 1 Sales Order."))
	if not company:
		frappe.throw(_("Company wajib diisi pada Sales Invoice."))

	income_account = _get_income_account(company)
	cost_center = _get_cost_center(company)

	items: list[dict] = []
	skipped: list[dict] = []
	so_summaries: list[dict] = []

	for sales_order in sales_orders:
		so = frappe.db.get_value(
			"Sales Order",
			sales_order,
			["name", "customer", "company", "docstatus"],
			as_dict=True,
		)
		if not so or so.docstatus != 1:
			skipped.append(
				{"sales_order": sales_order, "reason": _("Sales Order belum submitted atau tidak ditemukan.")}
			)
			continue
		if so.company != company:
			skipped.append(
				{
					"sales_order": sales_order,
					"reason": _("Company SO berbeda dengan Sales Invoice."),
				}
			)
			continue

		do_item_map = _build_do_item_map(sales_order)
		do_list = _get_billable_dos_for_so(sales_order, exclude_invoiced=exclude_invoiced)

		if not do_list:
			all_billable = frappe.db.count(
				"Delivery Order Towing",
				{
					"sales_order": sales_order,
					"status": ["in", list(BILLABLE_DO_STATUSES)],
					"docstatus": 1,
				},
			)
			if all_billable:
				skipped.append(
					{
						"sales_order": sales_order,
						"reason": _("Semua DO billable sudah punya Sales Invoice."),
					}
				)
			else:
				skipped.append(
					{
						"sales_order": sales_order,
						"reason": _("Belum ada DO Towing yang siap ditagih."),
					}
				)
			continue

		for do in do_list:
			items.append(
				_build_si_item_from_do(
					do,
					sales_order=sales_order,
					do_item_map=do_item_map,
					income_account=income_account,
					cost_center=cost_center,
				)
			)

		so_summaries.append(
			{
				"sales_order": sales_order,
				"customer": so.customer,
				"do_count": len(do_list),
			}
		)

	if not items:
		frappe.throw(
			_("Tidak ada DO Towing yang bisa ditagih dari Sales Order yang dipilih."),
			title=_("Tidak Ada Data Towing"),
		)

	customers = {row["customer"] for row in so_summaries}
	if len(customers) > 1:
		frappe.throw(
			_("Sales Order yang dipilih harus dari customer yang sama."),
			title=_("Customer Berbeda"),
		)

	customer = next(iter(customers), None)
	payment_meta = (
		_resolve_payment_terms(customer, company, sales_orders)
		if customer
		else {"payment_terms_template": None, "due_date": None, "payment_schedule": []}
	)

	return {
		"items": items,
		"customer": customer,
		"so_summaries": so_summaries,
		"skipped": skipped,
		"do_count": len(items),
		"payment_terms_template": payment_meta.get("payment_terms_template"),
		"due_date": payment_meta.get("due_date"),
		"payment_schedule": payment_meta.get("payment_schedule") or [],
	}


def build_towing_invoice_items_from_delivery_orders(
	delivery_orders: list[str],
	company: str,
	*,
	exclude_invoiced: bool = True,
) -> dict:
	"""Build Sales Invoice item rows from selected Delivery Order Towing."""
	if isinstance(delivery_orders, str):
		delivery_orders = json.loads(delivery_orders)

	delivery_orders = [do_name for do_name in dict.fromkeys(delivery_orders or []) if do_name]
	if not delivery_orders:
		frappe.throw(_("Pilih minimal 1 Delivery Order Towing."))
	if not company:
		frappe.throw(_("Company wajib diisi pada Sales Invoice."))

	income_account = _get_income_account(company)
	cost_center = _get_cost_center(company)

	items: list[dict] = []
	skipped: list[dict] = []
	do_summaries: list[dict] = []
	sales_orders: list[str] = []

	for do_name in delivery_orders:
		do = _get_delivery_order(do_name)
		if not do or do.docstatus != 1:
			skipped.append(
				{
					"delivery_order": do_name,
					"reason": _("Delivery Order belum submitted atau tidak ditemukan."),
				}
			)
			continue

		if not is_billable_do_status(do.status):
			skipped.append(
				{
					"delivery_order": do_name,
					"reason": _("Status DO harus Done untuk ditagih (saat ini: {0}).").format(
						do.status or "-"
					),
				}
			)
			continue

		if exclude_invoiced and do.get("sales_invoice"):
			skipped.append(
				{
					"delivery_order": do_name,
					"reason": _("DO sudah ditagih di {0}.").format(do.sales_invoice),
				}
			)
			continue

		so = frappe.db.get_value(
			"Sales Order",
			do.sales_order,
			["name", "customer", "company", "docstatus"],
			as_dict=True,
		)
		if not so or so.docstatus != 1:
			skipped.append(
				{
					"delivery_order": do_name,
					"reason": _("Sales Order terkait belum submitted atau tidak ditemukan."),
				}
			)
			continue
		if so.company != company:
			skipped.append(
				{
					"delivery_order": do_name,
					"reason": _("Company SO berbeda dengan Sales Invoice."),
				}
			)
			continue

		do_item_map = _build_do_item_map(do.sales_order)
		items.append(
			_build_si_item_from_do(
				do,
				sales_order=do.sales_order,
				do_item_map=do_item_map,
				income_account=income_account,
				cost_center=cost_center,
			)
		)
		do_summaries.append(
			{
				"delivery_order": do_name,
				"sales_order": do.sales_order,
				"customer": so.customer,
				"status": do.status,
			}
		)
		sales_orders.append(do.sales_order)

	if not items:
		frappe.throw(
			_("Tidak ada DO Towing yang bisa ditagih dari pilihan Anda."),
			title=_("Tidak Ada Data Towing"),
		)

	customers = {row["customer"] for row in do_summaries}
	if len(customers) > 1:
		frappe.throw(
			_("Delivery Order yang dipilih harus dari customer yang sama."),
			title=_("Customer Berbeda"),
		)

	customer = next(iter(customers), None)
	unique_sales_orders = list(dict.fromkeys(sales_orders))
	payment_meta = (
		_resolve_payment_terms(customer, company, unique_sales_orders)
		if customer
		else {"payment_terms_template": None, "due_date": None, "payment_schedule": []}
	)

	return {
		"items": items,
		"customer": customer,
		"do_summaries": do_summaries,
		"skipped": skipped,
		"do_count": len(items),
		"delivery_orders": [row["delivery_order"] for row in do_summaries],
		"payment_terms_template": payment_meta.get("payment_terms_template"),
		"due_date": payment_meta.get("due_date"),
		"payment_schedule": payment_meta.get("payment_schedule") or [],
	}


@frappe.whitelist()
def get_towing_invoice_items(
	delivery_orders=None,
	sales_orders=None,
	company=None,
	customer=None,
	exclude_invoiced=1,
	posting_date=None,
):
	"""Return SI item rows for bulk towing billing from Delivery Orders."""
	if delivery_orders:
		result = build_towing_invoice_items_from_delivery_orders(
			delivery_orders,
			company,
			exclude_invoiced=frappe.utils.cint(exclude_invoiced),
		)
	elif sales_orders:
		result = build_towing_invoice_items(
			sales_orders,
			company,
			exclude_invoiced=frappe.utils.cint(exclude_invoiced),
		)
		result["delivery_orders"] = extract_delivery_orders_from_items(result.get("items") or [])
	else:
		frappe.throw(_("Pilih minimal 1 Delivery Order Towing."))

	if customer and result.get("customer") and customer != result["customer"]:
		frappe.throw(
			_("Customer pada Sales Invoice tidak sama dengan Delivery Order yang dipilih."),
			title=_("Customer Tidak Cocok"),
		)

	if result.get("customer"):
		so_list = list(
			dict.fromkeys(row.get("sales_order") for row in result.get("do_summaries") or [])
		) or (
			sales_orders if isinstance(sales_orders, list) else json.loads(sales_orders or "[]")
		)
		payment_meta = _resolve_payment_terms(
			result["customer"],
			company,
			so_list,
			posting_date=posting_date,
		)
		result.update(payment_meta)

	return result


def extract_delivery_orders_from_items(items: list[dict]) -> list[str]:
	do_names = []
	for item in items or []:
		do_name = extract_delivery_order_from_item(item)
		if do_name:
			do_names.append(do_name)
	return list(dict.fromkeys(do_names))


@frappe.whitelist()
def debug_towing_billing_eligibility(delivery_order=None, sales_order=None, company=None, customer=None):
	"""Cek kenapa DO/SO tidak muncul di dialog tarik DO towing."""
	if delivery_order:
		return _debug_delivery_order_eligibility(delivery_order, company=company, customer=customer)
	return _debug_sales_order_eligibility(sales_order, company=company, customer=customer)


def _debug_delivery_order_eligibility(delivery_order, company=None, customer=None):
	reasons = []
	do = _get_delivery_order(delivery_order)
	if not do:
		return {"eligible": False, "reasons": [_("Delivery Order tidak ditemukan.")]}
	if do.docstatus != 1:
		reasons.append(_("Delivery Order belum Submitted."))
	if not is_billable_do_status(do.status):
		reasons.append(
			_("Status DO harus Done untuk ditagih (saat ini: {0}).").format(do.status or "-")
		)
	if do.get("sales_invoice"):
		reasons.append(_("DO sudah ditagih di {0}.").format(do.sales_invoice))

	so = frappe.db.get_value(
		"Sales Order",
		do.sales_order,
		["name", "docstatus", "company", "customer"],
		as_dict=True,
	)
	if not so:
		reasons.append(_("Sales Order terkait tidak ditemukan."))
	elif so.docstatus != 1:
		reasons.append(_("Sales Order belum Submitted."))
	elif company and so.company != company:
		reasons.append(
			_("Company SO ({0}) berbeda dengan Sales Invoice ({1}).").format(
				so.company, company
			)
		)
	elif customer and so.customer != customer:
		reasons.append(
			_("Customer DO ({0}) berbeda dengan Sales Invoice ({1}).").format(
				so.customer, customer
			)
		)

	return {
		"eligible": not reasons,
		"delivery_order": do,
		"reasons": reasons or [_("DO eligible — seharusnya muncul di dialog.")],
	}


def _debug_sales_order_eligibility(sales_order, company=None, customer=None):
	reasons = []
	so = frappe.db.get_value(
		"Sales Order",
		sales_order,
		["name", "docstatus", "company", "customer"],
		as_dict=True,
	)
	if not so:
		return {"eligible": False, "reasons": [_("Sales Order tidak ditemukan.")]}
	if so.docstatus != 1:
		reasons.append(_("Sales Order belum Submitted."))
	if company and so.company != company:
		reasons.append(
			_("Company SO ({0}) berbeda dengan Sales Invoice ({1}).").format(
				so.company, company
			)
		)
	if customer and so.customer != customer:
		reasons.append(
			_("Customer SO ({0}) berbeda dengan Sales Invoice ({1}).").format(
				so.customer, customer
			)
		)

	billable_dos = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"sales_order": sales_order,
			"docstatus": 1,
			"status": ["in", list(BILLABLE_DO_STATUSES)],
		},
		fields=["name", "sales_invoice", "status"],
	)
	uninvoiced = [row.name for row in billable_dos if not row.get("sales_invoice")]
	if not billable_dos:
		reasons.append(_("Belum ada DO Towing yang siap ditagih."))
	elif not uninvoiced:
		reasons.append(_("Semua DO billable sudah punya Sales Invoice."))

	return {
		"eligible": not reasons,
		"sales_order": so,
		"billable_do_count": len(billable_dos),
		"uninvoiced_do": uninvoiced,
		"reasons": reasons or [_("SO eligible — seharusnya muncul di dialog.")],
	}


def _eligible_do_sql(company, customer=None, txt=None):
	conditions = [
		"do.docstatus = 1",
		f"do.status IN ({_billable_status_sql()})",
		"IFNULL(do.sales_invoice, '') = ''",
		"so.docstatus = 1",
		"so.company = %s",
	]
	values: list = [company]

	if customer:
		conditions.append("do.customer = %s")
		values.append(customer)
	if txt:
		conditions.append(
			"(do.name LIKE %s OR do.nomor_polisi LIKE %s OR do.customer_name LIKE %s "
			"OR do.sales_order LIKE %s OR so.company LIKE %s)"
		)
		values.extend([f"%{txt}%", f"%{txt}%", f"%{txt}%", f"%{txt}%", f"%{txt}%"])

	return conditions, values


@frappe.whitelist()
def list_eligible_towing_delivery_orders(company, customer=None):
	"""List DO towing yang bisa ditagih + hint kalau kosong."""
	if not company:
		frappe.throw(_("Company wajib diisi."))

	conditions, values = _eligible_do_sql(company, customer=customer)
	where_clause = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			do.name,
			do.nomor_polisi,
			do.customer,
			do.customer_name,
			do.tanggal_do,
			do.status,
			do.sales_order,
			so.company
		FROM `tabDelivery Order Towing` do
		INNER JOIN `tabSales Order` so ON so.name = do.sales_order
		WHERE {where_clause}
		ORDER BY do.tanggal_do DESC, do.name DESC
		LIMIT 100
		""",
		tuple(values),
		as_dict=True,
	)

	hints = []
	if not rows:
		hints.append(
			_(
				"Tidak ada DO Towing berstatus Done yang siap ditagih untuk company {0}."
			).format(company)
		)
		if customer:
			hints.append(
				_("Filter customer aktif: {0}. Coba kosongkan Customer di SI lalu tarik ulang.").format(
					customer
				)
			)

		candidate_dos = frappe.db.sql(
			f"""
			SELECT do.name
			FROM `tabDelivery Order Towing` do
			INNER JOIN `tabSales Order` so ON so.name = do.sales_order
			WHERE do.docstatus = 1
			  AND do.status IN ({_billable_status_sql()})
			  AND IFNULL(do.sales_invoice, '') = ''
			  AND so.docstatus = 1
			LIMIT 10
			""",
			as_dict=True,
		)
		for row in candidate_dos:
			check = _debug_delivery_order_eligibility(
				row.name, company=company, customer=customer
			)
			if not check.get("eligible"):
				hints.append(f"{row.name}: {'; '.join(check.get('reasons') or [])}")

	return {"delivery_orders": rows, "hints": hints}


@frappe.whitelist()
def list_eligible_towing_sales_orders(company, customer=None):
	"""Backward-compatible alias — gunakan list_eligible_towing_delivery_orders."""
	result = list_eligible_towing_delivery_orders(company, customer=customer)
	result["sales_orders"] = result.get("delivery_orders") or []
	return result


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_towing_delivery_order_query(
	doctype, txt, searchfield, start, page_len, filters, as_dict=False, **kwargs
):
	"""Link query: DO towing yang siap ditagih."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	company = filters.get("company")
	customer = filters.get("customer")

	if not company:
		return []

	conditions, values = _eligible_do_sql(company, customer=customer, txt=txt or None)
	where_clause = " AND ".join(conditions)
	values.extend([cint(start), cint(page_len)])

	rows = frappe.db.sql(
		f"""
		SELECT
			do.name,
			so.company,
			do.nomor_polisi,
			do.customer_name,
			do.tanggal_do,
			do.status,
			do.sales_order
		FROM `tabDelivery Order Towing` do
		INNER JOIN `tabSales Order` so ON so.name = do.sales_order
		WHERE {where_clause}
		ORDER BY do.tanggal_do DESC, do.name DESC
		LIMIT %s, %s
		""",
		tuple(values),
		as_dict=True,
	)

	for row in rows:
		if row.get("tanggal_do"):
			row["tanggal_do"] = formatdate(row["tanggal_do"])

	return rows


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_towing_sales_order_query(doctype, txt, searchfield, start, page_len, filters):
	"""Backward-compatible alias."""
	return get_towing_delivery_order_query(
		doctype, txt, searchfield, start, page_len, filters
	)


def _items_already_towing_expanded(doc) -> bool:
	if not doc.get("items"):
		return False
	return all(
		(item.item_name or "").startswith("Jasa Towing")
		or "Jasa Towing" in (item.description or "")
		for item in doc.items
	)


def before_insert(doc, method):
	if not doc.get("items"):
		return

	sales_orders = list(
		dict.fromkeys(item.sales_order for item in doc.items if item.get("sales_order"))
	)
	if not sales_orders:
		return

	if not _items_already_towing_expanded(doc):
		try:
			result = build_towing_invoice_items(
				sales_orders,
				doc.company,
				exclude_invoiced=True,
			)
		except frappe.ValidationError:
			raise
		except Exception:
			return

		doc.set("items", [])
		for row in result["items"]:
			doc.append("items", row)

		frappe.msgprint(
			_("✅ {0} baris towing di-generate dari {1} Sales Order.").format(
				result["do_count"], len(result["so_summaries"])
			),
			indicator="green",
		)

	_apply_payment_terms_to_doc(doc, sales_orders)


def validate_towing_payment_terms(doc, method=None):
	"""Pastikan due date mengikuti payment terms saat SI towing disimpan."""
	if not _items_already_towing_expanded(doc):
		return
	sales_orders = list(
		dict.fromkeys(item.sales_order for item in doc.items if item.get("sales_order"))
	)
	_apply_payment_terms_to_doc(doc, sales_orders)


def link_towing_delivery_orders_on_submit(doc, method=None):
	"""Tandai DO sebagai Done dan link ke Sales Invoice setelah submit."""
	if doc.docstatus != 1 or not _items_already_towing_expanded(doc):
		return

	from frappe.utils import now_datetime

	for do_name in extract_delivery_orders_from_doc(doc):
		updates = {
			"sales_invoice": doc.name,
			"status": "Done",
		}
		if not frappe.db.get_value("Delivery Order Towing", do_name, "waktu_done"):
			updates["waktu_done"] = now_datetime()
		frappe.db.set_value(
			"Delivery Order Towing",
			do_name,
			updates,
			update_modified=True,
		)
