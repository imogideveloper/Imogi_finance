// Copyright (c) 2026, Imogi and contributors
// For license information, please see license.txt

frappe.ui.form.on('Installment Purchase Plan', {
	refresh: function(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.status !== 'Completed' && frm.doc.status !== 'Cancelled') {
			frm.add_custom_button(__('Create Purchase Order Now'), function() {
				frappe.confirm(
					__('Create Draft Purchase Order for all due/pending installment periods now?'),
					function() {
						frappe.call({
							method: 'imogi_finance.imogi_finance.doctype.installment_purchase_plan.installment_purchase_plan.create_all_due_purchase_orders',
							args: {
								plan_name: frm.doc.name
							},
							callback: function(r) {
								if (!r.exc) {
									frappe.msgprint({
										title: __('Success'),
										message: __('Created {0} Purchase Order(s) (Draft)', [r.message.total_created]),
										indicator: 'green'
									});
									frm.reload_doc();
								}
							}
						});
					}
				);
			}, __('Actions'));
		}

		if (frm.doc.status) {
			frm.set_indicator_formatter('status', function(doc) {
				const colors = {
					'Draft': 'grey',
					'Active': 'blue',
					'Completed': 'green',
					'Cancelled': 'red'
				};
				return colors[doc.status] || 'grey';
			});
		}
	},

	asset_price: calculate_preview,
	down_payment: calculate_preview
});

function calculate_preview(frm) {
	if (frm.doc.asset_price) {
		const principal = flt(frm.doc.asset_price) - flt(frm.doc.down_payment);
		frappe.show_alert({
			message: __('Principal (Pokok): {0}. Simpan dokumen untuk hitung jadwal angsuran anuitas lengkap.', [format_currency(principal)]),
			indicator: 'blue'
		});
	}
}

frappe.ui.form.on('Installment Purchase Plan Detail', {
	installment_schedule_before_remove: function(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.status === 'PO Created') {
			frappe.msgprint(__('Cannot remove period that already has a Purchase Order. Cancel the Purchase Order first.'));
			frappe.validated = false;
		}
	}
});
