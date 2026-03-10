// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('Tax Payment Batch', {
	refresh(frm) {
		// Add custom buttons for payment creation
		if (frm.doc.docstatus === 1 && !frm.doc.payment_entry && !frm.doc.journal_entry) {
			// Only show if not yet paid
			frm.add_custom_button(__('Create Payment Entry'), () => {
				createPaymentEntry(frm);
			});

			frm.add_custom_button(__('Create Journal Entry'), () => {
				createJournalEntry(frm);
			});
		}

		// Add refresh amount button
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__('Refresh Amount'), () => {
				refreshAmount(frm);
			});
		}
	},

	async source_closing(frm) {
		// Auto-populate amount when source_closing is selected
		if (!frm.doc.source_closing) {
			// Clear amount if source_closing is cleared
			frm.set_value('amount', 0);
			return;
		}

		try {
			// Fetch Tax Period Closing document
			const closing = await frappe.db.get_doc('Tax Period Closing', frm.doc.source_closing);

			if (!closing) {
				frappe.msgprint({
					title: __('Error'),
					message: __('Could not fetch Tax Period Closing data'),
					indicator: 'red'
				});
				return;
			}

			// Determine amount based on tax_type
			let amount = 0;
			const taxType = frm.doc.tax_type || 'PPN';

			if (taxType === 'PPN') {
				// Use VAT Net (Output - Input) for PPN
				amount = closing.vat_net || 0;
			} else if (taxType === 'PPh') {
				amount = closing.pph_total || 0;
			} else if (taxType === 'PB1') {
				amount = closing.pb1_total || 0;
			}

			// Set amount (only if positive)
			if (amount < 0) {
				amount = 0;
			}

			frm.set_value('amount', amount);

			// Show notification
			if (amount > 0) {
				frappe.show_alert({
					message: __('Amount updated from Tax Period Closing: {0}', [format_currency(amount, frm.doc.currency || 'IDR')]),
					indicator: 'green'
				}, 5);
			} else {
				frappe.msgprint({
					title: __('No Tax Payable'),
					message: __('The calculated tax amount is zero or negative. Please verify the Tax Period Closing data.'),
					indicator: 'orange'
				});
			}

		} catch (error) {
			console.error('Error fetching Tax Period Closing:', error);
			frappe.msgprint({
				title: __('Error'),
				message: error.message || __('Failed to fetch Tax Period Closing data'),
				indicator: 'red'
			});
		}
	},

	async tax_type(frm) {
		// Re-calculate amount when tax_type changes (if source_closing is set)
		if (frm.doc.source_closing) {
			// Trigger source_closing handler again to recalculate
			frm.trigger('source_closing');
		}
	}
});

// Helper function to refresh amount
async function refreshAmount(frm) {
	if (!frm.doc.name) {
		frappe.msgprint(__('Please save the document first'));
		return;
	}

	frappe.call({
		method: 'imogi_finance.imogi_finance.doctype.tax_payment_batch.tax_payment_batch.refresh_tax_payment_amount',
		args: {
			batch_name: frm.doc.name
		},
		freeze: true,
		freeze_message: __('Refreshing amount...'),
		callback: (r) => {
			if (r.message !== undefined) {
				frm.set_value('amount', r.message);
				frappe.show_alert({
					message: __('Amount refreshed: {0}', [format_currency(r.message, frm.doc.currency || 'IDR')]),
					indicator: 'green'
				}, 5);
			}
		}
	});
}

// Helper function to create Payment Entry
function createPaymentEntry(frm) {
	frappe.confirm(
		__('Create Payment Entry for tax payment of {0}?', [format_currency(frm.doc.amount, frm.doc.currency || 'IDR')]),
		() => {
			frappe.call({
				method: 'imogi_finance.imogi_finance.doctype.tax_payment_batch.tax_payment_batch.create_tax_payment_entry',
				args: {
					batch_name: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Creating Payment Entry...'),
				callback: (r) => {
					if (r.message) {
						frappe.show_alert({
							message: __('Payment Entry {0} created successfully', [r.message]),
							indicator: 'green'
						}, 5);
						frm.reload_doc();
					}
				}
			});
		}
	);
}

// Helper function to create Journal Entry
function createJournalEntry(frm) {
	frappe.confirm(
		__('Create Journal Entry for tax payment of {0}?', [format_currency(frm.doc.amount, frm.doc.currency || 'IDR')]),
		() => {
			frappe.call({
				method: 'imogi_finance.imogi_finance.doctype.tax_payment_batch.tax_payment_batch.create_tax_payment_journal_entry',
				args: {
					batch_name: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Creating Journal Entry...'),
				callback: (r) => {
					if (r.message) {
						frappe.show_alert({
							message: __('Journal Entry {0} created successfully', [r.message]),
							indicator: 'green'
						}, 5);
						frm.reload_doc();
					}
				}
			});
		}
	);
}
