frappe.provide("imogi_finance.form_field_visibility");

imogi_finance.form_field_visibility._last_fetch = {};
imogi_finance.form_field_visibility._pending_fetch = {};

imogi_finance.form_field_visibility.get_hidden_fields = function (doctype) {
	const map = frappe.boot.imogi_hidden_form_fields || {};
	return map[doctype] || [];
};

imogi_finance.form_field_visibility.hide_fields = function (frm, hidden) {
	(hidden || []).forEach((fieldname) => {
		const field = frm.fields_dict[fieldname];
		if (!field) {
			return;
		}

		if (field.df) {
			field.df.hidden = 1;
		}
		frm.set_df_property(fieldname, "hidden", 1);
		frm.toggle_display(fieldname, false);

		if (field.toggle) {
			field.toggle(false);
		}
		if (field.wrapper) {
			$(field.wrapper).hide();
		}
		if (field.$wrapper) {
			field.$wrapper.hide();
		}
	});
};

imogi_finance.form_field_visibility.fetch_hidden_fields = function (frm, force = false) {
	if (!frm?.doctype || frm.doctype === "Workspace UI Settings") {
		return;
	}

	const now = Date.now();
	const last_fetch = imogi_finance.form_field_visibility._last_fetch[frm.doctype] || 0;
	if (!force && now - last_fetch < 10000) {
		return;
	}
	if (imogi_finance.form_field_visibility._pending_fetch[frm.doctype]) {
		return;
	}

	imogi_finance.form_field_visibility._pending_fetch[frm.doctype] = true;
	const request = frappe.call({
		method: "imogi_finance.workspace_visibility.get_hidden_form_fields_for_doctype",
		args: { doctype: frm.doctype },
		callback(r) {
			const fresh = r.message || [];
			if (!frappe.boot.imogi_hidden_form_fields) {
				frappe.boot.imogi_hidden_form_fields = {};
			}
			frappe.boot.imogi_hidden_form_fields[frm.doctype] = fresh;
			imogi_finance.form_field_visibility._last_fetch[frm.doctype] = Date.now();
			imogi_finance.form_field_visibility.hide_fields(frm, fresh);
		},
	});

	if (request?.always) {
		request.always(() => {
			imogi_finance.form_field_visibility._pending_fetch[frm.doctype] = false;
		});
	} else {
		setTimeout(() => {
			imogi_finance.form_field_visibility._pending_fetch[frm.doctype] = false;
		}, 2000);
	}
};

imogi_finance.form_field_visibility.apply = function (frm, force_fetch = false) {
	if (!frm || !frm.doctype || frm.doctype === "Workspace UI Settings") {
		return;
	}

	const hidden = imogi_finance.form_field_visibility.get_hidden_fields(frm.doctype);
	imogi_finance.form_field_visibility.hide_fields(frm, hidden);
	imogi_finance.form_field_visibility.fetch_hidden_fields(frm, force_fetch);
};

$(document).on("form-refresh", function (_event, frm) {
	imogi_finance.form_field_visibility.apply(frm, true);
	setTimeout(() => imogi_finance.form_field_visibility.apply(frm), 300);
	setTimeout(() => imogi_finance.form_field_visibility.apply(frm), 1200);
});

frappe.after_ajax(() => {
	if (window.cur_frm) {
		imogi_finance.form_field_visibility.apply(window.cur_frm);
	}
});

setInterval(() => {
	if (window.cur_frm) {
		imogi_finance.form_field_visibility.apply(window.cur_frm);
	}
}, 1500);
