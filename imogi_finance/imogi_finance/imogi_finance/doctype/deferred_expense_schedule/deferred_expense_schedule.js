// Copyright (c) 2026, Imogi and contributors
// For license information, please see license.txt

frappe.ui.form.on('Deferred Expense Schedule', {
	refresh: function(frm) {
		// Add custom buttons
		if (frm.doc.docstatus === 1 && frm.doc.status !== 'Completed' && frm.doc.status !== 'Cancelled') {
			// Button untuk post all periods
			frm.add_custom_button(__('Post All Periods'), function() {
				frappe.confirm(
					__('Post all pending periods to Journal Entry? This will create {0} Journal Entries.',
					   [frm.doc.total_periods - (frm.doc.total_posted / frm.doc.total_amount * frm.doc.total_periods)]),
					function() {
						frappe.call({
							method: 'imogi_finance.imogi_finance.doctype.deferred_expense_schedule.deferred_expense_schedule.post_all_periods',
							args: {
								schedule_name: frm.doc.name
							},
							callback: function(r) {
								if (!r.exc) {
									frappe.msgprint({
										title: __('Success'),
										message: __('Posted {0} Journal Entries successfully', [r.message.total_posted]),
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

		// Color code status
		if (frm.doc.status) {
			frm.set_indicator_formatter('status', function(doc) {
				const colors = {
					'Draft': 'grey',
					'Scheduled': 'blue',
					'Posting': 'orange',
					'Completed': 'green',
					'Cancelled': 'red'
				};
				return colors[doc.status] || 'grey';
			});
		}

		// Format summary fields dengan rupiah
		frm.refresh_field('total_scheduled');
		frm.refresh_field('total_posted');
		frm.refresh_field('outstanding_amount');
	},

	total_amount: function(frm) {
		// Auto-recalculate when total_amount changes
		if (frm.doc.total_amount && frm.doc.total_periods) {
			const monthly = frm.doc.total_amount / frm.doc.total_periods;
			frappe.show_alert({
				message: __('Monthly Amount: {0}', [format_currency(monthly)]),
				indicator: 'blue'
			});
		}
	},

	total_periods: function(frm) {
		// Auto-recalculate when total_periods changes
		if (frm.doc.total_amount && frm.doc.total_periods) {
			const monthly = frm.doc.total_amount / frm.doc.total_periods;
			frappe.show_alert({
				message: __('Monthly Amount: {0}', [format_currency(monthly)]),
				indicator: 'blue'
			});
		}
	}
});

// Grid actions untuk child table
frappe.ui.form.on('Deferred Expense Schedule Detail', {
	monthly_schedule_add: function(frm, cdt, cdn) {
		// Auto-fill period number
		const row = locals[cdt][cdn];
		if (!row.period) {
			row.period = frm.doc.monthly_schedule.length;
			frm.refresh_field('monthly_schedule');
		}
	}
});

// Custom button pada row untuk post individual period
frappe.ui.form.on('Deferred Expense Schedule', {
	monthly_schedule_before_remove: function(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.status === 'Posted') {
			frappe.msgprint(__('Cannot remove posted period. Cancel Journal Entry first.'));
			frappe.validated = false;
		}
	}
});
