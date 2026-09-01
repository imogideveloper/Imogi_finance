// Copyright (c) 2026, Imogi and contributors

const DM_CARD_METHOD =
	"imogi_finance.imogi_finance.report.dashboard_management.dashboard_management.get_dashboard_management_cards";

const DM_PIPELINE_STATUS_FILTERS = {
	antrian: ["Open"],
	dikerjakan_tunggu_part: ["Waiting Part", "Prepared", "In Progress"],
	siap_diambil: ["Finished", "QC Review", "Waiting Payment"],
	selesai: ["Completed"],
};

function dm_inject_card_styles() {
	if (document.getElementById("imogi-dashboard-mgmt-card-style-v1")) return;
	const style = document.createElement("style");
	style.id = "imogi-dashboard-mgmt-card-style-v1";
	style.textContent = `
		.imogi-dm-dashboard .datatable,
		.imogi-dm-dashboard .report-wrapper,
		.imogi-dm-dashboard .report-footer,
		.imogi-dm-dashboard .report-summary,
		.imogi-dm-dashboard .chart-wrapper{display:none!important}
		.imogi-dm-scope{max-width:1400px;margin:16px auto;display:flex;flex-direction:column;gap:20px}
		.imogi-dm-caption{font-size:12px;color:#9ca3af;font-weight:600;text-transform:uppercase;letter-spacing:.02em}
		.imogi-dm-kpi-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
		@media (max-width:900px){.imogi-dm-kpi-row{grid-template-columns:repeat(2,1fr)}}
		@media (max-width:560px){.imogi-dm-kpi-row{grid-template-columns:1fr}}
		.imogi-dm-kpi-tile{min-width:0;border:1px solid #e2e5e9;border-radius:var(--border-radius-lg);background:#fff;padding:14px 16px;cursor:default}
		.imogi-dm-kpi-tile[data-clickable="1"]{cursor:pointer}
		.imogi-dm-kpi-tile[data-clickable="1"]:hover{border-color:var(--primary);box-shadow:0 1px 4px rgba(0,0,0,.08)}
		.imogi-dm-kpi-tile__label{font-size:12px;color:#6c757d;font-weight:600}
		.imogi-dm-kpi-tile__value{font-size:20px;font-weight:700;margin-top:4px;letter-spacing:-.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
		.imogi-dm-kpi-tile__sub{font-size:12px;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
		.imogi-dm-kpi-tile__sub--up{color:#059669}
		.imogi-dm-kpi-tile__sub--down{color:#dc3545}
		.imogi-dm-kpi-tile__sub--muted{color:#9ca3af}
		.imogi-dm-kpi-tile__breakdown{margin-top:6px}
		.imogi-dm-kpi-tile__breakdown-row{display:flex;justify-content:space-between;gap:8px;font-size:11px;color:#6c757d;margin-top:2px}
		.imogi-dm-kpi-tile__breakdown-row span:last-child{white-space:nowrap;font-weight:600}
		.imogi-dm-card{border:1px solid #e2e5e9;border-radius:var(--border-radius-lg);background:#fff;overflow:hidden}
		.imogi-dm-card__header{padding:12px 16px;background:#f8f9fa;border-bottom:1px solid #e2e5e9;font-size:14px;font-weight:600;color:#364152;display:flex;align-items:center;justify-content:space-between}
		.imogi-dm-card__header-sub{font-size:12px;color:#6c757d;font-weight:500}
		.imogi-dm-card__body{padding:14px 16px}
		.imogi-dm-two-col{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
		.imogi-dm-pnl-row{display:flex;align-items:baseline;justify-content:space-between;padding:7px 0;border-bottom:1px solid #f1f3f5;font-size:13px}
		.imogi-dm-pnl-row:last-child{border-bottom:none;font-weight:700;font-size:14px}
		.imogi-dm-pnl-row__label{color:#364152}
		.imogi-dm-pnl-row__value{font-weight:600;white-space:nowrap}
		.imogi-dm-pnl-row__value--neg{color:#dc3545}
		.imogi-dm-pipeline-stats{display:flex;align-items:center;gap:14px}
		.imogi-dm-pipeline-stat{display:flex;flex-direction:column;align-items:flex-end;line-height:1.2}
		.imogi-dm-pipeline-stat__value{font-size:16px;font-weight:700}
		.imogi-dm-pipeline-stat__value--active{color:#5e64ff}
		.imogi-dm-pipeline-stat__value--done{color:#059669}
		.imogi-dm-pipeline-stat__label{font-size:10px;color:#6c757d;font-weight:600;text-transform:uppercase;letter-spacing:.02em}
		.imogi-dm-pipeline-stat__divider{width:1px;height:26px;background:#e2e5e9}
		.imogi-dm-pipeline-bar-row{padding:9px 0;cursor:pointer}
		.imogi-dm-pipeline-bar-row:hover .imogi-dm-pipeline-bar-row__label{text-decoration:underline}
		.imogi-dm-pipeline-bar-row__top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;font-size:13px}
		.imogi-dm-pipeline-bar-row__label{font-weight:600;color:#364152}
		.imogi-dm-pipeline-bar-row__value{font-weight:700;color:#364152}
		.imogi-dm-pipeline-bar-row__track{display:block;background:#f1f3f5;border-radius:4px;height:8px;overflow:hidden}
		.imogi-dm-pipeline-bar-row__fill{display:block;height:100%;border-radius:4px}
		.imogi-dm-aging-row{display:flex;align-items:center;gap:10px;padding:6px 0;font-size:12px}
		.imogi-dm-aging-row__label{width:110px;flex-shrink:0;color:#364152;font-weight:600}
		.imogi-dm-aging-row__bar-track{flex:1;background:#f1f3f5;border-radius:4px;height:10px;overflow:hidden}
		.imogi-dm-aging-row__bar-fill{height:100%;border-radius:4px}
		.imogi-dm-aging-row__amount{width:120px;flex-shrink:0;text-align:right;font-weight:600;white-space:nowrap}
		.imogi-dm-list-header{display:grid;grid-template-columns:1fr 110px 130px;gap:10px;padding:0 0 6px;border-bottom:1px solid #f1f3f5;margin-bottom:2px}
		.imogi-dm-list-header span{font-size:11px;color:#9ca3af;font-weight:600;text-transform:uppercase;letter-spacing:.02em}
		.imogi-dm-list-header__amount{text-align:right}
		.imogi-dm-list-row{display:grid;grid-template-columns:1fr 110px 130px;gap:10px;align-items:center;padding:8px 0;border-bottom:1px solid #f1f3f5;font-size:13px;cursor:pointer}
		.imogi-dm-list-row:last-child{border-bottom:none}
		.imogi-dm-list-row:hover .imogi-dm-list-row__name{text-decoration:underline}
		.imogi-dm-list-row__party{font-weight:600;color:#364152}
		.imogi-dm-list-row__col--due{display:flex;flex-direction:column;min-width:0}
		.imogi-dm-list-row__due-date{color:#364152}
		.imogi-dm-list-row__due-late{font-size:11px;color:#dc3545;margin-top:2px}
		.imogi-dm-list-row__col--amount{font-weight:700;text-align:right;white-space:nowrap}
		.imogi-dm-empty{color:#9ca3af;font-size:12px;padding:8px 0}
	`;
	document.head.appendChild(style);
}

function dm_format_currency(amount, currency) {
	return frappe.format(amount, {
		fieldtype: "Currency",
		options: currency || frappe.defaults.get_default("currency"),
	});
}

function dm_ensure_cards_host($main) {
	let $host = $main.find(".imogi-dm-cards-host");
	if (!$host.length) {
		$host = $('<div class="imogi-dm-cards-host"></div>');
	}
	const $filters = $main.find(".page-form").first();
	if ($filters.length) {
		$host.insertAfter($filters);
	} else {
		$main.prepend($host);
	}
	return $host;
}

function dm_build_kpi_row(data) {
	const currency = data.currency;
	const so = data.so_pipeline || {};

	const tiles = [
		{
			label: __("Piutang (AR)"),
			value: dm_format_currency(data.ar.outstanding.amount, currency),
			sub: `${dm_format_currency(data.ar.late.amount, currency)} ${__("lewat jatuh tempo")}`,
			subClass: data.ar.late.amount > 0 ? "down" : "muted",
			route: "ar",
		},
		{
			label: __("Hutang (AP)"),
			value: dm_format_currency(data.ap.outstanding.amount, currency),
			sub: `${data.ap.late.count} ${__("tagihan lewat jatuh tempo")}`,
			subClass: data.ap.late.count > 0 ? "down" : "muted",
			route: "ap",
		},
		{
			label: __("Saldo Kas & Bank"),
			value: dm_format_currency(data.cash_bank.total, currency),
			breakdown: [
				[__("Kas"), dm_format_currency(data.cash_bank.cash, currency)],
				[__("Bank"), dm_format_currency(data.cash_bank.bank, currency)],
			],
			route: null,
		},
		{
			label: __("Omzet Periode Ini"),
			value: dm_format_currency(data.pnl.omzet, currency),
			sub: `${__("Margin Kotor")} ${flt(data.pnl.gross_margin_pct, 1)}%`,
			subClass: "muted",
			route: "omzet",
		},
		{
			label: __("Laba Bersih Periode Ini"),
			value: dm_format_currency(data.pnl.net_profit, currency),
			sub: `${__("Margin Bersih")} ${flt(data.pnl.net_margin_pct, 1)}%`,
			subClass: data.pnl.net_profit >= 0 ? "up" : "down",
			route: null,
		},
		{
			label: __("Service Order Aktif"),
			value: String(so.total_aktif || 0),
			sub: `${so.dikerjakan || 0} ${__("dikerjakan")} · ${so.tunggu_part || 0} ${__("tunggu part")}`,
			subClass: "muted",
			route: "so_active",
		},
	];

	return `
		<div class="imogi-dm-kpi-row">
			${tiles
				.map((t) => {
					const belowValue = t.breakdown
						? `<div class="imogi-dm-kpi-tile__breakdown">
							${t.breakdown
								.map(([label, value]) => `<div class="imogi-dm-kpi-tile__breakdown-row"><span>${label}</span><span>${value}</span></div>`)
								.join("")}
						</div>`
						: `<div class="imogi-dm-kpi-tile__sub imogi-dm-kpi-tile__sub--${t.subClass}">${t.sub}</div>`;

					return `
					<div class="imogi-dm-kpi-tile" data-clickable="${t.route ? 1 : 0}" data-route="${t.route || ""}">
						<div class="imogi-dm-kpi-tile__label">${t.label}</div>
						<div class="imogi-dm-kpi-tile__value">${t.value}</div>
						${belowValue}
					</div>`;
				})
				.join("")}
		</div>`;
}

function dm_build_pnl_card(data) {
	const currency = data.currency;
	const p = data.pnl;
	// HPP/Beban Operasional are stored as positive costs - negate them here
	// so frappe.format renders one cohesive "-Rp X" string (never build the
	// minus sign as a separate concatenated character - that broke across
	// lines since it isn't part of the currency formatter's non-breaking output).
	const rows = [
		[__("Omzet"), p.omzet],
		[__("HPP (Harga Pokok Penjualan)"), -p.hpp],
		[__("Laba Kotor"), p.gross_profit],
		[__("Beban Operasional"), -p.opex],
		[__("Laba Bersih"), p.net_profit],
	];

	return `
		<div class="imogi-dm-card">
			<div class="imogi-dm-card__header">
				<span>${__("Ringkasan Laba Rugi (P&L)")}</span>
				<span class="imogi-dm-card__header-sub">${__("Margin bersih")} ${flt(p.net_margin_pct, 1)}%</span>
			</div>
			<div class="imogi-dm-card__body">
				${rows
					.map(
						([label, value]) => `
						<div class="imogi-dm-pnl-row">
							<span class="imogi-dm-pnl-row__label">${label}</span>
							<span class="imogi-dm-pnl-row__value ${value < 0 ? "imogi-dm-pnl-row__value--neg" : ""}">${dm_format_currency(value, currency)}</span>
						</div>`,
					)
					.join("")}
			</div>
		</div>`;
}

function dm_build_trend_card() {
	return `
		<div class="imogi-dm-card">
			<div class="imogi-dm-card__header">
				<span>${__("Tren Omzet & Laba Kotor · 6 Bulan Terakhir")}</span>
			</div>
			<div class="imogi-dm-card__body">
				<div id="imogi-dm-trend-chart-target"></div>
			</div>
		</div>`;
}

function dm_render_trend_chart(data) {
	const target = document.getElementById("imogi-dm-trend-chart-target");
	if (!target) return;
	target.innerHTML = "";

	const trend = data.pnl_trend || [];
	if (!trend.length) {
		target.innerHTML = `<div class="imogi-dm-empty">${__("Belum ada data.")}</div>`;
		return;
	}

	new frappe.Chart(target, {
		data: {
			labels: trend.map((r) => r.month_label),
			datasets: [
				{ name: __("Omzet"), values: trend.map((r) => r.omzet) },
				{ name: __("Laba Kotor"), values: trend.map((r) => r.gross_profit) },
			],
		},
		type: "line",
		height: 220,
		colors: ["#5e64ff", "#28a745"],
		lineOptions: { regionFill: 1 },
		axisOptions: { xAxisMode: "tick" },
	});
}

function dm_build_pipeline_card(data) {
	const so = data.so_pipeline || {};
	const dikerjakanTungguPart = (so.dikerjakan || 0) + (so.tunggu_part || 0);
	const siapDiambil = so.siap_diambil || 0;
	const antrian = so.antrian || 0;
	const selesai = so.selesai || 0;
	const masihDiproses = antrian + dikerjakanTungguPart + siapDiambil;

	const rows = [
		{ key: "antrian", label: __("Antrian"), value: antrian, color: "#93c5fd" },
		{ key: "dikerjakan_tunggu_part", label: __("Dikerjakan / Tunggu Part"), value: dikerjakanTungguPart, color: "#3b82f6" },
		{ key: "siap_diambil", label: __("Siap Diambil"), value: siapDiambil, color: "#60a5fa" },
		{ key: "selesai", label: __("Selesai / Invoiced"), value: selesai, color: "#1e3a8a" },
	];
	const max = Math.max(1, ...rows.map((r) => r.value));

	return `
		<div class="imogi-dm-card">
			<div class="imogi-dm-card__header">
				<span>${__("Pipeline Service Order")}</span>
				<div class="imogi-dm-pipeline-stats">
					<div class="imogi-dm-pipeline-stat">
						<span class="imogi-dm-pipeline-stat__value imogi-dm-pipeline-stat__value--active">${masihDiproses}</span>
						<span class="imogi-dm-pipeline-stat__label">${__("Masih Diproses")}</span>
					</div>
					<span class="imogi-dm-pipeline-stat__divider"></span>
					<div class="imogi-dm-pipeline-stat">
						<span class="imogi-dm-pipeline-stat__value imogi-dm-pipeline-stat__value--done">${selesai}</span>
						<span class="imogi-dm-pipeline-stat__label">${__("Selesai / Invoiced")}</span>
					</div>
				</div>
			</div>
			<div class="imogi-dm-card__body">
				${rows
					.map(
						(r) => `
					<div class="imogi-dm-pipeline-bar-row" data-pipeline="${r.key}">
						<div class="imogi-dm-pipeline-bar-row__top">
							<span class="imogi-dm-pipeline-bar-row__label">${r.label}</span>
							<span class="imogi-dm-pipeline-bar-row__value">${r.value}</span>
						</div>
						<span class="imogi-dm-pipeline-bar-row__track">
							<span class="imogi-dm-pipeline-bar-row__fill" style="width:${(r.value / max) * 100}%;background:${r.color}"></span>
						</span>
					</div>`,
					)
					.join("")}
			</div>
		</div>`;
}

function dm_build_aging_card(data) {
	const currency = data.currency;
	const buckets = (data.ar && data.ar.aging_buckets) || {};
	const rows = [
		[__("Belum Jatuh Tempo"), buckets.not_due || 0, "#5e64ff"],
		[__("0–30 hari"), buckets.days_0_30 || 0, "#f0ad4e"],
		[__("31–60 hari"), buckets.days_31_60 || 0, "#fd7e14"],
		[__("61–90 hari"), buckets.days_61_90 || 0, "#dc3545"],
		[__("> 90 hari"), buckets.days_90_plus || 0, "#721c24"],
	];
	const max = Math.max(1, ...rows.map((r) => r[1]));

	return `
		<div class="imogi-dm-card">
			<div class="imogi-dm-card__header">
				<span>${__("Aging Piutang (AR)")}</span>
				<span class="imogi-dm-card__header-sub">${__("Total")} ${dm_format_currency(data.ar.outstanding.amount, currency)}</span>
			</div>
			<div class="imogi-dm-card__body">
				${rows
					.map(
						([label, amount, color]) => `
					<div class="imogi-dm-aging-row">
						<span class="imogi-dm-aging-row__label">${label}</span>
						<span class="imogi-dm-aging-row__bar-track">
							<span class="imogi-dm-aging-row__bar-fill" style="width:${(amount / max) * 100}%;background:${color}"></span>
						</span>
						<span class="imogi-dm-aging-row__amount">${dm_format_currency(amount, currency)}</span>
					</div>`,
					)
					.join("")}
			</div>
		</div>`;
}

function dm_build_document_list_card(title, rows, currency, { partyField, doctype }) {
	const header = `
		<div class="imogi-dm-list-header">
			<span>${__("Nama")}</span>
			<span>${__("Jatuh Tempo")}</span>
			<span class="imogi-dm-list-header__amount">${__("Jumlah")}</span>
		</div>`;

	const body = rows.length
		? rows
				.map((row) => {
					const late = row.late_days ? `${row.late_days} ${__("hari terlambat")}` : "";
					return `
					<div class="imogi-dm-list-row" data-doctype="${doctype}" data-name="${frappe.utils.escape_html(row.name)}">
						<div class="imogi-dm-list-row__col--name">
							<span class="imogi-dm-list-row__party imogi-dm-list-row__name">${frappe.utils.escape_html(row[partyField] || row.name)}</span>
						</div>
						<div class="imogi-dm-list-row__col--due">
							<span class="imogi-dm-list-row__due-date">${frappe.datetime.str_to_user(row.due_date)}</span>
							${late ? `<span class="imogi-dm-list-row__due-late">${late}</span>` : ""}
						</div>
						<div class="imogi-dm-list-row__col--amount">${dm_format_currency(row.outstanding_amount, currency)}</div>
					</div>`;
				})
				.join("")
		: `<div class="imogi-dm-empty">${__("Tidak ada data.")}</div>`;

	return `
		<div class="imogi-dm-card">
			<div class="imogi-dm-card__header"><span>${title}</span></div>
			<div class="imogi-dm-card__body">${rows.length ? header : ""}${body}</div>
		</div>`;
}

function dm_build_cards_html(data) {
	const currency = data.currency;

	return `
		<div class="imogi-dm-scope">
			<div class="imogi-dm-caption">${__("Semua Cabang")} · ${frappe.datetime.str_to_user(data.period.from_date)} – ${frappe.datetime.str_to_user(data.period.to_date)}</div>
			${dm_build_kpi_row(data)}
			<div class="imogi-dm-two-col">
				${dm_build_pnl_card(data)}
				${dm_build_trend_card()}
			</div>
			<div class="imogi-dm-two-col">
				${dm_build_pipeline_card(data)}
				${dm_build_document_list_card(__("Hutang Perlu Dibayar"), data.ap_due_list, currency, {
					partyField: "supplier_name",
					doctype: "Purchase Invoice",
				})}
			</div>
			<div class="imogi-dm-two-col">
				${dm_build_aging_card(data)}
				${dm_build_document_list_card(__("Piutang Jatuh Tempo Terbesar"), data.ar_overdue_top, currency, {
					partyField: "customer_name",
					doctype: "Sales Invoice",
				})}
			</div>
		</div>`;
}

function dm_open_list(doctype, filters) {
	frappe.set_route("List", doctype, filters);
}

function dm_bind_card_clicks(report, data) {
	const company = report.get_filter_value("company");
	const $main = report.page.main;

	$main.find(".imogi-dm-kpi-tile[data-clickable='1']").off("click.imogi_dm").on("click.imogi_dm", function () {
		const route = $(this).data("route");
		if (route === "ar") {
			dm_open_list("Sales Invoice", { company, outstanding_amount: [">", 0] });
		} else if (route === "ap") {
			dm_open_list("Purchase Invoice", { company, outstanding_amount: [">", 0] });
		} else if (route === "omzet") {
			dm_open_list("Sales Invoice", {
				company,
				posting_date: ["Between", [data.period.from_date, data.period.to_date]],
			});
		} else if (route === "so_active") {
			dm_open_list("Garage Service Order", { status: ["in", ["Waiting Part", "Prepared", "In Progress"]] });
		}
	});

	$main.find(".imogi-dm-pipeline-bar-row").off("click.imogi_dm").on("click.imogi_dm", function () {
		const key = $(this).data("pipeline");
		const statuses = DM_PIPELINE_STATUS_FILTERS[key];
		if (statuses) dm_open_list("Garage Service Order", { status: ["in", statuses] });
	});

	$main.find(".imogi-dm-list-row").off("click.imogi_dm").on("click.imogi_dm", function () {
		const doctype = $(this).data("doctype");
		const name = $(this).data("name");
		if (doctype && name) frappe.set_route("Form", doctype, name);
	});
}

function dm_render_cards(report) {
	const company = report.get_filter_value("company");
	if (!company) return;

	dm_inject_card_styles();
	report.page.main.addClass("imogi-dm-dashboard");
	report.page.container.addClass("full-width");
	dm_hide_report_chrome(report);

	frappe.call({
		method: DM_CARD_METHOD,
		args: {
			company,
			from_date: report.get_filter_value("from_date"),
			to_date: report.get_filter_value("to_date"),
		},
		callback(r) {
			if (!r.message) return;
			const $main = report.page.main;
			const $host = dm_ensure_cards_host($main);
			$host.html(dm_build_cards_html(r.message));
			dm_render_trend_chart(r.message);
			dm_bind_card_clicks(report, r.message);
			dm_hide_report_chrome(report);
		},
	});
}

function dm_hide_report_chrome(report) {
	report.page.main.find(".report-summary, .chart-wrapper, .report-wrapper, .report-footer, .datatable").hide();
	if (report.$message) report.$message.hide();
	if (report.$report) report.$report.hide();
}

function dm_wrap_report_refresh(report) {
	const finish = () => {
		dm_hide_report_chrome(report);
		dm_render_cards(report);
	};

	const original_refresh = report.refresh.bind(report);
	report.refresh = function (...args) {
		return original_refresh(...args).then((result) => {
			finish();
			return result;
		});
	};
}

function dm_setup_quick_links(report) {
	const company = () => report.get_filter_value("company");

	const links = [
		{
			group: __("Piutang & Hutang"),
			items: [
				{ label: __("Sales Invoice"), action: () => frappe.set_route("List", "Sales Invoice", { company: company() }) },
				{ label: __("Purchase Invoice"), action: () => frappe.set_route("List", "Purchase Invoice", { company: company() }) },
			],
		},
		{
			group: __("Operasional"),
			items: [
				{ label: __("Garage Service Order"), action: () => frappe.set_route("List", "Garage Service Order") },
				{ label: __("General Ledger"), action: () => frappe.set_route("query-report", "General Ledger", { company: company() }) },
			],
		},
	];

	for (const { group, items } of links) {
		for (const { label, action } of items) {
			report.page.add_inner_button(label, action, group);
		}
	}
}

frappe.query_reports["Dashboard Management"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
	],

	onload(report) {
		dm_setup_quick_links(report);
		dm_wrap_report_refresh(report);
		dm_render_cards(report);
	},
};
