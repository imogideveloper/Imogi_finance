// Purchase Invoice list — Group By Period + Group By Status (terpisah)

function imogi_pi_list_route_str() {
	try {
		const route = frappe.get_route?.() || frappe.router?.current_route;
		return route?.length ? route.join("/") : "";
	} catch (e) {
		return "";
	}
}

const PI_STATUS_ORDER = [
	"Draft",
	"Submitted",
	"Unpaid",
	"Partly Paid",
	"Paid",
	"Overdue",
	"Unpaid and Discounted",
	"Partly Paid and Discounted",
	"Overdue and Discounted",
	"Return",
	"Credit Note Issued",
	"Internal Transfer",
	"Cancelled",
];

const PI_STATUS_COLORS = {
	Draft: "red",
	Submitted: "blue",
	Unpaid: "orange",
	"Partly Paid": "yellow",
	Paid: "green",
	Overdue: "red",
	"Unpaid and Discounted": "orange",
	"Partly Paid and Discounted": "yellow",
	"Overdue and Discounted": "red",
	Return: "gray",
	"Credit Note Issued": "gray",
	"Internal Transfer": "darkgrey",
	Cancelled: "red",
};

const PERIOD_OPTIONS = ["Year", "Quarter", "Month", "Week", "Day"];

/** Status ERPNext yang digabung ke grup "Unpaid" (bukan grup terpisah). */
const STATUS_GROUPED_AS_UNPAID = ["Overdue", "Overdue and Discounted"];

function isRawOverdueStatus(status) {
	return STATUS_GROUPED_AS_UNPAID.includes(status);
}

/** Invoice lewat jatuh tempo (status DB Overdue atau Unpaid + late days > 0). */
function isDocPastDue(doc) {
	if (!doc) return false;
	const st = doc.status || "";
	if (isRawOverdueStatus(st)) return true;
	const late = piDaysPastDue(doc) || 0;
	return late > 0 && (st === "Unpaid" || st === "Unpaid and Discounted");
}

function statusGroupKey(resolvedStatus) {
	if (isRawOverdueStatus(resolvedStatus)) return "Unpaid";
	return resolvedStatus;
}

/** Jika user memilih Unpaid di filter, ikut sertakan Overdue (status di DB tetap Overdue). */
function expandStatusesForListFilter(values) {
	const set = new Set(values);
	if (set.has("Unpaid")) set.add("Overdue");
	if (set.has("Unpaid and Discounted")) set.add("Overdue and Discounted");
	return Array.from(set);
}

function siParseDate(value) {
	return value ? frappe.datetime.str_to_obj(value) : null;
}

/** Hari lewat jatuh tempo: hari ini − due_date (0 jika belum lewat). */
function piDaysPastDue(doc) {
	if (!doc?.due_date) return null;
	const due = siParseDate(doc.due_date);
	const today = siParseDate(frappe.datetime.get_today());
	if (!due || !today) return null;
	const MS_PER_DAY = 86400000;
	const tUTC = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
	const dUTC = Date.UTC(due.getFullYear(), due.getMonth(), due.getDate());
	const diff = Math.round((tUTC - dUTC) / MS_PER_DAY);
	return Math.max(0, diff);
}

const PI_STATUS_ICON_BY_STATUS = {
	Unpaid: "es-solid-alert-circle",
	"Unpaid and Discounted": "es-solid-alert-circle",
	Overdue: "es-solid-alert-circle",
	"Overdue and Discounted": "es-solid-alert-circle",
	"Partly Paid": "es-solid-dot",
	"Partly Paid and Discounted": "es-solid-dot",
	Paid: "es-solid-success",
	Draft: "es-line-edit",
	Submitted: "es-line-inbox",
	Return: "es-line-reply",
	"Credit Note Issued": "es-line-tag",
	"Internal Transfer": "es-line-move",
	Cancelled: "es-solid-close-circle",
};

const PI_GROUP_ICON_BY_LABEL = {
	Unpaid: "es-solid-alert-circle",
	"Partly Paid": "es-solid-dot",
	Paid: "es-solid-success",
};

function piStatusKeyFromDoc(doc) {
	const status = doc.status || "Draft";
	if (status === "Overdue" || status === "Overdue and Discounted") {
		return "Unpaid";
	}
	const late = piDaysPastDue(doc) || 0;
	if (late > 0 && (status === "Unpaid" || status === "Unpaid and Discounted")) {
		return "Unpaid";
	}
	return status;
}

function piStatusIconHtmlForDoc(doc) {
	const icon = PI_STATUS_ICON_BY_STATUS[piStatusKeyFromDoc(doc)] || "es-line-status";
	if (typeof frappe.utils.icon === "function") {
		return frappe.utils.icon(icon, "xs", "", "", "pi-status-icon");
	}
	return `<svg class="icon icon-xs pi-status-icon" aria-hidden="true"><use href="#${icon}"></use></svg>`;
}

function siGroupIconWrapHtml(label) {
	const icon = PI_GROUP_ICON_BY_LABEL[label] || "es-line-status";
	let svg = "";
	if (typeof frappe.utils.icon === "function") {
		svg = frappe.utils.icon(icon, "sm", "", "", "erg-group-title-icon");
	} else {
		svg = `<svg class="icon icon-sm erg-group-title-icon" aria-hidden="true"><use href="#${icon}"></use></svg>`;
	}
	return `<span class="erg-group-icon-wrap" aria-hidden="true">${svg}</span>`;
}

function piCountBadgeHtml(count) {
	const label = count === 1 ? __("1 invoice") : __("{0} invoices", [String(count)]);
	let icon = "";
	if (typeof frappe.utils.icon === "function") {
		icon = frappe.utils.icon("es-line-filetype", "xs", "", "", "erg-count-icon");
	}
	return icon + `<span class="erg-count-label">${frappe.utils.escape_html(label)}</span>`;
}

frappe.listview_settings["Purchase Invoice"] = {
	add_fields: [
		"supplier",
		"title",
		"base_grand_total",
		"outstanding_amount",
		"due_date",
		"company",
		"currency",
		"is_return",
		"posting_date",
		"grand_total",
		"status",
		"docstatus",
	],

	get_indicator: imogi_pi_list_get_indicator,
	get_indicator_html: imogi_pi_list_get_indicator_html,

	formatters: {
		status(_value, _df, doc) {
			return imogi_pi_list_get_indicator_html(doc, false);
		},
		name(value, _df, doc) {
			const name = value || doc.name || "";
			const supplier = doc.supplier || doc.title || "";
			return (
				`<span class="pi-subject-cell">` +
					`<span class="pi-subject-id">${frappe.utils.escape_html(name)}</span>` +
					(supplier
						? `<span class="pi-subject-supplier text-muted"> · ${frappe.utils.escape_html(supplier)}</span>`
						: "") +
				`</span>`
			);
		},
		posting_date: imogi_pi_format_posting_date,
		grand_total: imogi_pi_format_grand_total,
		due_date: imogi_pi_format_late_days,
	},

	onload: imogi_pi_list_onload,
};

function imogi_pi_list_onload(listview) {
	if (frappe.model.can_create("Delivery Note")) {
		listview.page.add_action_item(__("Delivery Note"), () => {
			erpnext.bulk_transaction_processing.create(listview, "Purchase Invoice", "Delivery Note");
		});
	}

	if (frappe.model.can_create("Payment Entry")) {
		listview.page.add_action_item(__("Payment"), () => {
			erpnext.bulk_transaction_processing.create(listview, "Purchase Invoice", "Payment Entry");
		});
	}

	const settings = frappe.listview_settings["Purchase Invoice"];
	if (settings && settings.get_indicator_html) {
		listview.get_indicator_html = settings.get_indicator_html.bind(listview);
	}
}

function patch_purchase_invoice_listview_settings() {
	// Client Script menimpa listview_settings — paksa handler imogi_finance.
	const settings = frappe.listview_settings["Purchase Invoice"];
	if (!settings) return;

	settings.add_fields = settings.add_fields || [];
	[
		"supplier",
		"title",
		"base_grand_total",
		"outstanding_amount",
		"due_date",
		"company",
		"currency",
		"is_return",
		"posting_date",
		"grand_total",
		"status",
		"docstatus",
	].forEach((fieldname) => {
		if (!settings.add_fields.includes(fieldname)) {
			settings.add_fields.push(fieldname);
		}
	});

	settings.get_indicator = imogi_pi_list_get_indicator;
	settings.get_indicator_html = imogi_pi_list_get_indicator_html;

	settings.formatters = settings.formatters || {};
	delete settings.formatters.title;
	if (!settings.formatters.name) {
		settings.formatters.name = function (value, df, doc) {
			const name = value || doc.name || "";
			const supplier = doc.supplier || doc.title || "";
			return (
				`<span class="pi-subject-cell">` +
					`<span class="pi-subject-id">${frappe.utils.escape_html(name)}</span>` +
					(supplier
						? `<span class="pi-subject-supplier text-muted"> · ${frappe.utils.escape_html(supplier)}</span>`
						: "") +
				`</span>`
			);
		};
	}
	settings.formatters.status = function (_value, _df, doc) {
		return imogi_pi_list_get_indicator_html(doc, false);
	};
	settings.formatters.posting_date = imogi_pi_format_posting_date;
	settings.formatters.grand_total = imogi_pi_format_grand_total;
	settings.formatters.due_date = imogi_pi_format_late_days;

	if (!settings.__pi_imogi_onload_wrapped) {
		const orig_onload = settings.onload;
		settings.onload = function (listview) {
			window.__imogi_pi_toolbar_active = true;
			imogi_pi_list_onload(listview);
			if (settings.get_indicator_html) {
				listview.get_indicator_html = settings.get_indicator_html.bind(listview);
			}
			imogi_pi_list_ensure_toolbar(listview);
			if (orig_onload && orig_onload !== settings.onload) {
				orig_onload.call(this, listview);
			}
			imogi_pi_list_ensure_toolbar(listview);
		};
		settings.__pi_imogi_onload_wrapped = true;
	}
}

function imogi_pi_list_get_indicator(doc) {
	const status = doc.status || "Draft";
	if (status === "Overdue" || status === "Overdue and Discounted") {
		return [__("Unpaid"), "orange", "status,=,Unpaid"];
	}
	const late = piDaysPastDue(doc) || 0;
	if (late > 0 && (status === "Unpaid" || status === "Unpaid and Discounted")) {
		return [__("Unpaid"), "orange", `status,=,${status}`];
	}
	const label = __(status);
	return [label, PI_STATUS_COLORS[status] || "grey", `status,=,${status}`];
}

function imogi_pi_list_get_indicator_html(doc, show_workflow_state) {
	const indicator = frappe.get_indicator(doc, "Purchase Invoice", show_workflow_state);
	if (!indicator) return "";

	const label = indicator[0];
	const color = indicator[1];
	const filter = indicator[2];
	const docstatus_description = [
		__("Document is in draft state"),
		__("Document has been submitted"),
		__("Document has been cancelled"),
	];
	const title = frappe.utils.escape_html(docstatus_description[doc.docstatus || 0]);
	const statusKey = piStatusKeyFromDoc(doc);

	return (
		`<span class="indicator-pill pi-status-pill ${color} filterable no-indicator-dot ellipsis"` +
			` data-filter="${frappe.utils.escape_html(filter)}" data-pi-status="${frappe.utils.escape_html(statusKey)}" title="${title}">` +
			piStatusIconHtmlForDoc(doc) +
			`<span class="pi-status-label">${frappe.utils.escape_html(label)}</span>` +
		`</span>`
	);
}

function imogi_pi_format_posting_date(value) {
	if (!value) {
		return `<span class="pi-cell-muted">—</span>`;
	}
	return `<span class="pi-posting-date">${frappe.datetime.str_to_user(value)}</span>`;
}

function imogi_pi_format_grand_total(value, df, doc) {
	if (value == null || value === "") {
		return `<span class="pi-cell-muted">—</span>`;
	}
	const formatted = frappe.format(value, df, doc);
	return `<span class="pi-grand-total">${formatted}</span>`;
}

function imogi_pi_format_late_days(_value, _df, doc) {
	const late = piDaysPastDue(doc) || 0;
	if (late > 0) {
		const clock =
			typeof frappe.utils.icon === "function"
				? frappe.utils.icon("es-solid-alert-triangle", "xs", "", "", "pi-late-icon pi-late-icon-blink")
				: "";
		return (
			`<span class="pi-late-days-cell pi-late-overdue text-danger" title="${frappe.utils.escape_html(
				__("Days past due date")
			)}">` +
				`<span class="pi-late-icon-wrap pi-late-icon-blink-wrap" aria-hidden="true">${clock}</span>` +
				`<span class="pi-late-text">${late} ${__("Days Ago")}</span>` +
			`</span>`
		);
	}
	if (doc.due_date) {
		return `<span class="pi-late-days-cell pi-due-date">${frappe.datetime.str_to_user(doc.due_date)}</span>`;
	}
	return `<span class="pi-late-days-cell pi-cell-muted">—</span>`;
}

function imogi_pi_list_ensure_toolbar(listview) {
	if (!listview || listview.doctype !== "Purchase Invoice") return;
	window.__imogi_pi_toolbar_active = true;
	if (typeof window.init_purchase_invoice_list_toolbar === "function") {
		window.init_purchase_invoice_list_toolbar(listview);
	}
}

// Client Script (__custom_list_js) runs AFTER this file and replaces listview_settings.
(function hook_pi_list_after_client_script() {
	if (frappe.model.__imogi_pi_list_meta_hooked) return;
	frappe.model.__imogi_pi_list_meta_hooked = true;
	const orig_init_doctype = frappe.model.init_doctype;
	frappe.model.init_doctype = function (doctype) {
		orig_init_doctype.apply(this, arguments);
		if (doctype !== "Purchase Invoice") return;
		patch_purchase_invoice_listview_settings();
		setTimeout(() => {
			if (cur_list?.doctype === "Purchase Invoice") {
				imogi_pi_list_ensure_toolbar(cur_list);
			}
		}, 50);
	};
})();

patch_purchase_invoice_listview_settings();
if (typeof frappe.ready === "function") {
	frappe.ready(patch_purchase_invoice_listview_settings);
} else {
	$(patch_purchase_invoice_listview_settings);
}
frappe.after_ajax(() => {
	if (imogi_pi_list_route_str() !== "List/Purchase Invoice") return;
	patch_purchase_invoice_listview_settings();
	imogi_pi_list_ensure_toolbar(cur_list);
});
$(document).on("page-change", function () {
	if (imogi_pi_list_route_str() === "List/Purchase Invoice") {
		setTimeout(() => {
			patch_purchase_invoice_listview_settings();
			imogi_pi_list_ensure_toolbar(cur_list);
		}, 0);
	}
});
