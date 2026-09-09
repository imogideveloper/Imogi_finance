// Wajib isi "Alasan Pembatalan" sebelum dokumen transaksi Towing di-cancel.
// Berlaku untuk semua doctype transaksi towing: Sales Order, Sales Invoice,
// Purchase Order, Purchase Invoice, Payment Entry, dan Delivery Order Towing.
//
// Dokumen yang sudah Cancelled (docstatus=2) terkunci total di Frappe, jadi
// satu-satunya cara realistis untuk menangkap alasannya adalah lewat dialog
// SEBELUM proses cancel benar-benar jalan (before_cancel / before_workflow_action).

(function () {
	const REASON_FIELDNAME = "custom_cancellation_reason";

	function prompt_cancellation_reason(frm) {
		return new Promise((resolve, reject) => {
			let confirmed = false;

			const dialog = new frappe.ui.Dialog({
				title: __("Alasan Pembatalan"),
				fields: [
					{
						fieldname: "reason",
						fieldtype: "Small Text",
						label: __("Alasan Cancel"),
						reqd: 1,
					},
				],
				primary_action_label: __("Konfirmasi Cancel"),
				primary_action(values) {
					confirmed = true;
					dialog.hide();
					frm.set_value(REASON_FIELDNAME, values.reason).then(() => resolve());
				},
				secondary_action_label: __("Batal"),
				secondary_action() {
					dialog.hide();
				},
				on_hide() {
					if (!confirmed) {
						reject();
					}
				},
			});

			dialog.show();
		});
	}

	// ─────────────────────────────────────────────────────────────
	// Standard Cancel (docstatus 1 -> 2) lewat tombol/menu Cancel bawaan Frappe
	// ─────────────────────────────────────────────────────────────
	const STANDARD_CANCEL_DOCTYPES = [
		"Sales Order",
		"Sales Invoice",
		"Purchase Order",
		"Purchase Invoice",
		"Payment Entry",
		"Delivery Order Towing",
	];

	STANDARD_CANCEL_DOCTYPES.forEach((doctype) => {
		frappe.ui.form.on(doctype, {
			before_cancel(frm) {
				return prompt_cancellation_reason(frm);
			},
		});
	});

	// ─────────────────────────────────────────────────────────────
	// Delivery Order Towing pakai Workflow — aksi "Cancel" di sana jalan
	// lewat before_workflow_action, bukan before_cancel biasa.
	// ─────────────────────────────────────────────────────────────
	frappe.ui.form.on("Delivery Order Towing", {
		before_workflow_action(frm) {
			if (frm.selected_workflow_action !== "Cancel") {
				return Promise.resolve();
			}

			// Dialog sudah cukup jelas sebagai indikator "sedang menunggu input";
			// unfreeze dulu supaya overlay freeze bawaan workflow tidak menutupi dialog.
			frappe.dom.unfreeze();

			return prompt_cancellation_reason(frm).then(() => {
				frappe.dom.freeze();
			});
		},
	});
})();
