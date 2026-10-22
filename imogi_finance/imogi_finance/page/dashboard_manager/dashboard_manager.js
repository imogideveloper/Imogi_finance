/**
 * Dashboard Manager - workshop edition.
 *
 * Data comes from imogi_finance.api.workshop_dashboard; the P&L figures are GL-Entry sourced so
 * they reconcile 1:1 with the standard Profit and Loss Statement report.
 *
 * Visual system (all of it token-driven so light/dark swap in one place):
 *   - series 1 blue / series 2 orange   -> the only two-series chart (Omzet vs Laba Kotor)
 *   - a single-hue blue ordinal ramp    -> ordered scales (pipeline stages, AR aging buckets)
 *   - status green/amber/red            -> state only (overdue, profit sign), always with a label
 * Each set was checked for CVD separation, lightness band and surface contrast in both modes
 * before being wired in - do not hand-tweak a hex here without re-checking the set it belongs to.
 */

const MONTHS_ID_LONG = [
	"Januari", "Februari", "Maret", "April", "Mei", "Juni",
	"Juli", "Agustus", "September", "Oktober", "November", "Desember",
];

const STYLE_ID = "dm-dashboard-manager-style-v2";

// Feather-style paths. Inline SVG rather than emoji, which wkhtmltopdf can't render (no
// color-emoji font in the PDF renderer).
const ICONS = {
	"trending-up": '<polyline points="3 17 9 11 13 15 21 7"/><polyline points="14 7 21 7 21 14"/>',
	"trending-down": '<polyline points="3 7 9 13 13 9 21 17"/><polyline points="14 17 21 17 21 10"/>',
	"bar-chart": '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
	wallet: '<path d="M21 12V7H5a2 2 0 0 1 0-4h14v4"/><path d="M3 5v14a2 2 0 0 0 2 2h16v-5"/><path d="M18 12a2 2 0 0 0 0 4h4v-4z"/>',
	"file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
	"credit-card": '<rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/>',
	tool: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
	clipboard: '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1"/>',
	inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
	"arrow-right": '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
	alert: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
};

function icon(name, size) {
	return `<svg class="dm-icon" width="${size || 16}" height="${size || 16}" viewBox="0 0 24 24" fill="none"
		stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
		aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

// ---------------------------------------------------------------------------
// Page bootstrap
// ---------------------------------------------------------------------------

frappe.pages["dashboard-manager"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Dashboard Manager",
		single_column: true,
	});

	inject_styles();

	// Desk wraps page head and body in bootstrap .container elements, which cap the width at
	// ~1140px and leave a wide empty gutter either side on a big monitor. A dashboard wants the
	// whole screen, so tag this page's own wrapper and widen only its two containers - scoped
	// by class off the element frappe hands us, so no other desk page is touched.
	$(wrapper).addClass("dm-full-width");

	const $wrap = $(get_shell()).appendTo(page.main);
	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const state = {
		page, $wrap, chart: null,
		company: null,
		period_type: "month",
		period_date: frappe.datetime.get_today(),
		period_year: today.getFullYear(),
		period_month: today.getMonth() + 1,
		period_week: week_of_month(today),
		period_start: frappe.datetime.month_start(),
		period_end: frappe.datetime.get_today(),
		trend_as_table: false,
	};

	frappe.call({ method: "imogi_finance.api.workshop_dashboard.get_filter_meta" }).then((r) => {
		const meta = r.message || {};
		state.company = meta.default_company || frappe.defaults.get_user_default("Company");
		setup_filters(page, state, meta.years || [today.getFullYear()]);
		setup_toolbar(state);
		page.set_primary_action(__("Refresh"), () => load(state), "refresh");
		page.add_inner_button(__("Pusat Approval"), () => frappe.set_route("approval-center"));
		page.add_inner_button(__("Download PDF"), () => download_pdf(state));
		load(state);
	});
};

function week_of_month(date_obj) {
	return Math.min(5, Math.ceil(date_obj.getDate() / 7));
}

// ---------------------------------------------------------------------------
// Filters - Frappe page fields (precise control) + in-page preset chips (one click)
// ---------------------------------------------------------------------------

function setup_filters(page, state, years) {
	const on_change = (key, field, cast) => () => {
		if (state._suppress) return;
		const raw = field().get_value();
		state[key] = cast ? cast(raw) : raw;
		update_filter_visibility(state);
		sync_chips(state);
		load(state);
	};

	state.company_field = page.add_field({
		label: __("Company"),
		fieldtype: "Link",
		fieldname: "company",
		options: "Company",
		default: state.company,
		change: () => {
			if (state._suppress) return;
			const value = state.company_field.get_value();
			if (!value || value === state.company) return;
			state.company = value;
			load(state);
		},
	});
	state.company_field.set_value(state.company);

	state.type_field = page.add_field({
		label: __("Tipe Periode"),
		fieldtype: "Select",
		fieldname: "period_type",
		options: [
			{ label: __("Hari"), value: "day" },
			{ label: __("Minggu"), value: "week" },
			{ label: __("Bulan"), value: "month" },
			{ label: __("Tahun"), value: "year" },
			{ label: __("Rentang Tanggal"), value: "range" },
			{ label: __("Semua Waktu"), value: "all" },
		],
		default: state.period_type,
		change: on_change("period_type", () => state.type_field, (v) => v || "all"),
	});

	state.date_field = page.add_field({
		label: __("Tanggal"),
		fieldtype: "Date",
		fieldname: "period_date",
		default: state.period_date,
		change: on_change("period_date", () => state.date_field, (v) => v || frappe.datetime.get_today()),
	});

	state.year_field = page.add_field({
		label: __("Tahun"),
		fieldtype: "Select",
		fieldname: "period_year",
		options: years.map((y) => ({ label: String(y), value: y })),
		default: state.period_year,
		change: () => {
			if (state._suppress) return;
			state.period_year = cint(state.year_field.get_value()) || state.period_year;
			refresh_week_options(state);
			sync_chips(state);
			load(state);
		},
	});

	state.month_field = page.add_field({
		label: __("Bulan"),
		fieldtype: "Select",
		fieldname: "period_month",
		options: MONTHS_ID_LONG.map((m, i) => ({ label: __(m), value: i + 1 })),
		default: state.period_month,
		change: () => {
			if (state._suppress) return;
			state.period_month = cint(state.month_field.get_value()) || state.period_month;
			refresh_week_options(state);
			sync_chips(state);
			load(state);
		},
	});

	state.week_field = page.add_field({
		label: __("Minggu ke-"),
		fieldtype: "Select",
		fieldname: "period_week",
		options: build_week_options(state.period_year, state.period_month),
		default: state.period_week,
		change: on_change("period_week", () => state.week_field, (v) => cint(v) || 1),
	});

	state.start_field = page.add_field({
		label: __("Dari Tanggal"),
		fieldtype: "Date",
		fieldname: "period_start",
		default: state.period_start,
		change: on_change("period_start", () => state.start_field),
	});

	state.end_field = page.add_field({
		label: __("Sampai Tanggal"),
		fieldtype: "Date",
		fieldname: "period_end",
		default: state.period_end,
		change: on_change("period_end", () => state.end_field),
	});

	update_filter_visibility(state);
}

function update_filter_visibility(state) {
	const t = state.period_type;
	state.date_field.$wrapper.toggle(t === "day");
	state.year_field.$wrapper.toggle(t === "week" || t === "month" || t === "year");
	state.month_field.$wrapper.toggle(t === "week" || t === "month");
	state.week_field.$wrapper.toggle(t === "week");
	state.start_field.$wrapper.toggle(t === "range");
	state.end_field.$wrapper.toggle(t === "range");
}

function build_week_options(year, month) {
	const daysInMonth = new Date(year, month, 0).getDate();
	const weekCount = daysInMonth >= 29 ? 5 : 4;
	const options = [];
	for (let w = 1; w <= weekCount; w++) {
		const startDay = (w - 1) * 7 + 1;
		const endDay = Math.min(startDay + 6, daysInMonth);
		options.push({ label: __("Minggu {0} ({1}-{2})", [w, startDay, endDay]), value: w });
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

// --- preset chips -----------------------------------------------------------

function preset_definitions() {
	const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	return [
		{ key: "day", label: __("Hari Ini"), values: { period_type: "day", period_date: frappe.datetime.get_today() } },
		{
			key: "week",
			label: __("Minggu Ini"),
			values: {
				period_type: "week", period_year: today.getFullYear(),
				period_month: today.getMonth() + 1, period_week: week_of_month(today),
			},
		},
		{
			key: "month",
			label: __("Bulan Ini"),
			values: { period_type: "month", period_year: today.getFullYear(), period_month: today.getMonth() + 1 },
		},
		{ key: "year", label: __("Tahun Ini"), values: { period_type: "year", period_year: today.getFullYear() } },
		{ key: "all", label: __("Semua Waktu"), values: { period_type: "all" } },
	];
}

function setup_toolbar(state) {
	const presets = preset_definitions();
	const html = presets.map((p) => `
		<button type="button" class="dm-chip" data-preset="${p.key}" aria-pressed="false">${p.label}</button>
	`).join("");
	state.$wrap.find("#dm-chips").html(html);

	state.$wrap.find("#dm-chips").on("click", ".dm-chip", function () {
		const preset = presets.find((p) => p.key === $(this).data("preset"));
		if (!preset) return;
		apply_preset(state, preset);
	});

	state.$wrap.find("#dm-trend-toggle").on("click", function () {
		state.trend_as_table = !state.trend_as_table;
		$(this).attr("aria-pressed", String(state.trend_as_table))
			.text(state.trend_as_table ? __("Grafik") : __("Tabel"));
		if (state._data) render_trend(state, state._data);
	});

	sync_chips(state);
}

function apply_preset(state, preset) {
	// Push the preset into the real page fields (so the two controls never disagree) without
	// letting each set_value fire its own reload - one load() at the end instead of five.
	state._suppress = true;
	Object.assign(state, preset.values);
	const writes = [
		state.type_field.set_value(state.period_type),
		state.date_field.set_value(state.period_date),
		state.year_field.set_value(state.period_year),
		state.month_field.set_value(state.period_month),
	];
	Promise.all(writes)
		.then(() => {
			refresh_week_options(state);
			return state.week_field.set_value(state.period_week);
		})
		.catch(() => {})
		.then(() => {
			state._suppress = false;
			update_filter_visibility(state);
			sync_chips(state);
			load(state);
		});
}

function sync_chips(state) {
	const presets = preset_definitions();
	const active = presets.find((p) => {
		return Object.keys(p.values).every((k) => String(state[k]) === String(p.values[k]));
	});
	state.$wrap.find("#dm-chips .dm-chip").each(function () {
		const on = active && $(this).data("preset") === active.key;
		$(this).attr("aria-pressed", String(!!on)).toggleClass("is-active", !!on);
	});
}

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------

function load(state) {
	// Overlapping requests: Refresh pressed mid-flight, or a control firing change twice. An
	// older response arriving after a newer one must never overwrite the DOM with stale data.
	const requestId = (state._loadSeq = (state._loadSeq || 0) + 1);
	// Refetch holds the previous render at reduced opacity - no global freeze overlay, no
	// skeleton flash, no layout jump.
	state.$wrap.addClass("is-loading");

	frappe.call({
		method: "imogi_finance.api.workshop_dashboard.get_dashboard_data",
		args: {
			company: state.company,
			period_type: state.period_type || "all",
			period_date: state.period_date,
			period_year: state.period_year,
			period_month: state.period_month,
			period_week: state.period_week,
			period_start: state.period_start,
			period_end: state.period_end,
		},
	})
		.then((r) => {
			if (requestId !== state._loadSeq) return; // a newer request has since taken over
			state.$wrap.removeClass("is-loading");
			if (!r.message) return;
			render(state, r.message);
		})
		.catch(() => {
			if (requestId === state._loadSeq) state.$wrap.removeClass("is-loading");
		});
}

function render(state, data) {
	state._data = data;
	state.last_period_label = data.period_label;

	render_context(state, data);
	render_hero(state, data);
	render_tiles(state, data);
	render_trend(state, data);
	render_pnl(state, data);
	render_piutang(state, data);
	render_aging(state, data);
	render_pipeline(state, data);
	render_hutang(state, data);

	bind_resize(state);
}

function render_context(state, data) {
	state.$wrap.find("#dm-period-label").text(data.period_label);
	state.$wrap.find("#dm-company-label").text(data.company || "");
	state.$wrap.find("#dm-refreshed").text(
		__("diperbarui {0}", [moment().format("HH:mm")])
	);
	state.$wrap.find("#dm-partial-badge").toggle(!!data.is_partial_period);
}

// ---------------------------------------------------------------------------
// Hero figure (exactly one per view) + stat tiles
// ---------------------------------------------------------------------------

function render_hero(state, data) {
	const k = data.kpi;
	const delta = k.omzet_change_pct === null || k.omzet_change_pct === undefined
		? `<span class="dm-hero-meta">${frappe.utils.escape_html(data.period_label)}</span>`
		: `${delta_chip(k.omzet_change_pct)}<span class="dm-hero-meta">${frappe.utils.escape_html(data.comparison_label || "")}</span>`;

	state.$wrap.find("#dm-hero").html(`
		<div class="dm-hero-head">
			<span class="dm-hero-label">${__("Omzet Terkumpul")}</span>
			${sparkline(data.trend.omzet)}
		</div>
		<div class="dm-hero-value" title="${fmt_rupiah(k.omzet)}">${fmt_compact(k.omzet)}</div>
		<div class="dm-hero-exact">${fmt_rupiah(k.omzet)}</div>
		<div class="dm-hero-delta">${delta}</div>
		<div class="dm-hero-foot">
			<span class="dm-swatch dm-sw-mute"></span>
			${__("HPP")} <b>${fmt_compact(data.pnl.hpp)}</b>
			<span class="dm-dot-sep">·</span>
			${k.omzet ? __("{0} dari omzet", [fmt_pct(data.pnl.hpp / k.omzet * 100)]) : __("belum ada omzet")}
		</div>
	`);
}

function render_tiles(state, data) {
	const k = data.kpi;
	const p = data.pnl;
	const profit_positive = p.laba_bersih >= 0;

	const tiles = [
		{
			icon: "bar-chart",
			label: __("Laba Bersih"),
			value: fmt_compact(p.laba_bersih),
			exact: fmt_rupiah(p.laba_bersih),
			sub: p.margin_bersih_pct === null
				? __("Margin bersih –")
				: __("Margin bersih {0}", [fmt_pct(p.margin_bersih_pct)]),
			chip: profit_positive
				? { tone: "good", icon: "trending-up", text: __("Laba") }
				: { tone: "crit", icon: "trending-down", text: __("Rugi") },
		},
		{
			icon: "wallet",
			label: __("Laba Kotor"),
			value: fmt_compact(k.laba_kotor),
			exact: fmt_rupiah(k.laba_kotor),
			sub: __("Omzet − HPP (part + jasa)"),
		},
		{
			icon: "file-text",
			label: __("Piutang Belum Lunas"),
			value: fmt_compact(k.piutang_belum_lunas),
			exact: fmt_rupiah(k.piutang_belum_lunas),
			sub: __("{0} invoice terbuka", [k.piutang_count]),
			route: () => goto_list("Sales Invoice", { company: state.company, outstanding_amount: [">", 0] }),
		},
		{
			icon: "credit-card",
			label: __("Hutang Supplier"),
			value: fmt_compact(k.hutang_belum_lunas),
			exact: fmt_rupiah(k.hutang_belum_lunas),
			sub: __("{0} invoice belum dibayar", [k.hutang_count]),
			route: () => goto_list("Purchase Invoice", { company: state.company, outstanding_amount: [">", 0] }),
		},
		{
			icon: "tool",
			label: __("Service Order Aktif"),
			value: String(k.so_aktif),
			sub: __("{0} dikerjakan · {1} tunggu part", [k.so_aktif_dikerjakan, k.so_aktif_tunggu_part]),
			route: () => goto_list("Garage Service Order", {
				status: ["in", ["Open", "Waiting Part", "Prepared", "In Progress", "Finished", "QC Review", "Waiting Payment"]],
			}),
		},
		{
			icon: "clipboard",
			label: __("Approval Pending"),
			value: fmt_compact(k.approval_pending_amount),
			exact: fmt_rupiah(k.approval_pending_amount),
			sub: __("{0} permintaan menunggu", [k.approval_pending_count]),
			route: () => frappe.set_route("approval-center"),
		},
	];

	const html = tiles.map((t, i) => `
		<div class="dm-tile${t.route ? " is-clickable" : ""}" ${t.route ? `tabindex="0" role="button" data-tile="${i}"` : ""}>
			<div class="dm-tile-head">
				<span class="dm-tile-icon">${icon(t.icon, 14)}</span>
				<span class="dm-tile-label">${t.label}</span>
				${t.chip ? status_chip(t.chip) : ""}
			</div>
			<div class="dm-tile-value"${t.exact ? ` title="${t.exact}"` : ""}>${t.value}</div>
			<div class="dm-tile-sub">${t.sub}</div>
			${t.route ? `<span class="dm-tile-go">${icon("arrow-right", 13)}</span>` : ""}
		</div>
	`).join("");

	const $tiles = state.$wrap.find("#dm-tiles").html(html);
	$tiles.find("[data-tile]").each(function () {
		const handler = tiles[cint($(this).data("tile"))].route;
		$(this).on("click", handler).on("keydown", (e) => {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				handler();
			}
		});
	});
}

function delta_chip(pct) {
	const up = pct >= 0;
	// Direction is carried by the arrow + sign as well as the hue, so it never reads by color alone.
	return `<span class="dm-delta ${up ? "dm-tone-good" : "dm-tone-crit"}">
		${icon(up ? "trending-up" : "trending-down", 13)}${up ? "+" : "−"}${fmt_pct(Math.abs(pct))}
	</span>`;
}

function status_chip(chip) {
	return `<span class="dm-chip-status dm-tone-${chip.tone}">${icon(chip.icon, 11)}${chip.text}</span>`;
}

// ---------------------------------------------------------------------------
// Trend - hand-rolled SVG so the marks, crosshair and theming follow the spec exactly
// ---------------------------------------------------------------------------

const TREND_SERIES = [
	{ key: "omzet", name: "Omzet", token: "--dm-s1" },
	{ key: "laba_kotor", name: "Laba Kotor", token: "--dm-s2" },
];

function render_trend(state, data) {
	const $body = state.$wrap.find("#dm-trend-body");
	const trend = data.trend || { months: [], omzet: [], laba_kotor: [] };

	if (!trend.months.length) {
		$body.html(empty_state(__("Belum ada data pada periode ini.")));
		return;
	}

	if (state.trend_as_table) {
		$body.html(trend_table(trend));
		return;
	}

	const width = Math.max(320, Math.floor($body.width() || 640));
	$body.html(line_chart_svg(trend, width));
	bind_trend_hover(state, $body, trend, width);
}

function trend_table(trend) {
	const rows = trend.months.map((label, i) => `
		<tr>
			<td>${frappe.utils.escape_html(label)}</td>
			<td class="dm-num">${fmt_rupiah(trend.omzet[i])}</td>
			<td class="dm-num">${fmt_rupiah(trend.laba_kotor[i])}</td>
		</tr>
	`).join("");
	return `
		<div class="dm-table-scroll">
			<table class="dm-table">
				<thead><tr>
					<th>${__("Periode")}</th>
					<th class="dm-num">${__("Omzet")}</th>
					<th class="dm-num">${__("Laba Kotor")}</th>
				</tr></thead>
				<tbody>${rows}</tbody>
			</table>
		</div>
	`;
}

function chart_geometry(trend, width) {
	// On a phone the card is ~330px wide; the desktop axis gutter alone would eat a fifth of it.
	const compact = width < 480;
	const height = compact ? 208 : 248;
	const pad = compact
		? { top: 12, right: 12, bottom: 26, left: 44 }
		: { top: 16, right: 18, bottom: 30, left: 62 };
	const values = [].concat(trend.omzet || [], trend.laba_kotor || []).map((v) => flt(v));
	const rawMax = Math.max(0, ...values);
	const rawMin = Math.min(0, ...values);
	const max = nice_ceil(rawMax || 1);
	const min = rawMin < 0 ? -nice_ceil(Math.abs(rawMin)) : 0;
	const plotW = width - pad.left - pad.right;
	const plotH = height - pad.top - pad.bottom;
	const n = trend.months.length;

	const x = (i) => (n === 1 ? pad.left + plotW / 2 : pad.left + (plotW * i) / (n - 1));
	const y = (v) => pad.top + plotH - ((flt(v) - min) / (max - min || 1)) * plotH;

	const tickCount = compact ? 3 : 4;
	const ticks = [];
	for (let t = 0; t <= tickCount; t++) {
		const value = min + ((max - min) * t) / tickCount;
		ticks.push({ value, y: y(value) });
	}

	return { width, height, pad, plotW, plotH, min, max, x, y, ticks, n, compact };
}

function line_chart_svg(trend, width) {
	const g = chart_geometry(trend, width);
	const fmt_tick = axis_formatter(Math.max(Math.abs(g.max), Math.abs(g.min)));

	// Hairline, solid gridlines one step off the surface - recessive by design.
	const grid = g.ticks.map((t) => `
		<line class="dm-gridline" x1="${g.pad.left}" y1="${t.y.toFixed(1)}" x2="${width - g.pad.right}" y2="${t.y.toFixed(1)}"/>
		<text class="dm-axis dm-axis-y" x="${g.pad.left - 10}" y="${(t.y + 4).toFixed(1)}">${fmt_tick(t.value)}</text>
	`).join("");

	const baselineY = g.y(0);
	const baseline = g.min < 0
		? `<line class="dm-baseline" x1="${g.pad.left}" y1="${baselineY.toFixed(1)}" x2="${width - g.pad.right}" y2="${baselineY.toFixed(1)}"/>`
		: "";

	// X labels thinned so they never collide. Stepping back from the last point (rather than
	// forward from the first and then forcing the last one in) keeps the gaps even and always
	// keeps the latest period, which is the label that matters most.
	const step = Math.max(1, Math.ceil(g.n / (g.compact ? 4 : 8)));
	const shown = new Set();
	for (let i = g.n - 1; i >= 0; i -= step) shown.add(i);
	const xLabels = trend.months.map((label, i) => {
		if (!shown.has(i)) return "";
		const anchor = i === 0 ? "start" : i === g.n - 1 ? "end" : "middle";
		return `<text class="dm-axis" x="${g.x(i).toFixed(1)}" y="${g.height - 10}" text-anchor="${anchor}">${frappe.utils.escape_html(label)}</text>`;
	}).join("");

	const series = TREND_SERIES.map((s, si) => {
		const vals = (trend[s.key] || []).map((v) => flt(v));
		const points = vals.map((v, i) => `${g.x(i).toFixed(1)},${g.y(v).toFixed(1)}`).join(" ");
		// Area wash only under the headline series - two overlapping washes go muddy.
		const area = si === 0
			? `<polygon class="dm-area" points="${g.pad.left},${baselineY.toFixed(1)} ${points} ${(width - g.pad.right).toFixed(1)},${baselineY.toFixed(1)}"/>`
			: "";
		const lastI = vals.length - 1;
		const endDot = `<circle class="dm-end-dot" cx="${g.x(lastI).toFixed(1)}" cy="${g.y(vals[lastI]).toFixed(1)}" r="4.5"/>`;
		return `<g class="dm-series dm-series-${si + 1}">${area}
			<polyline class="dm-line" points="${points}"/>
			${endDot}
		</g>`;
	}).join("");

	// One selective direct label: the headline series' last point. The legend plus the
	// crosshair readout carry everything else, so nothing needs a number on every point.
	const omzet = (trend.omzet || []).map((v) => flt(v));
	const lastI = omzet.length - 1;
	const labelX = Math.min(g.x(lastI), width - g.pad.right - 4);
	const labelY = Math.max(g.pad.top + 10, g.y(omzet[lastI]) - 12);
	const endLabel = `<text class="dm-end-label" x="${labelX.toFixed(1)}" y="${labelY.toFixed(1)}" text-anchor="end">${fmt_tick(omzet[lastI])}</text>`;

	const hover = `
		<g class="dm-crosshair" style="display:none">
			<line class="dm-crosshair-line" y1="${g.pad.top}" y2="${g.pad.top + g.plotH}"/>
			<circle class="dm-hover-dot dm-hover-1" r="4.5"/>
			<circle class="dm-hover-dot dm-hover-2" r="4.5"/>
		</g>
		<rect class="dm-hit" x="${g.pad.left}" y="${g.pad.top}" width="${g.plotW}" height="${g.plotH}" fill="transparent"/>
	`;

	return `<svg class="dm-chart" viewBox="0 0 ${width} ${g.height}" width="100%" height="${g.height}"
		role="img" aria-label="${__("Tren omzet dan laba kotor")}">
		${grid}${baseline}${series}${endLabel}${xLabels}${hover}
	</svg>`;
}

function bind_trend_hover(state, $body, trend, width) {
	const g = chart_geometry(trend, width);
	const svg = $body.find("svg.dm-chart")[0];
	if (!svg) return;
	const $cross = $body.find(".dm-crosshair");
	const $line = $body.find(".dm-crosshair-line");
	const $dots = [$body.find(".dm-hover-1"), $body.find(".dm-hover-2")];

	const show = (clientX) => {
		const box = svg.getBoundingClientRect();
		const scale = width / box.width;
		const localX = (clientX - box.left) * scale;
		let idx = 0;
		let best = Infinity;
		for (let i = 0; i < g.n; i++) {
			const d = Math.abs(g.x(i) - localX);
			if (d < best) { best = d; idx = i; }
		}
		$cross.css("display", "");
		$line.attr({ x1: g.x(idx), x2: g.x(idx) });
		TREND_SERIES.forEach((s, si) => {
			$dots[si].attr({ cx: g.x(idx), cy: g.y(flt((trend[s.key] || [])[idx])) });
		});

		const rows = TREND_SERIES.map((s, si) => `
			<div class="dm-tt-row">
				<span class="dm-tt-key dm-tt-key-${si + 1}"></span>
				<span class="dm-tt-name">${__(s.name)}</span>
				<span class="dm-tt-value">${fmt_rupiah((trend[s.key] || [])[idx])}</span>
			</div>
		`).join("");
		show_tooltip(`<div class="dm-tt-title">${frappe.utils.escape_html(trend.months[idx])}</div>${rows}`,
			box.left + g.x(idx) / scale, box.top + 8);
	};

	$body.find(".dm-hit")
		.on("pointermove", (e) => show(e.clientX))
		.on("pointerleave", () => { $cross.css("display", "none"); hide_tooltip(); });

	// Keyboard parity: focusing the chart steps through indexes with the same readout.
	svg.setAttribute("tabindex", "0");
	let kbIdx = g.n - 1;
	$(svg).on("keydown", (e) => {
		if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
		e.preventDefault();
		kbIdx = Math.max(0, Math.min(g.n - 1, kbIdx + (e.key === "ArrowRight" ? 1 : -1)));
		const box = svg.getBoundingClientRect();
		show(box.left + (g.x(kbIdx) / (width / box.width)));
	}).on("blur", () => { $cross.css("display", "none"); hide_tooltip(); });
}

function sparkline(values) {
	const vals = (values || []).map((v) => flt(v));
	if (vals.length < 2) return "";
	const w = 108;
	const h = 30;
	const max = Math.max(...vals);
	const min = Math.min(0, ...vals);
	const span = max - min || 1;
	const x = (i) => (w * i) / (vals.length - 1);
	const y = (v) => h - 3 - ((v - min) / span) * (h - 6);
	const points = vals.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
	const lastI = vals.length - 1;
	return `<svg class="dm-spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
		<polyline class="dm-spark-line" points="${points}"/>
		<circle class="dm-spark-dot" cx="${x(lastI).toFixed(1)}" cy="${y(vals[lastI]).toFixed(1)}" r="3"/>
	</svg>`;
}

// ---------------------------------------------------------------------------
// P&L statement
// ---------------------------------------------------------------------------

function render_pnl(state, data) {
	const p = data.pnl;
	const max = Math.max(
		Math.abs(p.omzet), Math.abs(p.hpp), Math.abs(p.laba_kotor),
		Math.abs(p.beban_operasional), Math.abs(p.laba_bersih), 1
	);

	const rows = [
		{ label: __("Omzet"), value: p.omzet, bar: "s1" },
		{ label: __("HPP (part + jasa)"), value: -p.hpp, bar: "mute", deduct: true },
		{ label: __("Laba Kotor"), value: p.laba_kotor, bar: "s1", subtotal: true },
		{ label: __("Beban Operasional"), value: -p.beban_operasional, bar: "mute", deduct: true },
	];

	const html = rows.map((r) => `
		<div class="dm-pnl-row${r.subtotal ? " is-subtotal" : ""}">
			<div class="dm-pnl-top">
				<span class="dm-pnl-label">${r.label}</span>
				<span class="dm-pnl-value${r.deduct ? " is-deduct" : ""}">${r.deduct ? "−" : ""}${fmt_rupiah(Math.abs(r.value))}</span>
			</div>
			<div class="dm-track" role="presentation">
				<div class="dm-fill dm-fill-${r.bar}" style="width:${(Math.abs(r.value) / max * 100).toFixed(1)}%"></div>
			</div>
		</div>
	`).join("");

	const positive = p.laba_bersih >= 0;
	const net = `
		<div class="dm-pnl-net ${positive ? "is-good" : "is-crit"}">
			<div class="dm-pnl-net-top">
				<span>${__("Laba Bersih")}</span>
				<span class="dm-pnl-net-value">${fmt_rupiah(p.laba_bersih)}</span>
			</div>
			<div class="dm-track">
				<div class="dm-fill ${positive ? "dm-fill-good" : "dm-fill-crit"}" style="width:${(Math.abs(p.laba_bersih) / max * 100).toFixed(1)}%"></div>
			</div>
			<div class="dm-pnl-net-foot">
				${status_chip(positive
					? { tone: "good", icon: "trending-up", text: __("Laba") }
					: { tone: "crit", icon: "trending-down", text: __("Rugi") })}
				<span>${p.margin_bersih_pct === null ? __("Margin bersih –") : __("Margin bersih {0}", [fmt_pct(p.margin_bersih_pct)])}</span>
			</div>
		</div>
	`;

	state.$wrap.find("#dm-pnl-body").html(html + net);
	state.$wrap.find("#dm-pnl-badge").text(
		p.margin_bersih_pct === null ? __("Margin bersih –") : __("Margin bersih {0}", [fmt_pct(p.margin_bersih_pct)])
	);
}

// ---------------------------------------------------------------------------
// Piutang
// ---------------------------------------------------------------------------

function render_piutang(state, data) {
	state.$wrap.find("#dm-piutang-meta").text(
		__("Total {0} · {1} invoice", [fmt_compact(data.piutang_total), data.kpi.piutang_count])
	);

	if (!data.piutang_list.length) {
		state.$wrap.find("#dm-piutang-body").html(empty_state(__("Tidak ada piutang belum lunas.")));
		return;
	}

	// data-label drives the phone layout, where each row collapses into a labelled block
	// instead of a 5-column table nobody can read at 390px.
	const rows = data.piutang_list.map((r) => `
		<tr tabindex="0" role="button" data-invoice="${frappe.utils.escape_html(r.invoice)}">
			<td class="dm-mono" data-label="${__("Invoice")}">${frappe.utils.escape_html(r.invoice)}</td>
			<td class="dm-ellipsis" data-label="${__("Customer")}" title="${frappe.utils.escape_html(r.customer)}">${frappe.utils.escape_html(r.customer)}</td>
			<td class="dm-nowrap" data-label="${__("Tanggal")}">${frappe.datetime.str_to_user(r.tanggal)}</td>
			<td data-label="${__("Umur")}">${age_chip(r.umur)}</td>
			<td class="dm-num" data-label="${__("Nilai")}">${fmt_rupiah(r.nilai)}</td>
		</tr>
	`).join("");

	const $body = state.$wrap.find("#dm-piutang-body").html(`
		<div class="dm-table-scroll">
			<table class="dm-table dm-table-hover dm-table-stack">
				<thead><tr>
					<th>${__("Invoice")}</th>
					<th>${__("Customer")}</th>
					<th>${__("Tanggal")}</th>
					<th>${__("Umur")}</th>
					<th class="dm-num">${__("Nilai")}</th>
				</tr></thead>
				<tbody>${rows}</tbody>
			</table>
		</div>
	`);

	const open = (name) => frappe.set_route("Form", "Sales Invoice", name);
	$body.find("tr[data-invoice]")
		.on("click", function () { open($(this).data("invoice")); })
		.on("keydown", function (e) {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				open($(this).data("invoice"));
			}
		});
}

function age_chip(days) {
	// Status tone always ships with the number itself, never hue alone.
	const tone = days <= 30 ? "good" : days <= 60 ? "warn" : "crit";
	return `<span class="dm-chip-status dm-tone-${tone}">${days} ${__("hari")}</span>`;
}

// ---------------------------------------------------------------------------
// Aging - ordered buckets on a single-hue ordinal ramp, stacked share + table twin
// ---------------------------------------------------------------------------

function render_aging(state, data) {
	const a = data.piutang_aging || {};
	const buckets = [
		{ label: __("0-30 hari"), value: flt(a["0-30"]), step: 1 },
		{ label: __("30-60 hari"), value: flt(a["30-60"]), step: 2 },
		{ label: __("60-90 hari"), value: flt(a["60-90"]), step: 3 },
		{ label: __("> 90 hari"), value: flt(a[">90"]), step: 5 },
	];
	const total = buckets.reduce((sum, b) => sum + b.value, 0);

	state.$wrap.find("#dm-aging-meta").text(__("Total {0}", [fmt_compact(total)]));

	if (!total) {
		state.$wrap.find("#dm-aging-body").html(empty_state(__("Belum ada piutang terbuka.")));
		return;
	}

	// 2px surface gaps do the separating between segments - no strokes around the marks.
	const segments = buckets.filter((b) => b.value > 0).map((b) => `
		<div class="dm-seg dm-ord-${b.step}" style="flex:${(b.value / total).toFixed(4)}"
			tabindex="0" role="img"
			data-tip="${frappe.utils.escape_html(b.label)}|${fmt_rupiah(b.value)} · ${fmt_pct(b.value / total * 100)}"
			aria-label="${frappe.utils.escape_html(b.label)}: ${fmt_rupiah(b.value)}"></div>
	`).join("");

	const rows = buckets.map((b) => `
		<div class="dm-aging-row">
			<span class="dm-swatch dm-ord-${b.step}"></span>
			<span class="dm-aging-label">${b.label}</span>
			<span class="dm-aging-share">${fmt_pct(total ? b.value / total * 100 : 0)}</span>
			<span class="dm-aging-value">${fmt_rupiah(b.value)}</span>
		</div>
	`).join("");

	// Everything past 60 days, as one number - the question a manager actually asks of an
	// aging table. Meter track is a lighter step of the same blue ramp, so the unfilled part
	// still reads as part of the scale.
	const at_risk = buckets[2].value + buckets[3].value;
	const risk_pct = total ? (at_risk / total) * 100 : 0;
	const risk_tone = risk_pct >= 40 ? "crit" : risk_pct >= 20 ? "warn" : "good";
	const risk_word = risk_pct >= 40 ? __("perlu tindakan") : risk_pct >= 20 ? __("perlu dipantau") : __("terkendali");

	const $body = state.$wrap.find("#dm-aging-body").html(`
		<div class="dm-stack">${segments}</div>
		<div class="dm-aging-rows">${rows}</div>
		<div class="dm-risk">
			<div class="dm-risk-top">
				<span>${__("Piutang berisiko (> 60 hari)")}</span>
				<b>${fmt_rupiah(at_risk)}</b>
			</div>
			<div class="dm-track dm-track-ramp">
				<div class="dm-fill dm-ord-5" style="width:${Math.min(100, risk_pct).toFixed(1)}%"></div>
			</div>
			<div class="dm-risk-foot">
				<span>${__("{0} dari total piutang", [fmt_pct(risk_pct)])}</span>
				<span class="dm-risk-chip">${status_chip({ tone: risk_tone, icon: risk_tone === "good" ? "trending-up" : "alert", text: risk_word })}</span>
			</div>
		</div>
	`);
	bind_tips($body);
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

const PIPELINE_STAGES = [
	{ key: "antrian", label: "Antrian", step: 1, statuses: ["Open"] },
	{ key: "tunggu_part", label: "Tunggu Part", step: 2, statuses: ["Waiting Part"] },
	{ key: "dikerjakan", label: "Dikerjakan", step: 3, statuses: ["Prepared", "In Progress"] },
	{ key: "siap_diambil", label: "Siap Diambil", step: 4, statuses: ["Finished", "QC Review", "Waiting Payment"] },
	{ key: "selesai", label: "Selesai", step: 5, statuses: ["Completed"] },
];

function render_pipeline(state, data) {
	const p = data.pipeline || {};
	const total = PIPELINE_STAGES.reduce((sum, s) => sum + cint(p[s.key]), 0);

	state.$wrap.find("#dm-pipeline-meta").text(__("{0} service order", [total]));

	state.$wrap.find("#dm-pipeline-summary").html(`
		<div class="dm-stat">
			<div class="dm-stat-num">${cint(p.masih_diproses)}</div>
			<div class="dm-stat-label">${__("Masih Diproses")}</div>
		</div>
		<div class="dm-stat-divider"></div>
		<div class="dm-stat">
			<div class="dm-stat-num">${cint(p.selesai)}</div>
			<div class="dm-stat-label">${__("Selesai / Invoiced")}</div>
		</div>
	`);

	const cells = PIPELINE_STAGES.map((s, i) => {
		const count = cint(p[s.key]);
		const share = total ? (count / total) * 100 : 0;
		return `
			${i > 0 ? '<div class="dm-step-sep" aria-hidden="true"></div>' : ""}
			<div class="dm-step" tabindex="0" role="button" data-stage="${i}"
				data-tip="${__(s.label)}|${count} SO · ${fmt_pct(share)} ${__("dari total")}">
				<span class="dm-step-accent dm-ord-${s.step}"></span>
				<div class="dm-step-num">${count}</div>
				<div class="dm-step-label">${__(s.label)}</div>
				<div class="dm-track dm-track-sm"><div class="dm-fill dm-ord-${s.step}" style="width:${share.toFixed(1)}%"></div></div>
			</div>
		`;
	}).join("");

	const $stages = state.$wrap.find("#dm-pipeline-stages").html(cells);
	const open = (i) => goto_list("Garage Service Order", { status: ["in", PIPELINE_STAGES[i].statuses] });
	$stages.find("[data-stage]")
		.on("click", function () { open(cint($(this).data("stage"))); })
		.on("keydown", function (e) {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				open(cint($(this).data("stage")));
			}
		});
	bind_tips($stages);

	// Every queue is listed, cleared ones included - a stable height, and "nothing pending"
	// is itself information a manager wants to see.
	const breakdown = p.approval_breakdown || [];
	const list = breakdown.map((b) => `
		<div class="dm-approval is-clickable" tabindex="0" role="button"
			data-approval="${frappe.utils.escape_html(b.doctype)}">
			<span class="dm-approval-name">${frappe.utils.escape_html(b.label || b.doctype)}</span>
			<span class="dm-approval-meta">
				${b.count
					? `<b>${b.count}</b> ${__("pending")}${b.amount ? ` <span class="dm-dot-sep">·</span> ${fmt_compact(b.amount)}` : ""}`
					: `<span class="dm-muted">${__("tidak ada")}</span>`}
			</span>
		</div>
	`).join("");

	// Straight into that queue in the Approval Center, where it can actually be approved -
	// the plain list view can only show them.
	const open_queue = (doctype) => frappe.set_route("approval-center", dm_slug(doctype));
	const $list = state.$wrap.find("#dm-approval-list").html(list);
	$list.find("[data-approval]")
		.on("click", function () { open_queue($(this).data("approval")); })
		.on("keydown", function (e) {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				open_queue($(this).data("approval"));
			}
		});
}

// ---------------------------------------------------------------------------
// Hutang supplier - ranked single-series magnitude, one hue
// ---------------------------------------------------------------------------

function render_hutang(state, data) {
	const rows = data.hutang_per_supplier || [];
	state.$wrap.find("#dm-hutang-meta").text(
		__("Total {0} · {1} supplier", [fmt_compact(data.hutang_total), data.hutang_supplier_count])
	);

	if (!rows.length) {
		state.$wrap.find("#dm-hutang-body").html(empty_state(__("Tidak ada hutang supplier terbuka.")));
		state.$wrap.find("#dm-hutang-foot").text("");
		return;
	}

	const max = Math.max(...rows.map((r) => flt(r.amount)), 1);
	const html = rows.map((r) => `
		<div class="dm-rank${r.supplier ? " is-clickable" : ""}" ${r.supplier ? `tabindex="0" role="button" data-supplier="${frappe.utils.escape_html(r.supplier)}"` : ""}>
			<div class="dm-rank-top">
				<span class="dm-rank-name dm-ellipsis" title="${frappe.utils.escape_html(r.supplier_name)}">${frappe.utils.escape_html(r.supplier_name)}</span>
				<span class="dm-rank-value">${fmt_rupiah(r.amount)}</span>
			</div>
			<div class="dm-track"><div class="dm-fill dm-fill-s1" style="width:${(flt(r.amount) / max * 100).toFixed(1)}%"></div></div>
			<div class="dm-rank-foot">
				${__("{0} invoice", [r.count])}
				${r.overdue ? `<span class="dm-chip-status dm-tone-crit">${icon("alert", 11)}${__("{0} jatuh tempo", [r.overdue])}</span>` : ""}
			</div>
		</div>
	`).join("");

	const $body = state.$wrap.find("#dm-hutang-body").html(html);
	$body.find("[data-supplier]")
		.on("click", function () {
			goto_list("Purchase Invoice", { supplier: $(this).data("supplier"), outstanding_amount: [">", 0] });
		})
		.on("keydown", function (e) {
			if (e.key === "Enter" || e.key === " ") {
				e.preventDefault();
				$(this).trigger("click");
			}
		});

	const shown = rows.length;
	const total = data.hutang_supplier_count;
	state.$wrap.find("#dm-hutang-foot").text(
		total > shown ? __("Menampilkan {0} dari {1} supplier — sisanya di laporan Accounts Payable.", [shown, total]) : ""
	);
}

// ---------------------------------------------------------------------------
// Shared tooltip (bars, segments, stages) - hover and keyboard focus behave the same
// ---------------------------------------------------------------------------

function tooltip_el() {
	let el = document.getElementById("dm-tooltip");
	if (!el) {
		el = document.createElement("div");
		el.id = "dm-tooltip";
		el.className = "dm-tooltip";
		el.setAttribute("role", "status");
		document.body.appendChild(el);
	}
	return el;
}

function show_tooltip(html, clientX, clientY) {
	const el = tooltip_el();
	el.innerHTML = html;
	el.style.display = "block";
	const box = el.getBoundingClientRect();
	const left = Math.min(Math.max(8, clientX - box.width / 2), window.innerWidth - box.width - 8);
	const top = Math.max(8, clientY - box.height - 10);
	el.style.left = `${left}px`;
	el.style.top = `${top}px`;
}

function hide_tooltip() {
	const el = document.getElementById("dm-tooltip");
	if (el) el.style.display = "none";
}

/** Wires every [data-tip="title|body"] inside $scope to the shared tooltip. */
function bind_tips($scope) {
	$scope.find("[data-tip]").each(function () {
		const parts = String($(this).data("tip")).split("|");
		const html = `<div class="dm-tt-title">${frappe.utils.escape_html(parts[0] || "")}</div>
			<div class="dm-tt-plain">${frappe.utils.escape_html(parts[1] || "")}</div>`;
		const place = (e) => {
			const box = this.getBoundingClientRect();
			show_tooltip(html, e && e.clientX ? e.clientX : box.left + box.width / 2, box.top);
		};
		$(this)
			.on("pointerenter pointermove", place)
			.on("focus", () => place())
			.on("pointerleave blur", hide_tooltip);
	});
}

// ---------------------------------------------------------------------------
// Drill-down
// ---------------------------------------------------------------------------

/** Doctype -> the url segment the Approval Center page matches on. */
function dm_slug(doctype) {
	return frappe.router.slug ? frappe.router.slug(doctype) : String(doctype).toLowerCase().replace(/ /g, "-");
}

function goto_list(doctype, filters) {
	frappe.route_options = Object.assign({}, filters);
	frappe.set_route("List", doctype);
}

// ---------------------------------------------------------------------------
// Resize - the SVG chart is measured, so re-render it (debounced) when width changes
// ---------------------------------------------------------------------------

function bind_resize(state) {
	if (state._resizeBound) return;
	state._resizeBound = true;
	let timer = null;
	$(window).on("resize.dm-dashboard", () => {
		clearTimeout(timer);
		timer = setTimeout(() => {
			if (state._data && state.$wrap.is(":visible")) render_trend(state, state._data);
		}, 160);
	});
}

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function fmt_rupiah(n) {
	const v = Math.round(flt(n));
	return (v < 0 ? "−" : "") + "Rp " + Math.abs(v).toLocaleString("id-ID");
}

/** Short form for big headline numbers; the exact value always rides along in a title/subline. */
function fmt_compact(n) {
	const v = flt(n);
	const abs = Math.abs(v);
	const sign = v < 0 ? "−" : "";
	const unit = (div, suffix) => {
		const scaled = abs / div;
		return `${sign}Rp ${scaled.toLocaleString("id-ID", { maximumFractionDigits: scaled < 10 ? 1 : 0 })} ${suffix}`;
	};
	if (abs >= 1e12) return unit(1e12, "T");
	if (abs >= 1e9) return unit(1e9, "M");
	if (abs >= 1e6) return unit(1e6, "jt");
	if (abs >= 1e4) return unit(1e3, "rb");
	return fmt_rupiah(v);
}

/**
 * Axis / direct labels: magnitude only (the card title carries the currency), and crucially one
 * unit locked across the whole axis - picking a unit per tick gives "2jt / 1,5jt / 500rb / 0",
 * which reads as a scale break that isn't there.
 */
function axis_formatter(domain_max) {
	const abs_max = Math.abs(flt(domain_max));
	const scaled_to = (div, suffix) => (n) => {
		const v = flt(n);
		if (!v) return "0";
		const scaled = Math.abs(v) / div;
		return `${v < 0 ? "−" : ""}${scaled.toLocaleString("id-ID", { maximumFractionDigits: scaled < 10 ? 1 : 0 })}${suffix}`;
	};
	if (abs_max >= 1e12) return scaled_to(1e12, "T");
	if (abs_max >= 1e9) return scaled_to(1e9, "M");
	if (abs_max >= 1e6) return scaled_to(1e6, "jt");
	if (abs_max >= 1e3) return scaled_to(1e3, "rb");
	return (n) => (flt(n) < 0 ? "−" : "") + Math.abs(flt(n)).toLocaleString("id-ID");
}

function fmt_pct(n) {
	// U+2212 minus, so a negative margin matches the minus used by fmt_rupiah/fmt_compact.
	const text = flt(n).toLocaleString("id-ID", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
	return `${text.replace(/^-/, "−")}%`;
}

function nice_ceil(value) {
	if (!value) return 1;
	const exp = Math.floor(Math.log10(Math.abs(value)));
	const base = Math.pow(10, exp);
	const steps = [1, 2, 2.5, 5, 10];
	for (const s of steps) {
		if (value <= s * base) return s * base;
	}
	return 10 * base;
}

function empty_state(text) {
	return `<div class="dm-empty">${icon("inbox", 22)}<span>${frappe.utils.escape_html(text)}</span></div>`;
}

// ---------------------------------------------------------------------------
// Shell
// ---------------------------------------------------------------------------

function get_shell() {
	return `
	<div class="dm-root">
		<div class="dm-toolbar">
			<div class="dm-toolbar-left">
				<div id="dm-chips" class="dm-chips" role="group" aria-label="${__("Periode cepat")}"></div>
			</div>
			<div class="dm-toolbar-right">
				<span id="dm-partial-badge" class="dm-chip-status dm-tone-warn" style="display:none">
					${__("periode berjalan")}
				</span>
				<span class="dm-context">
					<b id="dm-period-label"></b>
					<span class="dm-dot-sep">·</span>
					<span id="dm-company-label"></span>
					<span class="dm-dot-sep">·</span>
					<span id="dm-refreshed" class="dm-muted"></span>
				</span>
			</div>
		</div>

		<div class="dm-kpi-zone">
			<div id="dm-hero" class="dm-hero"></div>
			<div id="dm-tiles" class="dm-tiles"></div>
		</div>

		<div class="dm-section-title">${__("Kinerja Keuangan")}</div>
		<div class="dm-grid dm-grid-wide">
			<div class="dm-card">
				<div class="dm-card-head">
					<span class="dm-card-title">${__("Tren Omzet & Laba Kotor")}</span>
					<span class="dm-card-tools">
						<span class="dm-legend">
							<span class="dm-legend-item"><i class="dm-key dm-key-1"></i>${__("Omzet")}</span>
							<span class="dm-legend-item"><i class="dm-key dm-key-2"></i>${__("Laba Kotor")}</span>
						</span>
						<button type="button" id="dm-trend-toggle" class="dm-ghost-btn" aria-pressed="false">${__("Tabel")}</button>
					</span>
				</div>
				<div id="dm-trend-body" class="dm-chart-body"></div>
				<div class="dm-foot">${__("Sumber: GL Entry — cocok dengan laporan Profit and Loss Statement.")}</div>
			</div>
			<div class="dm-card">
				<div class="dm-card-head">
					<span class="dm-card-title">${__("Ringkasan Laba Rugi")}</span>
					<span class="dm-meta" id="dm-pnl-badge"></span>
				</div>
				<div id="dm-pnl-body"></div>
			</div>
		</div>

		<div class="dm-section-title">${__("Perlu Perhatian")}</div>
		<div class="dm-grid dm-grid-wide">
			<div class="dm-card">
				<div class="dm-card-head">
					<span class="dm-card-title">${__("Piutang Belum Lunas Terbesar")}</span>
					<span class="dm-meta" id="dm-piutang-meta"></span>
				</div>
				<div id="dm-piutang-body"></div>
			</div>
			<div class="dm-card">
				<div class="dm-card-head">
					<span class="dm-card-title">${__("Aging Piutang")}</span>
					<span class="dm-meta" id="dm-aging-meta"></span>
				</div>
				<div id="dm-aging-body"></div>
			</div>
		</div>

		<div class="dm-section-title">${__("Operasional")}</div>
		<div class="dm-grid dm-grid-wide">
			<div class="dm-card">
				<div class="dm-card-head">
					<span class="dm-card-title">${__("Pipeline Service Order")}</span>
					<span class="dm-meta" id="dm-pipeline-meta"></span>
				</div>
				<div id="dm-pipeline-summary" class="dm-stats"></div>
				<div id="dm-pipeline-stages" class="dm-steps"></div>
				<div class="dm-sub-title">${__("Approval Pending")}</div>
				<div id="dm-approval-list"></div>
			</div>
			<div class="dm-card">
				<div class="dm-card-head">
					<span class="dm-card-title">${__("Hutang Supplier Belum Lunas")}</span>
					<span class="dm-meta" id="dm-hutang-meta"></span>
				</div>
				<div id="dm-hutang-body"></div>
				<div class="dm-foot" id="dm-hutang-foot"></div>
			</div>
		</div>
	</div>
	`;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const TOKENS_LIGHT = `
		--dm-plane:#f6f6f4;
		--dm-surface:#ffffff;
		--dm-surface-2:#f1f0ec;
		--dm-surface-3:#e9e8e3;
		--dm-ink-1:#0b0b0b;
		--dm-ink-2:#52514e;
		--dm-ink-3:#898781;
		--dm-hairline:#e6e5e0;
		--dm-ring:rgba(11,11,11,.09);
		--dm-shadow:0 1px 2px rgba(11,11,11,.04),0 10px 26px -14px rgba(11,11,11,.14);
		--dm-shadow-hover:0 1px 2px rgba(11,11,11,.05),0 16px 34px -14px rgba(11,11,11,.20);
		--dm-s1:#2a78d6;
		--dm-s2:#eb6834;
		--dm-ord-1:#86b6ef;
		--dm-ord-2:#5598e7;
		--dm-ord-3:#2a78d6;
		--dm-ord-4:#1c5cab;
		--dm-ord-5:#104281;
		--dm-mute-fill:#c3c2b7;
		--dm-good:#0ca30c;
		--dm-good-ink:#006300;
		--dm-warn:#fab219;
		--dm-warn-ink:#845408;
		--dm-crit:#d03b3b;
		--dm-crit-ink:#a32020;
`;

const TOKENS_DARK = `
		--dm-plane:#141413;
		--dm-surface:#1e1e1d;
		--dm-surface-2:#282826;
		--dm-surface-3:#323230;
		--dm-ink-1:#ffffff;
		--dm-ink-2:#c3c2b7;
		--dm-ink-3:#898781;
		--dm-hairline:#2c2c2a;
		--dm-ring:rgba(255,255,255,.10);
		--dm-shadow:0 1px 2px rgba(0,0,0,.40),0 10px 26px -14px rgba(0,0,0,.60);
		--dm-shadow-hover:0 1px 2px rgba(0,0,0,.45),0 16px 34px -14px rgba(0,0,0,.70);
		--dm-s1:#3987e5;
		--dm-s2:#d95926;
		--dm-ord-1:#9ec5f4;
		--dm-ord-2:#6da7ec;
		--dm-ord-3:#3987e5;
		--dm-ord-4:#256abf;
		--dm-ord-5:#184f95;
		--dm-mute-fill:#4a4a46;
		--dm-good:#0ca30c;
		--dm-good-ink:#0ca30c;
		--dm-warn:#fab219;
		--dm-warn-ink:#fab219;
		--dm-crit:#d03b3b;
		--dm-crit-ink:#e66767;
`;

const DASHBOARD_CSS = `
	.dm-root{${TOKENS_LIGHT}
		color-scheme:light;
		background:var(--dm-plane);
		color:var(--dm-ink-1);
		border:1px solid var(--dm-hairline);
		border-radius:14px;
		padding:18px 18px 22px;
		font-size:13px;
		line-height:1.45;
		font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
	}
	[data-theme="dark"] .dm-root{${TOKENS_DARK} color-scheme:dark;}
	@media (prefers-color-scheme: dark){
		:root:not([data-theme="light"]) .dm-root{${TOKENS_DARK} color-scheme:dark;}
	}
	.dm-full-width > .page-head > .container,
	.dm-full-width > .container.page-body{max-width:none;width:100%;}
	.dm-root.is-loading{opacity:.55;pointer-events:none;}
	.dm-root *{box-sizing:border-box;}
	.dm-icon{flex:none;}
	.dm-muted{color:var(--dm-ink-3);}
	.dm-dot-sep{color:var(--dm-ink-3);margin:0 2px;}
	.dm-num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;}
	.dm-nowrap{white-space:nowrap;}
	.dm-mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:var(--dm-ink-2);}
	.dm-ellipsis{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;}

	/* ---- toolbar ---- */
	.dm-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px;}
	.dm-chips{display:flex;gap:6px;flex-wrap:wrap;background:var(--dm-surface-2);padding:4px;border-radius:10px;}
	.dm-chip{appearance:none;border:0;background:transparent;color:var(--dm-ink-2);font:inherit;font-size:12px;font-weight:600;
		padding:5px 11px;border-radius:7px;cursor:pointer;transition:background .15s,color .15s;}
	.dm-chip:hover{background:var(--dm-surface-3);color:var(--dm-ink-1);}
	.dm-chip.is-active{background:var(--dm-surface);color:var(--dm-ink-1);box-shadow:0 1px 2px var(--dm-ring);}
	.dm-toolbar-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
	.dm-context{font-size:12px;color:var(--dm-ink-2);}
	.dm-context b{color:var(--dm-ink-1);}

	/* ---- hero + tiles ---- */
	.dm-kpi-zone{display:grid;grid-template-columns:minmax(240px,300px) 1fr;gap:14px;margin-bottom:6px;}
	.dm-hero,.dm-tile,.dm-card{background:var(--dm-surface);border:1px solid var(--dm-hairline);border-radius:12px;box-shadow:var(--dm-shadow);}
	.dm-hero{padding:16px 18px;display:flex;flex-direction:column;gap:2px;}
	.dm-hero-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;}
	.dm-hero-label{font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--dm-ink-3);}
	.dm-hero-value{font-size:40px;font-weight:650;letter-spacing:-.02em;line-height:1.1;margin-top:2px;color:var(--dm-ink-1);}
	.dm-hero-exact{font-size:12px;color:var(--dm-ink-3);font-variant-numeric:tabular-nums;}
	.dm-hero-delta{display:flex;align-items:center;gap:6px;margin-top:8px;}
	.dm-hero-meta{font-size:11.5px;color:var(--dm-ink-3);}
	.dm-hero-foot{margin-top:auto;padding-top:12px;border-top:1px solid var(--dm-hairline);font-size:12px;color:var(--dm-ink-2);
		display:flex;align-items:center;gap:5px;flex-wrap:wrap;}
	.dm-hero-foot b{color:var(--dm-ink-1);}
	.dm-spark{flex:none;}
	.dm-spark-line{fill:none;stroke:var(--dm-ord-1);stroke-width:2;stroke-linecap:round;stroke-linejoin:round;}
	.dm-spark-dot{fill:var(--dm-s1);stroke:var(--dm-surface);stroke-width:2;}

	.dm-tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;}
	.dm-tile{padding:13px 14px;position:relative;display:flex;flex-direction:column;gap:3px;transition:box-shadow .16s,transform .16s;}
	.dm-tile.is-clickable{cursor:pointer;}
	.dm-tile.is-clickable:hover,.dm-tile.is-clickable:focus-visible{box-shadow:var(--dm-shadow-hover);transform:translateY(-1px);outline:none;}
	.dm-tile.is-clickable:focus-visible{border-color:var(--dm-s1);}
	.dm-tile-head{display:flex;align-items:center;gap:6px;min-height:18px;}
	.dm-tile-icon{color:var(--dm-ink-3);display:flex;}
	.dm-tile-label{font-size:10.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--dm-ink-3);
		overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
	.dm-tile-value{font-size:21px;font-weight:650;letter-spacing:-.01em;color:var(--dm-ink-1);}
	.dm-tile-sub{font-size:11.5px;color:var(--dm-ink-3);}
	.dm-tile-go{position:absolute;right:11px;bottom:11px;color:var(--dm-ink-3);opacity:0;transition:opacity .16s;display:flex;}
	.dm-tile.is-clickable:hover .dm-tile-go,.dm-tile.is-clickable:focus-visible .dm-tile-go{opacity:1;}

	/* ---- chips / status ---- */
	.dm-chip-status{display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:999px;
		white-space:nowrap;letter-spacing:.01em;}
	.dm-delta{display:inline-flex;align-items:center;gap:3px;font-size:12px;font-weight:700;font-variant-numeric:tabular-nums;}
	.dm-tone-good{color:var(--dm-good-ink);background:color-mix(in srgb,var(--dm-good) 14%,transparent);}
	.dm-tone-warn{color:var(--dm-warn-ink);background:color-mix(in srgb,var(--dm-warn) 18%,transparent);}
	.dm-tone-crit{color:var(--dm-crit-ink);background:color-mix(in srgb,var(--dm-crit) 14%,transparent);}
	.dm-delta.dm-tone-good,.dm-delta.dm-tone-crit{background:transparent;padding:0;}

	/* ---- sections / cards ---- */
	.dm-section-title{font-size:10.5px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--dm-ink-3);margin:24px 2px 10px;}
	.dm-grid{display:grid;gap:14px;align-items:start;}
	.dm-grid-wide{grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);}
	.dm-card{padding:15px 16px;min-width:0;}
	.dm-card-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px;flex-wrap:wrap;}
	.dm-card-title{font-size:12.5px;font-weight:650;color:var(--dm-ink-1);}
	.dm-meta,.dm-foot{font-size:11px;color:var(--dm-ink-3);font-variant-numeric:tabular-nums;}
	.dm-foot{margin-top:10px;}
	.dm-sub-title{font-size:10.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--dm-ink-3);
		margin:18px 0 6px;padding-top:12px;border-top:1px solid var(--dm-hairline);}
	.dm-card-tools{display:flex;align-items:center;gap:10px;}
	.dm-legend{display:flex;align-items:center;gap:10px;font-size:11px;color:var(--dm-ink-2);}
	.dm-legend-item{display:inline-flex;align-items:center;gap:5px;}
	.dm-key{width:12px;height:2px;border-radius:2px;display:inline-block;}
	.dm-key-1{background:var(--dm-s1);}
	.dm-key-2{background:var(--dm-s2);}
	.dm-swatch{width:9px;height:9px;border-radius:3px;display:inline-block;flex:none;}
	.dm-sw-s1{background:var(--dm-s1);}
	.dm-sw-mute{background:var(--dm-mute-fill);}
	.dm-ghost-btn{appearance:none;background:var(--dm-surface-2);border:1px solid transparent;color:var(--dm-ink-2);
		font:inherit;font-size:11px;font-weight:650;padding:3px 9px;border-radius:7px;cursor:pointer;transition:background .15s,color .15s;}
	.dm-ghost-btn:hover{background:var(--dm-surface-3);color:var(--dm-ink-1);}
	.dm-ghost-btn[aria-pressed="true"]{background:var(--dm-surface-3);color:var(--dm-ink-1);}

	/* ---- bars ---- */
	.dm-track{height:6px;background:var(--dm-surface-2);border-radius:4px;overflow:hidden;}
	.dm-track-sm{height:4px;margin-top:8px;}
	.dm-fill{height:100%;border-radius:4px;transition:width .5s cubic-bezier(.2,.8,.2,1);}
	.dm-fill-s1{background:var(--dm-s1);}
	.dm-fill-mute{background:var(--dm-mute-fill);}
	.dm-fill-good{background:var(--dm-good);}
	.dm-fill-crit{background:var(--dm-crit);}
	.dm-ord-1{background:var(--dm-ord-1);}
	.dm-ord-2{background:var(--dm-ord-2);}
	.dm-ord-3{background:var(--dm-ord-3);}
	.dm-ord-4{background:var(--dm-ord-4);}
	.dm-ord-5{background:var(--dm-ord-5);}

	/* ---- chart ---- */
	.dm-chart-body{min-height:248px;}
	.dm-chart{display:block;overflow:visible;}
	.dm-chart:focus-visible{outline:2px solid var(--dm-s1);outline-offset:2px;border-radius:6px;}
	.dm-chart .dm-gridline{stroke:var(--dm-hairline);stroke-width:1;}
	.dm-chart .dm-baseline{stroke:var(--dm-ink-3);stroke-width:1;}
	.dm-chart .dm-axis{fill:var(--dm-ink-3);font-size:10.5px;font-variant-numeric:tabular-nums;}
	.dm-chart .dm-axis-y{text-anchor:end;}
	.dm-chart .dm-line{fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;}
	.dm-chart .dm-series-1 .dm-line{stroke:var(--dm-s1);}
	.dm-chart .dm-series-2 .dm-line{stroke:var(--dm-s2);}
	.dm-chart .dm-series-1 .dm-area{fill:var(--dm-s1);opacity:.10;stroke:none;}
	.dm-chart .dm-series-1 .dm-end-dot{fill:var(--dm-s1);stroke:var(--dm-surface);stroke-width:2;}
	.dm-chart .dm-series-2 .dm-end-dot{fill:var(--dm-s2);stroke:var(--dm-surface);stroke-width:2;}
	.dm-chart .dm-end-label{fill:var(--dm-ink-2);font-size:11px;font-weight:650;font-variant-numeric:tabular-nums;}
	.dm-chart .dm-crosshair-line{stroke:var(--dm-ink-3);stroke-width:1;}
	.dm-chart .dm-hover-dot{stroke:var(--dm-surface);stroke-width:2;}
	.dm-chart .dm-hover-1{fill:var(--dm-s1);}
	.dm-chart .dm-hover-2{fill:var(--dm-s2);}
	.dm-chart .dm-hit{cursor:crosshair;}

	/* ---- tooltip ---- */
	.dm-tooltip{position:fixed;z-index:1055;display:none;min-width:150px;max-width:280px;padding:9px 11px;border-radius:9px;
		background:var(--dm-surface,#fff);color:var(--dm-ink-1,#0b0b0b);border:1px solid var(--dm-hairline,#e6e5e0);
		box-shadow:0 10px 30px -10px rgba(0,0,0,.35);font-size:12px;pointer-events:none;
		font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
	[data-theme="dark"] .dm-tooltip{${TOKENS_DARK}}
	.dm-tt-title{font-size:10.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--dm-ink-3);margin-bottom:5px;}
	.dm-tt-plain{font-weight:650;font-variant-numeric:tabular-nums;}
	.dm-tt-row{display:flex;align-items:center;gap:7px;padding:2px 0;}
	.dm-tt-key{width:12px;height:2px;border-radius:2px;flex:none;}
	.dm-tt-key-1{background:var(--dm-s1);}
	.dm-tt-key-2{background:var(--dm-s2);}
	.dm-tt-name{color:var(--dm-ink-3);font-size:11.5px;}
	.dm-tt-value{margin-left:auto;font-weight:650;font-variant-numeric:tabular-nums;}

	/* ---- P&L ---- */
	.dm-pnl-row{margin-bottom:13px;}
	.dm-pnl-row.is-subtotal{padding-top:11px;border-top:1px solid var(--dm-hairline);}
	.dm-pnl-top{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:5px;}
	.dm-pnl-label{font-size:12px;color:var(--dm-ink-2);}
	.dm-pnl-row.is-subtotal .dm-pnl-label{color:var(--dm-ink-1);font-weight:650;}
	.dm-pnl-value{font-size:12.5px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap;}
	.dm-pnl-value.is-deduct{color:var(--dm-ink-3);font-weight:500;}
	.dm-pnl-net{margin-top:14px;padding:12px 13px;border-radius:10px;background:var(--dm-surface-2);}
	.dm-pnl-net-top{display:flex;align-items:baseline;justify-content:space-between;gap:10px;font-weight:700;margin-bottom:7px;}
	.dm-pnl-net-value{font-size:17px;font-variant-numeric:tabular-nums;letter-spacing:-.01em;}
	.dm-pnl-net.is-good .dm-pnl-net-value{color:var(--dm-good-ink);}
	.dm-pnl-net.is-crit .dm-pnl-net-value{color:var(--dm-crit-ink);}
	.dm-pnl-net-foot{display:flex;align-items:center;gap:8px;margin-top:9px;font-size:11.5px;color:var(--dm-ink-3);}

	/* ---- tables ---- */
	.dm-table-scroll{overflow-x:auto;margin:0 -4px;}
	.dm-table{width:100%;border-collapse:collapse;font-size:12px;}
	.dm-table th{text-align:left;font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--dm-ink-3);
		padding:0 8px 7px;border-bottom:1px solid var(--dm-hairline);white-space:nowrap;}
	.dm-table td{padding:8px;border-bottom:1px solid var(--dm-hairline);color:var(--dm-ink-2);}
	.dm-table tbody tr:last-child td{border-bottom:0;}
	.dm-table td.dm-num{color:var(--dm-ink-1);font-weight:650;}
	.dm-table-hover tbody tr{cursor:pointer;transition:background .13s;}
	.dm-table-hover tbody tr:hover,.dm-table-hover tbody tr:focus-visible{background:var(--dm-surface-2);outline:none;}
	.dm-table-hover tbody tr:focus-visible td:first-child{box-shadow:inset 2px 0 0 var(--dm-s1);}
	.dm-table td.dm-ellipsis{max-width:180px;}

	/* ---- aging ---- */
	.dm-stack{display:flex;gap:2px;height:10px;margin:2px 0 16px;}
	.dm-stack .dm-seg{border-radius:3px;min-width:3px;cursor:default;transition:filter .15s;}
	.dm-stack .dm-seg:first-child{border-radius:5px 3px 3px 5px;}
	.dm-stack .dm-seg:last-child{border-radius:3px 5px 5px 3px;}
	.dm-stack .dm-seg:hover,.dm-stack .dm-seg:focus-visible{filter:brightness(1.08);outline:none;}
	.dm-aging-row{display:grid;grid-template-columns:11px 1fr auto auto;align-items:center;gap:9px;padding:7px 0;
		border-bottom:1px solid var(--dm-hairline);}
	.dm-aging-row:last-child{border-bottom:0;}
	.dm-aging-label{font-size:12px;color:var(--dm-ink-2);}
	.dm-aging-share{font-size:11px;color:var(--dm-ink-3);font-variant-numeric:tabular-nums;}
	.dm-aging-value{font-size:12px;font-weight:650;font-variant-numeric:tabular-nums;color:var(--dm-ink-1);}

	.dm-track-ramp{background:color-mix(in srgb,var(--dm-ord-1) 38%,transparent);}
	.dm-risk{margin-top:14px;padding-top:13px;border-top:1px solid var(--dm-hairline);}
	.dm-risk-top{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:7px;
		font-size:12px;color:var(--dm-ink-2);}
	.dm-risk-top b{color:var(--dm-ink-1);font-size:12.5px;font-variant-numeric:tabular-nums;}
	.dm-risk-foot{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:8px;
		font-size:11px;color:var(--dm-ink-3);}

	/* ---- pipeline ---- */
	.dm-stats{display:flex;align-items:center;gap:20px;margin-bottom:14px;}
	.dm-stat-num{font-size:24px;font-weight:650;letter-spacing:-.02em;line-height:1.1;}
	.dm-stat-label{font-size:11px;color:var(--dm-ink-3);}
	.dm-stat-divider{width:1px;align-self:stretch;background:var(--dm-hairline);}
	.dm-steps{display:flex;align-items:stretch;gap:0;}
	.dm-step{flex:1 1 0;min-width:0;padding:10px 10px 11px;border-radius:9px;background:var(--dm-surface-2);
		position:relative;overflow:hidden;cursor:pointer;transition:background .15s,transform .15s;}
	.dm-step:hover,.dm-step:focus-visible{background:var(--dm-surface-3);transform:translateY(-1px);outline:none;}
	.dm-step:focus-visible{box-shadow:0 0 0 2px var(--dm-s1);}
	.dm-step-accent{position:absolute;left:0;top:0;width:100%;height:3px;}
	.dm-step-num{font-size:19px;font-weight:650;line-height:1.2;margin-top:4px;}
	.dm-step-label{font-size:9.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--dm-ink-3);
		overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
	.dm-step-sep{flex:0 0 14px;align-self:center;height:1px;background:var(--dm-hairline);}
	.dm-approval{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 0;font-size:12px;
		border-bottom:1px solid var(--dm-hairline);color:var(--dm-ink-2);}
	.dm-approval:last-child{border-bottom:0;}
	.dm-approval.is-clickable{cursor:pointer;}
	.dm-approval.is-clickable:hover .dm-approval-name{color:var(--dm-s1);}
	.dm-approval-meta{color:var(--dm-ink-3);white-space:nowrap;font-variant-numeric:tabular-nums;}
	.dm-approval-meta b{color:var(--dm-ink-1);}

	/* ---- ranked list ---- */
	.dm-rank{padding:10px 0;border-bottom:1px solid var(--dm-hairline);}
	.dm-rank:last-child{border-bottom:0;}
	.dm-rank.is-clickable{cursor:pointer;}
	.dm-rank.is-clickable:hover .dm-rank-name,.dm-rank.is-clickable:focus-visible .dm-rank-name{color:var(--dm-s1);}
	.dm-rank:focus-visible{outline:none;}
	.dm-rank-top{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:6px;}
	.dm-rank-name{font-size:12px;font-weight:600;color:var(--dm-ink-1);flex:1 1 auto;min-width:0;}
	.dm-rank-value{font-size:12.5px;font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap;}
	.dm-rank-foot{display:flex;align-items:center;gap:8px;margin-top:6px;font-size:11px;color:var(--dm-ink-3);}

	/* ---- empty ---- */
	.dm-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:28px 10px;
		color:var(--dm-ink-3);font-size:12px;text-align:center;}

	/* ---- responsive ---- */
	@media (max-width:1180px){
		.dm-kpi-zone{grid-template-columns:minmax(0,1fr);}
		.dm-tiles{grid-template-columns:repeat(3,minmax(0,1fr));}
	}
	@media (max-width:900px){
		.dm-grid-wide{grid-template-columns:minmax(0,1fr);}
		.dm-tiles{grid-template-columns:repeat(2,minmax(0,1fr));}
		.dm-hero-value{font-size:34px;}
		.dm-steps{flex-wrap:wrap;gap:8px;}
		.dm-step{flex:1 1 44%;}
		.dm-step-sep{display:none;}
	}

	/* ---- phone ---- */
	@media (max-width:640px){
		.dm-root{padding:12px 10px 16px;border-radius:12px;}
		.dm-section-title{margin:18px 2px 8px;}
		.dm-grid{gap:10px;}
		.dm-kpi-zone{gap:10px;}
		.dm-tiles{gap:10px;}
		.dm-card,.dm-hero,.dm-tile{border-radius:11px;}

		/* toolbar: presets get their own scrollable row, context drops underneath */
		/* every one of these is a flex item, and a flex item's default min-width:auto is its
		   content width - the nowrap chip strip and the long context line would each widen
		   the toolbar, and with it the page, past a narrow screen. */
		.dm-toolbar{flex-direction:column;align-items:stretch;gap:8px;margin-bottom:12px;}
		/* min-width:0 alone still let these flex items take their max-content width on a
		   320px screen; capping at the container width is what actually holds them in. */
		.dm-toolbar > *{min-width:0;max-width:100%;width:100%;}
		.dm-toolbar-right{flex-wrap:wrap;}
		.dm-context{min-width:0;max-width:100%;}
		.dm-chips{min-width:0;max-width:100%;overflow-x:auto;flex-wrap:nowrap;-webkit-overflow-scrolling:touch;
			scrollbar-width:none;}
		.dm-chips::-webkit-scrollbar{display:none;}
		.dm-chip{flex:0 0 auto;padding:7px 12px;}
		.dm-toolbar-right{justify-content:flex-start;}
		.dm-context{font-size:11.5px;line-height:1.6;}

		.dm-hero{padding:14px;}
		.dm-hero-value{font-size:30px;}
		.dm-tile{padding:11px 12px;}
		.dm-tile-value{font-size:18px;}
		.dm-tile-head{align-items:flex-start;}
		.dm-tile-label{white-space:normal;overflow:visible;line-height:1.3;}
		.dm-tile-go{display:none;}
		.dm-card{padding:13px 12px;}
		.dm-chart-body{min-height:208px;}
		.dm-table-scroll{margin:0;}

		/* the 5-column AR table stops being a table and becomes one block per invoice */
		.dm-table-stack thead{display:none;}
		.dm-table-stack,.dm-table-stack tbody,.dm-table-stack tr,.dm-table-stack td{display:block;width:100%;}
		.dm-table-stack tr{padding:11px 2px;border-bottom:1px solid var(--dm-hairline);}
		.dm-table-stack tr:last-child{border-bottom:0;}
		.dm-table-stack td{border:0;padding:2px 0;display:flex;align-items:baseline;
			justify-content:space-between;gap:10px;}
		.dm-table-stack td::before{content:attr(data-label);color:var(--dm-ink-3);font-size:10px;
			font-weight:700;letter-spacing:.05em;text-transform:uppercase;flex:none;}
		.dm-table-stack td.dm-ellipsis{max-width:none;}
		.dm-table-stack td[data-label="Invoice"]{padding-bottom:5px;}
		.dm-table-stack td[data-label="Invoice"]::before{display:none;}
		.dm-table-stack td[data-label="Invoice"]{justify-content:flex-start;font-size:12px;}

		.dm-step{flex:1 1 calc(50% - 4px);min-width:0;}
		.dm-stats{gap:14px;}
		.dm-aging-row{grid-template-columns:11px minmax(0,1fr) auto auto;gap:7px;}
		.dm-approval{flex-wrap:wrap;gap:2px;}
		.dm-approval-name{flex:1 1 100%;}
	}
	@media (max-width:330px){
		.dm-tiles{grid-template-columns:minmax(0,1fr);}
	}
	@media (prefers-reduced-motion: reduce){
		.dm-root *{transition:none !important;}
	}
`;

// wkhtmltopdf's renderer has no reliable grid/flex support, so the PDF export swaps in this
// table-based stylesheet instead of touching the on-screen CSS. Tokens are the light set only -
// a printed dashboard is always on white.
const PDF_CSS = `
	.dm-root{${TOKENS_LIGHT}
		background:var(--dm-plane);color:var(--dm-ink-1);padding:16px;border-radius:12px;font-size:12.5px;
		font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
	.dm-root.is-loading{opacity:1;}
	.dm-toolbar{display:table;width:100%;margin-bottom:14px;}
	.dm-toolbar-left{display:table-cell;text-align:left;}
	.dm-toolbar-right{display:table-cell;text-align:right;white-space:nowrap;}
	.dm-chips{display:none;}
	.dm-context{font-size:12px;color:var(--dm-ink-2);}
	.dm-kpi-zone{display:table;width:100%;table-layout:fixed;border-spacing:12px 0;}
	.dm-hero{display:table-cell;width:28%;vertical-align:top;background:var(--dm-surface);border:1px solid var(--dm-hairline);
		border-radius:11px;padding:14px;}
	.dm-tiles-wrap{display:table-cell;vertical-align:top;}
	.dm-tiles{display:table;width:100%;table-layout:fixed;border-spacing:12px 0;}
	.dm-tile-row{display:table-row;}
	.dm-tile{display:table-cell;width:33.33%;vertical-align:top;background:var(--dm-surface);border:1px solid var(--dm-hairline);
		border-radius:11px;padding:11px 12px;}
	.dm-tile-go{display:none;}
	.dm-hero-head{display:table;width:100%;}
	.dm-hero-label{display:table-cell;font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--dm-ink-3);}
	.dm-spark{display:table-cell;text-align:right;}
	.dm-spark-line{fill:none;stroke:var(--dm-ord-1);stroke-width:2;}
	.dm-spark-dot{fill:var(--dm-s1);}
	.dm-hero-value{font-size:30px;font-weight:700;line-height:1.15;}
	.dm-hero-exact,.dm-hero-meta{font-size:11px;color:var(--dm-ink-3);}
	.dm-hero-delta{margin-top:6px;}
	.dm-hero-foot{margin-top:10px;padding-top:9px;border-top:1px solid var(--dm-hairline);font-size:11px;color:var(--dm-ink-2);}
	.dm-tile-head{margin-bottom:3px;}
	.dm-tile-icon{display:none;}
	.dm-tile-label{font-size:9.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--dm-ink-3);}
	.dm-tile-value{font-size:17px;font-weight:700;}
	.dm-tile-sub{font-size:10.5px;color:var(--dm-ink-3);}
	.dm-chip-status{font-size:10px;font-weight:700;padding:1px 6px;border-radius:999px;}
	.dm-chip-status .dm-icon,.dm-delta .dm-icon{margin-right:3px;vertical-align:-1px;}
	.dm-tone-good{color:#006300;background:#e3f3e3;}
	.dm-tone-warn{color:#845408;background:#fdf0d8;}
	.dm-tone-crit{color:#a32020;background:#fae3e3;}
	.dm-delta{font-size:11.5px;font-weight:700;}
	.dm-section-title{font-size:10px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--dm-ink-3);margin:18px 0 8px;}
	.dm-grid{display:table;width:100%;table-layout:fixed;border-spacing:12px 0;page-break-inside:avoid;}
	.dm-card{display:table-cell;vertical-align:top;background:var(--dm-surface);border:1px solid var(--dm-hairline);
		border-radius:11px;padding:13px 14px;page-break-inside:avoid;}
	.dm-grid-wide > .dm-card:first-child{width:58%;}
	.dm-card-head{display:table;width:100%;margin-bottom:10px;}
	.dm-card-title{display:table-cell;font-size:12px;font-weight:700;}
	.dm-card-tools,.dm-meta{display:table-cell;text-align:right;white-space:nowrap;font-size:10.5px;color:var(--dm-ink-3);}
	.dm-ghost-btn{display:none;}
	.dm-legend{font-size:10.5px;color:var(--dm-ink-2);}
	.dm-key{width:12px;height:2px;display:inline-block;vertical-align:middle;margin-right:4px;}
	.dm-key-1{background:var(--dm-s1);}
	.dm-key-2{background:var(--dm-s2);}
	.dm-swatch{width:9px;height:9px;display:inline-block;vertical-align:middle;margin-right:5px;}
	.dm-sw-s1{background:var(--dm-s1);}
	.dm-sw-mute{background:var(--dm-mute-fill);}
	.dm-foot{font-size:9.5px;color:var(--dm-ink-3);margin-top:8px;}
	.dm-sub-title{font-size:10px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--dm-ink-3);
		margin:14px 0 6px;padding-top:10px;border-top:1px solid var(--dm-hairline);}
	.dm-track{height:6px;background:var(--dm-surface-2);border-radius:4px;overflow:hidden;}
	.dm-track-sm{height:4px;margin-top:6px;}
	.dm-fill{height:100%;border-radius:4px;}
	.dm-fill-s1{background:var(--dm-s1);}
	.dm-fill-mute{background:var(--dm-mute-fill);}
	.dm-fill-good{background:var(--dm-good);}
	.dm-fill-crit{background:var(--dm-crit);}
	.dm-ord-1{background:var(--dm-ord-1);}
	.dm-ord-2{background:var(--dm-ord-2);}
	.dm-ord-3{background:var(--dm-ord-3);}
	.dm-ord-4{background:var(--dm-ord-4);}
	.dm-ord-5{background:var(--dm-ord-5);}
	.dm-chart{display:block;}
	.dm-chart .dm-gridline{stroke:var(--dm-hairline);stroke-width:1;}
	.dm-chart .dm-baseline{stroke:var(--dm-ink-3);}
	.dm-chart .dm-axis{fill:var(--dm-ink-3);font-size:10px;}
	.dm-chart .dm-axis-y{text-anchor:end;}
	.dm-chart .dm-line{fill:none;stroke-width:2;}
	.dm-chart .dm-series-1 .dm-line{stroke:var(--dm-s1);}
	.dm-chart .dm-series-2 .dm-line{stroke:var(--dm-s2);}
	.dm-chart .dm-series-1 .dm-area{fill:var(--dm-s1);opacity:.1;}
	.dm-chart .dm-series-1 .dm-end-dot{fill:var(--dm-s1);}
	.dm-chart .dm-series-2 .dm-end-dot{fill:var(--dm-s2);}
	.dm-chart .dm-end-label{fill:var(--dm-ink-2);font-size:10.5px;font-weight:700;}
	.dm-crosshair,.dm-hit{display:none;}
	.dm-pnl-row{margin-bottom:11px;}
	.dm-pnl-row.is-subtotal{padding-top:9px;border-top:1px solid var(--dm-hairline);}
	.dm-pnl-top{display:table;width:100%;margin-bottom:4px;}
	.dm-pnl-label{display:table-cell;text-align:left;font-size:11.5px;color:var(--dm-ink-2);}
	.dm-pnl-value{display:table-cell;text-align:right;font-size:12px;font-weight:700;white-space:nowrap;}
	.dm-pnl-value.is-deduct{color:var(--dm-ink-3);font-weight:400;}
	.dm-pnl-net{margin-top:12px;padding:11px 12px;border-radius:9px;background:var(--dm-surface-2);}
	.dm-pnl-net-top{display:table;width:100%;font-weight:700;margin-bottom:6px;}
	.dm-pnl-net-top > span:first-child{display:table-cell;text-align:left;}
	.dm-pnl-net-value{display:table-cell;text-align:right;font-size:16px;white-space:nowrap;}
	.dm-pnl-net.is-good .dm-pnl-net-value{color:#006300;}
	.dm-pnl-net.is-crit .dm-pnl-net-value{color:#a32020;}
	.dm-pnl-net-foot{margin-top:8px;font-size:11px;color:var(--dm-ink-3);}
	.dm-table{width:100%;border-collapse:collapse;font-size:11.5px;}
	.dm-table th{text-align:left;font-size:9.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
		color:var(--dm-ink-3);padding:0 7px 6px;border-bottom:1px solid var(--dm-hairline);}
	.dm-table td{padding:7px;border-bottom:1px solid var(--dm-hairline);color:var(--dm-ink-2);}
	.dm-table .dm-num{text-align:right;color:var(--dm-ink-1);font-weight:700;white-space:nowrap;}
	.dm-mono{font-family:monospace;font-size:10.5px;}
	.dm-stack{display:table;width:100%;table-layout:fixed;height:10px;margin:2px 0 14px;}
	.dm-seg{display:table-cell;}
	.dm-aging-row{display:table;width:100%;table-layout:fixed;padding:6px 0;border-bottom:1px solid var(--dm-hairline);}
	.dm-aging-row > span{display:table-cell;vertical-align:middle;}
	.dm-aging-label{font-size:11.5px;color:var(--dm-ink-2);}
	.dm-aging-share{width:52px;text-align:right;font-size:10.5px;color:var(--dm-ink-3);}
	.dm-aging-value{width:108px;text-align:right;font-size:11.5px;font-weight:700;}
	.dm-track-ramp{background:#cde2fb;}
	.dm-risk{margin-top:12px;padding-top:11px;border-top:1px solid var(--dm-hairline);}
	.dm-risk-top{display:table;width:100%;margin-bottom:6px;font-size:11.5px;color:var(--dm-ink-2);}
	.dm-risk-top > span{display:table-cell;text-align:left;}
	.dm-risk-top > b{display:table-cell;text-align:right;white-space:nowrap;color:var(--dm-ink-1);}
	.dm-risk-foot{display:table;width:100%;margin-top:7px;font-size:10.5px;color:var(--dm-ink-3);}
	.dm-risk-foot > span{display:table-cell;text-align:left;}
	.dm-risk-foot > .dm-risk-chip{display:table-cell;text-align:right;white-space:nowrap;}
	.dm-stats{display:table;margin-bottom:12px;}
	.dm-stat{display:table-cell;padding-right:22px;}
	.dm-stat-divider{display:none;}
	.dm-stat-num{font-size:22px;font-weight:700;}
	.dm-stat-label{font-size:10.5px;color:var(--dm-ink-3);}
	.dm-steps{display:table;width:100%;table-layout:fixed;}
	.dm-step{display:table-cell;vertical-align:top;background:var(--dm-surface-2);border-radius:8px;padding:9px;position:relative;}
	.dm-step-accent{display:block;height:3px;margin:-9px -9px 6px;}
	.dm-step-num{font-size:17px;font-weight:700;}
	.dm-step-label{font-size:9px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--dm-ink-3);}
	.dm-step-sep{display:table-cell;width:10px;}
	.dm-approval{display:table;width:100%;padding:6px 0;font-size:11.5px;border-bottom:1px solid var(--dm-hairline);color:var(--dm-ink-2);}
	.dm-approval-name{display:table-cell;text-align:left;}
	.dm-approval-meta{display:table-cell;text-align:right;white-space:nowrap;color:var(--dm-ink-3);}
	.dm-rank{padding:9px 0;border-bottom:1px solid var(--dm-hairline);}
	.dm-rank-top{display:table;width:100%;margin-bottom:5px;}
	.dm-rank-name{display:table-cell;text-align:left;font-size:11.5px;font-weight:600;}
	.dm-rank-value{display:table-cell;text-align:right;font-size:12px;font-weight:700;white-space:nowrap;}
	.dm-rank-foot{margin-top:5px;font-size:10.5px;color:var(--dm-ink-3);}
	.dm-empty{padding:20px;text-align:center;color:var(--dm-ink-3);font-size:11.5px;}
`;

function inject_styles() {
	if (document.getElementById(STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = STYLE_ID;
	style.textContent = DASHBOARD_CSS;
	document.head.appendChild(style);
}

// ---------------------------------------------------------------------------
// PDF export
// ---------------------------------------------------------------------------

function download_pdf(state) {
	if (!state.$wrap || !state.$wrap.length) return;
	const slug = (state.last_period_label || "dashboard")
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/(^-|-$)/g, "");

	// Clone first: the PDF needs the tiles wrapped in rows (table layout has no grid wrap),
	// and that reshaping must never touch the live page.
	const $clone = state.$wrap.clone();
	$clone.removeClass("is-loading");
	const $tiles = $clone.find("#dm-tiles");
	if ($tiles.length) {
		const $all = $tiles.children(".dm-tile");
		const rows = [];
		for (let i = 0; i < $all.length; i += 3) {
			rows.push($('<div class="dm-tiles"></div>').append($all.slice(i, i + 3).clone()));
		}
		const $wrapCell = $('<div class="dm-tiles-wrap"></div>').append(rows);
		$tiles.replaceWith($wrapCell);
	}

	const html = `<!doctype html><html><head><meta charset="utf-8">
		<style>body{margin:0;background:#fff;}${PDF_CSS}</style>
		</head><body>${$clone[0].outerHTML}</body></html>`;

	open_url_post("/api/method/imogi_finance.api.workshop_dashboard.dashboard_pdf", {
		html,
		filename: `dashboard-manager-${slug}.pdf`,
		orientation: "Landscape",
	});
}
