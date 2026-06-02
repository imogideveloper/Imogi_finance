frappe.ui.form.on("Salary Structure Assignment", {
	refresh(frm) {
		if (frm.layout && frm.layout.message) {
			frm.layout.message.empty().addClass("hidden");
		}
		show_contract_message(frm);
		lock_component_table(frm);
		lock_contract_period_fields(frm);
		add_contract_buttons(frm);
		render_contract_history(frm);

		if (frm.doc.docstatus === 0 && frm.doc.salary_structure) {
			frm.add_custom_button(__("Muat Komponen dari Struktur"), () =>
				load_from_salary_structure(frm)
			);
		}

		if (frm.fields_dict.status) {
			frm.set_df_property("status", "read_only", 1);
		}
		toggle_tracking_fields(frm);
		["previous_assignment_contract", "renewed_by_assignment_contract"].forEach((fieldname) => {
			if (frm.fields_dict[fieldname]) {
				frm.set_df_property(fieldname, "read_only", 1);
			}
		});
	},

	from_date(frm) {
		validate_end_date(frm);
	},

	end_date(frm) {
		validate_end_date(frm);
		update_status_preview(frm);
	},

	employee(frm) {
		toggle_tracking_fields(frm);
		render_contract_history(frm);
	},

	salary_structure(frm) {
		toggle_tracking_fields(frm);
		render_contract_history(frm);
	},
});

function set_contract_history_section_visible(frm, visible) {
	const hide = visible ? 0 : 1;
	if (frm.fields_dict.assignment_contract_history_section) {
		frm.set_df_property("assignment_contract_history_section", "hidden", hide);
	}
	if (frm.fields_dict.assignment_contract_history) {
		frm.set_df_property("assignment_contract_history", "hidden", hide);
	}
}

function render_contract_history(frm) {
	if (!frm.fields_dict.assignment_contract_history) {
		return;
	}

	if (frm.is_new()) {                                 // ← tambahkan blok ini
		set_contract_history_section_visible(frm, false);
		return;
	}


	if (!frm.doc.employee) {
		set_contract_history_section_visible(frm, false);
		return;
	}

	frappe.call({
		method: "imogi_finance.payroll.salary_structure_assignment.get_assignment_contract_history",
		args: { employee: frm.doc.employee },
		callback(r) {
			const rows = r.message || [];
			const has_history = rows.length > 0;
			set_contract_history_section_visible(frm, has_history);
			if (has_history) {
				frm.fields_dict.assignment_contract_history.$wrapper.html(
					build_contract_history_html(rows)
				);
			}
		},
	});
}

function build_contract_history_html(rows) {
	const tr = rows.map((row) => {
		const name = frappe.utils.escape_html(row.name || "");
		const status = frappe.utils.escape_html(row.status || "");
		const reason = frappe.utils.escape_html(row.change_reason || "-");
		const from_date = row.from_date ? frappe.datetime.str_to_user(row.from_date) : "-";
		const end_date = row.end_date ? frappe.datetime.str_to_user(row.end_date) : __("Tanpa End Date");
		return `
			<div class="imogi-ssa-history-row">
				<div>
					<div class="text-muted small">${__("Contract")}</div>
					<a class="font-weight-bold" href="/app/salary-structure-assignment/${encodeURIComponent(name)}">${name}</a>
				</div>
				<div>
					<div class="text-muted small">${__("Periode")}</div>
					<div>${from_date} - ${end_date}</div>
				</div>
				<div>
					<div class="text-muted small">${__("Status")}</div>
					<span class="indicator-pill ${get_history_status_class(status)}">${status}</span>
				</div>
				<div>
					<div class="text-muted small">${__("Alasan Perubahan")}</div>
					<div>${reason}</div>
				</div>
			</div>
		`;
	}).join("");

	return `
		<style>
			.imogi-ssa-history {
				display: flex;
				flex-direction: column;
				gap: 10px;
				margin-top: 8px;
			}
			.imogi-ssa-history-row {
				display: grid;
				grid-template-columns: minmax(180px, 1.3fr) minmax(170px, 1fr) minmax(120px, .7fr) minmax(220px, 1.4fr);
				gap: 14px;
				padding: 12px 14px;
				border: 1px solid var(--border-color);
				border-radius: 8px;
				background: var(--fg-color);
			}
			@media (max-width: 900px) {
				.imogi-ssa-history-row {
					grid-template-columns: 1fr;
				}
			}
		</style>
		<div class="imogi-ssa-history">
			${tr}
		</div>
	`;
}

function get_history_status_class(status) {
	const key = (status || "").toLowerCase();
	if (key === "activate") return "green";
	if (key === "expired") return "red";
	if (key === "expired soon") return "orange";
	return "gray";
}

function toggle_tracking_fields(frm) {
	const has_contract_tracking = Boolean(
		frm.doc.previous_assignment_contract || frm.doc.renewed_by_assignment_contract
	);
	if (frm.fields_dict.assignment_contract_tracking_section) {
		frm.set_df_property("assignment_contract_tracking_section", "hidden", has_contract_tracking ? 0 : 1);
	}
	if (frm.fields_dict.assignment_contract_tracking_column) {
		frm.set_df_property("assignment_contract_tracking_column", "hidden", has_contract_tracking ? 0 : 1);
	}
	if (frm.fields_dict.previous_assignment_contract) {
		frm.set_df_property(
			"previous_assignment_contract",
			"hidden",
			frm.doc.previous_assignment_contract ? 0 : 1
		);
	}
	if (frm.fields_dict.renewed_by_assignment_contract) {
		frm.set_df_property(
			"renewed_by_assignment_contract",
			"hidden",
			frm.doc.renewed_by_assignment_contract ? 0 : 1
		);
	}
	if (frm.fields_dict.change_reason) {
		frm.set_df_property("change_reason", "hidden", has_contract_tracking ? 0 : 1);
		frm.set_df_property("change_reason", "reqd", has_contract_tracking ? 1 : 0);
	}
}

function get_contract_status(frm) {
	if (!frm.doc.end_date) {
		return frm.doc.renewed_by_assignment_contract ? "Expired" : "Activate";
	}
	if (frm.doc.renewed_by_assignment_contract) {
		return "Expired";
	}
	const days_until_end = frappe.datetime.get_diff(frm.doc.end_date, frappe.datetime.get_today());
	if (days_until_end < 0) {
		return "Expired";
	}
	if (days_until_end <= 30) {
		return "Expired Soon";
	}
	return "Activate";
}

function is_expiring_soon(frm) {
	return get_contract_status(frm) === "Expired Soon";
}

function show_contract_message(frm) {
	const status = get_contract_status(frm);
	const message = status === "Expired"
		? "<strong>Assignment Contract Expired</strong> — Contract ini sudah melewati End Date. "
			+ "Klik <b>Perpanjang Contract</b> untuk membuat contract baru."
		: is_expiring_soon(frm)
			? "<strong>Assignment Contract Expired Soon</strong> — Siapkan perpanjangan sebelum End Date. "
				+ "Gunakan <b>Perpanjang Contract</b> jika contract akan diteruskan."
		: "<strong>Assignment Contract</strong> — Kontrak penugasan gaji karyawan. "
			+ "Isi komponen di tabel <b>Komponen Gaji</b> saat Draft. "
			+ "Setelah Submitted, komponen terkunci dan perubahan harus lewat contract baru.";

	const indicator = status === "Expired" ? "red" : is_expiring_soon(frm) ? "orange" : "blue";
	frm.layout.show_message(`<div>${__(message)}</div>`, indicator, true);
}

function lock_contract_period_fields(frm) {
	const locked = frm.doc.docstatus === 1;
	["from_date", "end_date"].forEach((fieldname) => {
		if (frm.fields_dict[fieldname]) {
			frm.set_df_property(fieldname, "read_only", locked ? 1 : 0);
		}
	});
}

function lock_component_table(frm) {
	if (!frm.fields_dict.salary_component_amounts) {
		return;
	}
	const locked = frm.doc.docstatus === 1;
	frm.set_df_property("salary_component_amounts", "read_only", locked ? 1 : 0);
	frm.set_df_property("salary_component_amounts", "cannot_add_rows", locked ? 1 : 0);
	frm.set_df_property("salary_component_amounts", "cannot_delete_rows", locked ? 1 : 0);

	const grid = frm.fields_dict.salary_component_amounts.grid;
	if (grid) {
		grid.cannot_add_rows = locked;
		grid.cannot_delete_rows = locked;
		["salary_component", "amount"].forEach((fieldname) => {
			grid.update_docfield_property(fieldname, "read_only", locked ? 1 : 0);
		});
	}
	frm.refresh_field("salary_component_amounts");
}

function add_contract_buttons(frm) {
	if (frm.doc.docstatus !== 1) {
		return;
	}

	const label = get_contract_status(frm) === "Expired" || is_expiring_soon(frm)
		? __("Perpanjang Contract")
		: __("Buat Perubahan Contract");
	frm.add_custom_button(label, () => {
		create_new_contract_from_current(frm);
	}, __("Assignment Contract"));

	if (frm.doc.employee) {
		frm.add_custom_button(__("Lihat Riwayat Contract"), () => {
			frappe.route_options = { employee: frm.doc.employee };
			frappe.set_route("List", "Salary Structure Assignment");
		}, __("Assignment Contract"));
	}
}

function create_new_contract_from_current(frm) {
	frappe.call({
		method: "imogi_finance.payroll.salary_structure_assignment.get_assignment_contract_renewal_defaults",
		args: { source_name: frm.doc.name },
		callback(r) {
			const defaults = r.message || {};
			open_new_contract(defaults);
		},
	});
}

function open_new_contract(defaults) {
	frappe.model.with_doctype("Salary Structure Assignment", () => {
		const doc = frappe.model.get_new_doc("Salary Structure Assignment");
		const fields = defaults.fields || {};
		Object.keys(fields).forEach((fieldname) => {
			if (frappe.meta.has_field("Salary Structure Assignment", fieldname)) {
				doc[fieldname] = fields[fieldname];
			}
		});

		(defaults.salary_component_amounts || []).forEach((row) => {
			const child = frappe.model.add_child(
				doc,
				"Salary Structure Assignment Component",
				"salary_component_amounts"
			);
			child.salary_component = row.salary_component;
			child.amount = row.amount;
		});

		frappe.set_route("Form", "Salary Structure Assignment", doc.name);
		frappe.show_alert({
			message: __("Draft Assignment Contract baru dibuat dari contract lama."),
			indicator: "green",
		});
	});
}

function validate_end_date(frm) {
	if (!frm.doc.from_date || !frm.doc.end_date) {
		return;
	}
	if (frappe.datetime.get_diff(frm.doc.end_date, frm.doc.from_date) < 0) {
		frappe.msgprint(__("End Date tidak boleh lebih kecil dari From Date."));
		frm.set_value("end_date", "");
	}
}

function update_status_preview(frm) {
	if (!frm.fields_dict.status) {
		return;
	}
	frm.set_value("status", get_contract_status(frm));
}

function load_from_salary_structure(frm) {
	if (!frm.doc.salary_structure) {
		frappe.msgprint(__("Pilih Salary Structure terlebih dahulu."));
		return;
	}

	if (frm.doc.salary_component_amounts?.length) {
		frappe.confirm(
			__("Tabel Komponen Gaji sudah berisi baris. Ganti dengan komponen dari struktur?"),
			() => fetch_structure_components(frm),
			() => {}
		);
		return;
	}

	fetch_structure_components(frm);
}

function fetch_structure_components(frm) {
	frappe.call({
		method: "frappe.client.get",
		args: { doctype: "Salary Structure", name: frm.doc.salary_structure },
		callback(r) {
			const struct = r.message;
			if (!struct) return;

			const rows = [];
			(struct.earnings || []).forEach((row) => {
				if (!row.salary_component) return;
				rows.push({
					salary_component: row.salary_component,
					amount: flt(row.amount) || 0,
				});
			});

			if (!rows.length) {
				frappe.msgprint(__("Tidak ada komponen earning di struktur ini."));
				return;
			}

			frm.clear_table("salary_component_amounts");
			rows.forEach((row) => {
				const child = frm.add_child("salary_component_amounts");
				child.salary_component = row.salary_component;
				child.amount = row.amount;
			});
			frm.refresh_field("salary_component_amounts");

			frappe.show_alert({
				message: __("Komponen dimuat dari {0}", [frm.doc.salary_structure]),
				indicator: "green",
			});
		},
	});
}
