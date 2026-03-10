// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('Tax Period Closing', {
	refresh(frm) {
		// Setup custom buttons based on document state
		setup_action_buttons(frm);

		// Show status indicators in dashboard
		show_status_indicators(frm);

		// Setup link field queries/filters
		setup_queries(frm);

		// Show period lock warning if submitted
		show_period_lock_warning(frm);
	},

	onload(frm) {
		// One-time initialization
		setup_permissions(frm);
	},

	company(frm) {
		// Auto-fetch tax profile when company changes
		if (frm.doc.company && !frm.doc.tax_profile) {
			fetch_tax_profile(frm);
		}
	},

	period_month(frm) {
		// Update period dates when month changes
		update_period_dates(frm);
	},

	period_year(frm) {
		// Update period dates when year changes
		update_period_dates(frm);
	},

	status(frm) {
		// Refresh to update button visibility
		frm.refresh();
	}
});

function setup_action_buttons(frm) {
	// Clear existing custom buttons
	frm.clear_custom_buttons();

	if (frm.doc.docstatus === 0) {
		// Draft state buttons

		// Tax Operations group
		frm.add_custom_button(__('Refresh Tax Registers'), () => {
			refresh_tax_registers(frm);
		}, __('Tax Operations'));

		if (frm.doc.coretax_settings_input || frm.doc.coretax_settings_output) {
			frm.add_custom_button(__('Generate CoreTax Exports'), () => {
				generate_coretax_exports_dialog(frm);
			}, __('Tax Operations'));
		}

		// Reports group
		frm.add_custom_button(__('View Period Statistics'), () => {
			show_period_statistics(frm);
		}, __('Reports'));

		// Register details button (NEW in v15+)
		if (frm.doc.register_snapshot) {
			frm.add_custom_button(__('View Register Details'), () => {
				show_register_details(frm);
			}, __('Reports'));
		}
	}

	if (frm.doc.docstatus === 1) {
		// Submitted state buttons

		// Create VAT Netting Entry (only if not already created)
		if (!frm.doc.vat_netting_journal_entry && (frm.doc.input_vat_total || frm.doc.output_vat_total)) {
			frm.add_custom_button(__('Create VAT Netting Entry'), () => {
				create_vat_netting_entry(frm);
			}).addClass('btn-primary');
		}

		// Navigate to netting entry if exists
		if (frm.doc.vat_netting_journal_entry) {
			frm.add_custom_button(__('View Netting Entry'), () => {
				frappe.set_route('Form', 'Journal Entry', frm.doc.vat_netting_journal_entry);
			}, __('Navigate'));
		}

		// View period statistics
		frm.add_custom_button(__('View Period Statistics'), () => {
			show_period_statistics(frm);
		}, __('Reports'));
	}
}

function show_status_indicators(frm) {
	// Clear existing indicators
	frm.dashboard.clear_headline();

	// Show period information
	if (frm.doc.period_month && frm.doc.period_year) {
		const month_names = [
			'January', 'February', 'March', 'April', 'May', 'June',
			'July', 'August', 'September', 'October', 'November', 'December'
		];
		const period_label = `${month_names[frm.doc.period_month - 1]} ${frm.doc.period_year}`;

		if (frm.doc.status === 'Closed' && frm.doc.docstatus === 1) {
			frm.dashboard.add_indicator(
				__('Period Closed: {0}', [period_label]),
				'blue'
			);
		} else if (frm.doc.status === 'Approved') {
			frm.dashboard.add_indicator(
				__('Period: {0} - Approved', [period_label]),
				'green'
			);
		} else if (frm.doc.status === 'Reviewed') {
			frm.dashboard.add_indicator(
				__('Period: {0} - Under Review', [period_label]),
				'orange'
			);
		}
	}

	// Show register statistics if available
	if (frm.doc.input_invoice_count || frm.doc.output_invoice_count) {
		const total_invoices = (frm.doc.input_invoice_count || 0) + (frm.doc.output_invoice_count || 0);
		frm.dashboard.add_indicator(
			__('Verified Invoices: {0}', [total_invoices]),
			'green'
		);
	}

	// Show data source indicator
	if (frm.doc.data_source === 'fallback_empty') {
		frm.dashboard.add_indicator(
			__('Warning: Using fallback data'),
			'red'
		);
	} else if (frm.doc.data_source === 'register_integration') {
		frm.dashboard.add_indicator(
			__('Data: Register Integration v15+'),
			'green'
		);
	}

	// Show VAT netting indicator
	if (frm.doc.vat_netting_journal_entry) {
		frm.dashboard.add_indicator(
			__('VAT Netting: {0}', [frm.doc.vat_netting_journal_entry]),
			'green'
		);
	}

	// Show last refresh time
	if (frm.doc.last_refresh_on) {
		const refresh_time = frappe.datetime.str_to_user(frm.doc.last_refresh_on);
		frm.dashboard.add_indicator(
			__('Last Refreshed: {0}', [refresh_time]),
			'gray'
		);
	}

	// Show generation in progress warning
	if (frm.doc.is_generating) {
		frm.dashboard.add_indicator(
			__('Register Generation In Progress...'),
			'orange'
		);
	}
}

function setup_queries(frm) {
	// Filter tax profile by company
	frm.set_query('tax_profile', function() {
		if (frm.doc.company) {
			return {
				filters: {
					'company': frm.doc.company
				}
			};
		}
	});

	// Filter PPN payable account by company
	frm.set_query('netting_payable_account', function() {
		if (frm.doc.company) {
			return {
				filters: {
					'company': frm.doc.company,
					'account_type': 'Tax',
					'is_group': 0
				}
			};
		}
	});

	// Filter CoreTax settings
	frm.set_query('coretax_settings_input', function() {
		return {
			filters: {
				'direction': 'Input'
			}
		};
	});

	frm.set_query('coretax_settings_output', function() {
		return {
			filters: {
				'direction': 'Output'
			}
		};
	});
}

function setup_permissions(frm) {
	// Check if user has privileged roles using standard Frappe API
	const privileged_roles = ['System Manager', 'Accounts Manager', 'Tax Reviewer'];
	frm.is_privileged_user = privileged_roles.some(role => frappe.user.has_role(role));
}

function show_period_lock_warning(frm) {
	if (frm.doc.docstatus === 1 && frm.doc.status === 'Closed') {
		frm.dashboard.set_headline_alert(
			__('This period is locked. Tax invoice fields cannot be edited in Purchase/Sales Invoices for this period.'),
			'blue'
		);
	}
}

function fetch_tax_profile(frm) {
	if (!frm.doc.company) return;

	frappe.call({
		method: 'frappe.client.get_value',
		args: {
			doctype: 'Tax Profile',
			filters: {
				company: frm.doc.company
			},
			fieldname: 'name'
		},
		callback: (r) => {
			if (r.message && r.message.name) {
				frm.set_value('tax_profile', r.message.name);
				frappe.show_alert({
					message: __('Tax Profile auto-set to {0}', [r.message.name]),
					indicator: 'green'
				}, 3);
			}
		}
	});
}

function update_period_dates(frm) {
	if (!frm.doc.period_month || !frm.doc.period_year) return;

	// Calculate period dates on client side for immediate feedback
	const month = parseInt(frm.doc.period_month);
	const year = parseInt(frm.doc.period_year);

	const date_from = new Date(year, month - 1, 1);
	const date_to = new Date(year, month, 0);

	frm.set_value('date_from', frappe.datetime.obj_to_str(date_from));
	frm.set_value('date_to', frappe.datetime.obj_to_str(date_to));
}

function refresh_tax_registers(frm) {
	if (!frm.doc.name || frm.doc.__islocal) {
		frappe.msgprint(__('Please save the document first'));
		return;
	}

	if (!frm.doc.company || !frm.doc.date_from || !frm.doc.date_to) {
		frappe.msgprint(__('Please set Company and Period before refreshing registers'));
		return;
	}

	frappe.confirm(
		__('This will regenerate tax register snapshots for the period {0} to {1}. Continue?',
			[frm.doc.date_from, frm.doc.date_to]),
		() => {
			frappe.call({
				method: 'imogi_finance.imogi_finance.doctype.tax_period_closing.tax_period_closing.refresh_tax_registers',
				args: {
					closing_name: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Generating tax register snapshot...'),
				callback: (r) => {
					if (r.message) {
						frappe.show_alert({
							message: __('Tax registers refreshed successfully'),
							indicator: 'green'
						}, 5);
						frm.reload_doc();
					}
				}
			});
		}
	);
}

function generate_coretax_exports_dialog(frm) {
	if (!frm.doc.name || frm.doc.__islocal) {
		frappe.msgprint(__('Please save the document first'));
		return;
	}

	const d = new frappe.ui.Dialog({
		title: __('Generate CoreTax Exports'),
		fields: [
			{
				fieldtype: 'HTML',
				options: `
					<div class="alert alert-info">
						<strong>${__('Export Information:')}</strong><br>
						${__('This will generate CSV/XLSX files compatible with CoreTax system.')}<br>
						${__('Only verified tax invoices will be included in the export.')}
					</div>
				`
			},
			{
				fieldtype: 'Section Break',
				label: __('Current Settings')
			},
			{
				fieldtype: 'HTML',
				options: `
					<table class="table table-bordered table-sm">
						<tr>
							<td><strong>${__('Input VAT Settings:')}</strong></td>
							<td>${frm.doc.coretax_settings_input || '<em>Not set</em>'}</td>
						</tr>
						<tr>
							<td><strong>${__('Output VAT Settings:')}</strong></td>
							<td>${frm.doc.coretax_settings_output || '<em>Not set</em>'}</td>
						</tr>
					</table>
				`
			}
		],
		primary_action_label: __('Generate Exports'),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: 'imogi_finance.imogi_finance.doctype.tax_period_closing.tax_period_closing.generate_coretax_exports',
				args: {
					closing_name: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Generating CoreTax exports...'),
				callback: (r) => {
					if (r.message) {
						frappe.show_alert({
							message: __('CoreTax exports generated successfully'),
							indicator: 'green'
						}, 5);
						frm.reload_doc();
					}
				}
			});
		}
	});

	d.show();
}

function create_vat_netting_entry(frm) {
	if (!frm.doc.name || frm.doc.__islocal) {
		frappe.msgprint(__('Please save the document first'));
		return;
	}

	if (!frm.doc.input_vat_total && !frm.doc.output_vat_total) {
		frappe.msgprint(__('No VAT amounts to net. Please refresh tax registers first.'));
		return;
	}

	const vat_net = (frm.doc.output_vat_total || 0) - (frm.doc.input_vat_total || 0);
	const net_formatted = format_currency(vat_net, frm.doc.currency || 'IDR');

	frappe.confirm(
		__('Create VAT Netting Journal Entry?<br><br>Input VAT: {0}<br>Output VAT: {1}<br><strong>Net Payable: {2}</strong>',
			[
				format_currency(frm.doc.input_vat_total || 0, frm.doc.currency || 'IDR'),
				format_currency(frm.doc.output_vat_total || 0, frm.doc.currency || 'IDR'),
				net_formatted
			]),
		() => {
			frappe.call({
				method: 'imogi_finance.imogi_finance.doctype.tax_period_closing.tax_period_closing.create_vat_netting_entry_for_closing',
				args: {
					closing_name: frm.doc.name
				},
				freeze: true,
				freeze_message: __('Creating VAT netting entry...'),
				callback: (r) => {
					if (r.message) {
						frappe.show_alert({
							message: __('VAT Netting Journal Entry created: {0}', [r.message]),
							indicator: 'green'
						}, 5);
						frm.reload_doc();

						// Ask if user wants to view the journal entry
						frappe.confirm(
							__('Would you like to view the Journal Entry now?'),
							() => {
								frappe.set_route('Form', 'Journal Entry', r.message);
							}
						);
					}
				}
			});
		}
	);
}

function show_period_statistics(frm) {
	if (!frm.doc.name || frm.doc.__islocal) {
		frappe.msgprint(__('Please save the document first'));
		return;
	}

	frappe.call({
		method: 'imogi_finance.api.tax_closing.get_period_statistics',
		args: {
			closing_name: frm.doc.name
		},
		freeze: true,
		freeze_message: __('Loading period statistics...'),
		callback: (r) => {
			if (r.message) {
				show_statistics_dialog(r.message);
			}
		}
	});
}

function show_statistics_dialog(stats) {
	const d = new frappe.ui.Dialog({
		title: __('Period Statistics'),
		size: 'large',
		fields: [
			{
				fieldtype: 'HTML',
				options: build_statistics_html(stats)
			}
		],
		primary_action_label: __('Close'),
		primary_action() {
			d.hide();
		}
	});

	d.show();
}

function build_statistics_html(stats) {
	return `
		<div class="row">
			<div class="col-md-6">
				<h5>${__('Purchase Invoices (Input VAT)')}</h5>
				<table class="table table-bordered table-sm">
					<tr>
						<td>${__('Total Invoices:')}</td>
						<td class="text-right"><strong>${stats.purchase_invoice_count || 0}</strong></td>
					</tr>
					<tr>
						<td>${__('Verified Invoices:')}</td>
						<td class="text-right"><strong>${stats.purchase_invoice_verified || 0}</strong></td>
					</tr>
					<tr>
						<td>${__('Unverified Invoices:')}</td>
						<td class="text-right"><strong>${stats.purchase_invoice_unverified || 0}</strong></td>
					</tr>
					<tr class="table-info">
						<td>${__('Input VAT Total:')}</td>
						<td class="text-right"><strong>${format_currency(stats.input_vat_total || 0, 'IDR')}</strong></td>
					</tr>
				</table>
			</div>

			<div class="col-md-6">
				<h5>${__('Sales Invoices (Output VAT)')}</h5>
				<table class="table table-bordered table-sm">
					<tr>
						<td>${__('Total Invoices:')}</td>
						<td class="text-right"><strong>${stats.sales_invoice_count || 0}</strong></td>
					</tr>
					<tr>
						<td>${__('Verified Invoices:')}</td>
						<td class="text-right"><strong>${stats.sales_invoice_verified || 0}</strong></td>
					</tr>
					<tr>
						<td>${__('Unverified Invoices:')}</td>
						<td class="text-right"><strong>${stats.sales_invoice_unverified || 0}</strong></td>
					</tr>
					<tr class="table-info">
						<td>${__('Output VAT Total:')}</td>
						<td class="text-right"><strong>${format_currency(stats.output_vat_total || 0, 'IDR')}</strong></td>
					</tr>
				</table>
			</div>
		</div>

		<hr>

		<div class="row">
			<div class="col-md-12">
				<h5>${__('VAT Summary')}</h5>
				<table class="table table-bordered">
					<tr class="table-success">
						<td><strong>${__('VAT Net (Output - Input):')}</strong></td>
						<td class="text-right"><strong>${format_currency((stats.output_vat_total || 0) - (stats.input_vat_total || 0), 'IDR')}</strong></td>
					</tr>
				</table>
			</div>
		</div>

		${stats.purchase_invoice_unverified > 0 || stats.sales_invoice_unverified > 0 ? `
			<div class="alert alert-warning">
				<strong>${__('Warning:')}</strong><br>
				${__('There are unverified invoices in this period. Please verify all invoices before closing the period.')}
			</div>
		` : `
			<div class="alert alert-success">
				<strong>${__('All Clear:')}</strong><br>
				${__('All invoices in this period have been verified.')}
			</div>
		`}
	`;
}

// Register Integration - ERPNext v15+ Features

function show_register_details(frm) {
	if (!frm.doc.register_snapshot) {
		frappe.msgprint(__('No register snapshot available'));
		return;
	}

	let snapshot;
	try {
		snapshot = JSON.parse(frm.doc.register_snapshot);
	} catch (e) {
		frappe.msgprint(__('Failed to parse register snapshot'));
		return;
	}

	const d = new frappe.ui.Dialog({
		title: __('Register Details - {0}', [frm.doc.name]),
		size: 'extra-large',
		fields: [
			{
				fieldtype: 'HTML',
				options: build_register_details_html(snapshot, frm.doc)
			}
		],
		primary_action_label: __('Close'),
		primary_action() {
			d.hide();
		}
	});

	d.show();
}

function build_register_details_html(snapshot, doc) {
	const meta = snapshot.meta || {};
	const data_source = meta.data_source || 'unknown';
	const data_source_badge = data_source === 'register_integration'
		? '<span class="badge badge-success">Register Integration v15+</span>'
		: '<span class="badge badge-danger">Fallback Data</span>';

	return `
		<div class="register-details-container">
			<!-- Header Section -->
			<div class="row mb-3">
				<div class="col-md-12">
					<div class="alert alert-info">
						<div class="row">
							<div class="col-md-4">
								<strong>${__('Company:')}</strong> ${meta.company || '-'}<br>
								<strong>${__('Period:')}</strong> ${meta.date_from || '-'} to ${meta.date_to || '-'}
							</div>
							<div class="col-md-4">
								<strong>${__('Data Source:')}</strong> ${data_source_badge}<br>
								<strong>${__('Verification:')}</strong> ${doc.verification_status || 'Verified'}
							</div>
							<div class="col-md-4">
								<strong>${__('Generated:')}</strong> ${meta.generated_at ? frappe.datetime.str_to_user(meta.generated_at) : '-'}<br>
								<strong>${__('By:')}</strong> ${meta.generated_by || '-'}
							</div>
						</div>
					</div>
				</div>
			</div>

			<!-- VAT Summary -->
			<div class="row mb-4">
				<div class="col-md-4">
					<div class="card">
						<div class="card-header bg-primary text-white">
							<strong>${__('Input VAT (Purchases)')}</strong>
						</div>
						<div class="card-body">
							<table class="table table-sm table-borderless">
								<tr>
									<td>${__('Total Amount:')}</td>
									<td class="text-right"><strong>${format_currency(snapshot.input_vat_total || 0, 'IDR')}</strong></td>
								</tr>
								<tr>
									<td>${__('Invoice Count:')}</td>
									<td class="text-right"><strong>${snapshot.input_invoice_count || 0}</strong></td>
								</tr>
								<tr>
									<td>${__('Avg per Invoice:')}</td>
									<td class="text-right">${snapshot.input_invoice_count > 0 ? format_currency((snapshot.input_vat_total || 0) / snapshot.input_invoice_count, 'IDR') : '-'}</td>
								</tr>
							</table>
						</div>
					</div>
				</div>

				<div class="col-md-4">
					<div class="card">
						<div class="card-header bg-success text-white">
							<strong>${__('Output VAT (Sales)')}</strong>
						</div>
						<div class="card-body">
							<table class="table table-sm table-borderless">
								<tr>
									<td>${__('Total Amount:')}</td>
									<td class="text-right"><strong>${format_currency(snapshot.output_vat_total || 0, 'IDR')}</strong></td>
								</tr>
								<tr>
									<td>${__('Invoice Count:')}</td>
									<td class="text-right"><strong>${snapshot.output_invoice_count || 0}</strong></td>
								</tr>
								<tr>
									<td>${__('Avg per Invoice:')}</td>
									<td class="text-right">${snapshot.output_invoice_count > 0 ? format_currency((snapshot.output_vat_total || 0) / snapshot.output_invoice_count, 'IDR') : '-'}</td>
								</tr>
							</table>
						</div>
					</div>
				</div>

				<div class="col-md-4">
					<div class="card">
						<div class="card-header ${snapshot.vat_net >= 0 ? 'bg-warning' : 'bg-info'} text-white">
							<strong>${__('VAT Net Position')}</strong>
						</div>
						<div class="card-body">
							<table class="table table-sm table-borderless">
								<tr>
									<td>${__('Net Amount:')}</td>
									<td class="text-right"><strong>${format_currency(snapshot.vat_net || 0, 'IDR')}</strong></td>
								</tr>
								<tr>
									<td>${__('Direction:')}</td>
									<td class="text-right">
										${snapshot.vat_net > 0 ? '<span class="badge badge-warning">Payable</span>' :
										  snapshot.vat_net < 0 ? '<span class="badge badge-info">Receivable</span>' :
										  '<span class="badge badge-secondary">Zero</span>'}
									</td>
								</tr>
								<tr>
									<td>${__('Net Rate:')}</td>
									<td class="text-right">${snapshot.output_vat_total > 0 ? ((snapshot.vat_net / snapshot.output_vat_total) * 100).toFixed(2) : '0.00'}%</td>
								</tr>
							</table>
						</div>
					</div>
				</div>
			</div>

			<!-- Withholding Tax Summary -->
			<div class="row mb-4">
				<div class="col-md-6">
					<div class="card">
						<div class="card-header bg-secondary text-white">
							<strong>${__('Withholding Tax (PPh)')}</strong>
						</div>
						<div class="card-body">
							<table class="table table-sm table-borderless">
								<tr>
									<td>${__('Total Amount:')}</td>
									<td class="text-right"><strong>${format_currency(snapshot.pph_total || 0, 'IDR')}</strong></td>
								</tr>
								<tr>
									<td>${__('GL Entry Count:')}</td>
									<td class="text-right"><strong>${snapshot.withholding_entry_count || 0}</strong></td>
								</tr>
							</table>
							${build_withholding_breakdown(snapshot.withholding_by_account || {})}
						</div>
					</div>
				</div>

				<div class="col-md-6">
					<div class="card">
						<div class="card-header bg-secondary text-white">
							<strong>${__('Other Taxes')}</strong>
						</div>
						<div class="card-body">
							<table class="table table-sm">
								<tr>
									<td>${__('PB1 Total:')}</td>
									<td class="text-right"><strong>${format_currency(snapshot.pb1_total || 0, 'IDR')}</strong></td>
								</tr>
								<tr>
									<td>${__('BPJS Total:')}</td>
									<td class="text-right"><strong>${format_currency(snapshot.bpjs_total || 0, 'IDR')}</strong></td>
								</tr>
							</table>
							${build_pb1_breakdown(snapshot.pb1_breakdown || {})}
						</div>
					</div>
				</div>
			</div>

			<!-- Data Quality Indicators -->
			${data_source === 'fallback_empty' ? `
				<div class="alert alert-danger">
					<strong>${__('Data Quality Warning:')}</strong><br>
					${__('Register integration failed. Using fallback empty data.')}<br>
					${meta.error ? `<small>${__('Error:')} ${meta.error}</small>` : ''}
				</div>
			` : ''}

			${(snapshot.input_invoice_count === 0 && snapshot.output_invoice_count === 0 && snapshot.withholding_entry_count === 0) ? `
				<div class="alert alert-warning">
					<strong>${__('Empty Period:')}</strong><br>
					${__('No tax transactions found in this period. This may indicate a configuration issue or genuinely empty period.')}
				</div>
			` : ''}
		</div>
	`;
}

function build_withholding_breakdown(withholding_by_account) {
	if (!withholding_by_account || Object.keys(withholding_by_account).length === 0) {
		return '';
	}

	let html = '<div class="mt-3"><strong>' + __('Breakdown by Account:') + '</strong><table class="table table-sm mt-2">';
	for (const [account, amount] of Object.entries(withholding_by_account)) {
		html += `<tr><td><small>${account}</small></td><td class="text-right"><small>${format_currency(amount, 'IDR')}</small></td></tr>`;
	}
	html += '</table></div>';
	return html;
}

function build_pb1_breakdown(pb1_breakdown) {
	if (!pb1_breakdown || Object.keys(pb1_breakdown).length === 0) {
		return '';
	}

	let html = '<div class="mt-3"><strong>' + __('PB1 by Branch:') + '</strong><table class="table table-sm mt-2">';
	for (const [branch, amount] of Object.entries(pb1_breakdown)) {
		const branch_label = branch === '_default' ? __('Default') : branch;
		html += `<tr><td><small>${branch_label}</small></td><td class="text-right"><small>${format_currency(amount, 'IDR')}</small></td></tr>`;
	}
	html += '</table></div>';
	return html;
}
