import json

import frappe
from erpnext.accounts.party import get_due_date
from erpnext.controllers.accounts_controller import get_payment_terms
from frappe import _
from frappe.utils import cint, flt, getdate, today

DEFAULT_TOWING_ITEM = "JASA-TOWING-001"


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


def _get_done_dos_for_so(sales_order: str, *, exclude_invoiced: bool = True) -> list[frappe._dict]:
	do_list = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"sales_order": sales_order,
			"status": "Done",
			"docstatus": 1,
		},
		fields=[
			"name",
			"nomor_mesin",
			"nomor_polisi",
			"tipe_kendaraan",
			"merk_kendaraan",
			"lokasi_pickup",
			"lokasi_tujuan",
			"harga_jasa",
			"sales_order",
			"sales_invoice",
		],
		order_by="tanggal_do asc, name asc",
	)
	if exclude_invoiced:
		do_list = [do for do in do_list if not do.get("sales_invoice")]
	return do_list


def _build_si_item_from_do(
	do: frappe._dict,
	*,
	sales_order: str,
	do_item_map: dict[str, str],
	income_account: str | None,
	cost_center: str | None,
) -> dict:
	nomor_mesin = do.get("nomor_mesin") or do.get("nomor_polisi") or "N/A"
	tipe = do.get("tipe_kendaraan") or ""
	merk = do.get("merk_kendaraan") or ""
	kendaraan = f"{merk} {tipe}".strip() or "Kendaraan"
	rute = f"{do.get('lokasi_pickup') or '-'} → {do.get('lokasi_tujuan') or '-'}"
	item_code = do_item_map.get(do.name) or DEFAULT_TOWING_ITEM
	description = f"Jasa Towing - {nomor_mesin}\n{kendaraan} | {rute}\n{do.name}"

	return {
		"item_code": item_code,
		"item_name": f"Jasa Towing - {nomor_mesin}",
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
		do_list = _get_done_dos_for_so(sales_order, exclude_invoiced=exclude_invoiced)

		if not do_list:
			all_done = frappe.db.count(
				"Delivery Order Towing",
				{"sales_order": sales_order, "status": "Done", "docstatus": 1},
			)
			if all_done:
				skipped.append(
					{
						"sales_order": sales_order,
						"reason": _("Semua DO Done sudah punya Sales Invoice."),
					}
				)
			else:
				skipped.append(
					{
						"sales_order": sales_order,
						"reason": _("Belum ada DO Towing berstatus Done."),
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


@frappe.whitelist()
def get_towing_invoice_items(
	sales_orders, company, customer=None, exclude_invoiced=1, posting_date=None
):
	"""Return SI item rows for bulk towing billing from multiple Sales Orders."""
	result = build_towing_invoice_items(
		sales_orders,
		company,
		exclude_invoiced=frappe.utils.cint(exclude_invoiced),
	)
	if customer and result.get("customer") and customer != result["customer"]:
		frappe.throw(
			_("Customer pada Sales Invoice tidak sama dengan Sales Order yang dipilih."),
			title=_("Customer Tidak Cocok"),
		)

	if result.get("customer"):
		payment_meta = _resolve_payment_terms(
			result["customer"],
			company,
			sales_orders if isinstance(sales_orders, list) else json.loads(sales_orders),
			posting_date=posting_date,
		)
		result.update(payment_meta)

	return result


@frappe.whitelist()
def debug_towing_billing_eligibility(sales_order, company=None, customer=None):
	"""Cek kenapa SO tidak muncul di dialog tarik DO towing."""
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

	done_dos = frappe.get_all(
		"Delivery Order Towing",
		filters={"sales_order": sales_order, "docstatus": 1, "status": "Done"},
		fields=["name", "sales_invoice"],
	)
	uninvoiced = [row.name for row in done_dos if not row.get("sales_invoice")]
	if not done_dos:
		reasons.append(_("Belum ada DO Towing berstatus Done dan Submitted."))
	elif not uninvoiced:
		reasons.append(_("Semua DO Done sudah punya Sales Invoice."))

	return {
		"eligible": not reasons,
		"sales_order": so,
		"done_do_count": len(done_dos),
		"uninvoiced_do": uninvoiced,
		"reasons": reasons or [_("SO eligible — seharusnya muncul di dialog.")],
	}


def _eligible_towing_so_sql(company, customer=None, txt=None):
	conditions = ["so.docstatus = 1", "so.company = %s"]
	values: list = [company]

	if customer:
		conditions.append("so.customer = %s")
		values.append(customer)
	if txt:
		conditions.append("(so.name LIKE %s OR so.customer_name LIKE %s)")
		values.extend([f"%{txt}%", f"%{txt}%"])

	conditions.append(
		"""EXISTS (
			SELECT 1 FROM `tabDelivery Order Towing` do
			WHERE do.sales_order = so.name
			  AND do.docstatus = 1
			  AND do.status = 'Done'
			  AND IFNULL(do.sales_invoice, '') = ''
		)"""
	)
	return conditions, values


@frappe.whitelist()
def list_eligible_towing_sales_orders(company, customer=None):
	"""List SO towing yang bisa ditagih + hint kalau kosong."""
	if not company:
		frappe.throw(_("Company wajib diisi."))

	conditions, values = _eligible_towing_so_sql(company, customer=customer)
	where_clause = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT so.name, so.customer, so.customer_name, so.transaction_date, so.company
		FROM `tabSales Order` so
		WHERE {where_clause}
		ORDER BY so.transaction_date DESC, so.name DESC
		LIMIT 50
		""",
		tuple(values),
		as_dict=True,
	)

	hints = []
	if not rows:
		hints.append(
			_("Tidak ada SO Submitted dengan DO Towing Done yang belum ditagih untuk company {0}.").format(
				company
			)
		)
		if customer:
			hints.append(
				_("Filter customer aktif: {0}. Coba kosongkan Customer di SI lalu tarik ulang.").format(
					customer
				)
			)

		candidate_sos = frappe.db.sql(
			"""
			SELECT DISTINCT do.sales_order
			FROM `tabDelivery Order Towing` do
			INNER JOIN `tabSales Order` so ON so.name = do.sales_order
			WHERE do.docstatus = 1
			  AND do.status = 'Done'
			  AND IFNULL(do.sales_invoice, '') = ''
			  AND so.docstatus = 1
			LIMIT 10
			""",
			as_dict=True,
		)
		for row in candidate_sos:
			check = debug_towing_billing_eligibility(
				row.sales_order, company=company, customer=customer
			)
			if not check.get("eligible"):
				hints.append(f"{row.sales_order}: {'; '.join(check.get('reasons') or [])}")

	return {"sales_orders": rows, "hints": hints}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_towing_sales_order_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query: SO towing yang punya DO Done belum ditagih."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	company = filters.get("company")
	customer = filters.get("customer")

	if not company:
		return []

	conditions, values = _eligible_towing_so_sql(company, customer=customer, txt=txt or None)
	where_clause = " AND ".join(conditions)
	values.extend([cint(start), cint(page_len)])

	return frappe.db.sql(
		f"""
		SELECT
			so.name,
			so.customer_name,
			so.transaction_date,
			so.company
		FROM `tabSales Order` so
		WHERE {where_clause}
		ORDER BY so.transaction_date DESC, so.name DESC
		LIMIT %s, %s
		""",
		tuple(values),
		as_dict=True,
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
