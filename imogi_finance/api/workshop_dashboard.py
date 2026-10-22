"""Aggregated data for the workshop Dashboard Manager page (imogi_finance/page/dashboard_manager).

Modelled on the towing branch's api/dispatch_dashboard.py - same period resolver, same
GL-Entry-sourced P&L so the figures reconcile 1:1 with the Profit and Loss Statement report -
with the operational half swapped from Delivery Order Towing to Garage Service Order, and
"uang jalan belum cair" swapped for supplier payables.
"""

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	cint,
	date_diff,
	flt,
	get_first_day,
	get_last_day,
	getdate,
	nowdate,
)
from frappe.utils.pdf import get_pdf

from imogi_finance.api.approval_center import APPROVAL_TYPES, _state_field

ALLOWED_ROLES = ["System Manager", "Garage Manager", "Sales Manager", "Accounts Manager"]

MONTHS_ID_LONG = [
	"Januari", "Februari", "Maret", "April", "Mei", "Juni",
	"Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

MONTHS_ID = [
	"Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
	"Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]


# Garage Service Order status (Open / Waiting Part / Prepared / In Progress / Finished /
# QC Review / Waiting Payment / Completed / Cancelled) grouped into the five stages a
# workshop manager actually thinks in.
SO_STAGES = [
	("antrian", "ANTRIAN", ["Open"]),
	("tunggu_part", "TUNGGU PART", ["Waiting Part"]),
	("dikerjakan", "DIKERJAKAN", ["Prepared", "In Progress"]),
	("siap_diambil", "SIAP DIAMBIL", ["Finished", "QC Review", "Waiting Payment"]),
	("selesai", "SELESAI / INVOICED", ["Completed"]),
]
SO_OPEN_STAGES = ["antrian", "tunggu_part", "dikerjakan", "siap_diambil"]


@frappe.whitelist()
def get_filter_meta():
	"""Year range for the period filter, derived from the earliest Garage Service Order on record."""
	frappe.only_for(ALLOWED_ROLES)

	current_year = getdate(nowdate()).year
	min_date = None
	if frappe.db.exists("DocType", "Garage Service Order"):
		min_date = frappe.db.sql(
			"select min(order_date) from `tabGarage Service Order` where docstatus < 2"
		)[0][0]
	if not min_date:
		min_date = frappe.db.sql("select min(posting_date) from `tabGL Entry` where is_cancelled = 0")[0][0]

	start_year = getdate(min_date).year if min_date else current_year
	return {
		"years": list(range(current_year, start_year - 1, -1)),
		"default_company": _resolve_company(None),
	}


@frappe.whitelist()
def get_dashboard_data(
	company=None,
	period_type="all", period_date=None, period_year=None, period_month=None, period_week=None,
	period_start=None, period_end=None,
):
	"""period_type: "day" | "week" | "month" | "year" | "range" | "all".
	- "day" uses period_date (YYYY-MM-DD).
	- "week"/"month" use period_year + period_month (1-12); "week" also needs period_week (1-5,
	  counting Nth 7-day block of the month: 1-7, 8-14, 15-21, 22-28, 29-end).
	- "year" uses period_year.
	- "range" uses period_start + period_end (YYYY-MM-DD, inclusive both ends).
	- "all" ignores every other arg and aggregates since the beginning of operations."""
	frappe.only_for(ALLOWED_ROLES)

	company = _resolve_company(company)
	today = getdate(nowdate())
	period = _resolve_period(
		period_type, period_date, cint(period_year), cint(period_month), cint(period_week),
		period_start, period_end, today,
	)

	piutang = _get_piutang(company, period["start"], period["end"])
	hutang = _get_hutang_supplier(company, period["start"], period["end"])
	approval = _get_approval_pending(period["start"], period["end"])
	pipeline = _get_service_order_pipeline(period["start"], period["end"])
	kpi = _get_kpi(company, period, piutang, hutang, approval, pipeline)
	pnl = _get_pnl(company, period["start"], period["end"], kpi)
	trend = _get_trend(company, period_type, period["start"], period["end"])

	return {
		"company": company,
		"period_label": period["label"],
		"comparison_label": period["comparison_label"],
		"is_partial_period": period["is_partial"],
		"kpi": kpi,
		"pnl": pnl,
		"trend": trend,
		"piutang_list": piutang["list"],
		"piutang_aging": piutang["aging"],
		"piutang_total": piutang["total"],
		"pipeline": {**pipeline, "approval_breakdown": approval["breakdown"]},
		"hutang_per_supplier": hutang["rows"],
		"hutang_total": hutang["total"],
		"hutang_supplier_count": hutang["supplier_count"],
	}


def _resolve_company(company):
	company = (
		company
		or frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)
	if not company:
		frappe.throw(_("Company belum di-set. Isi Default Company di Global Defaults dulu."))
	return company


# ---------------------------------------------------------------------------
# Period
# ---------------------------------------------------------------------------

def _resolve_period(
	period_type, period_date, period_year, period_month, period_week, period_start, period_end, today,
):
	if not period_type or period_type == "all":
		return {
			"start": None, "end": today, "label": "Semua Waktu",
			"comparison_label": None, "is_partial": False,
			"prev_start": None, "prev_end": None,
		}

	year = period_year or today.year
	month = period_month or today.month

	if period_type == "day":
		ref = getdate(period_date) if period_date else today
		start = end = full_end = ref
		label = f"{ref.day} {MONTHS_ID_LONG[ref.month - 1]} {ref.year}"
		comparison_label = "vs kemarin"
		prev_start = prev_end = add_days(ref, -1)

	elif period_type == "week":
		week = period_week or 1
		month_first = getdate(f"{year}-{month:02d}-01")
		last_day = get_last_day(month_first)
		start_day = (week - 1) * 7 + 1
		end_day = min(start_day + 6, last_day.day)
		start = getdate(f"{year}-{month:02d}-{start_day:02d}")
		full_end = getdate(f"{year}-{month:02d}-{end_day:02d}")
		end = min(full_end, today)
		label = f"Minggu {week} · {MONTHS_ID_LONG[month - 1]} {year} ({start_day}-{end_day})"
		comparison_label = "vs minggu lalu"
		prev_start = add_days(start, -7)
		prev_end = add_days(full_end, -7)

	elif period_type == "year":
		start = getdate(f"{year}-01-01")
		full_end = getdate(f"{year}-12-31")
		end = min(full_end, today)
		label = str(year)
		comparison_label = "vs tahun lalu"
		prev_start = getdate(f"{year - 1}-01-01")
		prev_end = getdate(f"{year - 1}-12-31")

	elif period_type == "range":
		if not period_start or not period_end:
			frappe.throw(_("Tanggal mulai dan tanggal akhir wajib diisi untuk filter rentang."))
		start = getdate(period_start)
		full_end = getdate(period_end)
		if full_end < start:
			frappe.throw(_("Tanggal akhir tidak boleh sebelum tanggal mulai."))
		end = min(full_end, today)
		duration = date_diff(full_end, start) + 1
		label = _range_label(start, full_end)
		comparison_label = "vs periode sebelumnya"
		prev_end = add_days(start, -1)
		prev_start = add_days(prev_end, -(duration - 1))

	else:  # month
		month_first = getdate(f"{year}-{month:02d}-01")
		start = get_first_day(month_first)
		full_end = get_last_day(month_first)
		end = min(full_end, today)
		label = f"{MONTHS_ID_LONG[month - 1]} {year}"
		comparison_label = "vs bulan lalu"
		prev_ref = add_months(month_first, -1)
		prev_start = get_first_day(prev_ref)
		prev_end = get_last_day(prev_ref)

	return {
		"start": start, "end": end, "label": label,
		"comparison_label": comparison_label, "is_partial": end < full_end,
		"prev_start": prev_start, "prev_end": prev_end,
	}


def _range_label(start, end):
	"""'1-5 Agustus 2026' when same month, '28 Jul - 3 Agu 2026' across months,
	'29 Des 2025 - 2 Jan 2026' across years."""
	if start.year == end.year and start.month == end.month:
		return f"{start.day}-{end.day} {MONTHS_ID_LONG[start.month - 1]} {start.year}"
	if start.year == end.year:
		return f"{start.day} {MONTHS_ID[start.month - 1]} - {end.day} {MONTHS_ID[end.month - 1]} {start.year}"
	return (
		f"{start.day} {MONTHS_ID[start.month - 1]} {start.year} - "
		f"{end.day} {MONTHS_ID[end.month - 1]} {end.year}"
	)


def _period_date_filter(period_start, period_end, fieldname):
	"""Empty dict for "all time" (period_start is None); a between-filter otherwise."""
	if not period_start:
		return {}
	return {fieldname: ["between", [period_start, period_end]]}


# ---------------------------------------------------------------------------
# P&L (GL Entry)
# ---------------------------------------------------------------------------

# HPP = GL Expense entries against Cost of Goods Sold accounts, the same "COGS" grouping the
# standard Profit and Loss Statement report shows. Shared between _omzet_hpp_for_period (to
# include it in HPP) and _get_pnl (to exclude it from Beban Operasional) so the two can never
# drift out of sync with each other.
_HPP_ACCOUNT_CONDITION = "coalesce(acc.account_type, '') = 'Cost of Goods Sold'"


def _gl_root_type_amount(company, period_start, period_end, root_type, extra_where=""):
	"""Sum of GL Entry (credit-debit for Income, debit-credit for Expense) over the company's
	accounts of the given root_type. Mirrors how the standard Profit and Loss Statement report
	totals each side, so dashboard figures reconcile with it."""
	# Secondary finance books (e.g. a parallel depreciation book) post their own GL Entry rows
	# for the same transactions. The P&L report only counts the company's default book (or
	# blank/null finance_book) - without this filter any non-default book gets summed twice.
	default_finance_book = frappe.get_cached_value("Company", company, "default_finance_book") or ""

	date_condition = (
		"and gl.posting_date between %(start)s and %(end)s"
		if period_start
		else "and gl.posting_date <= %(end)s"
	)
	sign = "gl.credit - gl.debit" if root_type == "Income" else "gl.debit - gl.credit"
	rows = frappe.db.sql(
		f"""
		select sum({sign}) amt
		from `tabGL Entry` gl
		inner join `tabAccount` acc on acc.name = gl.account
		where gl.is_cancelled = 0
			and gl.company = %(company)s
			and acc.root_type = %(root_type)s
			and (gl.finance_book is null or gl.finance_book in ('', %(default_finance_book)s))
			{extra_where}
			{date_condition}
		""",
		{
			"company": company, "root_type": root_type, "start": period_start, "end": period_end,
			"default_finance_book": default_finance_book,
		},
		as_dict=1,
	)
	return flt(rows[0].amt) if rows and rows[0].amt else 0


def _omzet_hpp_for_period(company, start, end):
	"""Omzet and HPP sourced from GL Entry (submitted, posted transactions only) rather than the
	Garage Service Order's own total_amount, so they reconcile 1:1 with the Profit and Loss
	Statement report. A service order therefore only counts once its Sales Invoice / spare-part
	Purchase Invoice is actually submitted - not as soon as the operational record is filled in."""
	omzet = _gl_root_type_amount(company, start, end, "Income")
	hpp = _gl_root_type_amount(company, start, end, "Expense", extra_where=f"and {_HPP_ACCOUNT_CONDITION}")
	return omzet, hpp


def _get_pnl(company, period_start, period_end, kpi):
	# Beban Operasional is every non-COGS Expense GL entry - COGS is already counted inside
	# kpi["laba_kotor"] via _omzet_hpp_for_period.
	beban_operasional = _gl_root_type_amount(
		company, period_start, period_end, "Expense", extra_where=f"and not ({_HPP_ACCOUNT_CONDITION})"
	)

	laba_bersih = kpi["laba_kotor"] - beban_operasional
	margin_bersih_pct = (laba_bersih / kpi["omzet"] * 100) if kpi["omzet"] else None

	return {
		"omzet": kpi["omzet"],
		"hpp": kpi["omzet"] - kpi["laba_kotor"],
		"laba_kotor": kpi["laba_kotor"],
		"beban_operasional": beban_operasional,
		"laba_bersih": laba_bersih,
		"margin_bersih_pct": margin_bersih_pct,
	}


# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------

def _get_kpi(company, period, piutang, hutang, approval, pipeline):
	omzet, hpp = _omzet_hpp_for_period(company, period["start"], period["end"])
	laba_kotor = omzet - hpp
	margin_kotor_pct = (laba_kotor / omzet * 100) if omzet else None

	omzet_change_pct = None
	if period["prev_start"]:
		prev_omzet, _prev_hpp = _omzet_hpp_for_period(company, period["prev_start"], period["prev_end"])
		omzet_change_pct = ((omzet - prev_omzet) / prev_omzet * 100) if prev_omzet else None

	return {
		"omzet": omzet,
		"omzet_change_pct": omzet_change_pct,
		"laba_kotor": laba_kotor,
		"margin_kotor_pct": margin_kotor_pct,
		"piutang_belum_lunas": piutang["total"],
		"piutang_count": piutang["count"],
		"hutang_belum_lunas": hutang["total"],
		"hutang_count": hutang["count"],
		"so_aktif": pipeline["masih_diproses"],
		"so_aktif_dikerjakan": pipeline["dikerjakan"],
		"so_aktif_tunggu_part": pipeline["tunggu_part"],
		"approval_pending_amount": approval["amount"],
		"approval_pending_count": approval["count"],
	}


# ---------------------------------------------------------------------------
# Trend
# ---------------------------------------------------------------------------

def _get_trend(company, period_type, start_date, end_date):
	"""Trend granularity follows the selected filter: days for "day", weeks for "week",
	years for "year", and months for "month"/"all".

	"range" shows one point per day across the exact selected span when that's 31 days
	or fewer (any more and a daily chart stops being readable, so it falls back to the
	trailing-6-months view instead)."""
	if period_type == "day":
		return _trend_days(company, end_date, 14)
	if period_type == "week":
		return _trend_weeks(company, end_date, 8)
	if period_type == "year":
		return _trend_years(company, end_date, 5)
	if period_type == "range" and start_date:
		span = date_diff(end_date, start_date) + 1
		if span <= 31:
			return _trend_days(company, end_date, span)
	return _trend_months(company, end_date, 6)


def _trend_days(company, end_date, n):
	labels, omzet_series, laba_series = [], [], []
	for i in range(n - 1, -1, -1):
		d = add_days(end_date, -i)
		omzet, hpp = _omzet_hpp_for_period(company, d, d)
		labels.append(f"{d.day} {MONTHS_ID[d.month - 1]}")
		omzet_series.append(omzet)
		laba_series.append(omzet - hpp)
	return {"months": labels, "omzet": omzet_series, "laba_kotor": laba_series}


def _trend_weeks(company, end_date, n):
	monday = add_days(end_date, -end_date.weekday())
	labels, omzet_series, laba_series = [], [], []
	for i in range(n - 1, -1, -1):
		start = add_days(monday, -7 * i)
		end = min(add_days(start, 6), end_date)
		omzet, hpp = _omzet_hpp_for_period(company, start, end)
		labels.append(f"{start.day}/{start.month}")
		omzet_series.append(omzet)
		laba_series.append(omzet - hpp)
	return {"months": labels, "omzet": omzet_series, "laba_kotor": laba_series}


def _trend_months(company, end_date, n):
	labels, omzet_series, laba_series = [], [], []
	for i in range(n - 1, -1, -1):
		ref = add_months(end_date, -i)
		start = get_first_day(ref)
		end = min(get_last_day(ref), end_date)
		omzet, hpp = _omzet_hpp_for_period(company, start, end)
		labels.append(f"{MONTHS_ID[ref.month - 1]} {str(ref.year)[2:]}")
		omzet_series.append(omzet)
		laba_series.append(omzet - hpp)
	return {"months": labels, "omzet": omzet_series, "laba_kotor": laba_series}


def _trend_years(company, end_date, n):
	labels, omzet_series, laba_series = [], [], []
	for i in range(n - 1, -1, -1):
		y = end_date.year - i
		start = getdate(f"{y}-01-01")
		end = min(getdate(f"{y}-12-31"), end_date)
		omzet, hpp = _omzet_hpp_for_period(company, start, end)
		labels.append(str(y))
		omzet_series.append(omzet)
		laba_series.append(omzet - hpp)
	return {"months": labels, "omzet": omzet_series, "laba_kotor": laba_series}


# ---------------------------------------------------------------------------
# Piutang / Hutang
# ---------------------------------------------------------------------------

def _get_piutang(company, period_start=None, period_end=None):
	"""Real Accounts Receivable: submitted Sales Invoices still carrying an outstanding balance
	(invoiced, not yet paid) - not "service order selesai tapi belum di-invoice" (that's an
	earlier stage of the pipeline, already visible via the Pipeline / SO Aktif cards)."""
	rows = frappe.get_all(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"company": company,
			"outstanding_amount": [">", 0],
			**_period_date_filter(period_start, period_end, "posting_date"),
		},
		fields=["name", "customer_name", "outstanding_amount", "posting_date"],
	)

	today = getdate(nowdate())
	aging = {"0-30": 0, "30-60": 0, "60-90": 0, ">90": 0}
	enriched = []
	for r in rows:
		posting_date = getdate(r.posting_date)
		umur = date_diff(today, posting_date)
		amount = flt(r.outstanding_amount)

		if umur <= 30:
			aging["0-30"] += amount
		elif umur <= 60:
			aging["30-60"] += amount
		elif umur <= 90:
			aging["60-90"] += amount
		else:
			aging[">90"] += amount

		enriched.append({
			"invoice": r.name,
			"customer": r.customer_name or "-",
			"tanggal": str(posting_date),
			"umur": umur,
			"nilai": amount,
		})

	enriched.sort(key=lambda x: x["nilai"], reverse=True)
	total = sum(e["nilai"] for e in enriched)
	return {"list": enriched[:10], "aging": aging, "total": total, "count": len(enriched)}


def _get_hutang_supplier(company, period_start=None, period_end=None):
	"""Supplier payables still open - submitted Purchase Invoices with an outstanding balance,
	grouped per supplier. The workshop's counterpart to towing's "uang jalan belum cair": money
	already committed (spare part, sublet, operasional) but not paid out yet."""
	rows = frappe.get_all(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"company": company,
			"outstanding_amount": [">", 0],
			**_period_date_filter(period_start, period_end, "posting_date"),
		},
		fields=["name", "supplier", "supplier_name", "outstanding_amount", "due_date"],
	)

	today = getdate(nowdate())
	by_supplier = {}
	for r in rows:
		# keyed by supplier id so the dashboard row can drill into a filtered list view;
		# supplier_name is what actually gets displayed.
		key = r.supplier or r.supplier_name or ""
		bucket = by_supplier.setdefault(
			key,
			{
				"supplier": key,
				"supplier_name": r.supplier_name or r.supplier or "Supplier belum diisi",
				"count": 0,
				"amount": 0,
				"overdue": 0,
			},
		)
		bucket["count"] += 1
		bucket["amount"] += flt(r.outstanding_amount)
		if r.due_date and getdate(r.due_date) < today:
			bucket["overdue"] += 1

	rows_sorted = sorted(by_supplier.values(), key=lambda x: x["amount"], reverse=True)
	total = sum(r["amount"] for r in rows_sorted)
	return {
		"rows": rows_sorted[:5],
		"total": total,
		"supplier_count": len(rows_sorted),
		"count": len(rows),
	}


# ---------------------------------------------------------------------------
# Operasional
# ---------------------------------------------------------------------------

def _get_service_order_pipeline(period_start=None, period_end=None):
	"""Garage Service Order counts per pipeline stage. Deliberately not company-filtered: the
	doctype is scoped by Garage Branch, it carries no company field."""
	pipeline = {key: 0 for key, _label, _statuses in SO_STAGES}
	pipeline["masih_diproses"] = 0

	if not frappe.db.exists("DocType", "Garage Service Order"):
		return pipeline

	rows = frappe.get_all(
		"Garage Service Order",
		filters={
			"docstatus": ["<", 2],
			"status": ["!=", "Cancelled"],
			**_period_date_filter(period_start, period_end, "order_date"),
		},
		fields=["status"],
	)

	for key, _label, statuses in SO_STAGES:
		pipeline[key] = sum(1 for r in rows if r.status in statuses)
	pipeline["masih_diproses"] = sum(pipeline[key] for key in SO_OPEN_STAGES)

	return pipeline


def _get_approval_pending(period_start=None, period_end=None):
	"""Documents sitting in an approval queue, per queue.

	Matched on the workflow's own state field and NOT on docstatus: Administrative Payment
	Voucher holds its "Pending Approval" state at docstatus 0 (Draft), so a docstatus=1 filter
	silently reports zero vouchers waiting no matter how many there are. The queue list itself
	is shared with the Approval Center page (imogi_finance.api.approval_center.APPROVAL_TYPES)
	so the card total and that page's list always agree.
	"""
	total_amount = 0
	total_count = 0
	breakdown = []
	for cfg in APPROVAL_TYPES:
		if not frappe.db.exists("DocType", cfg["doctype"]):
			continue

		state_field = _state_field(cfg["doctype"])
		filters = {state_field: ["in", cfg["pending_states"]]}
		if period_start:
			filters["creation"] = ["between", [period_start, f"{period_end} 23:59:59"]]

		amount_field = cfg.get("amount_field")
		fields = [amount_field] if amount_field and frappe.get_meta(cfg["doctype"]).has_field(amount_field) else ["name"]
		rows = frappe.get_all(cfg["doctype"], filters=filters, fields=fields)

		count = len(rows)
		amount = sum(flt(r.get(amount_field)) for r in rows) if amount_field else 0
		total_count += count
		total_amount += amount
		breakdown.append(
			{
				"doctype": cfg["doctype"],
				"label": cfg["label"],
				"count": count,
				"amount": amount,
			}
		)
	return {"amount": total_amount, "count": total_count, "breakdown": breakdown}


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

@frappe.whitelist()
def dashboard_pdf(html, filename="dashboard-manager.pdf", orientation="Landscape"):
	"""Render a client-captured snapshot of the Dashboard Manager page to PDF for download."""
	frappe.only_for(ALLOWED_ROLES)

	pdf_content = get_pdf(
		html,
		{
			"orientation": orientation,
			"proxy": "http://0.0.0.0:0",
			"bypass-proxy-for": urlparse(frappe.utils.get_url(allow_header_override=False)).hostname,
			"load-error-handling": "ignore",
			# Without this wkhtmltopdf renders at a narrow default viewport, which trips our own
			# max-width:900px "mobile" CSS and collapses every card into a single stacked column.
			"viewport-size": "1600x1000",
			"margin-top": "8mm",
			"margin-bottom": "8mm",
			"margin-left": "8mm",
			"margin-right": "8mm",
		},
	)
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = pdf_content
	frappe.local.response.type = "pdf"
