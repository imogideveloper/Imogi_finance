// Copyright (c) 2026, Imogi and contributors

const FM_CARD_METHOD =
	"imogi_finance.imogi_finance.report.finance_monitor_dashboard.finance_monitor_dashboard.get_finance_monitor_cards";

function fm_inject_card_styles() {
	if (document.getElementById("imogi-finance-monitor-card-style-v8")) return;
	const style = document.createElement("style");
	style.id = "imogi-finance-monitor-card-style-v8";
	style.textContent = `
		.imogi-fm-dashboard .datatable,
		.imogi-fm-dashboard .report-wrapper,
		.imogi-fm-dashboard .report-footer,
		.imogi-fm-dashboard .report-summary,
		.imogi-fm-dashboard .chart-wrapper{display:none!important}
		.imogi-fm-cards{display:flex;flex-wrap:wrap;gap:16px;margin:16px 0;align-items:flex-start}
		.imogi-fm-invoice-card{width:min(100%,500px);max-width:500px;flex:0 0 auto;border-radius:var(--border-radius-lg);overflow:hidden;display:flex;flex-direction:column;border:1px solid #e2e5e9;background:#f8f9fa;box-shadow:0 1px 3px rgba(0,0,0,.06)}
		.imogi-fm-invoice-card__header{display:flex;align-items:center;gap:10px;padding:12px 16px;background:#f0f1f3;border-bottom:1px solid #e2e5e9}
		.imogi-fm-invoice-card__icon{font-size:18px;line-height:1;color:#6c757d}
		.imogi-fm-invoice-card__title{font-size:15px;font-weight:600;margin:0;flex:1;color:#364152}
		.imogi-fm-invoice-card__metrics{display:grid;grid-template-columns:auto auto;column-gap:28px;row-gap:12px;justify-content:end;align-items:baseline;padding:12px 16px 14px}
		.imogi-fm-metric__link{font-size:15px;font-weight:500;color:var(--primary);text-decoration:none;cursor:pointer;justify-self:end;text-align:right;white-space:nowrap}
		.imogi-fm-metric__link:hover{text-decoration:none;color:var(--primary)}
		.imogi-fm-metric__amount{font-size:20px;font-weight:700;line-height:1.25;letter-spacing:-.02em;white-space:nowrap;justify-self:end;text-align:right}
		.imogi-fm-metric__amount--unpaid{color:#059669}
		.imogi-fm-metric__amount--late{color:#dc3545}
	`;
	document.head.appendChild(style);
}

function fm_format_currency(amount, currency) {
	return frappe.format(amount, {
		fieldtype: "Currency",
		options: currency || frappe.defaults.get_default("currency"),
	});
}

function fm_ensure_cards_host($main) {
	let $host = $main.find(".imogi-fm-cards-host");
	if (!$host.length) {
		$host = $('<div class="imogi-fm-cards-host"></div>');
	}
	const $filters = $main.find(".page-form").first();
	if ($filters.length) {
		$host.insertAfter($filters);
	} else {
		$main.prepend($host);
	}
	return $host;
}

function fm_render_cards(report) {
	const company = report.get_filter_value("company");
	if (!company) return;

	fm_inject_card_styles();
	report.page.main.addClass("imogi-fm-dashboard");
	fm_hide_report_chrome(report);

	frappe.call({
		method: FM_CARD_METHOD,
		args: { company },
		callback(r) {
			if (!r.message) return;
			const $main = report.page.main;
			const $host = fm_ensure_cards_host($main);
			$host.html(fm_build_cards_html(r.message));
			fm_bind_card_clicks(report);
			fm_hide_report_chrome(report);
		},
	});
}

function fm_build_invoice_card(card, side, currency) {
	const unpaid = card.unpaid || {};
	const late = card.late || {};
	const icon = side === "sales" ? "es-line-file" : "es-line-receipt";

	return `
		<div class="imogi-fm-invoice-card imogi-fm-invoice-card--${side}" data-side="${side}">
			<div class="imogi-fm-invoice-card__header">
				<span class="imogi-fm-invoice-card__icon">${frappe.utils.icon(icon, "md")}</span>
				<h6 class="imogi-fm-invoice-card__title">${card.title}</h6>
			</div>
			<div class="imogi-fm-invoice-card__metrics">
				<a href="#" class="imogi-fm-metric__link" data-route="${side}_unpaid">${unpaid.count || 0} ${__("Unpaid Invoices")}</a>
				<span class="imogi-fm-metric__amount imogi-fm-metric__amount--unpaid">${fm_format_currency(unpaid.amount, currency)}</span>
				<a href="#" class="imogi-fm-metric__link" data-route="${side}_late">${late.count || 0} ${__("Late Invoices")}</a>
				<span class="imogi-fm-metric__amount imogi-fm-metric__amount--late">${fm_format_currency(late.amount, currency)}</span>
			</div>
		</div>`;
}

function fm_build_cards_html(data) {
	const currency = data.currency;
	const sales = data.sales || {};
	const purchase = data.purchase || {};

	return `
		<div class="imogi-fm-cards">
			${fm_build_invoice_card(sales, "sales", currency)}
			${fm_build_invoice_card(purchase, "purchase", currency)}
		</div>
	`;
}

function fm_open_invoice_list(doctype, company, filters) {
	frappe.set_route("List", doctype, { company, docstatus: 1, ...filters });
}

function fm_bind_card_clicks(report) {
	const company = report.get_filter_value("company");
	const today = frappe.datetime.get_today();
	const $main = report.page.main;

	$main.find(".imogi-fm-metric__link").off("click.imogi_fm").on("click.imogi_fm", function (e) {
		e.preventDefault();
		const route = $(this).data("route");
		if (route === "sales_unpaid") {
			fm_open_invoice_list("Sales Invoice", company, { outstanding_amount: [">", 0] });
		} else if (route === "sales_late") {
			fm_open_invoice_list("Sales Invoice", company, {
				outstanding_amount: [">", 0],
				due_date: ["<", today],
			});
		} else if (route === "purchase_unpaid") {
			fm_open_invoice_list("Purchase Invoice", company, { outstanding_amount: [">", 0] });
		} else if (route === "purchase_late") {
			fm_open_invoice_list("Purchase Invoice", company, {
				outstanding_amount: [">", 0],
				due_date: ["<", today],
			});
		}
	});
}

function fm_open_late_invoices(report, doctype = "Sales Invoice") {
	frappe.set_route("List", doctype, {
		company: report.get_filter_value("company"),
		outstanding_amount: [">", 0],
		due_date: ["<", frappe.datetime.get_today()],
		docstatus: 1,
	});
}

function fm_hide_report_chrome(report) {
	report.page.main.find(".report-summary, .chart-wrapper, .report-wrapper, .report-footer, .datatable").hide();
	if (report.$message) report.$message.hide();
	if (report.$report) report.$report.hide();
}

function fm_wrap_report_refresh(report) {
	const finish = () => {
		fm_hide_report_chrome(report);
		fm_render_cards(report);
	};

	const original_refresh = report.refresh.bind(report);
	report.refresh = function (...args) {
		return original_refresh(...args).then((result) => {
			finish();
			return result;
		});
	};
}

function fm_setup_quick_links(report) {
	const company = () => report.get_filter_value("company");
	const period = () => [
		report.get_filter_value("from_date"),
		report.get_filter_value("to_date"),
	];

	const links = [
		{
			group: __("Customer"),
			items: [
				{ label: __("Unpaid Invoices"), action: () => fm_open_invoice_list("Sales Invoice", company(), { outstanding_amount: [">", 0] }) },
				{ label: __("Late Invoices"), action: () => fm_open_late_invoices(report, "Sales Invoice") },
				{ label: __("Partly Billed SO"), action: () => frappe.set_route("List", "Sales Order", { company: company(), per_billed: ["<", 100], docstatus: 1 }) },
			],
		},
		{
			group: __("Supplier"),
			items: [
				{ label: __("Unpaid Bills"), action: () => fm_open_invoice_list("Purchase Invoice", company(), { outstanding_amount: [">", 0] }) },
				{ label: __("Late Bills"), action: () => fm_open_late_invoices(report, "Purchase Invoice") },
				{ label: __("Partly Billed PO"), action: () => frappe.set_route("List", "Purchase Order", { company: company(), per_billed: ["<", 100], docstatus: 1 }) },
			],
		},
		{
			group: __("Cash"),
			items: [
				{
					label: __("Payment Entries"),
					action: () =>
						frappe.set_route("List", "Payment Entry", {
							company: company(),
							posting_date: ["Between", period()],
							docstatus: 1,
						}),
				},
			],
		},
	];

	for (const { group, items } of links) {
		for (const { label, action } of items) {
			report.page.add_inner_button(label, action, group);
		}
	}
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
		fm_setup_quick_links(report);
		fm_wrap_report_refresh(report);
		fm_render_cards(report);
	},
};
