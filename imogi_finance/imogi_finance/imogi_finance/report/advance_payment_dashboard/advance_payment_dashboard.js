// Copyright (c) 2026, Imogi and contributors
// For license information, please see license.txt

frappe.query_reports["Advance Payment Dashboard"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today()
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Select",
			options: "\nSupplier\nEmployee\nCustomer"
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Dynamic Link",
			options: "party_type",
			get_query: function() {
				var party_type = frappe.query_report.get_filter_value('party_type');
				if (party_type) {
					return {
						doctype: party_type
					};
				}
			}
		},
		{
			fieldname: "account",
			label: __("Account"),
			fieldtype: "Link",
			options: "Account",
			get_query: function() {
				var company = frappe.query_report.get_filter_value('company');
				return {
					filters: {
						'company': company,
						'is_group': 0
					}
				};
			}
		},
		{
			fieldname: "allocation_status",
			label: __("Allocation Status"),
			fieldtype: "Select",
			options: "\nUnallocated\nPartially Allocated\nFully Allocated"
		}
	]
};
