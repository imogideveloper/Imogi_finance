frappe.provide("imogi_finance.form_field_visibility");

imogi_finance.form_field_visibility.get_hidden_fields = function (doctype) {
	const map = frappe.boot.imogi_hidden_form_fields || {};
	return map[doctype] || [];
};

imogi_finance.form_field_visibility.apply = function (frm) {
	if (!frm || !frm.doctype || frm.doctype === "Workspace UI Settings") {
		return;
	}

	const hidden = imogi_finance.form_field_visibility.get_hidden_fields(frm.doctype);
	if (!hidden.length) {
		return;
	}

	hidden.forEach((fieldname) => {
		if (!frm.fields_dict[fieldname]) {
			return;
		}
		frm.set_df_property(fieldname, "hidden", 1);
	});
};

$(document).on("form-refresh", function (_event, frm) {
	imogi_finance.form_field_visibility.apply(frm);
});
