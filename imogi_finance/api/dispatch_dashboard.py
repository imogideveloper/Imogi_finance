"""Aggregated data for the Sirius Dispatch dashboard (imogi_finance/page/sirius_dispatch)."""

from urllib.parse import urlparse

import frappe
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, nowdate, date_diff, cint
from frappe.utils.pdf import get_pdf

MONTHS_ID_LONG = [
	"Januari", "Februari", "Maret", "April", "Mei", "Juni",
	"Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

APPROVAL_DOCTYPES = [
	{"doctype": "Expense Request", "amount_field": "amount", "pending_states": ["Pending Review"]},
	{"doctype": "Additional Budget Request", "amount_field": "amount", "pending_states": ["Pending Approval"]},
	{"doctype": "Budget Reclass Request", "amount_field": "amount", "pending_states": ["Pending Approval"]},
	{
		"doctype": "Internal Charge Request",
		"amount_field": "total_amount",
		"pending_states": ["Pending L1 Approval", "Pending L2 Approval", "Pending L3 Approval"],
	},
	{
		"doctype": "Administrative Payment Voucher",
		"amount_field": "amount",
		"pending_states": ["Pending Approval"],
	},
]

MONTHS_ID = [
	"Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
	"Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]


@frappe.whitelist()
def get_filter_meta():
	"""Year range for the period filter, derived from the earliest Delivery Order Towing on record."""
	frappe.only_for(["System Manager", "Sales Manager", "Accounts Manager"])

	current_year = getdate(nowdate()).year
	min_date = frappe.db.sql(
		"select min(tanggal_do) from `tabDelivery Order Towing` where docstatus = 1"
	)[0][0]
	start_year = getdate(min_date).year if min_date else current_year
	return {"years": list(range(current_year, start_year - 1, -1))}


@frappe.whitelist()
def get_dashboard_data(period_type="all", period_date=None, period_year=None, period_month=None, period_week=None):
	"""period_type: "day" | "week" | "month" | "year" | "all".
	- "day" uses period_date (YYYY-MM-DD).
	- "week"/"month" use period_year + period_month (1-12); "week" also needs period_week (1-5,
	  counting Nth 7-day block of the month: 1-7, 8-14, 15-21, 22-28, 29-end).
	- "year" uses period_year.
	- "all" ignores every other arg and aggregates since the beginning of operations."""
	frappe.only_for(["System Manager", "Sales Manager", "Accounts Manager"])

	today = getdate(nowdate())
	period = _resolve_period(period_type, period_date, cint(period_year), cint(period_month), cint(period_week), today)

	kpi = _get_kpi(period["start"], period["end"], period["prev_start"], period["prev_end"])
	pnl = _get_pnl(period["start"], period["end"], kpi)
	trend = _get_trend(today)
	piutang = _get_piutang(period["start"], period["end"])
	pipeline = _get_pipeline(period["start"], period["end"])
	uang_jalan = _get_uang_jalan_per_rute(period["start"], period["end"])

	return {
		"period_label": period["label"],
		"comparison_label": period["comparison_label"],
		"is_partial_period": period["is_partial"],
		"kpi": kpi,
		"pnl": pnl,
		"trend": trend,
		"piutang_list": piutang["list"],
		"piutang_aging": piutang["aging"],
		"piutang_total": piutang["total"],
		"pipeline": pipeline,
		"uang_jalan_per_rute": uang_jalan["rows"],
		"uang_jalan_total": uang_jalan["total"],
		"uang_jalan_route_count": uang_jalan["route_count"],
	}


def _resolve_period(period_type, period_date, period_year, period_month, period_week, today):
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
		start = end = ref
		full_end = ref
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


def _invoiced_do_filters(start, end):
	filters = {"docstatus": 1, "sales_invoice": ["is", "set"]}
	if start:
		filters["tanggal_invoice"] = ["between", [start, end]]
	else:
		filters["tanggal_invoice"] = ["<=", end]
	return filters


def _omzet_hpp_for_period(start, end):
	dos = frappe.get_all(
		"Delivery Order Towing",
		filters=_invoiced_do_filters(start, end),
		fields=["name", "harga_jasa", "uang_jalan_amount"],
	)
	omzet = sum(flt(d.harga_jasa) for d in dos)
	uang_jalan_cost = sum(flt(d.uang_jalan_amount) for d in dos)

	komisi_cost = 0
	if dos:
		do_names = [d.name for d in dos]
		komisi_rows = frappe.get_all(
			"Driver Commission Item",
			filters={
				"delivery_order_towing": ["in", do_names],
				"parenttype": "Driver Commission",
			},
			fields=["komisi_amount", "parent"],
		)
		if komisi_rows:
			parents = list({r.parent for r in komisi_rows})
			valid_parents = set(
				frappe.get_all(
					"Driver Commission",
					filters={"name": ["in", parents], "docstatus": 1, "status": ["in", ["Approved", "Paid"]]},
					pluck="name",
				)
			)
			komisi_cost = sum(flt(r.komisi_amount) for r in komisi_rows if r.parent in valid_parents)

	hpp = uang_jalan_cost + komisi_cost
	return omzet, hpp


def _period_date_filter(period_start, period_end, fieldname="tanggal_do"):
	"""Empty dict for "all time" (period_start is None); a between-filter otherwise."""
	if not period_start:
		return {}
	return {fieldname: ["between", [period_start, period_end]]}


def _get_kpi(period_start, period_end, prev_start, prev_end):
	omzet, hpp = _omzet_hpp_for_period(period_start, period_end)
	laba_kotor = omzet - hpp
	margin_kotor_pct = (laba_kotor / omzet * 100) if omzet else None

	omzet_change_pct = None
	if prev_start:
		prev_omzet, _ = _omzet_hpp_for_period(prev_start, prev_end)
		omzet_change_pct = ((omzet - prev_omzet) / prev_omzet * 100) if prev_omzet else None

	date_filter = _period_date_filter(period_start, period_end)

	piutang_rows = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"docstatus": 1,
			"status": ["in", ["Delivered", "Done", "Awaiting Dokument"]],
			"sales_invoice": ["is", "not set"],
			**date_filter,
		},
		fields=["harga_jasa"],
	)
	piutang_total = sum(flt(r.harga_jasa) for r in piutang_rows)

	uj_rows = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"docstatus": 1,
			"status": ["!=", "Cancelled"],
			"uang_jalan_status": ["!=", "Dibayar"],
			**date_filter,
		},
		fields=["uang_jalan_amount"],
	)
	uang_jalan_total = sum(flt(r.uang_jalan_amount) for r in uj_rows)

	do_aktif_rows = frappe.get_all(
		"Delivery Order Towing",
		filters={"docstatus": 1, "status": ["not in", ["Done", "Cancelled"]], **date_filter},
		fields=["status"],
	)
	dalam_perjalanan = sum(1 for r in do_aktif_rows if r.status == "Pick Up")
	tunggu_dokumen = sum(1 for r in do_aktif_rows if r.status in ("Delivered", "Awaiting Dokument"))

	approval_amount, approval_count = _get_approval_pending(period_start, period_end)

	return {
		"omzet": omzet,
		"omzet_change_pct": omzet_change_pct,
		"laba_kotor": laba_kotor,
		"margin_kotor_pct": margin_kotor_pct,
		"piutang_belum_ditagih": piutang_total,
		"piutang_count": len(piutang_rows),
		"uang_jalan_belum_cair": uang_jalan_total,
		"uang_jalan_count": len(uj_rows),
		"do_aktif": len(do_aktif_rows),
		"do_aktif_jalan": dalam_perjalanan,
		"do_aktif_tunggu_dokumen": tunggu_dokumen,
		"approval_pending_amount": approval_amount,
		"approval_pending_count": approval_count,
	}


def _get_approval_pending(period_start=None, period_end=None):
	total_amount = 0
	total_count = 0
	for cfg in APPROVAL_DOCTYPES:
		if not frappe.db.exists("DocType", cfg["doctype"]):
			continue
		filters = {"docstatus": 1, "workflow_state": ["in", cfg["pending_states"]]}
		if period_start:
			filters["creation"] = ["between", [period_start, f"{period_end} 23:59:59"]]
		rows = frappe.get_all(cfg["doctype"], filters=filters, fields=[cfg["amount_field"]])
		total_count += len(rows)
		total_amount += sum(flt(r.get(cfg["amount_field"])) for r in rows)
	return total_amount, total_count


def _get_pnl(period_start, period_end, kpi):
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	beban_operasional = 0
	if company:
		if period_start:
			date_condition = "and gl.posting_date between %(start)s and %(end)s"
		else:
			date_condition = "and gl.posting_date <= %(end)s"
		rows = frappe.db.sql(
			f"""
			select sum(gl.debit - gl.credit) amt
			from `tabGL Entry` gl
			inner join `tabAccount` acc on acc.name = gl.account
			where gl.is_cancelled = 0
				and gl.company = %(company)s
				and acc.root_type = 'Expense'
				{date_condition}
			""",
			{"company": company, "start": period_start, "end": period_end},
			as_dict=1,
		)
		beban_operasional = flt(rows[0].amt) if rows and rows[0].amt else 0

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


def _get_trend(today):
	months, omzet_series, laba_series = [], [], []
	for i in range(5, -1, -1):
		ref = add_months(today, -i)
		start = get_first_day(ref)
		end = today if i == 0 else get_last_day(ref)
		omzet, hpp = _omzet_hpp_for_period(start, end)
		months.append(f"{MONTHS_ID[ref.month - 1]} {str(ref.year)[2:]}")
		omzet_series.append(omzet)
		laba_series.append(omzet - hpp)
	return {"months": months, "omzet": omzet_series, "laba_kotor": laba_series}


def _get_piutang(period_start=None, period_end=None):
	rows = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"docstatus": 1,
			"status": ["in", ["Delivered", "Done", "Awaiting Dokument"]],
			"sales_invoice": ["is", "not set"],
			**_period_date_filter(period_start, period_end),
		},
		fields=[
			"name", "customer_name", "harga_jasa",
			"waktu_done", "waktu_delivered", "tanggal_do",
		],
	)

	today = getdate(nowdate())
	aging = {"0-30": 0, "30-60": 0, "60-90": 0, ">90": 0}
	enriched = []
	for r in rows:
		selesai = r.waktu_done or r.waktu_delivered or r.tanggal_do
		selesai_date = getdate(selesai)
		umur = date_diff(today, selesai_date)
		amount = flt(r.harga_jasa)

		if umur <= 30:
			aging["0-30"] += amount
		elif umur <= 60:
			aging["30-60"] += amount
		elif umur <= 90:
			aging["60-90"] += amount
		else:
			aging[">90"] += amount

		enriched.append({
			"do": r.name,
			"customer": r.customer_name or "-",
			"selesai": str(selesai_date),
			"umur": umur,
			"nilai": amount,
		})

	enriched.sort(key=lambda x: x["nilai"], reverse=True)
	total = sum(e["nilai"] for e in enriched)
	return {"list": enriched[:10], "aging": aging, "total": total}


def _get_pipeline(period_start=None, period_end=None):
	rows = frappe.get_all(
		"Delivery Order Towing",
		filters={"docstatus": 1, "status": ["!=", "Cancelled"], **_period_date_filter(period_start, period_end)},
		fields=["status"],
	)
	antrian = sum(1 for r in rows if r.status in ("Draft", "Assigned"))
	dalam_perjalanan = sum(1 for r in rows if r.status == "Pick Up")
	tunggu_dokumen = sum(1 for r in rows if r.status in ("Delivered", "Awaiting Dokument"))
	selesai = sum(1 for r in rows if r.status == "Done")
	return {
		"antrian": antrian,
		"dalam_perjalanan": dalam_perjalanan,
		"delivered_tunggu_dokumen": tunggu_dokumen,
		"selesai_invoiced": selesai,
		"masih_diproses": antrian + dalam_perjalanan + tunggu_dokumen,
	}


def _get_uang_jalan_per_rute(period_start=None, period_end=None):
	rows = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"docstatus": 1,
			"status": ["!=", "Cancelled"],
			"uang_jalan_status": ["!=", "Dibayar"],
			**_period_date_filter(period_start, period_end),
		},
		fields=["kota_pickup", "kota_tujuan", "lokasi_pickup", "lokasi_tujuan", "uang_jalan_amount"],
	)

	by_route = {}
	for r in rows:
		origin = r.kota_pickup or r.lokasi_pickup or "Asal belum diisi"
		dest = r.kota_tujuan or r.lokasi_tujuan or "Tujuan belum diisi"
		key = f"{origin} → {dest}"
		if key not in by_route:
			by_route[key] = {"rute": key, "count": 0, "amount": 0}
		by_route[key]["count"] += 1
		by_route[key]["amount"] += flt(r.uang_jalan_amount)

	rows_sorted = sorted(by_route.values(), key=lambda x: x["amount"], reverse=True)
	total = sum(r["amount"] for r in rows_sorted)
	return {"rows": rows_sorted[:5], "total": total, "route_count": len(rows_sorted)}


@frappe.whitelist()
def dashboard_pdf(html, filename="dashboard-manager.pdf", orientation="Landscape"):
	"""Render a client-captured snapshot of the Dashboard Manager page to PDF for download."""
	frappe.only_for(["System Manager", "Sales Manager", "Accounts Manager"])

	pdf_content = get_pdf(
		html,
		{
			"orientation": orientation,
			"proxy": "http://0.0.0.0:0",
			"bypass-proxy-for": urlparse(frappe.utils.get_url(allow_header_override=False)).hostname,
			"load-error-handling": "ignore",
			# Without this wkhtmltopdf renders at a narrow default viewport, which trips our own
			# max-width:900px "mobile" CSS and collapses every card to a single stacked column.
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
