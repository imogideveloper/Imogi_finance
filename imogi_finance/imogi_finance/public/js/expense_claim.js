/**
 * Expense Claim customizations for advance payment linking
 * Copyright (c) 2026, Imogi and contributors
 * For license information, please see license.txt
 */

frappe.ui.form.on('Expense Claim', {
	refresh: function(frm) {
		// Add button to link employee advances
		if (frm.doc.docstatus === 1 && frm.doc.employee) {
			frm.add_custom_button(__('Link Employee Advances'), function() {
				link_employee_advances(frm);
			}, __('Tools'));
			
			// Show advance allocation section if there are advances
			show_advance_allocation(frm);
		}
		
		// Add custom button to view advance payment dashboard
		if (frm.doc.employee) {
			frm.add_custom_button(__('View Employee Advances'), function() {
				frappe.route_options = {
					"party_type": "Employee",
					"party": frm.doc.employee
				};
				frappe.set_route("query-report", "Advance Payment Dashboard");
			}, __('View'));
		}
	},
	
	employee: function(frm) {
		// Load employee advances when employee is selected
		if (frm.doc.employee && frm.doc.docstatus === 0) {
			load_employee_advances(frm);
		}
	}
});

function link_employee_advances(frm) {
	frappe.call({
		method: 'imogi_finance.expense_claim_integration.expense_claim_advances.link_employee_advances',
		args: {
			doc: frm.doc
		},
		callback: function(r) {
			if (!r.exc) {
				frappe.show_alert({
					message: __('Employee advances linked successfully'),
					indicator: 'green'
				});
				frm.reload_doc();
			}
		}
	});
}

function load_employee_advances(frm) {
	if (!frm.doc.employee) return;
	
	frappe.call({
		method: 'imogi_finance.expense_claim_integration.expense_claim_advances.get_employee_advances',
		args: {
			employee: frm.doc.employee,
			company: frm.doc.company
		},
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				let advances_html = '<div class="alert alert-info">';
				advances_html += '<strong>' + __('Available Employee Advances') + ':</strong><br>';
				
				r.message.forEach(function(advance) {
					advances_html += `<div style="margin-top: 5px;">
						${advance.voucher_type}: ${advance.voucher_no} - 
						${format_currency(advance.outstanding_amount, frm.doc.currency)} 
						(${frappe.datetime.str_to_user(advance.posting_date)})
					</div>`;
				});
				
				advances_html += '</div>';
				
				// Show the advances info
				frm.dashboard.add_comment(advances_html, null, true);
			}
		}
	});
}

function show_advance_allocation(frm) {
	frappe.call({
		method: 'imogi_finance.expense_claim_integration.expense_claim_advances.get_allocated_advances',
		args: {
			expense_claim: frm.doc.name
		},
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				let html = '<div class="form-group">';
				html += '<label class="control-label">Allocated Advances</label>';
				html += '<table class="table table-bordered" style="margin-top: 10px;">';
				html += '<thead><tr>';
				html += '<th>Voucher Type</th>';
				html += '<th>Voucher No</th>';
				html += '<th>Posting Date</th>';
				html += '<th class="text-right">Amount</th>';
				html += '</tr></thead><tbody>';
				
				let total = 0;
				r.message.forEach(function(adv) {
					html += '<tr>';
					html += '<td>' + adv.against_voucher_type + '</td>';
					html += '<td><a href="/app/' + frappe.router.slug(adv.against_voucher_type) + '/' + adv.against_voucher_no + '">' + adv.against_voucher_no + '</a></td>';
					html += '<td>' + frappe.datetime.str_to_user(adv.posting_date) + '</td>';
					html += '<td class="text-right">' + format_currency(Math.abs(adv.amount), frm.doc.currency) + '</td>';
					html += '</tr>';
					total += Math.abs(adv.amount);
				});
				
				html += '<tr class="font-weight-bold">';
				html += '<td colspan="3" class="text-right">Total Allocated</td>';
				html += '<td class="text-right">' + format_currency(total, frm.doc.currency) + '</td>';
				html += '</tr>';
				html += '</tbody></table></div>';
				
				// Add to form
				frm.fields_dict['advances_html'].$wrapper.html(html);
			}
		}
	});
}
