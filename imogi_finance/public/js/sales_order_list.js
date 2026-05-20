console.log("SALES ORDER LIST JS LOADED");

function imogi_so_list_route_str() {
	try {
		const route = frappe.get_route?.() || frappe.router?.current_route;
		return route?.length ? route.join("/") : "";
	} catch (e) {
		return "";
	}
}

// Frappe List View Settings: opsi maksimum di UI hanya 4–10 (bukan 14).
const SO_LIST_MIN_TOTAL_FIELDS = 10;

const SO_STATUS_COLORS = {
	Draft: "grey",
	Submitted: "blue",
	"SI Created": "blue",
	"Outstanding Invoice": "orange",
	"Partial Paid": "orange",
	Paid: "green",
	Cancelled: "red",
};

const SO_STATUS_ICON = {
	"Outstanding Invoice": "es-solid-dot",
	"Partial Paid": "es-solid-dot",
	"SI Created": "es-line-inbox",
	Paid: "es-solid-success",
	Submitted: "es-line-inbox",
	Draft: "es-line-edit",
	Cancelled: "es-solid-close-circle",
};

frappe.listview_settings["Sales Order"] = {
	add_fields: [
		"custom_payment_status",
		"docstatus",
		"transaction_date",
		"outstanding_amount",
		"currency",
		"grand_total",
		"advance_paid",
	],

	get_indicator(doc) {
		const status = get_business_status(doc);
		const color = SO_STATUS_COLORS[status] || "grey";
		return [__(status), color, `custom_payment_status,=,${frappe.utils.escape_html(status)}`];
	},

	get_indicator_html(doc, show_workflow_state) {
		const indicator = frappe.get_indicator(doc, this.doctype, show_workflow_state);
		if (!indicator) return "";

		const status = get_business_status(doc);
		const label = indicator[0];
		const color = indicator[1];
		const filter = indicator[2];
		const title = frappe.utils.escape_html(doc.name || "");

		return (
			`<span class="indicator-pill so-status-pill ${color} filterable no-indicator-dot ellipsis"` +
			` data-filter="${frappe.utils.escape_html(filter)}" data-so-status="${frappe.utils.escape_html(status)}" title="${title}">` +
			soStatusIconHtml(status) +
			`<span class="so-status-label">${frappe.utils.escape_html(label)}</span>` +
			`</span>`
		);
	},

	formatters: {
		custom_payment_status(value, df, doc) {
			const status = get_business_status(doc);
			const color = SO_STATUS_COLORS[status] || "grey";
			return (
				`<span class="indicator-pill so-status-pill ${color} no-indicator-dot ellipsis" data-so-status="${frappe.utils.escape_html(status)}">` +
				soStatusIconHtml(status) +
				`<span class="so-status-label">${frappe.utils.escape_html(__(status))}</span>` +
				`</span>`
			);
		},
		grand_total(value, df, doc) {
			if (value == null || value === "") {
				return `<span class="text-muted">—</span>`;
			}
			const formatted = frappe.format(value, df, doc);
			return `<span class="so-grand-total">${formatted}</span>`;
		},
		outstanding_amount: format_so_outstanding_amount,
	},

	onload(listview) {
		patch_sales_order_listview_settings();
		inject_so_status_styles();
		setup_so_outstanding_list(listview);
		listview.get_indicator_html = imogi_so_list_get_indicator_html;
		if (imogi_finance.so_list?.init_toolbar) {
			imogi_finance.so_list.init_toolbar(listview);
		}
		listview.page.add_inner_button(__("📅 Filter Tanggal"), function () {
			show_date_filter_dialog(listview);
		});
	},
};

patch_sales_order_listview_settings();
if (typeof frappe.ready === "function") {
	frappe.ready(patch_sales_order_listview_settings);
} else {
	$(patch_sales_order_listview_settings);
}
frappe.after_ajax(() => {
	if (imogi_so_list_route_str() !== "List/Sales Order") return;
	patch_sales_order_listview_settings();
	if (!$("#so-list-toolbar").length) {
		imogi_so_list_ensure_toolbar(cur_list);
	}
});
$(document).on("page-change", function () {
	if (imogi_so_list_route_str() === "List/Sales Order") {
		setTimeout(() => {
			patch_sales_order_listview_settings();
			imogi_so_list_ensure_toolbar(cur_list);
		}, 0);
	}
});

function imogi_so_list_ensure_toolbar(listview) {
	if (!listview || listview.doctype !== "Sales Order") return;

	const run = () => {
		if (typeof window.init_imogi_so_status_toolbar === "function") {
			window.init_imogi_so_status_toolbar(listview);
		} else if (imogi_finance.so_list?.init_toolbar) {
			imogi_finance.so_list.init_toolbar(listview);
		}
	};

	if (typeof window.init_imogi_so_status_toolbar === "function") {
		run();
		return;
	}

	frappe.require("/assets/imogi_finance/js/sales_order_list_toolbar.js", run);
}

// Client Script (__custom_list_js) runs AFTER this file and replaces listview_settings.
(function hook_so_list_after_client_script() {
	if (frappe.model.__imogi_so_list_meta_hooked) return;
	frappe.model.__imogi_so_list_meta_hooked = true;
	const orig_init_doctype = frappe.model.init_doctype;
	frappe.model.init_doctype = function (doctype) {
		orig_init_doctype.apply(this, arguments);
		if (doctype !== "Sales Order") return;
		patch_sales_order_listview_settings();
		setTimeout(() => {
			if (cur_list?.doctype === "Sales Order") {
				imogi_so_list_ensure_toolbar(cur_list);
			}
		}, 50);
	};
})();

function normalize_so_payment_status(status) {
	const value = (status || "").trim();
	if (value === "Partial Paid") return "Outstanding Invoice";
	return value;
}

function get_business_status(doc) {
	if (cint(doc.docstatus) === 2) return "Cancelled";
	if (cint(doc.docstatus) === 0) return "Draft";
	return normalize_so_payment_status(doc.custom_payment_status) || "Submitted";
}

function soStatusIconHtml(status) {
	const icon = SO_STATUS_ICON[status] || "es-line-status";
	if (typeof frappe.utils.icon === "function") {
		return frappe.utils.icon(icon, "xs", "", "", "so-status-icon");
	}
	return `<svg class="icon icon-xs so-status-icon" aria-hidden="true"><use href="#${icon}"></use></svg>`;
}

function inject_so_status_styles() {
	if (document.getElementById("so-list-status-style")) return;
	const style = document.createElement("style");
	style.id = "so-list-status-style";
	style.textContent =
		"[data-page-route^='List/Sales Order'] .so-status-pill{display:inline-flex!important;align-items:center!important;gap:5px;max-width:100%;padding:3px 10px 3px 8px;border-radius:999px;font-size:11px;font-weight:600;line-height:1;height:22px;box-sizing:border-box;box-shadow:0 1px 2px rgba(15,23,42,.04)}" +
		"[data-page-route^='List/Sales Order'] .so-status-pill .so-status-icon{width:12px!important;height:12px!important;min-width:12px!important;flex-shrink:0}" +
		"[data-page-route^='List/Sales Order'] .so-status-pill.orange{background:#fff4e8;color:#b45309;border:1px solid #fed7aa}" +
		"[data-page-route^='List/Sales Order'] .so-status-pill.green{background:#ecfdf3;color:#166534;border:1px solid #bbf7d0}" +
		"[data-page-route^='List/Sales Order'] .so-status-pill.blue{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}" +
		"[data-page-route^='List/Sales Order'] .so-status-pill.grey{background:#f3f4f6;color:#4b5563;border:1px solid #e5e7eb}" +
		"[data-page-route^='List/Sales Order'] .so-status-pill.red{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca}";
	document.head.appendChild(style);
}

function format_so_outstanding_amount(value, df, doc) {
	const status = get_business_status(doc);
	if (status !== "Outstanding Invoice") {
		return `<span class="so-outstanding-empty text-muted">—</span>`;
	}
	const amount = flt(value);
	if (!amount) {
		return `<span class="so-outstanding-empty text-muted">—</span>`;
	}
	const formatted =
		typeof format_currency === "function"
			? format_currency(amount, doc.currency)
			: frappe.format(amount, df, doc);
	return (
		`<span class="so-outstanding-amount" title="${frappe.utils.escape_html(
			__("Outstanding Amount")
		)}">${formatted}</span>`
	);
}

function inject_so_outstanding_styles() {
	if (document.getElementById("so-list-outstanding-style")) return;
	const style = document.createElement("style");
	style.id = "so-list-outstanding-style";
	style.textContent =
		"[data-page-route^='List/Sales Order'] .list-row-col[data-fieldname='outstanding_amount']," +
		"[data-page-route^='List/Sales Order'] .list-row-head .list-row-col.so-col-outstanding{" +
		"flex:0 0 136px!important;width:136px!important;max-width:136px!important;text-align:right!important}" +
		"[data-page-route^='List/Sales Order'] .so-outstanding-amount{" +
		"font-weight:600;color:#c2410c;font-variant-numeric:tabular-nums;white-space:nowrap}";
	document.head.appendChild(style);
}

function ensure_so_outstanding_list_column(listview) {
	if (!listview?.list_view_settings) return;

	let fields = [];
	try {
		fields = JSON.parse(listview.list_view_settings.fields || "[]");
	} catch (e) {
		fields = [];
	}

	const spec = { fieldname: "outstanding_amount", label: __("Outstanding") };
	let idx = fields.findIndex((f) => f.fieldname === "outstanding_amount");
	if (idx === -1) {
		const gt = fields.findIndex((f) => f.fieldname === "grand_total");
		if (gt >= 0) fields.splice(gt + 1, 0, spec);
		else fields.push(spec);
		idx = fields.findIndex((f) => f.fieldname === "outstanding_amount");
	}

	const gt = fields.findIndex((f) => f.fieldname === "grand_total");
	if (idx > -1 && gt > -1 && idx !== gt + 1) {
		const [col] = fields.splice(idx, 1);
		fields.splice(gt + 1, 0, col);
	}

	const fields_json = JSON.stringify(fields);
	const needs_update =
		listview.list_view_settings.fields !== fields_json ||
		cint(listview.list_view_settings.total_fields) < SO_LIST_MIN_TOTAL_FIELDS;

	if (needs_update) {
		listview.list_view_settings.fields = fields_json;
		listview.list_view_settings.total_fields = String(SO_LIST_MIN_TOTAL_FIELDS);
		if (typeof listview.setup_columns === "function") {
			listview.setup_columns();
		}
	}

	persist_so_list_total_fields(listview);
}

function persist_so_list_total_fields(listview) {
	const current = cint(listview?.list_view_settings?.total_fields);
	if (current >= SO_LIST_MIN_TOTAL_FIELDS) return;
	if (listview.__so_total_fields_persisting) return;
	listview.__so_total_fields_persisting = true;

	const payload = Object.assign({}, listview.list_view_settings, {
		total_fields: String(SO_LIST_MIN_TOTAL_FIELDS),
	});

	frappe.call({
		method: "frappe.desk.doctype.list_view_settings.list_view_settings.save_listview_settings",
		args: {
			doctype: "Sales Order",
			listview_settings: payload,
			removed_listview_fields: [],
		},
		callback(r) {
			listview.__so_total_fields_persisting = false;
			if (r.message?.listview_settings) {
				listview.list_view_settings = r.message.listview_settings;
				if (typeof listview.setup_columns === "function") {
					listview.setup_columns();
				}
				if (typeof listview.render === "function") {
					listview.render();
				}
			}
		},
		error() {
			listview.__so_total_fields_persisting = false;
		},
	});
}

function tag_so_outstanding_column_headers(listview) {
	if (!listview?.$result) return;
	const cols = listview.columns || [];
	listview.$result.find(".list-row-head .list-row-col").each(function (i) {
		const col = cols[i];
		if (col?.df?.fieldname === "outstanding_amount") {
			$(this).addClass("so-col-outstanding").attr("data-fieldname", "outstanding_amount");
		}
	});
	listview.$result.find(".list-row-container .level-left .list-row-col").each(function (i) {
		const col = cols[i];
		if (col?.df?.fieldname === "outstanding_amount") {
			$(this).addClass("so-col-outstanding").attr("data-fieldname", "outstanding_amount");
		}
	});
}

function setup_so_outstanding_list(listview) {
	patch_sales_order_listview_settings();
	inject_so_status_styles();
	inject_so_outstanding_styles();
	ensure_so_outstanding_list_column(listview);
	tag_so_outstanding_column_headers(listview);

	if (!listview.__so_outstanding_render_patched) {
		listview.__so_outstanding_render_patched = true;
		const orig_render = listview.render.bind(listview);
		listview.render = function () {
			const result = orig_render();
			tag_so_outstanding_column_headers(listview);
			return result;
		};
	}
}

function imogi_so_list_get_indicator(doc) {
	const status = get_business_status(doc);
	const color = SO_STATUS_COLORS[status] || "grey";
	return [__(status), color, `custom_payment_status,=,${status}`];
}

function imogi_so_list_get_indicator_html(doc, show_workflow_state) {
	const indicator = frappe.get_indicator(doc, "Sales Order", show_workflow_state);
	if (!indicator) return "";

	const status = get_business_status(doc);
	const label = indicator[0];
	const color = indicator[1];
	const filter = indicator[2];
	const title = frappe.utils.escape_html(doc.name || "");

	return (
		`<span class="indicator-pill so-status-pill ${color} filterable no-indicator-dot ellipsis"` +
		` data-filter="${frappe.utils.escape_html(filter)}" data-so-status="${frappe.utils.escape_html(status)}" title="${title}">` +
		soStatusIconHtml(status) +
		`<span class="so-status-label">${frappe.utils.escape_html(label)}</span>` +
		`</span>`
	);
}

function imogi_so_list_format_payment_status(value, df, doc) {
	const status = get_business_status(doc);
	const color = SO_STATUS_COLORS[status] || "grey";
	return (
		`<span class="indicator-pill so-status-pill ${color} no-indicator-dot ellipsis" data-so-status="${frappe.utils.escape_html(status)}">` +
		soStatusIconHtml(status) +
		`<span class="so-status-label">${frappe.utils.escape_html(__(status))}</span>` +
		`</span>`
	);
}

function patch_sales_order_listview_settings() {
	// Client Script menimpa listview_settings — paksa handler imogi_finance.
	if (typeof window.get_so_business_status === "function") {
		window.get_so_business_status = function (doc) {
			return get_business_status(doc);
		};
	}

	const settings = frappe.listview_settings["Sales Order"];
	if (!settings) return;

	settings.add_fields = settings.add_fields || [];
	["outstanding_amount", "currency", "grand_total", "custom_payment_status", "docstatus"].forEach(
		(fieldname) => {
			if (!settings.add_fields.includes(fieldname)) {
				settings.add_fields.push(fieldname);
			}
		}
	);

	settings.get_indicator = imogi_so_list_get_indicator;
	settings.get_indicator_html = imogi_so_list_get_indicator_html;

	settings.formatters = settings.formatters || {};
	settings.formatters.outstanding_amount = format_so_outstanding_amount;
	settings.formatters.grand_total =
		frappe.listview_settings["Sales Order"]?.formatters?.grand_total ||
		function (value, df, doc) {
			if (value == null || value === "") return `<span class="text-muted">—</span>`;
			return `<span class="so-grand-total">${frappe.format(value, df, doc)}</span>`;
		};
	settings.formatters.custom_payment_status = imogi_so_list_format_payment_status;

	if (!settings.__so_outstanding_onload_wrapped) {
		const orig_onload = settings.onload;
		settings.onload = function (listview) {
			setup_so_outstanding_list(listview);
			if (orig_onload) {
				orig_onload.call(this, listview);
			}
			// Client Script onload injects #erg-wrap — toolbar must run after that.
			imogi_so_list_ensure_toolbar(listview);
			setTimeout(() => tag_so_outstanding_column_headers(listview), 300);
		};
		settings.__so_outstanding_onload_wrapped = true;
	}
}

function cint(v) {
	return parseInt(v || 0, 10);
}

function show_date_filter_dialog(listview) {
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "Sales Order",
			fields: ["transaction_date"],
			limit: 0,
			order_by: "transaction_date asc",
		},
		callback: function (r) {
			if (!r.message) return;
			let years = [
				...new Set(r.message.map((d) => frappe.datetime.str_to_obj(d.transaction_date).getFullYear())),
			].sort();
			show_year_picker(listview, years, r.message);
		},
	});
}

function show_year_picker(listview, years, all_data) {
	const month_names = [
		"Januari",
		"Februari",
		"Maret",
		"April",
		"Mei",
		"Juni",
		"Juli",
		"Agustus",
		"September",
		"Oktober",
		"November",
		"Desember",
	];
	let year_buttons = years
		.map((year) => {
			let count = all_data.filter(
				(d) => frappe.datetime.str_to_obj(d.transaction_date).getFullYear() === year
			).length;
			return `<div class="date-filter-item" data-year="${year}" style="padding:10px 20px;margin:5px;border:1px solid #d1d8dd;border-radius:6px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;transition:background 0.2s;"><span style="font-weight:600;font-size:15px;">📅 ${year}</span><span style="background:#e8f4f8;color:#2490ef;padding:2px 10px;border-radius:12px;font-size:12px;">${count} order</span></div>`;
		})
		.join("");

	let d = new frappe.ui.Dialog({
		title: "🗓️ Pilih Tahun",
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "year_picker",
				options: `<div style="padding:10px;"><p style="color:#8d99a6;margin-bottom:10px;font-size:13px;">Pilih tahun untuk memfilter Sales Order</p>${year_buttons}<div style="margin-top:15px;padding-top:10px;border-top:1px solid #eee;"><button class="btn btn-sm btn-default" id="clear-date-filter" style="width:100%;">❌ Hapus Filter Tanggal</button></div></div>`,
			},
		],
	});
	d.show();

	d.$wrapper
		.find(".date-filter-item")
		.on("mouseenter", function () {
			$(this).css("background", "#f0f7ff");
		})
		.on("mouseleave", function () {
			$(this).css("background", "");
		});
	d.$wrapper.find(".date-filter-item").on("click", function () {
		let year = parseInt($(this).data("year"));
		d.hide();
		show_month_picker(listview, year, all_data, month_names);
	});
	d.$wrapper.find("#clear-date-filter").on("click", function () {
		try {
			listview.filter_area.remove("transaction_date");
		} catch (e) {}
		listview.refresh();
		d.hide();
		frappe.show_alert({ message: "Filter tanggal dihapus", indicator: "blue" }, 3);
	});
}

function show_month_picker(listview, year, all_data, month_names) {
	let months_data = all_data.filter(
		(d) => frappe.datetime.str_to_obj(d.transaction_date).getFullYear() === year
	);
	let months = [
		...new Set(months_data.map((d) => frappe.datetime.str_to_obj(d.transaction_date).getMonth())),
	].sort((a, b) => a - b);
	let month_buttons = months
		.map((month) => {
			let count = months_data.filter(
				(d) => frappe.datetime.str_to_obj(d.transaction_date).getMonth() === month
			).length;
			return `<div class="month-filter-item" data-month="${month + 1}" style="padding:10px 20px;margin:5px;border:1px solid #d1d8dd;border-radius:6px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;transition:background 0.2s;"><span style="font-weight:500;font-size:14px;">📆 ${month_names[month]}</span><span style="background:#e8f4f8;color:#2490ef;padding:2px 10px;border-radius:12px;font-size:12px;">${count} order</span></div>`;
		})
		.join("");

	let d = new frappe.ui.Dialog({
		title: `🗓️ ${year} — Pilih Bulan`,
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "month_picker",
				options: `<div style="padding:10px;"><p style="color:#8d99a6;margin-bottom:10px;font-size:13px;">Pilih bulan atau tampilkan semua order di ${year}</p><button class="btn btn-sm btn-primary" id="filter-whole-year" style="width:100%;margin-bottom:10px;">📅 Semua order ${year}</button>${month_buttons}<div style="margin-top:10px;padding-top:10px;border-top:1px solid #eee;display:flex;gap:8px;"><button class="btn btn-sm btn-default" id="back-to-year" style="flex:1;">← Kembali</button><button class="btn btn-sm btn-default" id="clear-filter-month" style="flex:1;">❌ Hapus Filter</button></div></div></div>`,
			},
		],
	});
	d.show();

	d.$wrapper
		.find(".month-filter-item")
		.on("mouseenter", function () {
			$(this).css("background", "#f0f7ff");
		})
		.on("mouseleave", function () {
			$(this).css("background", "");
		});
	d.$wrapper.find("#filter-whole-year").on("click", function () {
		apply_date_filter(listview, `${year}-01-01`, `${year}-12-31`, `Tahun ${year}`);
		d.hide();
	});
	d.$wrapper.find(".month-filter-item").on("click", function () {
		let month = parseInt($(this).data("month"));
		let from = frappe.datetime.obj_to_str(new Date(year, month - 1, 1));
		let last_day = new Date(year, month, 0).getDate();
		let to = frappe.datetime.obj_to_str(new Date(year, month - 1, last_day));
		apply_date_filter(listview, from, to, `${month_names[month - 1]} ${year}`);
		d.hide();
	});
	d.$wrapper.find("#back-to-year").on("click", function () {
		d.hide();
		let years = [
			...new Set(all_data.map((d) => frappe.datetime.str_to_obj(d.transaction_date).getFullYear())),
		].sort();
		show_year_picker(listview, years, all_data);
	});
	d.$wrapper.find("#clear-filter-month").on("click", function () {
		try {
			listview.filter_area.remove("transaction_date");
		} catch (e) {}
		listview.refresh();
		d.hide();
		frappe.show_alert({ message: "Filter tanggal dihapus", indicator: "blue" }, 3);
	});
}

function apply_date_filter(listview, from_date, to_date, label) {
	try {
		listview.filter_area.remove("transaction_date");
	} catch (e) {}
	listview.filter_area.add([
		["Sales Order", "transaction_date", ">=", from_date],
		["Sales Order", "transaction_date", "<=", to_date],
	]);
	listview.refresh();
	frappe.show_alert({ message: `Filter: ${label}`, indicator: "green" }, 4);
}
