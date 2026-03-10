// Copyright (c) 2024, Imogi Finance and contributors
// For license information, please see license.txt

frappe.query_reports["VAT Output Register Verified"] = {
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
			"fieldname": "customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"get_query": function() {
				return {
					query: "erpnext.controllers.queries.customer_query"
				};
			}
		},
		{
			"fieldname": "verification_status",
			"label": __("Verification Status"),
			"fieldtype": "Select",
			"options": ["", "Verified", "Needs Review", "Rejected"],
			"default": "Verified"
		}
	],
	
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Format verification status with color indicators
		if (column.fieldname == "out_fp_status") {
			if (value === "Verified") {
				value = `<span class="indicator-pill green">${value}</span>`;
			} else if (value === "Needs Review") {
				value = `<span class="indicator-pill orange">${value}</span>`;
			} else if (value === "Rejected") {
				value = `<span class="indicator-pill red">${value}</span>`;
			}
		}
		
		return value;
	},
	
	"onload": function(report) {
		// Validate configuration on load
		frappe.call({
			method: "imogi_finance.imogi_finance.utils.tax_report_utils.validate_tax_register_configuration",
			args: {
				register_type: "output",
				company: frappe.query_report.get_filter_value("company")
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
		
		// Add custom buttons
		report.page.add_inner_button(__("Configuration Check"), function() {
			check_configuration(report);
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
			register_type: "output",
			company: company
		},
		callback: function(r) {
			if (r.message) {
				let message = r.message.message;
				if (r.message.action) {
					message += "<br><br>" + r.message.action;
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
