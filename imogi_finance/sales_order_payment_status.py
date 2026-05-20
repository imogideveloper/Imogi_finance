import frappe
from frappe import _
from frappe.utils import cint, flt


def get_sales_order_financial_summary(sales_order_name: str, so_doc=None) -> dict:
	"""Financial snapshot for Sales Order payment / outstanding display."""
	if so_doc is None:
		so_doc = frappe.get_doc("Sales Order", sales_order_name)

	so_total = flt(so_doc.rounded_total or so_doc.grand_total)
	remaining_to_bill = _get_remaining_billable_on_so(so_doc)
	per_billed = flt(so_doc.per_billed)

	invoices = frappe.db.sql(
		"""
		SELECT
			si.name,
			si.docstatus,
			si.outstanding_amount,
			si.grand_total
		FROM `tabSales Invoice` si
		INNER JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
		WHERE sii.sales_order = %s
		  AND si.docstatus < 2
		GROUP BY si.name
		""",
		(sales_order_name,),
		as_dict=True,
	)

	total_si_grand = 0.0
	total_si_outstanding = 0.0
	has_invoice = bool(invoices)

	for inv in invoices:
		if cint(inv.docstatus) != 1:
			continue
		total_si_grand += flt(inv.grand_total)
		total_si_outstanding += flt(inv.outstanding_amount)

	# Outstanding SO = sisa nilai SO yang belum tertagih di Sales Invoice (grand total).
	so_invoice_gap = max(0, flt(so_total - total_si_grand))
	paid_on_invoices = max(0, total_si_grand - total_si_outstanding)
	fully_billed = per_billed >= 99.99 or remaining_to_bill <= 0.005

	return {
		"so_total": so_total,
		"remaining_to_bill": remaining_to_bill,
		"per_billed": per_billed,
		"fully_billed": fully_billed,
		"total_si_grand": total_si_grand,
		"total_si_outstanding": total_si_outstanding,
		"paid_on_invoices": paid_on_invoices,
		"so_invoice_gap": so_invoice_gap,
		"total_remaining": so_invoice_gap,
		"has_submitted_invoice": total_si_grand > 0,
		"has_invoice": has_invoice,
	}


def _get_remaining_billable_on_so(so) -> float:
	total = 0.0
	for row in so.get("items") or []:
		pending = flt(row.amount) - flt(row.billed_amt)
		if pending > 0:
			total += pending
	return flt(total)


def _resolve_payment_status(summary: dict, so_docstatus: int) -> str:
	tolerance = 1.0

	if not summary["has_invoice"]:
		return "Submitted" if cint(so_docstatus) == 1 else "Draft"

	so_invoice_gap = summary["so_invoice_gap"]
	total_si_outstanding = summary["total_si_outstanding"]

	if so_invoice_gap <= tolerance and total_si_outstanding <= tolerance:
		return "Paid"

	if summary["has_submitted_invoice"]:
		if so_invoice_gap > tolerance or total_si_outstanding > tolerance:
			return "Outstanding Invoice"

	return "SI Created"


def update_sales_order_payment_status(sales_order_name: str):
	if not sales_order_name:
		return

	so = frappe.db.get_value(
		"Sales Order",
		sales_order_name,
		["name", "docstatus"],
		as_dict=True,
	)

	if not so:
		return

	if so.docstatus == 2:
		frappe.db.set_value(
			"Sales Order",
			sales_order_name,
			{"custom_payment_status": "Cancelled", "outstanding_amount": 0},
			update_modified=False,
		)
		return

	summary = get_sales_order_financial_summary(sales_order_name)
	payment_status = _resolve_payment_status(summary, so.docstatus)

	frappe.db.set_value(
		"Sales Order",
		sales_order_name,
		{
			"custom_payment_status": payment_status,
			"outstanding_amount": summary["so_invoice_gap"],
		},
		update_modified=False,
	)


def update_from_sales_order(doc, method=None):
	update_sales_order_payment_status(doc.name)


def update_from_sales_invoice(doc, method=None):
	sales_orders = {item.sales_order for item in doc.items if item.sales_order}
	for so_name in sales_orders:
		update_sales_order_payment_status(so_name)


def update_from_payment_entry(doc, method=None):
	sales_invoices = {
		ref.reference_name
		for ref in doc.get("references") or []
		if ref.reference_doctype == "Sales Invoice" and ref.reference_name
	}

	if not sales_invoices:
		return

	sales_orders = set()
	for invoice_name in sales_invoices:
		for row in frappe.db.sql(
			"""
			SELECT DISTINCT sales_order
			FROM `tabSales Invoice Item`
			WHERE parent = %s AND IFNULL(sales_order, '') != ''
			""",
			(invoice_name,),
			as_dict=True,
		):
			sales_orders.add(row.sales_order)

	for so_name in sales_orders:
		update_sales_order_payment_status(so_name)
