frappe.ui.form.on("Payroll Entry", {
	onload(frm) {
		patch_hrms_payroll_date_handlers(frm);
		hide_payroll_period_detail_fields(frm);
		ensure_payroll_frequency_default(frm);
		toggle_auto_payroll_period_fields(frm);
		if (frm.is_new() && frm.doc.company) {
			auto_apply_payroll_period(frm);
		} else if (frm.doc.payroll_period) {
			load_sub_period_options(frm, frm.doc.payroll_sub_period, get_reference_date_for_period(frm));
		}
	},

	refresh(frm) {
		set_payroll_period_intro(frm);
		hide_payroll_period_detail_fields(frm);
		ensure_payroll_frequency_default(frm);
		toggle_auto_payroll_period_fields(frm);
		ensure_sub_period_dates(frm);
		match_periode_gaji_width_to_company(frm);
		if (frm.is_new() && frm.doc.company && !frm.doc.payroll_period) {
			auto_apply_payroll_period(frm);
		}
		add_request_payment_button(frm);
	},

	company(frm) {
		if (frm.doc.payroll_period && !frm.doc.__auto_applying_payroll_period) {
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
		if (frm.doc.company && frm.doc.docstatus === 0) {
			auto_apply_payroll_period(frm);
		}
	},

	payroll_period(frm) {
		if (frm.doc.__syncing_from_payroll_period || frm.doc.__auto_applying_payroll_period) {
			return;
		}
		if (frm.doc.payroll_period) {
			load_sub_period_options(frm, null, get_reference_date_for_period(frm));
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

	payroll_frequency(frm) {
		if (frm.doc.payroll_period) {
			ensure_sub_period_dates(frm);
		}
	},

	run_payroll_indonesia(frm) {
		refresh_december_checkbox(frm);
	},

	end_date(frm) {
		refresh_december_checkbox(frm);
	},
});

function get_reference_date_for_period(frm) {
	// Bulan gaji dari tanggal hari ini (bukan dari Posting Date yang bisa diedit user).
	return frappe.datetime.get_today();
}

function set_payroll_period_silent(frm, payroll_period) {
	if (!payroll_period || frm.doc.payroll_period === payroll_period) {
		return;
	}
	frm.doc.payroll_period = payroll_period;
}

function ensure_payroll_frequency_default(frm) {
	if (!frm.doc.salary_slip_based_on_timesheet && !frm.doc.payroll_frequency) {
		frm.doc.payroll_frequency = "Monthly";
	}
}

function auto_apply_payroll_period(frm) {
	if (frm.doc.docstatus > 0 || frm.doc.__auto_applying_payroll_period || !frm.doc.company) {
		return;
	}

	frm.doc.__auto_applying_payroll_period = true;
	frappe.call({
		method: "imogi_finance.payroll.payroll_period_integration.auto_fill_payroll_entry_period",
		args: {
			company: frm.doc.company,
			posting_date: get_reference_date_for_period(frm),
		},
		callback(r) {
			frm.doc.__auto_applying_payroll_period = false;
			const data = r.message;
			if (!data || !data.payroll_period) {
				frappe.msgprint(
					__(
						"Payroll Period untuk company {0} tidak ditemukan. Buat Payroll Period tahun {1} dulu.",
						[
							frm.doc.company,
							frappe.datetime.str_to_obj(get_reference_date_for_period(frm)).getFullYear(),
						]
					)
				);
				return;
			}

			const apply_sub = (sub_period) => {
				if (!sub_period) {
					frappe.msgprint(
						__(
							"Periode gaji (25–24) untuk tanggal {0} tidak ditemukan. "
								+ "Pastikan Payroll Period tahun {1} sudah dibuat.",
							[
								get_reference_date_for_period(frm),
								frappe.datetime
									.str_to_obj(get_reference_date_for_period(frm))
									.getFullYear(),
							]
						)
					);
					return;
				}
				set_payroll_period_silent(frm, data.payroll_period);
				load_sub_period_options(frm, sub_period.label, get_reference_date_for_period(frm));
			};

			ensure_payroll_frequency_default(frm);
			if (data.sub_period) {
				apply_sub(data.sub_period);
			} else {
				set_payroll_period_silent(frm, data.payroll_period);
			}
		},
		error() {
			frm.doc.__auto_applying_payroll_period = false;
		},
	});
}

function add_request_payment_button(frm) {
	// Payroll disbursement goes through an Administrative Payment Voucher
	// (wet-signature approval + Payment Entry posting) instead of the raw
	// "Make Bank Entry" button, so it can't be paid without going through
	// approval first. Only offer this once the payroll run itself is final.
	if (frm.doc.docstatus !== 1) {
		return;
	}

	if (frm.doc.linked_payment_voucher) {
		frm.add_custom_button(__("Lihat Payment Voucher"), () => {
			frappe.set_route("Form", "Administrative Payment Voucher", frm.doc.linked_payment_voucher);
		});
		return;
	}

	frm.add_custom_button(__("Request Payment"), () => {
		frappe.call({
			method: "imogi_finance.payroll.payroll_payment.request_payroll_payment",
			args: { payroll_entry_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Membuat Payment Voucher..."),
			callback(r) {
				if (r.message && r.message.payment_voucher) {
					frappe.set_route("Form", "Administrative Payment Voucher", r.message.payment_voucher);
				}
			},
		});
	});
}

function refresh_december_checkbox(frm) {
	if (frm.fields_dict.run_payroll_indonesia_december) {
		frm.refresh_field("run_payroll_indonesia_december");
	}
}

function patch_hrms_payroll_date_handlers(frm) {
	if (frm.__payroll_period_handlers_patched) {
		return;
	}
	frm.__payroll_period_handlers_patched = true;

	const original_set_start_end = frm.events.set_start_end_dates;
	if (original_set_start_end) {
		frm.events.set_start_end_dates = function (form) {
			if (form.doc.payroll_period) {
				ensure_sub_period_dates(form);
				return Promise.resolve();
			}
			return original_set_start_end(form);
		};
	}

	const original_set_end = frm.events.set_end_date;
	if (original_set_end) {
		frm.events.set_end_date = function (form) {
			if (form.doc.payroll_period || form.doc.__syncing_from_payroll_period) {
				return;
			}
			return original_set_end(form);
		};
	}
}

function set_payroll_period_intro(frm) {
	if (frm.layout && frm.layout.message) {
		frm.layout.message.empty().addClass("hidden");
	}

	if (!frm.doc.company || frm.doc.docstatus > 0 || !frm.fields_dict.payroll_sub_period) {
		return;
	}

	const intro_text = __(
		"<b>Periode Gaji (Bulan)</b> terisi otomatis dari bulan berjalan (cutoff <b>25–24</b>). "
			+ "<b>Posting Date</b> default tanggal <b>24</b> akhir periode dan <b>bisa diubah</b> "
			+ "(tidak harus sama dengan periode gaji)."
	);

	if (frm.__payroll_period_intro_text === intro_text) {
		return;
	}
	frm.__payroll_period_intro_text = intro_text;

	frm.layout.show_message(`<div>${intro_text}</div>`, "blue", true);
}

const PAYROLL_PERIOD_DETAIL_FIELDS = [
	"payroll_frequency",
	"start_date",
	"end_date",
	"column_break_13",
	"deduct_tax_for_unclaimed_employee_benefits",
	"deduct_tax_for_unsubmitted_tax_exemption_proof",
	"employer_contributions_section",
	"total_employer_contribution",
	"employer_contributions_summary",
];

function match_periode_gaji_width_to_company(frm) {
	// Periode Gaji (Bulan) lives alone in its own full-width Section Break
	// (needed so it doesn't share a row with Company - see
	// fix_pe_pp_layout_v2.py). Explicit user request (2026-08-20): rather
	// than stretching it edge-to-edge, cap it to the exact same rendered
	// width as the Company field above it, so the two lines up visually.
	// Clean up the old always-100%-width <style> tag from an earlier
	// iteration of this fix - Frappe desk is an SPA, so a leftover
	// <style> injected into document.head during a previous visit this
	// session survives route changes until a hard reload.
	const stale_style = document.getElementById("pe-widen-periode-style");
	if (stale_style) {
		stale_style.remove();
	}

	const $company = frm.fields_dict.company && frm.fields_dict.company.$wrapper;
	const $periode = frm.fields_dict.payroll_sub_period && frm.fields_dict.payroll_sub_period.$wrapper;
	if (!$company || !$company.length || !$periode || !$periode.length) {
		return;
	}
	const company_width = $company.width();
	if (!company_width) {
		return;
	}

	// garage_desk.css forces `.frappe-control[data-fieldtype="Select"]
	// select { width: 150px !important }` (and other wrapper-level
	// !important rules) site-wide. A plain jQuery .css() call sets a
	// NORMAL inline style, which always loses to ANY !important rule from
	// an external stylesheet, no matter how it's targeted. An inline
	// !important (via the native setProperty(..., "important") API) is the
	// only thing that reliably wins over that - CSS origin/importance
	// ordering puts author-!important-inline above author-!important-sheet
	// regardless of selector specificity.
	const force = ($el, props) => {
		$el.each(function () {
			Object.entries(props).forEach(([prop, value]) => {
				this.style.setProperty(prop, value, "important");
			});
		});
	};

	// .form-column's children are flex items with flex-grow:1 by default,
	// which would stretch straight past a plain width/max-width regardless
	// of value - flex-basis pins the actual size.
	force($periode, {
		"max-width": `${company_width}px`,
		"width": `${company_width}px`,
		"flex": `0 0 ${company_width}px`,
	});
	force($periode.find(".control-input, .control-input-wrapper, select, input"), {
		"max-width": "100%",
		"width": "100%",
		"flex": "none",
	});
}

function hide_payroll_period_detail_fields(frm) {
	[...PAYROLL_PERIOD_DETAIL_FIELDS, "payroll_period"].forEach((fieldname) => {
		if (frm.fields_dict[fieldname]) {
			frm.set_df_property(fieldname, "hidden", 1);
		}
	});
}

function toggle_auto_payroll_period_fields(frm) {
	// Periode Gaji (Bulan) auto-fills from the current month on a new
	// Payroll Entry, but explicit user request (2026-08-19): keep it
	// editable while Draft so a user can pick a different month (e.g.
	// running payroll late for a prior period) instead of only ever
	// accepting whatever auto_apply_payroll_period() detected. Locked
	// again once Submitted, same as the rest of the document.
	const auto_mode = frm.doc.docstatus === 0;
	if (frm.fields_dict.payroll_sub_period) {
		frm.set_df_property("payroll_sub_period", "read_only", auto_mode ? 0 : 1);
		frm.toggle_reqd("payroll_sub_period", auto_mode && !!frm.doc.payroll_period);
	}
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

function find_sub_period_row_for_posting_date(rows, posting_date) {
	const ref = frappe.datetime.str_to_obj(posting_date);
	for (const row of rows) {
		const end = frappe.datetime.str_to_obj(row.end_date);
		if (end.getFullYear() === ref.getFullYear() && end.getMonth() === ref.getMonth()) {
			return row;
		}
	}
	for (const row of rows) {
		if (
			frappe.datetime.get_diff(row.start_date, posting_date) <= 0 &&
			frappe.datetime.get_diff(posting_date, row.end_date) <= 0
		) {
			return row;
		}
	}
	return null;
}

function sub_period_dates_match(frm, row) {
	if (!row) {
		return true;
	}
	return (
		String(frm.doc.start_date || "") === String(row.start_date || "") &&
		String(frm.doc.end_date || "") === String(row.end_date || "")
	);
}

function ensure_sub_period_dates(frm) {
	if (!frm.doc.payroll_period || !frm.doc.payroll_sub_period) {
		return;
	}
	const row = resolve_sub_period_row(frm, frm.doc.payroll_sub_period);
	if (row && !sub_period_dates_match(frm, row)) {
		sync_sub_period_to_form(frm, row);
	}
}

function load_sub_period_options(frm, selected, posting_date) {
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

			const due = posting_date || get_reference_date_for_period(frm);
			const from_posting = due ? find_sub_period_row_for_posting_date(rows, due) : null;
			const from_selected = resolve_sub_period_row(frm, selected);
			const row = from_selected || from_posting || (rows.length === 1 ? rows[0] : null);

			if (row) {
				sync_sub_period_to_form(frm, row);
			} else {
				frm.refresh_field("payroll_sub_period");
				mark_form_clean_if_submitted(frm);
			}

			// set_df_property("options", ...) / refresh_field() above rebuild
			// the <select> control's DOM, wiping out any inline style applied
			// during the earlier synchronous refresh() - reapply once that
			// settles instead of only right after refresh().
			match_periode_gaji_width_to_company(frm);
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

	frm.doc.payroll_sub_period = row.label;
	frm.doc.start_date = row.start_date;
	frm.doc.end_date = row.end_date;
	frm.refresh_fields(["payroll_sub_period", "start_date", "end_date"]);

	set_posting_date_from_end(frm, row.end_date);

	frappe
		.call({
			method: "imogi_finance.payroll.payroll_period_integration.get_payroll_month_label",
			args: { end_date: row.end_date },
			callback(label_r) {
				if (label_r.message) {
					frm.doc.periode = label_r.message;
					frm.refresh_field("periode");
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
	if (!end_date || frm.doc.posting_date) {
		return;
	}
	// Default saat kosong: tanggal 24 akhir periode cutoff (bukan akhir bulan kalender).
	frm.doc.posting_date = end_date;
	frm.refresh_field("posting_date");
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
