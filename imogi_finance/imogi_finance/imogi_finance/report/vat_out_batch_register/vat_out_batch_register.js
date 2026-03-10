// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.query_reports["VAT OUT Batch Register"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 0
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			"reqd": 0
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 0
		},
		{
			"fieldname": "docstatus",
			"label": __("Status"),
			"fieldtype": "Select",
			"options": "\nDraft\nSubmitted\nCancelled",
			"default": "",
			"reqd": 0
		},
		{
			"fieldname": "upload_status",
			"label": __("Upload Status"),
			"fieldtype": "Select",
			"options": "\nNot Started\nIn Progress\nCompleted\nFailed",
			"default": "",
			"reqd": 0
		}
	],
	
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Color-code status
		if (column.fieldname === "docstatus") {
			if (value === "Submitted") {
				value = `<span class="indicator-pill green">${value}</span>`;
			} else if (value === "Cancelled") {
				value = `<span class="indicator-pill red">${value}</span>`;
			} else if (value === "Draft") {
				value = `<span class="indicator-pill blue">${value}</span>`;
			}
		}
		
		if (column.fieldname === "coretax_upload_status") {
			if (value === "Completed") {
				value = `<span class="indicator-pill green">${value}</span>`;
			} else if (value === "Failed") {
				value = `<span class="indicator-pill red">${value}</span>`;
			} else if (value === "In Progress") {
				value = `<span class="indicator-pill orange">${value}</span>`;
			} else if (value === "Not Started") {
				value = `<span class="indicator-pill grey">${value}</span>`;
			}
		}
		
		return value;
	}
};
