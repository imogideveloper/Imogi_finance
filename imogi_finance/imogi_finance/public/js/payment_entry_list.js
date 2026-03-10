frappe.listview_settings['Payment Entry'] = {
	add_fields: ["paid_amount", "received_amount", "payment_type"],
	get_indicator: function(doc) {
		if (doc.docstatus == 1) {
			return [__("Submitted"), "blue", "docstatus,=,1"];
		} else if (doc.docstatus == 2) {
			return [__("Cancelled"), "red", "docstatus,=,2"];
		} else {
			return [__("Draft"), "grey", "docstatus,=,0"];
		}
	},
	formatters: {
		paid_amount: function(value, df, doc) {
			if (doc.payment_type === "Pay") {
				return frappe.format(value, {fieldtype: 'Currency', options: 'currency'});
			}
			return "";
		},
		received_amount: function(value, df, doc) {
			if (doc.payment_type === "Receive") {
				return frappe.format(value, {fieldtype: 'Currency', options: 'currency'});
			}
			return "";
		}
	},
	hide_name_column: false
};
