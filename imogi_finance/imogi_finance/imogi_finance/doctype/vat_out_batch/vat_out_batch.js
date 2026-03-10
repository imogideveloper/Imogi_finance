// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('VAT OUT Batch', {
	refresh: function(frm) {
		// Add custom buttons based on status
		if (frm.doc.docstatus === 0) {
			// Draft state - Get Available Invoices button
			if (!frm.doc.exported_on) {
				frm.add_custom_button(__('Get Available Invoices'), function() {
					get_available_invoices(frm);
				}).css({'background-color': '#4CAF50', 'color': 'white', 'font-weight': 'bold'});
				
				frm.add_custom_button(__('Rebuild All Groups'), function() {
					rebuild_all_groups(frm);
				}).css({'background-color': '#FF9800', 'color': 'white'});
				
				frm.add_custom_button(__('Manage Groups'), function() {
					show_manage_groups_dialog(frm);
				}).css({'background-color': '#2196F3', 'color': 'white', 'font-weight': 'bold'});
				
				frm.add_custom_button(__('Generate CoreTax Upload File'), function() {
					generate_coretax_file(frm);
				}, __('Actions'));
			}
			
			// Upload status buttons
			if (frm.doc.exported_on) {
				frm.add_custom_button(__('Mark Upload In Progress'), function() {
					mark_upload_status(frm, 'In Progress');
				}, __('Upload Status'));
				
				frm.add_custom_button(__('Mark Upload Completed'), function() {
					mark_upload_status(frm, 'Completed');
				}, __('Upload Status'));
				
				frm.add_custom_button(__('Mark Upload Failed'), function() {
					mark_upload_status(frm, 'Failed');
				}, __('Upload Status'));
			}
			
			// Import buttons
			if (frm.doc.exported_on && !frm.is_new()) {
				frm.add_custom_button(__('Import FP Numbers'), function() {
					show_import_dialog(frm);
				}, __('Import'));
				
				frm.add_custom_button(__('Export CSV Template'), function() {
					export_csv_template(frm);
				}, __('Export'));
			}
		}
		
		// Reconciliation button (always available after export)
		if (frm.doc.exported_on) {
			frm.add_custom_button(__('Generate Reconciliation File'), function() {
				generate_reconciliation_file(frm);
			}, __('Actions'));
		}
		
		// View Invoices button
		if (!frm.is_new()) {
			frm.add_custom_button(__('View Batch Invoices'), function() {
				show_batch_invoices(frm);
			});
		}
		
		// Clone button for cancelled batches
		if (frm.doc.docstatus === 2) {
			frm.add_custom_button(__('Clone Batch'), function() {
				clone_batch(frm);
			});
		}
		
		// Add instructions HTML
		add_instructions_html(frm);
	}
});

function get_available_invoices(frm) {
	if (!frm.doc.company || !frm.doc.date_from || !frm.doc.date_to) {
		frappe.msgprint(__('Please set Company, Date From, and Date To first.'));
		return;
	}
	
	frappe.call({
		method: 'get_available_invoices',
		doc: frm.doc,
		freeze: true,
		freeze_message: __('Auto-grouping invoices...'),
		callback: function(r) {
			if (r.message) {
				frm.reload_doc();
				
				// Show summary dialog
				let groups = r.message.groups || [];
				let html = '<div style="margin-bottom: 15px;">';
				html += `<p><strong>Total Invoices:</strong> ${r.message.total_invoices}</p>`;
				html += `<p><strong>Total Groups:</strong> ${r.message.total_groups}</p>`;
				html += '</div>';
				
				if (groups.length > 0) {
					html += '<table class="table table-bordered table-sm">';
					html += '<thead><tr>';
					html += '<th>Group</th><th>Customer</th><th>NPWP</th><th>Invoices</th><th>DPP</th><th>PPN</th>';
					html += '</tr></thead><tbody>';
					
					groups.forEach(function(g) {
						html += '<tr>';
						html += `<td>${g.group_id}</td>`;
						html += `<td>${g.customer_name || g.customer}</td>`;
						html += `<td>${g.customer_npwp || '-'}</td>`;
						html += `<td>${g.invoice_count}</td>`;
						html += `<td>${format_currency(g.total_dpp)}</td>`;
						html += `<td>${format_currency(g.total_ppn)}</td>`;
						html += '</tr>';
					});
					
					html += '</tbody></table>';
				}
				
				frappe.msgprint({
					title: __('Invoices Grouped Successfully'),
					message: html,
					indicator: 'green'
				});
			}
		}
	});
}

function show_batch_invoices(frm) {
	frappe.route_options = {
		"out_fp_batch": frm.doc.name
	};
	frappe.set_route("List", "Sales Invoice");
}

function generate_coretax_file(frm) {
	frappe.confirm(
		__('Generate Excel file for CoreTax DJP upload? This will lock the grouping.'),
		function() {
			frappe.call({
				method: 'imogi_finance.vat_out_batch_api.generate_coretax_upload_file',
				args: {
					batch_name: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Generating export file...'),
				callback: function(r) {
					if (r.message && r.message.status === 'success') {
						frappe.show_alert({
							message: __('Export file generated successfully'),
							indicator: 'green'
						}, 5);
						frm.reload_doc();
					}
				}
			});
		}
	);
}

function mark_upload_status(frm, status) {
	frm.set_value('coretax_upload_status', status);
	
	if (status === 'Completed') {
		frm.set_value('uploaded_on', frappe.datetime.now_datetime());
	}
	
	frm.save();
}

function show_import_dialog(frm) {
	let d = new frappe.ui.Dialog({
		title: __('Import FP Numbers from CoreTax'),
		fields: [
			{
				fieldname: 'fp_file',
				fieldtype: 'Attach',
				label: __('FP Numbers Excel File'),
				reqd: 1,
				description: __('Upload the Excel file downloaded from CoreTax DJP after generating FP numbers')
			},
			{
				fieldname: 'instructions',
				fieldtype: 'HTML',
				options: `
					<div class="alert alert-info" style="margin-top: 10px;">
						<strong>Instructions:</strong><br>
						1. Upload Excel file from CoreTax DJP<br>
						2. Must contain columns: Group ID, FP No Seri, FP No Faktur, FP Date<br>
						3. FP numbers will be matched by Group ID
					</div>
				`
			}
		],
		primary_action_label: __('Import'),
		primary_action: function(values) {
			frappe.call({
				method: 'imogi_finance.vat_out_batch_api.import_fp_numbers_from_file',
				args: {
					batch_name: frm.doc.name,
					file_url: values.fp_file
				},
				freeze: true,
				freeze_message: __('Importing FP numbers...'),
				callback: function(r) {
					if (r.message && r.message.status === 'success') {
						frappe.show_alert({
							message: __('FP numbers imported: {0}', [r.message.imported_count]),
							indicator: 'green'
						}, 5);
						d.hide();
						frm.reload_doc();
					}
				}
			});
		}
	});
	
	d.show();
}

function generate_reconciliation_file(frm) {
	frappe.call({
		method: 'imogi_finance.vat_out_batch_api.generate_reconciliation_file',
		args: {
			batch_name: frm.doc.name
		},
		freeze: true,
		freeze_message: __('Generating reconciliation file...'),
		callback: function(r) {
			if (r.message && r.message.status === 'success') {
				frappe.show_alert({
					message: __('Reconciliation file generated'),
					indicator: 'green'
				}, 5);
				frm.reload_doc();
			}
		}
	});
}

function clone_batch(frm) {
	frappe.model.with_doctype('VAT OUT Batch', function() {
		let new_doc = frappe.model.copy_doc(frm.doc);
		new_doc.docstatus = 0;
		new_doc.status = 'Draft';
		new_doc.exported_on = null;
		new_doc.coretax_export_file = null;
		new_doc.reconciliation_file = null;
		new_doc.coretax_upload_status = 'Not Started';
		new_doc.uploaded_on = null;
		new_doc.submit_on = null;
		
		frappe.set_route('Form', 'VAT OUT Batch', new_doc.name);
	});
}

function add_instructions_html(frm) {
	if (frm.doc.docstatus === 0 && !frm.doc.exported_on) {
		frm.dashboard.add_comment(`
			<div class="alert alert-info">
				<strong>Workflow:</strong><br>
				1. Set date range and save<br>
				2. Click <strong>"Get Available Invoices"</strong> to auto-group<br>
				3. Generate CoreTax upload file<br>
				4. Upload to CoreTax DJP manually<br>
				5. Import FP numbers back<br>
				6. Submit batch
			</div>
		`, 'blue', true);
	}
	
	if (frm.doc.exported_on && frm.doc.docstatus === 0) {
		frm.dashboard.add_comment(`
			<div class="alert alert-warning">
				<strong>Next Steps:</strong><br>
				1. Upload Excel file to <a href="https://coretax.pajak.go.id" target="_blank">CoreTax DJP</a><br>
				2. Generate FP numbers in CoreTax<br>
				3. Download result Excel from CoreTax<br>
				4. Click <strong>"Import FP Numbers"</strong> to import back<br>
				5. Verify all invoices have FP numbers<br>
				6. Submit batch to finalize
			</div>
		`, 'orange', true);
	}
}

function format_currency(value) {
	return frappe.format(value, {fieldtype: 'Currency'});
}

function rebuild_all_groups(frm) {
	frappe.confirm(
		__('This will reset all group assignments and rebuild from scratch. Manual grouping edits will be lost. Continue?'),
		function() {
			// Yes
			frappe.call({
				method: 'get_available_invoices',
				doc: frm.doc,
				args: {
					force_rebuild: true
				},
				freeze: true,
				freeze_message: __('Rebuilding all groups...'),
				callback: function(r) {
					if (r.message) {
						frm.reload_doc();
						frappe.show_alert({
							message: __('Groups rebuilt successfully'),
							indicator: 'green'
						}, 5);
					}
				}
			});
		}
	);
}

function show_manage_groups_dialog(frm) {
	if (!frm.doc.name || frm.is_new()) {
		frappe.msgprint(__('Please save the batch first.'));
		return;
	}
	
	let d = new frappe.ui.Dialog({
		title: __('Manage Invoice Groups'),
		size: 'extra-large',
		fields: [
			{
				fieldname: 'html_instructions',
				fieldtype: 'HTML',
				options: `
					<div class="alert alert-info" style="margin-bottom: 15px;">
						<strong>Instructions:</strong><br>
						• Select invoices from the left to add to groups<br>
						• View current groups on the right<br>
						• Add to existing group or create new group<br>
						• Move or remove invoices as needed
					</div>
				`
			},
			{
				fieldname: 'section_break_1',
				fieldtype: 'Section Break',
				label: __('Available Invoices')
			},
			{
				fieldname: 'search_invoice',
				fieldtype: 'Data',
				label: __('Search Invoice'),
				placeholder: __('Enter invoice number or customer name')
			},
			{
				fieldname: 'html_available_invoices',
				fieldtype: 'HTML'
			},
			{
				fieldname: 'column_break_1',
				fieldtype: 'Column Break'
			},
			{
				fieldname: 'current_groups_section',
				fieldtype: 'Section Break',
				label: __('Current Groups')
			},
			{
				fieldname: 'html_current_groups',
				fieldtype: 'HTML'
			}
		],
		primary_action_label: __('Close'),
		primary_action: function() {
			d.hide();
			frm.reload_doc();
		}
	});
	
	// Load available invoices
	function load_available_invoices(search_text = '') {
		frappe.call({
			method: 'frappe.client.get_list',
			args: {
				doctype: 'Sales Invoice',
				filters: [
					['docstatus', '=', 1],
					['company', '=', frm.doc.company],
					['posting_date', 'between', [frm.doc.date_from, frm.doc.date_to]],
					['out_fp_status', '=', 'Verified'],
					['out_fp_batch', 'in', ['', frm.doc.name]]
				],
				fields: ['name', 'customer', 'customer_name', 'posting_date', 'grand_total', 'out_fp_batch', 'out_fp_group_id', 'out_fp_customer_npwp'],
				order_by: 'posting_date desc',
				limit_page_length: 100
			},
			callback: function(r) {
				if (r.message) {
					let invoices = r.message;
					if (search_text) {
						search_text = search_text.toLowerCase();
						invoices = invoices.filter(inv => 
							inv.name.toLowerCase().includes(search_text) || 
							(inv.customer_name || '').toLowerCase().includes(search_text)
						);
					}
					
					render_available_invoices(invoices);
				}
			}
		});
	}
	
	function render_available_invoices(invoices) {
		let html = '<div style="max-height: 400px; overflow-y: auto;">';
		
		if (invoices.length === 0) {
			html += '<p class="text-muted">No available invoices found</p>';
		} else {
			html += '<table class="table table-bordered table-sm">';
			html += '<thead><tr>';
			html += '<th>Invoice</th><th>Customer</th><th>Date</th><th>Amount</th><th>Status</th><th>Action</th>';
			html += '</tr></thead><tbody>';
			
			invoices.forEach(function(inv) {
				let status_badge = '';
				if (inv.out_fp_batch === frm.doc.name && inv.out_fp_group_id) {
					status_badge = `<span class="badge badge-success">Group ${inv.out_fp_group_id}</span>`;
				} else {
					status_badge = '<span class="badge badge-secondary">Not Grouped</span>';
				}
				
				html += '<tr>';
				html += `<td><a href="/app/sales-invoice/${inv.name}" target="_blank">${inv.name}</a></td>`;
				html += `<td>${inv.customer_name || inv.customer}</td>`;
				html += `<td>${frappe.datetime.str_to_user(inv.posting_date)}</td>`;
				html += `<td>${format_currency(inv.grand_total)}</td>`;
				html += `<td>${status_badge}</td>`;
				html += `<td>`;
				
				if (inv.out_fp_batch === frm.doc.name && inv.out_fp_group_id) {
					html += `<button class="btn btn-xs btn-warning" onclick="move_invoice_dialog('${inv.name}', ${inv.out_fp_group_id})">Move</button> `;
					html += `<button class="btn btn-xs btn-danger" onclick="remove_invoice_from_batch('${inv.name}')">Remove</button>`;
				} else {
					html += `<button class="btn btn-xs btn-primary" onclick="add_invoice_dialog('${inv.name}')">Add to Group</button> `;
					html += `<button class="btn btn-xs btn-success" onclick="create_new_group_with_invoice('${inv.name}')">New Group</button>`;
				}
				
				html += '</td></tr>';
			});
			
			html += '</tbody></table>';
		}
		
		html += '</div>';
		d.fields_dict.html_available_invoices.$wrapper.html(html);
	}
	
	// Load current groups
	function load_current_groups() {
		frappe.call({
			method: 'get_groups_summary',
			doc: frm.doc,
			callback: function(r) {
				if (r.message) {
					render_current_groups(r.message);
				}
			}
		});
	}
	
	function render_current_groups(groups) {
		let html = '<div style="max-height: 400px; overflow-y: auto;">';
		
		if (groups.length === 0) {
			html += '<p class="text-muted">No groups created yet</p>';
		} else {
			groups = groups.sort((a, b) => a.group_id - b.group_id);
			
			html += '<table class="table table-bordered table-sm">';
			html += '<thead><tr>';
			html += '<th>Group</th><th>Customer</th><th>NPWP</th><th>Invoices</th><th>DPP</th><th>PPN</th>';
			html += '</tr></thead><tbody>';
			
			groups.forEach(function(g) {
				html += '<tr>';
				html += `<td><strong>${g.group_id}</strong></td>`;
				html += `<td>${g.customer_name || g.customer}</td>`;
				html += `<td>${g.customer_npwp || '-'}</td>`;
				html += `<td>${g.invoice_count}</td>`;
				html += `<td>${format_currency(g.total_dpp)}</td>`;
				html += `<td>${format_currency(g.total_ppn)}</td>`;
				html += '</tr>';
				
				// Show invoice list
				if (g.invoices && g.invoices.length > 0) {
					html += '<tr><td colspan="6" style="padding-left: 30px; background-color: #f8f9fa;">';
					html += '<small>';
					g.invoices.forEach((inv_name, idx) => {
						html += `<a href="/app/sales-invoice/${inv_name}" target="_blank">${inv_name}</a>`;
						if (idx < g.invoices.length - 1) html += ', ';
					});
					html += '</small>';
					html += '</td></tr>';
				}
			});
			
			html += '</tbody></table>';
		}
		
		html += '</div>';
		d.fields_dict.html_current_groups.$wrapper.html(html);
	}
	
	// Global functions for dialog actions
	window.add_invoice_dialog = function(invoice_name) {
		frappe.call({
			method: 'get_groups_summary',
			doc: frm.doc,
			callback: function(r) {
				if (r.message && r.message.length > 0) {
					let groups = r.message.sort((a, b) => a.group_id - b.group_id);
					let group_options = groups.map(g => {
						return {
							label: `Group ${g.group_id}: ${g.customer_name || g.customer} (${g.invoice_count} invoices)`,
							value: g.group_id
						};
					});
					
					frappe.prompt([
						{
							fieldname: 'group_id',
							fieldtype: 'Select',
							label: __('Select Group'),
							options: group_options,
							reqd: 1
						}
					], function(values) {
						add_invoice_to_group(invoice_name, values.group_id);
					}, __('Add to Group'));
				} else {
					frappe.msgprint(__('No groups available. Create a new group instead.'));
				}
			}
		});
	};
	
	window.add_invoice_to_group = function(invoice_name, group_id) {
		frappe.call({
			method: 'add_invoice_to_group',
			doc: frm.doc,
			args: {
				invoice_name: invoice_name,
				group_id: parseInt(group_id)
			},
			freeze: true,
			callback: function(r) {
				if (r.message) {
					frappe.show_alert({
						message: __('Invoice added to group'),
						indicator: 'green'
					}, 3);
					load_available_invoices();
					load_current_groups();
				}
			}
		});
	};
	
	window.create_new_group_with_invoice = function(invoice_name) {
		frappe.call({
			method: 'create_new_group_with_invoice',
			doc: frm.doc,
			args: {
				invoice_name: invoice_name
			},
			freeze: true,
			callback: function(r) {
				if (r.message) {
					frappe.show_alert({
						message: __('New group created'),
						indicator: 'green'
					}, 3);
					load_available_invoices();
					load_current_groups();
				}
			}
		});
	};
	
	window.move_invoice_dialog = function(invoice_name, current_group_id) {
		frappe.call({
			method: 'get_groups_summary',
			doc: frm.doc,
			callback: function(r) {
				if (r.message) {
					let groups = r.message.filter(g => g.group_id !== current_group_id).sort((a, b) => a.group_id - b.group_id);
					if (groups.length === 0) {
						frappe.msgprint(__('No other groups available'));
						return;
					}
					
					let group_options = groups.map(g => {
						return {
							label: `Group ${g.group_id}: ${g.customer_name || g.customer} (${g.invoice_count} invoices)`,
							value: g.group_id
						};
					});
					
					frappe.prompt([
						{
							fieldname: 'new_group_id',
							fieldtype: 'Select',
							label: __('Move to Group'),
							options: group_options,
							reqd: 1
						}
					], function(values) {
						move_invoice_to_group(invoice_name, values.new_group_id);
					}, __('Move Invoice'));
				}
			}
		});
	};
	
	window.move_invoice_to_group = function(invoice_name, new_group_id) {
		frappe.call({
			method: 'move_invoice_to_group',
			doc: frm.doc,
			args: {
				invoice_name: invoice_name,
				new_group_id: parseInt(new_group_id)
			},
			freeze: true,
			callback: function(r) {
				if (r.message) {
					frappe.show_alert({
						message: __('Invoice moved'),
						indicator: 'green'
					}, 3);
					load_available_invoices();
					load_current_groups();
				}
			}
		});
	};
	
	window.remove_invoice_from_batch = function(invoice_name) {
		frappe.confirm(
			__('Remove {0} from this batch?', [invoice_name]),
			function() {
				frappe.call({
					method: 'remove_invoice_from_batch',
					doc: frm.doc,
					args: {
						invoice_name: invoice_name
					},
					freeze: true,
					callback: function(r) {
						if (r.message) {
							frappe.show_alert({
								message: __('Invoice removed'),
								indicator: 'orange'
							}, 3);
							load_available_invoices();
							load_current_groups();
						}
					}
				});
			}
		);
	};
	
	// Search functionality
	d.fields_dict.search_invoice.$input.on('input', function() {
		let search_text = d.get_value('search_invoice');
		load_available_invoices(search_text);
	});
	
	// Initial load
	load_available_invoices();
	load_current_groups();
	
	d.show();
}

function export_csv_template(frm) {
	frappe.call({
		method: 'imogi_finance.imogi_finance.doctype.vat_out_batch.vat_out_batch.export_csv_template',
		args: {
			batch_name: frm.doc.name
		},
		freeze: true,
		freeze_message: __('Generating CSV template...'),
		callback: function(r) {
			if (r.message) {
				let result = r.message;
				
				// Show warnings if any invoices missing FP numbers
				if (result.missing_fp_count > 0) {
					frappe.msgprint({
						title: __('Warning'),
						indicator: 'orange',
						message: __('{0} invoice(s) are missing FP numbers. Run "Import FP Numbers" first to prefill all FP numbers in the template.', [result.missing_fp_count])
					});
				}
				
				// Create and download CSV
				let csv_content = result.csv_content;
				let blob = new Blob([csv_content], { type: 'text/csv;charset=utf-8;' });
				let link = document.createElement('a');
				let url = URL.createObjectURL(blob);
				link.setAttribute('href', url);
				link.setAttribute('download', result.filename);
				link.style.visibility = 'hidden';
				document.body.appendChild(link);
				link.click();
				document.body.removeChild(link);
				
				frappe.show_alert({
					message: __('CSV template downloaded: {0}', [result.filename]),
					indicator: 'green'
				}, 5);
			}
		}
	});
}
