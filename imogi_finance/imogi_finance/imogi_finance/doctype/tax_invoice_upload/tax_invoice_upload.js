// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('Tax Invoice Upload', {
	refresh: function(frm) {
		// Add Retry Sync button if status is Error
		if (frm.doc.status === 'Error' && !frm.is_new()) {
			frm.add_custom_button(__('Retry Sync'), function() {
				retry_sync_single(frm);
			}).css({'background-color': '#FF9800', 'color': 'white'});
		}
	}
});

function retry_sync_single(frm) {
	frappe.call({
		method: 'imogi_finance.imogi_finance.doctype.tax_invoice_upload.tax_invoice_upload_api.retry_sync',
		args: {
			names: [frm.doc.name]
		},
		freeze: true,
		freeze_message: __('Retrying sync...'),
		callback: function(r) {
			if (r.message) {
				let result = r.message;
				if (result.synced > 0) {
					frappe.show_alert({
						message: __('Sync successful'),
						indicator: 'green'
					}, 3);
					frm.reload_doc();
				} else if (result.errors && result.errors.length > 0) {
					frappe.msgprint({
						title: __('Sync Failed'),
						indicator: 'red',
						message: result.errors[0].reason
					});
				}
			}
		}
	});
}

// List view customizations
frappe.listview_settings['Tax Invoice Upload'] = {
	onload: function(listview) {
		// Add Bulk Create button
		listview.page.add_inner_button(__('Bulk Create'), function() {
			show_bulk_create_dialog(listview);
		}).addClass('btn-primary');
		
		// Add Retry Sync bulk action
		listview.page.add_action_item(__('Retry Sync'), function() {
			let selected = listview.get_checked_items();
			if (selected.length === 0) {
				frappe.msgprint(__('Please select records to retry sync'));
				return;
			}
			
			let names = selected.map(item => item.name);
			retry_sync_bulk(names, listview);
		});
		
		// Add quick filters
		listview.page.add_field({
			fieldtype: 'Link',
			fieldname: 'vat_out_batch',
			label: __('VAT OUT Batch'),
			options: 'VAT OUT Batch',
			change: function() {
				let batch = this.get_value();
				if (batch) {
					listview.filter_area.add([[listview.doctype, 'vat_out_batch', '=', batch]]);
				} else {
					listview.filter_area.remove('vat_out_batch');
				}
			}
		});
	},
	
	// Add indicator color based on status
	get_indicator: function(doc) {
		if (doc.status === 'Synced') {
			return [__('Synced'), 'green', 'status,=,Synced'];
		} else if (doc.status === 'Error') {
			return [__('Error'), 'red', 'status,=,Error'];
		} else {
			return [__('Draft'), 'gray', 'status,=,Draft'];
		}
	}
};

function retry_sync_bulk(names, listview) {
	frappe.call({
		method: 'imogi_finance.imogi_finance.doctype.tax_invoice_upload.tax_invoice_upload_api.retry_sync',
		args: {
			names: names
		},
		freeze: true,
		freeze_message: __('Retrying sync for {0} records...', [names.length]),
		callback: function(r) {
			if (r.message) {
				let result = r.message;
				
				// Show summary
				frappe.msgprint({
					title: __('Retry Sync Results'),
					indicator: result.failed === 0 ? 'green' : 'orange',
					message: __('Synced: {0}<br>Failed: {1}', [result.synced, result.failed])
				});
				
				// Show errors if any
				if (result.errors && result.errors.length > 0) {
					let error_html = '<table class="table table-bordered table-sm"><thead><tr><th>Name</th><th>Reason</th></tr></thead><tbody>';
					result.errors.forEach(function(err) {
						error_html += `<tr><td>${err.name}</td><td>${err.reason}</td></tr>`;
					});
					error_html += '</tbody></table>';
					
					frappe.msgprint({
						title: __('Sync Errors'),
						indicator: 'red',
						message: error_html
					});
				}
				
				listview.refresh();
			}
		}
	});
}

function show_bulk_create_dialog(listview) {
	let d = new frappe.ui.Dialog({
		title: __('Bulk Create Tax Invoice Uploads'),
		size: 'large',
		fields: [
			{
				fieldname: 'instructions',
				fieldtype: 'HTML',
				options: `
					<div class="alert alert-info" style="margin-bottom: 15px;">
						<strong>Instructions:</strong><br>
						1. Export CSV template from VAT OUT Batch<br>
						2. Download FP PDFs from CoreTax DJP<br>
						3. Rename PDFs to 16-digit FP number format (e.g., 0109876543210001.pdf)<br>
						4. Create ZIP file with all PDFs<br>
						5. Upload ZIP + CSV files below
					</div>
				`
			},
			{
				fieldname: 'batch_name',
				fieldtype: 'Link',
				label: __('VAT OUT Batch'),
				options: 'VAT OUT Batch',
				reqd: 1,
				description: __('Select the batch that generated the CSV template')
			},
			{
				fieldname: 'csv_file',
				fieldtype: 'Attach',
				label: __('CSV File'),
				reqd: 1,
				description: __('Upload CSV file with FP metadata')
			},
			{
				fieldname: 'zip_file',
				fieldtype: 'Attach',
				label: __('ZIP File with PDFs'),
				reqd: 1,
				description: __('Upload ZIP file containing FP PDFs')
			},
			{
				fieldname: 'section_options',
				fieldtype: 'Section Break',
				label: __('Options')
			},
			{
				fieldname: 'require_all_batch_invoices',
				fieldtype: 'Check',
				label: __('Require all batch invoices in CSV'),
				default: 0,
				description: __('Fail if batch has invoices not in CSV')
			},
			{
				fieldname: 'require_all_csv_have_pdf',
				fieldtype: 'Check',
				label: __('Require all CSV rows have PDFs'),
				default: 0,
				description: __('Fail if any CSV row is missing PDF in ZIP')
			},
			{
				fieldname: 'overwrite_existing',
				fieldtype: 'Check',
				label: __('Overwrite existing records'),
				default: 0,
				description: __('Update existing records with new PDFs')
			}
		],
		primary_action_label: __('Create'),
		primary_action: function(values) {
			d.hide();
			start_bulk_creation(values, listview);
		}
	});
	
	d.show();
}

function start_bulk_creation(values, listview) {
	frappe.call({
		method: 'imogi_finance.imogi_finance.doctype.tax_invoice_upload.tax_invoice_upload_api.bulk_create_from_csv',
		args: {
			batch_name: values.batch_name,
			zip_url: values.zip_file,
			csv_url: values.csv_file,
			require_all_batch_invoices: values.require_all_batch_invoices ? 1 : 0,
			require_all_csv_have_pdf: values.require_all_csv_have_pdf ? 1 : 0,
			overwrite_existing: values.overwrite_existing ? 1 : 0
		},
		freeze: true,
		freeze_message: __('Starting bulk creation...'),
		callback: function(r) {
			if (r.message) {
				let result = r.message;
				
				// Check if job was queued for background processing
				if (result.queued) {
					show_progress_dialog(result.job_id, listview);
				} else {
					// Show immediate results
					show_bulk_results(result, listview);
				}
			}
		}
	});
}

function show_progress_dialog(job_id, listview) {
	let progress_dialog = new frappe.ui.Dialog({
		title: __('Processing Bulk Creation'),
		indicator: 'blue',
		fields: [
			{
				fieldname: 'progress_html',
				fieldtype: 'HTML',
				options: `
					<div class="text-center" style="padding: 20px;">
						<div class="progress" style="height: 30px; margin-bottom: 20px;">
							<div class="progress-bar progress-bar-striped progress-bar-animated" 
								role="progressbar" id="bulk-progress-bar" 
								style="width: 0%">0%</div>
						</div>
						<p id="bulk-progress-message">Processing...</p>
					</div>
				`
			}
		]
	});
	
	progress_dialog.show();
	progress_dialog.get_close_btn().hide();
	
	// Poll for job status
	let poll_interval = setInterval(function() {
		frappe.call({
			method: 'imogi_finance.imogi_finance.doctype.tax_invoice_upload.tax_invoice_upload_api.get_bulk_job_status',
			args: {
				job_id: job_id
			},
			callback: function(r) {
				if (r.message) {
					let status = r.message;
					
					// Update progress bar
					let progress_pct = status.progress_pct || 0;
					$('#bulk-progress-bar').css('width', progress_pct + '%').text(progress_pct + '%');
					$('#bulk-progress-message').text(status.message || 'Processing...');
					
					// Check if finished
					if (status.status === 'finished') {
						clearInterval(poll_interval);
						progress_dialog.hide();
						show_bulk_results(status.result, listview);
					} else if (status.status === 'failed' || status.status === 'error') {
						clearInterval(poll_interval);
						progress_dialog.hide();
						frappe.msgprint({
							title: __('Bulk Creation Failed'),
							indicator: 'red',
							message: status.message
						});
					}
				}
			}
		});
	}, 2000);  // Poll every 2 seconds
	
	// Cleanup on dialog close
	progress_dialog.onhide = function() {
		clearInterval(poll_interval);
	};
}

function show_bulk_results(result, listview) {
	// Build results HTML
	let html = '<div style="margin-bottom: 20px;">';
	html += `<h4>Summary</h4>`;
	html += `<p><strong>Created:</strong> ${result.created}</p>`;
	html += `<p><strong>Updated:</strong> ${result.updated}</p>`;
	html += `<p><strong>Skipped:</strong> ${result.skipped}</p>`;
	html += '</div>';
	
	// Show errors if any
	if (result.row_errors && result.row_errors.length > 0) {
		html += '<div style="margin-bottom: 20px;">';
		html += '<h5 style="color: red;">Row Errors</h5>';
		html += '<table class="table table-bordered table-sm">';
		html += '<thead><tr><th>Row</th><th>FP Number</th><th>Reason</th></tr></thead><tbody>';
		
		result.row_errors.slice(0, 20).forEach(function(err) {
			html += `<tr><td>${err.row}</td><td>${err.fp_number}</td><td>${err.reason}</td></tr>`;
		});
		
		if (result.row_errors.length > 20) {
			html += `<tr><td colspan="3"><em>...and ${result.row_errors.length - 20} more errors</em></td></tr>`;
		}
		
		html += '</tbody></table></div>';
	}
	
	// Show unmatched PDFs
	if (result.pdf_unmatched && result.pdf_unmatched.length > 0) {
		html += '<div style="margin-bottom: 20px;">';
		html += '<h5 style="color: orange;">Unmatched PDFs</h5>';
		html += `<p>These PDFs in ZIP were not in CSV: ${result.pdf_unmatched.slice(0, 10).join(', ')}`;
		if (result.pdf_unmatched.length > 10) {
			html += ` ...and ${result.pdf_unmatched.length - 10} more`;
		}
		html += '</p></div>';
	}
	
	// Show missing PDFs
	if (result.csv_missing_pdf && result.csv_missing_pdf.length > 0) {
		html += '<div style="margin-bottom: 20px;">';
		html += '<h5 style="color: orange;">Missing PDFs</h5>';
		html += `<p>These CSV rows had no PDF in ZIP: ${result.csv_missing_pdf.slice(0, 10).join(', ')}`;
		if (result.csv_missing_pdf.length > 10) {
			html += ` ...and ${result.csv_missing_pdf.length - 10} more`;
		}
		html += '</p></div>';
	}
	
	// Show created docs links
	if (result.created_docs && result.created_docs.length > 0) {
		html += '<div>';
		html += '<h5 style="color: green;">Created/Updated Records</h5>';
		html += '<ul>';
		result.created_docs.slice(0, 10).forEach(function(doc) {
			html += `<li><a href="/app/tax-invoice-upload/${doc.name}">${doc.fp_number}</a> → ${doc.sales_invoice}</li>`;
		});
		if (result.created_docs.length > 10) {
			html += `<li><em>...and ${result.created_docs.length - 10} more</em></li>`;
		}
		html += '</ul>';
		
		// Add filter link if batch was specified
		if (result.created_docs[0].vat_out_batch) {
			html += `<p><a href="/app/tax-invoice-upload?vat_out_batch=${encodeURIComponent(result.created_docs[0].vat_out_batch)}">View all records from this batch</a></p>`;
		}
		html += '</div>';
	}
	
	// Show dialog
	let results_dialog = new frappe.ui.Dialog({
		title: __('Bulk Creation Results'),
		size: 'extra-large',
		fields: [
			{
				fieldname: 'results_html',
				fieldtype: 'HTML',
				options: html
			}
		],
		primary_action_label: __('Close'),
		primary_action: function() {
			results_dialog.hide();
			listview.refresh();
		}
	});
	
	results_dialog.show();
}
