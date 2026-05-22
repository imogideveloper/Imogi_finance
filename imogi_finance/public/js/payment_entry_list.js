// List filters/buttons; indicator logic is in payment_entry_allocation_status.js (app_include).

const IMOGI_PE_LIST_SETTINGS = {
	add_fields: [
		"paid_amount",
		"received_amount",
		"payment_type",
		"unallocated_amount",
		"payment_status",
		"party",
		"posting_date",
	],
	get_indicator(doc) {
		return typeof imogi_pe_allocation_indicator === "function"
			? imogi_pe_allocation_indicator(doc)
			: null;
	},
	formatters: {
		paid_amount(value, df, doc) {
			if (doc.payment_type === "Pay") {
				return frappe.format(value, { fieldtype: "Currency", options: "currency" });
			}
			return "";
		},
		received_amount(value, df, doc) {
			if (doc.payment_type === "Receive") {
				return frappe.format(value, { fieldtype: "Currency", options: "currency" });
			}
			return "";
		},
		unallocated_amount(value, df, doc) {
			if (doc.docstatus !== 1) return "";
			const unalloc = parseFloat(value || 0);
			if (unalloc > 0) {
				return `<span style="color: orange; font-weight: bold;">
                    ⚠ ${format_currency(unalloc)}
                </span>`;
			}
			return `<span style="color: green;">✓ Allocated</span>`;
		},
	},
	onload(listview) {
		listview.page.add_inner_button(
			__("Unallocated"),
			function () {
				listview.filter_area.add([
					["Payment Entry", "unallocated_amount", ">", "0"],
					["Payment Entry", "docstatus", "=", "1"],
				]);
			},
			__("Filter By")
		);

		listview.page.add_inner_button(
			__("Allocated"),
			function () {
				listview.filter_area.add([
					["Payment Entry", "unallocated_amount", "=", "0"],
					["Payment Entry", "docstatus", "=", "1"],
				]);
			},
			__("Filter By")
		);
	},
	hide_name_column: false,
};

function imogi_merge_pe_listview_settings() {
	const existing = frappe.listview_settings["Payment Entry"] || {};
	const prev_onload = existing.onload;
	const imogi_onload = IMOGI_PE_LIST_SETTINGS.onload;

	frappe.listview_settings["Payment Entry"] = Object.assign({}, existing, IMOGI_PE_LIST_SETTINGS, {
		get_indicator(doc) {
			return typeof imogi_pe_allocation_indicator === "function"
				? imogi_pe_allocation_indicator(doc)
				: null;
		},
		onload(listview) {
			imogi_onload(listview);
			if (prev_onload && prev_onload !== imogi_onload) {
				prev_onload(listview);
			}
		},
	});
}

imogi_merge_pe_listview_settings();

// Client Script "Filter Date Payment Entry" may replace listview_settings; restore after load.
$(document).on("app_ready", imogi_merge_pe_listview_settings);
