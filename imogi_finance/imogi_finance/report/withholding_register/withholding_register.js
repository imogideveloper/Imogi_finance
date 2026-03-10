// Copyright (c) 2024, Imogi Finance and contributors
// For license information, please see license.txt

frappe.query_reports["Withholding Register"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.month_start(),
			"reqd": 0
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.month_end(),
			"reqd": 0
		},
		{
			"fieldname": "accounts",
			"label": __("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"get_query": function() {
				const company = frappe.query_report.get_filter_value("company");
				return {
					filters: {
						"company": company,
						"account_type": ["in", ["Tax", "Payable"]],
						"is_group": 0
					}
				};
			}
		},
		{
			"fieldname": "party",
			"label": __("Party"),
			"fieldtype": "Link",
			"options": "Supplier",
			"get_query": function() {
				return {
					query: "erpnext.controllers.queries.supplier_query"
				};
			}
		},
		{
			"fieldname": "voucher_type",
			"label": __("Voucher Type"),
			"fieldtype": "Select",
			"options": ["", "Purchase Invoice", "Payment Entry", "Journal Entry", "Expense Claim"]
		}
	],
	
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Format net amount with color indicators
		if (column.fieldname == "net_amount") {
			const amount = parseFloat(data.net_amount);
			if (amount > 0) {
				// Credit balance (liability increased)
				value = `<span style="color: var(--text-green)">${value}</span>`;
			} else if (amount < 0) {
				// Debit balance (liability decreased/payment)
				value = `<span style="color: var(--text-red)">${value}</span>`;
			}
		}
		
		return value;
	},
	
	"onload": function(report) {
		// Validate configuration on load
		const company = frappe.query_report.get_filter_value("company");
		if (company) {
			frappe.call({
				method: "imogi_finance.imogi_finance.utils.tax_report_utils.validate_tax_register_configuration",
				args: {
					register_type: "withholding",
					company: company
				},
				callback: function(r) {
					if (r.message && !r.message.valid) {
						frappe.msgprint({
							title: __("Configuration Required"),
							indicator: r.message.indicator || "red",
							message: r.message.message + "<br>" + (r.message.action || "")
						});
					}
				}
			});
		}
		
		// Add custom buttons
		report.page.add_inner_button(__("Configuration Check"), function() {
			check_configuration(report);
		}, __("Tools"));
		
		report.page.add_inner_button(__("Show PPh Accounts"), function() {
			show_pph_accounts(report);
		}, __("Tools"));
		
		report.page.add_inner_button(__("Export to Excel"), function() {
			export_to_excel(report);
		}, __("Tools"));
	}
};

function check_configuration(report) {
	const company = frappe.query_report.get_filter_value("company");
	
	if (!company) {
		frappe.msgprint(__("Please select a company first."));
		return;
	}
	
	frappe.call({
		method: "imogi_finance.imogi_finance.utils.tax_report_utils.validate_tax_register_configuration",
		args: {
			register_type: "withholding",
			company: company
		},
		callback: function(r) {
			if (r.message) {
				let message = r.message.message;
				if (r.message.action) {
					message += "<br><br>" + r.message.action;
				}
				
				// Show configured accounts if available
				if (r.message.accounts && r.message.accounts.length > 0) {
					message += "<br><br><strong>" + __("Configured PPh Accounts:") + "</strong><br>";
					message += "<ul>";
					r.message.accounts.forEach(function(account) {
						message += `<li>${account}</li>`;
					});
					message += "</ul>";
				}
				
				frappe.msgprint({
					title: __("Configuration Status"),
					indicator: r.message.indicator || "blue",
					message: message
				});
			}
		}
	});
}

function show_pph_accounts(report) {
	const company = frappe.query_report.get_filter_value("company");
	
	if (!company) {
		frappe.msgprint(__("Please select a company first."));
		return;
	}
	
	// Get Tax Profile for the company
	frappe.db.get_value("Tax Profile", {"company": company}, "name", function(r) {
		if (r && r.name) {
			frappe.set_route("Form", "Tax Profile", r.name);
		} else {
			frappe.msgprint({
				title: __("Tax Profile Not Found"),
				indicator: "red",
				message: __("No Tax Profile found for company {0}. Please create one to configure PPh accounts.", [company])
			});
		}
	});
}

function export_to_excel(report) {
	// Use native ERPNext export functionality
	const filters = frappe.query_report.get_filter_values();
	
	frappe.call({
		method: "frappe.desk.query_report.export_query",
		args: {
			report_name: report.report_name,
			file_format_type: "Excel",
			filters: filters
		},
		callback: function(r) {
			if (r.message) {
				const link = document.createElement("a");
				link.href = r.message.file_url;
				link.download = r.message.file_name;
				link.click();
			}
		}
	});
}
