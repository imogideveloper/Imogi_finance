// Default Qty = 1 for non-stock (service) items on selling documents.
frappe.provide("imogi_finance.service_item");

imogi_finance.service_item.DEFAULT_QTY = 1;

imogi_finance.service_item.set_default_qty_if_service = function (cdt, cdn) {
	const row = locals[cdt] && locals[cdt][cdn];
	if (!row || !row.item_code) {
		return;
	}

	frappe.db.get_value("Item", row.item_code, "is_stock_item", (r) => {
		if (r.exc || r.message === undefined || r.message === null) {
			return;
		}
		if (cint(r.message.is_stock_item)) {
			return;
		}
		if (flt(row.qty) > 0) {
			return;
		}

		frappe.model.set_value(
			cdt,
			cdn,
			"qty",
			imogi_finance.service_item.DEFAULT_QTY
		);
	});
};

["Sales Order Item", "Sales Invoice Item"].forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		item_code(frm, cdt, cdn) {
			frappe.after_ajax(() => {
				imogi_finance.service_item.set_default_qty_if_service(cdt, cdn);
			});
		},
	});
});
