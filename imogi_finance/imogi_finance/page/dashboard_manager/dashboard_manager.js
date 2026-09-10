const MONTHS_ID_LONG = [
	"Januari", "Februari", "Maret", "April", "Mei", "Juni",
	"Juli", "Agustus", "September", "Oktober", "November", "Desember",
];

frappe.pages["dashboard-manager"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Dashboard Manager",
		single_column: true,
	});

	inject_styles();

	const $wrap = $(get_shell()).appendTo(page.main);
	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const state = {
		$wrap, chart: null,
		period_type: "all",
		period_date: frappe.datetime.get_today(),
		period_year: today.getFullYear(),
		period_month: today.getMonth() + 1,
		period_week: 1,
	};

	frappe.call({ method: "imogi_finance.api.dispatch_dashboard.get_filter_meta" }).then((r) => {
		const years = (r.message && r.message.years) || [today.getFullYear()];
		setup_filters(page, state, years);
		page.set_primary_action("Refresh", () => load(state), "refresh");
		load(state);
	});
};

function setup_filters(page, state, years) {
	state.type_field = page.add_field({
		label: "Tipe Periode",
		fieldtype: "Select",
		fieldname: "period_type",
		options: [
			{ label: "Hari", value: "day" },
			{ label: "Minggu", value: "week" },
			{ label: "Bulan", value: "month" },
			{ label: "Tahun", value: "year" },
			{ label: "Semua Waktu", value: "all" },
		],
		default: "all",
		change: () => {
			state.period_type = state.type_field.get_value() || "all";
			update_filter_visibility(state);
			load(state);
		},
	});

	state.date_field = page.add_field({
		label: "Tanggal",
		fieldtype: "Date",
		fieldname: "period_date",
		default: state.period_date,
		change: () => {
			state.period_date = state.date_field.get_value() || frappe.datetime.get_today();
			load(state);
		},
	});

	state.year_field = page.add_field({
		label: "Tahun",
		fieldtype: "Select",
		fieldname: "period_year",
		options: years.map((y) => ({ label: String(y), value: y })),
		default: state.period_year,
		change: () => {
			state.period_year = cint(state.year_field.get_value()) || state.period_year;
			refresh_week_options(state);
			load(state);
		},
	});

	state.month_field = page.add_field({
		label: "Bulan",
		fieldtype: "Select",
		fieldname: "period_month",
		options: MONTHS_ID_LONG.map((m, i) => ({ label: m, value: i + 1 })),
		default: state.period_month,
		change: () => {
			state.period_month = cint(state.month_field.get_value()) || state.period_month;
			refresh_week_options(state);
			load(state);
		},
	});

	state.week_field = page.add_field({
		label: "Minggu ke-",
		fieldtype: "Select",
		fieldname: "period_week",
		options: build_week_options(state.period_year, state.period_month),
		default: state.period_week,
		change: () => {
			state.period_week = cint(state.week_field.get_value()) || 1;
			load(state);
		},
	});

	update_filter_visibility(state);
}

function update_filter_visibility(state) {
	const t = state.period_type;
	state.date_field.$wrapper.toggle(t === "day");
	state.year_field.$wrapper.toggle(t === "week" || t === "month" || t === "year");
	state.month_field.$wrapper.toggle(t === "week" || t === "month");
	state.week_field.$wrapper.toggle(t === "week");
}

function build_week_options(year, month) {
	const daysInMonth = new Date(year, month, 0).getDate();
	const weekCount = daysInMonth >= 29 ? 5 : 4;
	const options = [];
	for (let w = 1; w <= weekCount; w++) {
		const startDay = (w - 1) * 7 + 1;
		const endDay = Math.min(startDay + 6, daysInMonth);
		options.push({ label: `Minggu ${w} (${startDay}-${endDay})`, value: w });
	}
	return options;
}

function refresh_week_options(state) {
	const options = build_week_options(state.period_year, state.period_month);
	state.week_field.df.options = options;
	state.week_field.refresh();
	if (state.period_week > options.length) {
		state.period_week = options.length;
		state.week_field.set_value(options.length);
	}
}

function load(state) {
	frappe.call({
		method: "imogi_finance.api.dispatch_dashboard.get_dashboard_data",
		args: {
			period_type: state.period_type || "all",
			period_date: state.period_date,
			period_year: state.period_year,
			period_month: state.period_month,
			period_week: state.period_week,
		},
		freeze: true,
		freeze_message: "Memuat dashboard...",
	}).then((r) => {
		if (!r.message) return;
		render(state, r.message);
	});
}

function render(state, data) {
	render_kpis(state, data);
	render_trend(state, data);
	render_pnl(state, data);
	render_piutang(state, data);
	render_aging(state, data);
	render_pipeline(state, data);
	render_rute(state, data);
}

// ---------------------------------------------------------------------
// KPI row
// ---------------------------------------------------------------------
function render_kpis(state, data) {
	const k = data.kpi;
	const cards = [
		{
			icon: "📈",
			color: "blue",
			label: "OMZET TERKUMPUL",
			value: fmt_rupiah(k.omzet),
			sub: k.omzet_change_pct === null
				? `${data.period_label}`
				: change_badge(k.omzet_change_pct) + " " + (data.comparison_label || ""),
		},
		{
			icon: "💹",
			color: "green",
			label: "LABA KOTOR",
			value: fmt_rupiah(k.laba_kotor),
			sub: k.margin_kotor_pct === null ? "Margin kotor –" : `Margin kotor ${k.margin_kotor_pct.toFixed(1)}%`,
		},
		{
			icon: "🧾",
			color: "red",
			label: "PIUTANG BELUM DITAGIH",
			value: fmt_rupiah(k.piutang_belum_ditagih),
			sub: `${k.piutang_count} DO belum invoice`,
		},
		{
			icon: "🧭",
			color: "amber",
			label: "UANG JALAN BELUM CAIR",
			value: fmt_rupiah(k.uang_jalan_belum_cair),
			sub: `${k.uang_jalan_count} DO menunggu`,
		},
		{
			icon: "🚚",
			color: "blue",
			label: "DO AKTIF",
			value: k.do_aktif,
			sub: `${k.do_aktif_jalan} jalan · ${k.do_aktif_tunggu_dokumen} tunggu dokumen`,
		},
		{
			icon: "📋",
			color: "amber",
			label: "APPROVAL PENDING",
			value: fmt_rupiah(k.approval_pending_amount),
			sub: `${k.approval_pending_count} permintaan`,
		},
	];

	const html = cards.map((c) => `
		<div class="sd-kpi">
			<div class="sd-kpi-icon sd-c-${c.color}">${c.icon}</div>
			<div class="sd-kpi-body">
				<div class="sd-kpi-label">${c.label}</div>
				<div class="sd-kpi-value">${c.value}</div>
				<div class="sd-kpi-sub">${c.sub}</div>
			</div>
		</div>
	`).join("");

	state.$wrap.find("#sd-kpis").html(html);
}

function change_badge(pct) {
	const up = pct >= 0;
	return `<span class="sd-change ${up ? "sd-up" : "sd-down"}">${up ? "▲" : "▼"} ${Math.abs(pct).toFixed(1)}%</span>`;
}

// ---------------------------------------------------------------------
// Trend chart
// ---------------------------------------------------------------------
function render_trend(state, data) {
	const el = state.$wrap.find("#sd-trend-chart")[0];
	el.innerHTML = "";

	if (typeof frappe.Chart === "undefined") return;

	state.chart = new frappe.Chart(el, {
		data: {
			labels: data.trend.months,
			datasets: [
				{ name: "Omzet", values: data.trend.omzet },
				{ name: "Laba Kotor", values: data.trend.laba_kotor },
			],
		},
		type: "line",
		height: 220,
		colors: ["#2f6fed", "#16a34a"],
		lineOptions: { regionFill: 1, hideDots: 0 },
		axisOptions: { xIsSeries: 1 },
		tooltipOptions: {
			formatTooltipY: (v) => fmt_rupiah(v),
		},
	});

	state.$wrap.find("#sd-partial-note").text(
		data.is_partial_period ? "*periode berjalan — data belum lengkap." : ""
	);
}

// ---------------------------------------------------------------------
// P&L
// ---------------------------------------------------------------------
function render_pnl(state, data) {
	const p = data.pnl;
	const max = Math.max(Math.abs(p.omzet), Math.abs(p.hpp), Math.abs(p.laba_kotor), Math.abs(p.beban_operasional), Math.abs(p.laba_bersih), 1);

	const rows = [
		{ label: "Omzet", value: p.omzet, color: "blue" },
		{ label: "HPP (Uang Jalan + Komisi Driver)", value: -p.hpp, color: "gray", prefix: "−" },
		{ label: "Laba Kotor", value: p.laba_kotor, color: "amber", bold: true },
		{ label: "Beban Operasional (Cost Center)", value: -p.beban_operasional, color: "gray", prefix: "−" },
		{ label: "Laba Bersih", value: p.laba_bersih, color: p.laba_bersih >= 0 ? "green" : "red", bold: true },
	];

	const html = rows.map((r) => {
		const pct = Math.min(100, Math.abs(r.value) / max * 100);
		const displayValue = r.prefix
			? `${r.prefix}${fmt_rupiah(Math.abs(r.value))}`
			: fmt_rupiah(r.value);
		return `
			<div class="sd-pnl-row ${r.bold ? "sd-pnl-bold" : ""}">
				<div class="sd-pnl-top">
					<span>${r.label}</span>
					<span class="${r.value < 0 ? "sd-neg" : ""}">${displayValue}</span>
				</div>
				<div class="sd-bar-track"><div class="sd-bar-fill sd-c-${r.color}" style="width:${pct}%"></div></div>
			</div>
		`;
	}).join("");

	state.$wrap.find("#sd-pnl-body").html(html);

	const marginLabel = p.margin_bersih_pct === null ? "Margin bersih –" : `Margin bersih ${p.margin_bersih_pct.toFixed(1)}%`;
	state.$wrap.find("#sd-margin-badge").text(marginLabel);
}

// ---------------------------------------------------------------------
// Piutang table
// ---------------------------------------------------------------------
function render_piutang(state, data) {
	state.$wrap.find("#sd-piutang-total").text(
		`Total ${fmt_rupiah(data.piutang_total)} · ${data.piutang_list.length} invoice`
	);

	if (!data.piutang_list.length) {
		state.$wrap.find("#sd-piutang-table").html('<div class="sd-empty">Tidak ada piutang belum ditagih.</div>');
		return;
	}

	const rows = data.piutang_list.map((r) => `
		<tr>
			<td class="sd-mono">${r.do}</td>
			<td>${frappe.utils.escape_html(r.customer)}</td>
			<td>${frappe.datetime.str_to_user(r.selesai)}</td>
			<td><span class="sd-pill ${aging_pill_class(r.umur)}">${r.umur} hari</span></td>
			<td class="sd-right">${fmt_rupiah(r.nilai)}</td>
		</tr>
	`).join("");

	state.$wrap.find("#sd-piutang-table").html(`
		<table class="sd-table">
			<thead><tr><th>NO. DO</th><th>CUSTOMER</th><th>SELESAI</th><th>UMUR</th><th class="sd-right">NILAI</th></tr></thead>
			<tbody>${rows}</tbody>
		</table>
	`);
}

function aging_pill_class(days) {
	if (days <= 7) return "sd-pill-green";
	if (days <= 30) return "sd-pill-amber";
	return "sd-pill-red";
}

// ---------------------------------------------------------------------
// Aging buckets
// ---------------------------------------------------------------------
function render_aging(state, data) {
	const a = data.piutang_aging;
	const total = data.piutang_total || 1;
	const buckets = [
		{ key: "0-30 hari", value: a["0-30"], color: "blue" },
		{ key: "30-60 hari", value: a["30-60"], color: "gray" },
		{ key: "60-90 hari", value: a["60-90"], color: "amber" },
		{ key: "> 90 hari", value: a[">90"], color: "gray" },
	];

	state.$wrap.find("#sd-aging-total").text(`Total ${fmt_rupiah(data.piutang_total)}`);

	const html = buckets.map((b) => `
		<div class="sd-aging-row">
			<div class="sd-aging-label">${b.key}</div>
			<div class="sd-bar-track sd-bar-track-wide"><div class="sd-bar-fill sd-c-${b.color}" style="width:${Math.min(100, b.value / total * 100)}%"></div></div>
			<div class="sd-aging-value">${fmt_rupiah(b.value)}</div>
		</div>
	`).join("");

	state.$wrap.find("#sd-aging-body").html(html);
}

// ---------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------
function render_pipeline(state, data) {
	const p = data.pipeline;

	state.$wrap.find("#sd-pipeline-summary").html(`
		<div class="sd-pipe-stat">
			<div class="sd-pipe-num sd-c-text-blue">${p.masih_diproses}</div>
			<div class="sd-pipe-label">Masih Diproses</div>
		</div>
		<div class="sd-pipe-stat">
			<div class="sd-pipe-num sd-c-text-green">${p.selesai_invoiced}</div>
			<div class="sd-pipe-label">Selesai / Invoiced</div>
		</div>
	`);

	const stages = [
		{ label: "ANTRIAN", value: p.antrian },
		{ label: "DALAM PERJALANAN", value: p.dalam_perjalanan },
		{ label: "DELIVERED / TUNGGU DOKUMEN", value: p.delivered_tunggu_dokumen },
		{ label: "SELESAI / INVOICED", value: p.selesai_invoiced },
	];

	const html = stages.map((s, i) => `
		${i > 0 ? '<div class="sd-pipe-arrow">›</div>' : ""}
		<div class="sd-pipe-box">
			<div class="sd-pipe-box-num">${s.value}</div>
			<div class="sd-pipe-box-label">${s.label}</div>
		</div>
	`).join("");

	state.$wrap.find("#sd-pipeline-stages").html(html);
}

// ---------------------------------------------------------------------
// Uang jalan per rute
// ---------------------------------------------------------------------
function render_rute(state, data) {
	state.$wrap.find("#sd-rute-total").text(
		`Total ${fmt_rupiah(data.uang_jalan_total)} · ${data.uang_jalan_route_count} rute`
	);

	if (!data.uang_jalan_per_rute.length) {
		state.$wrap.find("#sd-rute-body").html('<div class="sd-empty">Tidak ada uang jalan menunggu.</div>');
		state.$wrap.find("#sd-rute-footnote").text("");
		return;
	}

	const max = Math.max(...data.uang_jalan_per_rute.map((r) => r.amount), 1);
	const html = data.uang_jalan_per_rute.map((r) => `
		<div class="sd-rute-row">
			<div class="sd-rute-top">
				<span class="sd-rute-amount">${fmt_rupiah(r.amount)}</span>
			</div>
			<div class="sd-bar-track sd-bar-track-wide"><div class="sd-bar-fill sd-c-amber" style="width:${r.amount / max * 100}%"></div></div>
			<div class="sd-rute-label">${frappe.utils.escape_html(r.rute)} · ${r.count} DO</div>
		</div>
	`).join("");

	state.$wrap.find("#sd-rute-body").html(html);

	const shown = data.uang_jalan_per_rute.length;
	const total = data.uang_jalan_route_count;
	state.$wrap.find("#sd-rute-footnote").text(
		total > shown ? `Menampilkan ${shown} dari ${total} rute — sisanya cek di menu Armada & Driver.` : ""
	);
}

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
function fmt_rupiah(n) {
	n = Math.round(n || 0);
	const sign = n < 0 ? "-" : "";
	return sign + "Rp " + Math.abs(n).toLocaleString("id-ID");
}

function get_shell() {
	return `
		<div class="sd-wrap">
			<div class="sd-kpi-grid" id="sd-kpis"></div>

			<div class="sd-section-title">KINERJA KEUANGAN</div>
			<div class="sd-grid-2">
				<div class="sd-card">
					<div class="sd-card-head">
						<span>TREN OMZET &amp; LABA KOTOR</span>
						<span class="sd-legend"><i style="background:#2f6fed"></i>Omzet <i style="background:#16a34a"></i>Laba Kotor</span>
					</div>
					<div id="sd-trend-chart"></div>
					<div class="sd-footnote" id="sd-partial-note"></div>
				</div>
				<div class="sd-card">
					<div class="sd-card-head">
						<span>RINGKASAN LABA RUGI (P&amp;L)</span>
						<span class="sd-muted" id="sd-margin-badge"></span>
					</div>
					<div id="sd-pnl-body"></div>
				</div>
			</div>

			<div class="sd-section-title">PERLU PERHATIAN</div>
			<div class="sd-grid-2">
				<div class="sd-card">
					<div class="sd-card-head">
						<span>PIUTANG BELUM DITAGIH TERBESAR</span>
						<span class="sd-muted" id="sd-piutang-total"></span>
					</div>
					<div id="sd-piutang-table"></div>
				</div>
				<div class="sd-card">
					<div class="sd-card-head">
						<span>AGING PIUTANG BELUM DITAGIH</span>
						<span class="sd-muted" id="sd-aging-total"></span>
					</div>
					<div id="sd-aging-body"></div>
				</div>
			</div>

			<div class="sd-section-title">OPERASIONAL</div>
			<div class="sd-grid-2">
				<div class="sd-card">
					<div class="sd-card-head">
						<span>PIPELINE DELIVERY ORDER</span>
						<span class="sd-muted">DO aktif, di luar Cancelled</span>
					</div>
					<div class="sd-pipe-summary" id="sd-pipeline-summary"></div>
					<div class="sd-pipe-stages" id="sd-pipeline-stages"></div>
				</div>
				<div class="sd-card">
					<div class="sd-card-head">
						<span>UANG JALAN BELUM CAIR PER RUTE</span>
						<span class="sd-muted" id="sd-rute-total"></span>
					</div>
					<div id="sd-rute-body"></div>
					<div class="sd-footnote" id="sd-rute-footnote"></div>
				</div>
			</div>
		</div>
	`;
}

function inject_styles() {
	if (document.getElementById("dashboard-manager-style")) return;
	const style = document.createElement("style");
	style.id = "dashboard-manager-style";
	style.textContent = `
		.sd-wrap {
			background: #faf8f4;
			padding: 20px;
			border-radius: 8px;
			color: #262321;
			font-size: 13px;
		}
		.sd-kpi-grid {
			display: grid;
			grid-template-columns: repeat(6, minmax(0, 1fr));
			gap: 14px;
			margin-bottom: 24px;
		}
		.sd-kpi {
			background: #fff;
			border: 1px solid #ece7de;
			border-radius: 10px;
			padding: 14px;
			display: flex;
			gap: 10px;
			box-shadow: 0 1px 2px rgba(0,0,0,.03);
		}
		.sd-kpi-icon {
			width: 30px; height: 30px; border-radius: 8px;
			display: flex; align-items: center; justify-content: center;
			font-size: 15px; flex-shrink: 0;
		}
		.sd-c-blue { background: #e8eefd; }
		.sd-c-green { background: #e5f6ea; }
		.sd-c-red { background: #fbe9e9; }
		.sd-c-amber { background: #fbf0da; }
		.sd-kpi-label { font-size: 10px; font-weight: 600; color: #9a9188; letter-spacing: .03em; margin-bottom: 4px; }
		.sd-kpi-value { font-size: 17px; font-weight: 700; color: #201d1a; line-height: 1.2; }
		.sd-kpi-sub { font-size: 11px; color: #9a9188; margin-top: 3px; }
		.sd-change { font-weight: 600; }
		.sd-up { color: #16a34a; }
		.sd-down { color: #dc2626; }

		.sd-section-title {
			font-size: 11px; font-weight: 700; letter-spacing: .06em;
			color: #a39a8d; margin: 22px 0 10px;
		}
		.sd-grid-2 {
			display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
		}
		.sd-card {
			background: #fff; border: 1px solid #ece7de; border-radius: 10px;
			padding: 16px; box-shadow: 0 1px 2px rgba(0,0,0,.03);
		}
		.sd-card-head {
			display: flex; justify-content: space-between; align-items: center;
			font-size: 11px; font-weight: 700; color: #6b645b; letter-spacing: .03em;
			margin-bottom: 12px;
		}
		.sd-muted { font-weight: 500; color: #a39a8d; font-size: 11px; }
		.sd-legend { display: flex; align-items: center; gap: 6px; font-weight: 500; color: #6b645b; }
		.sd-legend i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 2px; }
		.sd-footnote { font-size: 10px; color: #b3aa9d; margin-top: 6px; }

		.sd-pnl-row { margin-bottom: 12px; }
		.sd-pnl-top { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px; }
		.sd-pnl-bold .sd-pnl-top { font-weight: 700; }
		.sd-neg { color: #dc2626; }
		.sd-bar-track { height: 6px; background: #f2ede4; border-radius: 4px; overflow: hidden; }
		.sd-bar-track-wide { height: 8px; }
		.sd-bar-fill { height: 100%; border-radius: 4px; }
		.sd-bar-fill.sd-c-blue { background: #2f6fed; }
		.sd-bar-fill.sd-c-green { background: #16a34a; }
		.sd-bar-fill.sd-c-red { background: #dc2626; }
		.sd-bar-fill.sd-c-amber { background: #d9a441; }
		.sd-bar-fill.sd-c-gray { background: #beb6a8; }

		.sd-table { width: 100%; border-collapse: collapse; font-size: 12px; }
		.sd-table th {
			text-align: left; font-size: 10px; color: #a39a8d; font-weight: 600;
			padding: 6px 8px; border-bottom: 1px solid #ece7de;
		}
		.sd-table td { padding: 8px; border-bottom: 1px solid #f4f0e9; }
		.sd-table .sd-right { text-align: right; }
		.sd-mono { font-family: monospace; font-size: 11px; color: #6b645b; }
		.sd-pill { padding: 2px 8px; border-radius: 20px; font-size: 10px; font-weight: 600; }
		.sd-pill-green { background: #e5f6ea; color: #16a34a; }
		.sd-pill-amber { background: #fbf0da; color: #b7791f; }
		.sd-pill-red { background: #fbe9e9; color: #dc2626; }
		.sd-empty { color: #a39a8d; font-size: 12px; padding: 12px 0; }

		.sd-aging-row { display: grid; grid-template-columns: 70px 1fr 90px; align-items: center; gap: 10px; margin-bottom: 12px; }
		.sd-aging-label { font-size: 11px; color: #6b645b; }
		.sd-aging-value { font-size: 12px; text-align: right; font-weight: 600; }

		.sd-pipe-summary { display: flex; gap: 28px; margin-bottom: 14px; }
		.sd-pipe-num { font-size: 22px; font-weight: 700; }
		.sd-c-text-blue { color: #2f6fed; }
		.sd-c-text-green { color: #16a34a; }
		.sd-pipe-label { font-size: 11px; color: #a39a8d; }
		.sd-pipe-stages { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
		.sd-pipe-box {
			background: #f6f3ec; border-radius: 8px; padding: 10px 12px; flex: 1; min-width: 90px; text-align: center;
		}
		.sd-pipe-box-num { font-size: 16px; font-weight: 700; color: #201d1a; }
		.sd-pipe-box-label { font-size: 9px; color: #9a9188; margin-top: 2px; letter-spacing: .02em; }
		.sd-pipe-arrow { color: #c9c1b4; font-size: 14px; }

		.sd-rute-row { margin-bottom: 12px; }
		.sd-rute-top { display: flex; justify-content: flex-end; margin-bottom: 4px; }
		.sd-rute-amount { font-size: 12px; font-weight: 700; }
		.sd-rute-label { font-size: 11px; color: #9a9188; margin-top: 4px; }

		@media (max-width: 900px) {
			.sd-kpi-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
			.sd-grid-2 { grid-template-columns: 1fr; }
		}
	`;
	document.head.appendChild(style);
}
