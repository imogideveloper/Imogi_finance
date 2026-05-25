frappe.ui.form.on("Payroll Entry", {
	onload(frm) {
		toggle_manual_dates(frm);
		if (frm.doc.payroll_period) {
			load_sub_period_options(frm, frm.doc.payroll_sub_period);
		}
	},

	refresh(frm) {
		set_payroll_period_intro(frm);
		toggle_manual_dates(frm);
		if (frm.fields_dict.employer_contributions_summary) {
			frm.set_df_property("employer_contributions_summary", "cannot_add_rows", true);
			frm.set_df_property("employer_contributions_summary", "cannot_delete_rows", true);
		}
		if (
			frm.doc.docstatus === 1 &&
			frm.fields_dict.total_employer_contribution &&
			!flt(frm.doc.total_employer_contribution) &&
			frm.doc.salary_slips_submitted
		) {
			frappe.call({
				method:
					"imogi_finance.payroll.employer_contributions.refresh_payroll_entry_employer_summary",
				args: { payroll_entry: frm.doc.name },
				callback(r) {
					if (!r.message) {
						return;
					}
					frm.set_value(
						"total_employer_contribution",
						r.message.total_employer_contribution
					);
					frm.reload_doc();
				},
			});
		}
	},

	company(frm) {
		if (frm.doc.payroll_period) {
			frappe.db.get_value("Payroll Period", frm.doc.payroll_period, "company").then((r) => {
				if (
					r.message &&
					r.message.company &&
					frm.doc.company &&
					r.message.company !== frm.doc.company
				) {
					frm.set_value("payroll_period", "");
					frm.set_value("payroll_sub_period", "");
				}
			});
		}
		frm.set_query("payroll_period", () => ({
			filters: frm.doc.company ? { company: frm.doc.company } : {},
		}));
	},

	payroll_period(frm) {
		frm.set_value("payroll_sub_period", "");
		toggle_manual_dates(frm);
		if (frm.doc.payroll_period) {
			load_sub_period_options(frm);
		} else {
			clear_sub_period_options(frm);
			frm.__payroll_period_intro_text = null;
			if (frm.layout && frm.layout.message) {
				frm.layout.message.empty().addClass("hidden");
			}
		}
	},

	payroll_sub_period(frm) {
		if (frm.doc.__syncing_from_payroll_period) {
			return;
		}
		const row = resolve_sub_period_row(frm, frm.doc.payroll_sub_period);
		if (row) {
			sync_sub_period_to_form(frm, row);
		}
		refresh_december_checkbox(frm);
	},

	run_payroll_indonesia(frm) {
		refresh_december_checkbox(frm);
	},

	end_date(frm) {
		refresh_december_checkbox(frm);
	},
});

function refresh_december_checkbox(frm) {
	if (frm.fields_dict.run_payroll_indonesia_december) {
		frm.refresh_field("run_payroll_indonesia_december");
	}
}

function set_payroll_period_intro(frm) {
	// layout.show_message menambah (append) tanpa clear — refresh berkali-kali = banner dobel
	if (frm.layout && frm.layout.message) {
		frm.layout.message.empty().addClass("hidden");
	}

	if (!frm.doc.payroll_period) {
		return;
	}

	const intro_text = __(
		"Pilih <b>Payroll Period</b> lalu <b>Periode Gaji (Bulan)</b> (pola 25–24). Start/End Date dan Periode mengikuti pilihan. Centang <b>Run Payroll Indonesia</b> untuk PPh21 TER."
	);

	if (frm.__payroll_period_intro_text === intro_text) {
		return;
	}
	frm.__payroll_period_intro_text = intro_text;

	frm.layout.show_message(`<div>${intro_text}</div>`, "blue", true);
}

function toggle_manual_dates(frm) {
	const use_pp = !!frm.doc.payroll_period;
	frm.set_df_property("start_date", "read_only", use_pp ? 1 : 0);
	frm.set_df_property("end_date", "read_only", use_pp ? 1 : 0);
	frm.toggle_reqd("payroll_sub_period", use_pp);
}

function clear_sub_period_options(frm) {
	frm.set_df_property("payroll_sub_period", "options", "");
	frm.doc.__sub_period_map = {};
	frm.doc.__sub_period_by_name = {};
}

function resolve_sub_period_row(frm, selected) {
	if (!selected || !frm.doc.__sub_period_map) {
		return null;
	}
	if (frm.doc.__sub_period_map[selected]) {
		return frm.doc.__sub_period_map[selected];
	}
	if (frm.doc.__sub_period_by_name && frm.doc.__sub_period_by_name[selected]) {
		return frm.doc.__sub_period_by_name[selected];
	}
	return null;
}

function load_sub_period_options(frm, selected) {
	frappe.call({
		method: "imogi_finance.payroll.payroll_period_integration.get_payroll_sub_periods",
		args: { payroll_period: frm.doc.payroll_period },
		callback(r) {
			const rows = r.message || [];
			if (!rows.length) {
				frappe.msgprint(
					__(
						"Tidak ada periode di Payroll Period ini. Buka Payroll Period lalu Save sekali."
					)
				);
				clear_sub_period_options(frm);
				return;
			}

			const map = {};
			const options = rows.map((row) => {
				map[row.label] = row;
				return row.label;
			});
			frm.doc.__sub_period_map = map;
			frm.doc.__sub_period_by_name = {};
			rows.forEach((row) => {
				frm.doc.__sub_period_by_name[row.name] = row;
			});

			frm.set_df_property("payroll_sub_period", "options", options.join("\n"));

			const row =
				resolve_sub_period_row(frm, selected) ||
				(rows.length === 1 ? rows[0] : null);
			if (row) {
				sync_sub_period_to_form(frm, row);
			} else {
				frm.refresh_field("payroll_sub_period");
				mark_form_clean_if_submitted(frm);
			}
		},
	});
}

function sync_sub_period_to_form(frm, row) {
	if (!row) {
		return;
	}

	frm.doc.__payroll_sub_period_name = row.name;

	if (frm.doc.docstatus > 0) {
		set_field_without_dirty(frm, "payroll_sub_period", row.label);
		set_field_without_dirty(frm, "start_date", row.start_date);
		set_field_without_dirty(frm, "end_date", row.end_date);
		mark_form_clean_if_submitted(frm);
		return;
	}

	frm.doc.__syncing_from_payroll_period = true;
	frm.set_value("payroll_sub_period", row.label);
	frm.set_value("start_date", row.start_date);
	frm.set_value("end_date", row.end_date);
	set_posting_date_from_end(frm, row.end_date);
	frappe
		.call({
			method: "imogi_finance.payroll.payroll_period_integration.get_payroll_month_label",
			args: { end_date: row.end_date },
			callback(label_r) {
				if (label_r.message) {
					frm.set_value("periode", label_r.message);
				}
				frm.doc.__syncing_from_payroll_period = false;
				refresh_december_checkbox(frm);
			},
			error() {
				frm.doc.__syncing_from_payroll_period = false;
				refresh_december_checkbox(frm);
			},
		});
}

function set_posting_date_from_end(frm, end_date) {
	if (!end_date) {
		return;
	}
	const end = frappe.datetime.str_to_obj(end_date);
	const last_day = new Date(end.getFullYear(), end.getMonth() + 1, 0);
	frm.set_value("posting_date", frappe.datetime.obj_to_str(last_day));
}

function set_field_without_dirty(frm, fieldname, value) {
	const cur = frm.doc[fieldname];
	if (cur === value || (cur && value && String(cur) === String(value))) {
		return;
	}
	frm.doc[fieldname] = value;
	frm.refresh_field(fieldname);
}

function mark_form_clean_if_submitted(frm) {
	if (frm.doc.docstatus > 0) {
		frm.doc.__unsaved = 0;
		$(frm.wrapper).attr("data-state", "clean");
	}
}
