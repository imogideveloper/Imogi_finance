"""Aggregated data for the Sirius Dispatch dashboard (imogi_finance/page/sirius_dispatch)."""

import frappe
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate, date_diff, cint

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
def get_dashboard_data():
	frappe.only_for(["System Manager", "Sales Manager", "Accounts Manager"])

	today = getdate(nowdate())
	period_start = get_first_day(today)
	prev_month_ref = add_months(today, -1)
	prev_start = get_first_day(prev_month_ref)
	prev_end = get_last_day(prev_month_ref)

	kpi = _get_kpi(period_start, today, prev_start, prev_end)
	pnl = _get_pnl(period_start, today, kpi)
	trend = _get_trend(today)
	piutang = _get_piutang()
	pipeline = _get_pipeline()
	uang_jalan = _get_uang_jalan_per_rute()

	return {
		"period_label": f"{MONTHS_ID[today.month - 1]} {today.year}",
		"is_partial_month": today.day < (get_last_day(today)).day,
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


def _invoiced_do_filters(start, end):
	return {
		"docstatus": 1,
		"sales_invoice": ["is", "set"],
		"tanggal_invoice": ["between", [start, end]],
	}


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


def _get_kpi(period_start, today, prev_start, prev_end):
	omzet, hpp = _omzet_hpp_for_period(period_start, today)
	laba_kotor = omzet - hpp
	margin_kotor_pct = (laba_kotor / omzet * 100) if omzet else None

	prev_omzet, _ = _omzet_hpp_for_period(prev_start, prev_end)
	omzet_change_pct = ((omzet - prev_omzet) / prev_omzet * 100) if prev_omzet else None

	piutang_rows = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"docstatus": 1,
			"status": ["in", ["Delivered", "Done", "Awaiting Dokument"]],
			"sales_invoice": ["is", "not set"],
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
		},
		fields=["uang_jalan_amount"],
	)
	uang_jalan_total = sum(flt(r.uang_jalan_amount) for r in uj_rows)

	do_aktif_rows = frappe.get_all(
		"Delivery Order Towing",
		filters={"docstatus": 1, "status": ["not in", ["Done", "Cancelled"]]},
		fields=["status"],
	)
	dalam_perjalanan = sum(1 for r in do_aktif_rows if r.status == "Pick Up")
	tunggu_dokumen = sum(1 for r in do_aktif_rows if r.status in ("Delivered", "Awaiting Dokument"))

	approval_amount, approval_count = _get_approval_pending()

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


def _get_approval_pending():
	total_amount = 0
	total_count = 0
	for cfg in APPROVAL_DOCTYPES:
		if not frappe.db.exists("DocType", cfg["doctype"]):
			continue
		rows = frappe.get_all(
			cfg["doctype"],
			filters={"docstatus": 1, "workflow_state": ["in", cfg["pending_states"]]},
			fields=[cfg["amount_field"]],
		)
		total_count += len(rows)
		total_amount += sum(flt(r.get(cfg["amount_field"])) for r in rows)
	return total_amount, total_count


def _get_pnl(period_start, today, kpi):
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	beban_operasional = 0
	if company:
		rows = frappe.db.sql(
			"""
			select sum(gl.debit - gl.credit) amt
			from `tabGL Entry` gl
			inner join `tabAccount` acc on acc.name = gl.account
			where gl.is_cancelled = 0
				and gl.company = %s
				and acc.root_type = 'Expense'
				and gl.posting_date between %s and %s
			""",
			(company, period_start, today),
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


def _get_piutang():
	rows = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"docstatus": 1,
			"status": ["in", ["Delivered", "Done", "Awaiting Dokument"]],
			"sales_invoice": ["is", "not set"],
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


def _get_pipeline():
	rows = frappe.get_all(
		"Delivery Order Towing",
		filters={"docstatus": 1, "status": ["!=", "Cancelled"]},
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


def _get_uang_jalan_per_rute():
	rows = frappe.get_all(
		"Delivery Order Towing",
		filters={
			"docstatus": 1,
			"status": ["!=", "Cancelled"],
			"uang_jalan_status": ["!=", "Dibayar"],
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
