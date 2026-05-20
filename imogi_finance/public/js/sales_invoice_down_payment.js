// Re-apply SO down-payment line amounts after ERPNext client-side recalculation.
frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (!frm.is_new() || frm._imogi_dp_applied) {
			return;
		}
		const remarks = frm.doc.remarks || "";
		if (!remarks.includes("<!--imogi_dp:")) {
			return;
		}
		imogi_sync_down_payment_invoice(frm);
	},
});

function imogi_sync_down_payment_invoice(frm) {
	if (frm._imogi_dp_syncing) {
		return;
	}
	frm._imogi_dp_syncing = true;

	frappe.call({
		method: "imogi_finance.sales_invoice_from_so.sync_imogi_down_payment_invoice",
		args: { doc: frm.doc },
		freeze: false,
		callback(r) {
			frm._imogi_dp_syncing = false;
			if (!r.message || r.exc) {
				return;
			}
			frappe.model.sync(r.message);
			frm._imogi_dp_applied = true;
			frm.refresh_field("items");
			frm.refresh_field("taxes");
			frm.refresh_field("grand_total");
			frm.refresh_field("net_total");
			frm.refresh_field("total");
		},
		error() {
			frm._imogi_dp_syncing = false;
		},
	});
}
