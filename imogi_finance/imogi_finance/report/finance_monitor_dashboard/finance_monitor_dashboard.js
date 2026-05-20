// Copyright (c) 2026, Imogi and contributors

const FM_CARD_METHOD =
	"imogi_finance.imogi_finance.report.finance_monitor_dashboard.finance_monitor_dashboard.get_finance_monitor_cards";

function fm_inject_card_styles() {
	if (document.getElementById("imogi-finance-monitor-card-style")) return;
	const style = document.createElement("style");
	style.id = "imogi-finance-monitor-card-style";
	style.textContent = `
		.imogi-fm-cards{margin:12px 0 16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
		.imogi-fm-card{border:1px solid var(--border-color);border-radius:var(--border-radius-lg);padding:14px 16px;background:var(--card-bg);cursor:pointer;transition:box-shadow .15s,border-color .15s}
		.imogi-fm-card:hover{box-shadow:var(--shadow-sm);border-color:var(--primary)}
		.imogi-fm-card__label{font-size:12px;color:var(--text-muted);margin-bottom:6px}
		.imogi-fm-card__count{font-size:26px;font-weight:700;line-height:1.2}
		.imogi-fm-card__amount{font-size:13px;margin-top:4px;color:var(--text-color)}
		.imogi-fm-card--late{border-left:4px solid #dc3545}
		.imogi-fm-card--unpaid{border-left:4px solid #f0ad4e}
		.imogi-fm-aging{margin:0 0 16px;padding:14px 16px;border:1px solid var(--border-color);border-radius:var(--border-radius-lg);background:var(--card-bg)}
		.imogi-fm-aging h6{margin:0 0 12px;font-size:13px;font-weight:600}
		.imogi-fm-aging__bars{display:flex;align-items:flex-end;gap:8px;height:72px}
		.imogi-fm-aging__bar{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0}
		.imogi-fm-aging__fill{width:100%;max-width:48px;border-radius:4px 4px 0 0;background:var(--primary);min-height:2px}
		.imogi-fm-aging__lbl{font-size:10px;color:var(--text-muted);text-align:center;line-height:1.2}
	`;
	document.head.appendChild(style);
}

function fm_format_currency(amount, currency) {
	return frappe.format(amount, {
		fieldtype: "Currency",
		options: currency || frappe.defaults.get_default("currency"),
	});
}

function fm_render_cards(report) {
	const company = report.get_filter_value("company");
	if (!company) return;

	fm_inject_card_styles();

	frappe.call({
		method: FM_CARD_METHOD,
		args: { company },
		callback(r) {
			if (!r.message) return;
			const $main = report.page.main;
			let $host = $main.find(".imogi-fm-cards-host");
			if (!$host.length) {
				$host = $('<div class="imogi-fm-cards-host"></div>');
				const $summary = $main.find(".report-summary");
				if ($summary.length) {
					$summary.after($host);
				} else {
					$main.prepend($host);
				}
			}
			$host.html(fm_build_cards_html(r.message));
			fm_bind_card_clicks(report);
		},
	});
}

function fm_build_cards_html(data) {
	const currency = data.currency;
	const unpaid = data.unpaid || {};
	const late = data.late || {};
	const buckets = data.aging_buckets || {};
	const max_bucket = Math.max(
		1,
		...["not_due", "days_1_7", "days_8_30", "days_31_60", "days_60_plus"].map((k) => flt(buckets[k]))
	);

	const bucket_defs = [
		{ key: "not_due", label: __("Not Due"), color: "#5e64ff" },
		{ key: "days_1_7", label: __("1–7 Late"), color: "#f0ad4e" },
		{ key: "days_8_30", label: __("8–30 Late"), color: "#fd7e14" },
		{ key: "days_31_60", label: __("31–60 Late"), color: "#dc3545" },
		{ key: "days_60_plus", label: __("60+ Late"), color: "#721c24" },
	];

	const agingBars = bucket_defs
		.map((b) => {
			const val = flt(buckets[b.key]);
			const pct = Math.round((val / max_bucket) * 100);
			return `
			<div class="imogi-fm-aging__bar" title="${frappe.utils.escape_html(fm_format_currency(val, currency))}">
				<div class="imogi-fm-aging__fill" style="height:${pct}%;background:${b.color}"></div>
				<div class="imogi-fm-aging__lbl">${b.label}</div>
			</div>`;
		})
		.join("");

	return `
		<div class="imogi-fm-cards">
			<div class="imogi-fm-card imogi-fm-card--unpaid" data-route="unpaid">
				<div class="imogi-fm-card__label">${__("Unpaid Invoices")}</div>
				<div class="imogi-fm-card__count">${unpaid.count || 0}</div>
				<div class="imogi-fm-card__amount">${fm_format_currency(unpaid.amount, currency)}</div>
			</div>
			<div class="imogi-fm-card imogi-fm-card--late" data-route="late">
				<div class="imogi-fm-card__label">${__("Late Invoices")}</div>
				<div class="imogi-fm-card__count">${late.count || 0}</div>
				<div class="imogi-fm-card__amount">${fm_format_currency(late.amount, currency)}</div>
			</div>
			<div class="imogi-fm-card" data-route="so_partly">
				<div class="imogi-fm-card__label">${__("SO Partly Billed")}</div>
				<div class="imogi-fm-card__count">${data.so_partly_billed_count || 0}</div>
				<div class="imogi-fm-card__amount text-muted">${__("Open list")}</div>
			</div>
		</div>
		<div class="imogi-fm-aging">
			<h6>${__("Receivable aging (by due date)")}</h6>
			<div class="imogi-fm-aging__bars">${agingBars}</div>
		</div>
	`;
}

function fm_bind_card_clicks(report) {
	const company = report.get_filter_value("company");
	const today = frappe.datetime.get_today();

	report.page.main.find(".imogi-fm-card").off("click.imogi_fm").on("click.imogi_fm", function () {
		const route = $(this).data("route");
		if (route === "unpaid") {
			frappe.set_route("List", "Sales Invoice", {
				company,
				outstanding_amount: [">", 0],
				docstatus: 1,
			});
		} else if (route === "late") {
			frappe.set_route("List", "Sales Invoice", {
				company,
				outstanding_amount: [">", 0],
				due_date: ["<", today],
				docstatus: 1,
			});
		} else if (route === "so_partly") {
			frappe.set_route("List", "Sales Order", {
				company,
				per_billed: ["<", 100],
				docstatus: 1,
			});
		}
	});
}

function fm_open_late_invoices(report) {
	frappe.set_route("List", "Sales Invoice", {
		company: report.get_filter_value("company"),
		outstanding_amount: [">", 0],
		due_date: ["<", frappe.datetime.get_today()],
		docstatus: 1,
	});
}

frappe.query_reports["Finance Monitor Dashboard"] = {
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
		report.page.add_inner_button(__("Unpaid Invoices"), () => {
			frappe.set_route("List", "Sales Invoice", {
				company: report.get_filter_value("company"),
				outstanding_amount: [">", 0],
				docstatus: 1,
			});
		});

		report.page.add_inner_button(__("Late Invoices"), () => fm_open_late_invoices(report));

		report.page.add_inner_button(__("Partly Billed SO"), () => {
			frappe.set_route("List", "Sales Order", {
				company: report.get_filter_value("company"),
				per_billed: ["<", 100],
				docstatus: 1,
			});
		});

		report.page.add_inner_button(__("Payment Entries"), () => {
			frappe.set_route("List", "Payment Entry", {
				company: report.get_filter_value("company"),
				posting_date: [
					"Between",
					[report.get_filter_value("from_date"), report.get_filter_value("to_date")],
				],
				docstatus: 1,
			});
		});

		fm_render_cards(report);
	},

	refresh(report) {
		fm_render_cards(report);
	},

	formatter(value, row, column, data, default_formatter) {
		if (data && (data.is_section || data.is_empty)) {
			if (column.fieldname === "row_type") {
				const style = data.is_section
					? "font-weight:600;font-size:13px;padding:8px 0;color:var(--text-color)"
					: "color:var(--text-muted);font-style:italic";
				return `<span style="${style}">${frappe.utils.escape_html(data.row_type || "")}</span>`;
			}
			return "";
		}

		value = default_formatter(value, row, column, data);

		if (column.fieldname === "outstanding_amount" && data && flt(data.outstanding_amount) > 0) {
			return `<span style="color:#d9534f;font-weight:600">${value}</span>`;
		}

		if (column.fieldname === "late_days" && data && flt(data.late_days) > 0) {
			const color = flt(data.late_days) > 30 ? "#dc3545" : "#f0ad4e";
			return `<span style="color:${color};font-weight:600">${value}</span>`;
		}

		if (column.fieldname === "status" && data && data.status) {
			const status = data.status;
			const orange = ["Partially Paid", "Partial Paid", "Outstanding Invoice", "Partly Billed", "SI Created"];
			const green = ["Paid", "Fully Billed"];
			let color = "blue";
			if (green.includes(status)) color = "green";
			else if (orange.includes(status)) color = "orange";
			else if (status === "Overdue" || status === "Unpaid") color = "red";
			return `<span class="indicator-pill ${color}">${status}</span>`;
		}

		return value;
	},
};
