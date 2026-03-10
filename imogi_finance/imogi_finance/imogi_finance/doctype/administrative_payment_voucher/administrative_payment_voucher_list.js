frappe.listview_settings["Administrative Payment Voucher"] = {
	onload(listview) {
		const branch_field = listview.page.add_field({
			label: __("Branch"),
			fieldtype: "Link",
			fieldname: "branch_filter",
			options: "Branch",
			change(value) {
				listview.filter_area.clear();
				if (value) {
					listview.filter_area.add([[listview.doctype, "branch", "=", value]]);
				}
				listview.refresh();
			},
		});

		const default_branch = frappe.defaults.get_user_default("branch");
		if (default_branch) {
			branch_field.set_value(default_branch);
		}
	},
};
