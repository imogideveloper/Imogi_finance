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
			+ "Komponen di tabel <b>Komponen Gaji</b> tetap bisa diedit walau sudah Submitted. "
			+ "Semua perubahan tercatat otomatis - cek lewat <b>Assignment Contract &gt; History Contract</b>.";

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
	// Komponen Gaji lock-after-submit intentionally disabled - explicit
	// user request (2026-08-19) to let Nilai be edited (and rows added)
	// directly on a Submitted contract. This mirrors the same change made
	// server-side in payroll/salary_structure_assignment.py's own
	// validate_salary_structure_assignment - see that function's comment
	// for the audit-trail tradeoff this opts out of.
	if (!frm.fields_dict.salary_component_amounts) {
		return;
	}
	frm.set_df_property("salary_component_amounts", "read_only", 0);
	frm.set_df_property("salary_component_amounts", "cannot_add_rows", 0);
	frm.set_df_property("salary_component_amounts", "cannot_delete_rows", 0);

	const grid = frm.fields_dict.salary_component_amounts.grid;
	if (grid) {
		grid.cannot_add_rows = false;
		grid.cannot_delete_rows = false;
		["salary_component", "amount"].forEach((fieldname) => {
			grid.update_docfield_property(fieldname, "read_only", 0);
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

	frm.add_custom_button(__("History Contract"), () => {
		show_change_history(frm);
	}, __("Assignment Contract"));
}

const HISTORY_KIND_META = {
	field: { icon: "edit", color: "#6c8ef5" },
	edit: { icon: "edit", color: "#e0982b" },
	add: { icon: "add", color: "#2ecc71" },
	remove: { icon: "delete", color: "#e25c5c" },
};

function show_change_history(frm) {
	frappe.call({
		method: "imogi_finance.payroll.salary_structure_assignment.get_assignment_contract_change_log",
		args: { source_name: frm.doc.name },
		freeze: true,
		callback(r) {
			render_change_history_dialog(frm, r.message || []);
		},
	});
}

const ID_MONTHS = [
	"Januari", "Februari", "Maret", "April", "Mei", "Juni",
	"Juli", "Agustus", "September", "Oktober", "November", "Desember",
];
const ID_MONTHS_SHORT = [
	"Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
	"Jul", "Agu", "Sep", "Okt", "Nov", "Des",
];

function render_change_history_dialog(frm, entries) {
	// Flatten satu "entry" (satu kali save, bisa berisi banyak perubahan)
	// jadi baris-baris atomic, supaya bisa di-listview & di-group per tanggal.
	const flat = [];
	entries.forEach((entry) => {
		entry.changes.forEach((change) => {
			flat.push(Object.assign({ creation: entry.creation, user: entry.user }, change));
		});
	});

	const dialog = new frappe.ui.Dialog({
		title: `${frappe.utils.icon("list", "md")} ${__("History Contract")} — ${frm.doc.name}`,
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "history_html" }],
	});

	inject_history_styles();

	const group_options = [
		{ value: "day", label: __("Hari") },
		{ value: "month", label: __("Bulan") },
		{ value: "year", label: __("Tahun") },
	];
	let group_by = "day";

	const toggle_html = group_options.map((opt) => `
		<button type="button" class="btn btn-xs ssa-hist-toggle-btn${opt.value === group_by ? " active" : ""}" data-group="${opt.value}">
			${opt.label}
		</button>
	`).join("");

	dialog.fields_dict.history_html.$wrapper.html(`
		<div class="ssa-hist-toolbar">
			<span class="ssa-hist-toolbar-label">${__("Kelompokkan per")}</span>
			<div class="ssa-hist-toggle-group">${toggle_html}</div>
		</div>
		<div class="ssa-hist-list"></div>
	`);

	const $wrapper = dialog.fields_dict.history_html.$wrapper;

	function render_list() {
		const $list = $wrapper.find(".ssa-hist-list");
		if (!flat.length) {
			$list.html(`
				<div class="ssa-hist-empty">
					${frappe.utils.icon("list", "lg")}
					<div>${__("Belum ada perubahan tercatat untuk contract ini.")}</div>
				</div>
			`);
			return;
		}
		const groups = group_changes_by_date(flat, group_by);
		const body_rows = groups.map((g) => render_date_group(g, group_by)).join("");
		$list.html(`
			<table class="ssa-hist-table">
				<thead>
					<tr>
						<th class="ssa-hist-col-time">${__("Waktu")}</th>
						<th class="ssa-hist-col-kind">${__("Jenis")}</th>
						<th class="ssa-hist-col-field">${__("Field / Komponen")}</th>
						<th class="ssa-hist-col-old">${__("Nilai Lama")}</th>
						<th class="ssa-hist-col-new">${__("Nilai Baru")}</th>
						<th class="ssa-hist-col-user">${__("Diubah Oleh")}</th>
					</tr>
				</thead>
				<tbody>${body_rows}</tbody>
			</table>
		`);
	}

	$wrapper.on("click", ".ssa-hist-toggle-btn", function () {
		$wrapper.find(".ssa-hist-toggle-btn").removeClass("active");
		$(this).addClass("active");
		group_by = $(this).data("group");
		render_list();
	});

	render_list();
	dialog.show();
}

function group_changes_by_date(flat, group_by) {
	const buckets = {};
	flat.forEach((change) => {
		const [y, m, d] = change.creation.slice(0, 10).split("-");
		const month_idx = parseInt(m, 10) - 1;
		let key, label;
		if (group_by === "day") {
			key = `${y}-${m}-${d}`;
			label = `${parseInt(d, 10)} ${ID_MONTHS[month_idx]} ${y}`;
		} else if (group_by === "month") {
			key = `${y}-${m}`;
			label = `${ID_MONTHS[month_idx]} ${y}`;
		} else {
			key = y;
			label = y;
		}
		if (!buckets[key]) {
			buckets[key] = { key, label, items: [] };
		}
		buckets[key].items.push(change);
	});
	return Object.values(buckets).sort((a, b) => (a.key < b.key ? 1 : -1));
}

function row_time_label(creation, group_by) {
	const [y, m, d] = creation.slice(0, 10).split("-");
	const time = creation.slice(11, 16);
	if (group_by === "day") {
		return time;
	}
	if (group_by === "month") {
		return `${parseInt(d, 10)} ${ID_MONTHS_SHORT[parseInt(m, 10) - 1]}, ${time}`;
	}
	return `${parseInt(d, 10)} ${ID_MONTHS_SHORT[parseInt(m, 10) - 1]}, ${time}`;
}

const HISTORY_KIND_LABEL = {
	field: __("Ubah"),
	edit: __("Ubah"),
	add: __("Tambah"),
	remove: __("Hapus"),
};

function render_date_group(group, group_by) {
	const rows = group.items.map((change) => render_history_row(change, group_by)).join("");
	return `
		<tr class="ssa-hist-date-row">
			<td colspan="6">
				<span>${frappe.utils.escape_html(group.label)}</span>
				<span class="ssa-hist-date-count">${group.items.length}</span>
			</td>
		</tr>
		${rows}
	`;
}

function render_history_row(change, group_by) {
	const meta = HISTORY_KIND_META[change.kind] || HISTORY_KIND_META.field;
	const kind_label = HISTORY_KIND_LABEL[change.kind] || HISTORY_KIND_LABEL.field;
	const user_info = frappe.user_info(change.user);
	const user_name = frappe.utils.escape_html(user_info.fullname || change.user);
	const when_exact = frappe.datetime.str_to_user(change.creation);
	const time_label = row_time_label(change.creation, group_by);

	// Kolom "Field / Komponen": untuk edit komponen -> nama komponen gaji,
	// untuk field-level (mis. End Date, Status) -> nama field itu sendiri.
	const field_label = change.kind === "field"
		? frappe.utils.escape_html(change.label)
		: frappe.utils.escape_html(change.component);

	let old_cell = "—";
	let new_cell = "—";
	if (change.kind === "add") {
		new_cell = `<span class="ssa-hist-badge ssa-hist-new">${frappe.utils.escape_html(change.amount)}</span>`;
	} else if (change.kind === "remove") {
		old_cell = `<span class="ssa-hist-badge ssa-hist-old">${frappe.utils.escape_html(change.amount)}</span>`;
	} else {
		old_cell = `<span class="ssa-hist-badge ssa-hist-old">${frappe.utils.escape_html(change.old)}</span>`;
		new_cell = `<span class="ssa-hist-badge ssa-hist-new">${frappe.utils.escape_html(change.new)}</span>`;
	}

	return `
		<tr class="ssa-hist-row" style="--hist-color: ${meta.color};">
			<td class="ssa-hist-col-time" title="${frappe.utils.escape_html(when_exact)}">${time_label}</td>
			<td class="ssa-hist-col-kind">
				<span class="ssa-hist-kind-badge">
					${frappe.utils.icon(meta.icon, "xs")} ${kind_label}
				</span>
			</td>
			<td class="ssa-hist-col-field">${field_label}</td>
			<td class="ssa-hist-col-old">${old_cell}</td>
			<td class="ssa-hist-col-new">${new_cell}</td>
			<td class="ssa-hist-col-user">
				${frappe.avatar(change.user, "avatar-xs")} <span>${user_name}</span>
			</td>
		</tr>
	`;
}

function inject_history_styles() {
	if (document.getElementById("ssa-hist-styles")) {
		return;
	}
	const style = document.createElement("style");
	style.id = "ssa-hist-styles";
	style.textContent = `
		.ssa-hist-toolbar {
			display: flex;
			align-items: center;
			gap: 10px;
			padding-bottom: 10px;
			margin-bottom: 8px;
			border-bottom: 1px solid var(--border-color);
		}
		.ssa-hist-toolbar-label {
			font-size: 12px;
			color: var(--text-muted);
		}
		.ssa-hist-toggle-group {
			display: inline-flex;
			background: var(--control-bg);
			border-radius: var(--border-radius);
			padding: 2px;
			gap: 2px;
		}
		.ssa-hist-toggle-btn {
			border: none;
			background: transparent;
			color: var(--text-muted);
			font-size: 12px;
			padding: 3px 12px;
			border-radius: calc(var(--border-radius) - 2px);
			box-shadow: none;
		}
		.ssa-hist-toggle-btn.active {
			background: var(--fg-color);
			color: var(--text-color);
			font-weight: 600;
			box-shadow: var(--shadow-sm);
		}
		.ssa-hist-list {
			max-height: 58vh;
			overflow-y: auto;
			padding-right: 2px;
		}
		.ssa-hist-table {
			width: 100%;
			border-collapse: collapse;
			font-size: 12.5px;
		}
		.ssa-hist-table thead th {
			position: sticky;
			top: 0;
			z-index: 2;
			background: var(--fg-color);
			color: var(--text-muted);
			text-transform: uppercase;
			letter-spacing: .3px;
			font-size: 10.5px;
			font-weight: 600;
			text-align: left;
			padding: 6px 10px;
			border-bottom: 2px solid var(--border-color);
			white-space: nowrap;
		}
		.ssa-hist-table td {
			padding: 7px 10px;
			border-bottom: 1px solid var(--border-color);
			vertical-align: middle;
			color: var(--text-color);
			line-height: 1.5;
		}
		.ssa-hist-table tbody tr.ssa-hist-row:hover {
			background: var(--subtle-accent, var(--fg-hover-color));
		}
		.ssa-hist-row {
			border-left: 3px solid var(--hist-color);
		}
		.ssa-hist-date-row td {
			position: sticky;
			top: 27px;
			z-index: 1;
			background: var(--subtle-fg);
			font-weight: 600;
			padding: 5px 10px;
			border-bottom: 1px solid var(--border-color);
		}
		.ssa-hist-date-count {
			font-weight: 400;
			font-size: 11px;
			color: var(--text-muted);
			background: var(--bg-color);
			border-radius: 10px;
			padding: 1px 8px;
			margin-left: 6px;
		}
		.ssa-hist-col-time {
			white-space: nowrap;
			color: var(--text-muted);
			font-variant-numeric: tabular-nums;
			font-size: 11.5px;
			cursor: default;
		}
		.ssa-hist-col-kind {
			white-space: nowrap;
		}
		.ssa-hist-kind-badge {
			display: inline-flex;
			align-items: center;
			gap: 4px;
			color: var(--hist-color);
			font-weight: 600;
			font-size: 11.5px;
		}
		.ssa-hist-kind-badge svg {
			width: 12px;
			height: 12px;
			stroke: currentColor;
		}
		.ssa-hist-col-field {
			font-weight: 500;
			white-space: nowrap;
		}
		.ssa-hist-col-old, .ssa-hist-col-new {
			white-space: nowrap;
		}
		.ssa-hist-col-user {
			white-space: nowrap;
			color: var(--text-muted);
			display: flex;
			align-items: center;
			gap: 6px;
		}
		.ssa-hist-badge {
			display: inline-block;
			padding: 1px 6px;
			border-radius: 3px;
			font-weight: 600;
			font-size: 12px;
			margin: 0 2px;
		}
		.ssa-hist-badge.ssa-hist-old {
			background: rgba(226, 92, 92, 0.12);
			color: #c0392b;
			text-decoration: line-through;
			text-decoration-color: rgba(192, 57, 43, 0.5);
		}
		.ssa-hist-badge.ssa-hist-new {
			background: rgba(46, 204, 113, 0.14);
			color: #1f8b4c;
		}
		.ssa-hist-empty {
			display: flex;
			flex-direction: column;
			align-items: center;
			gap: 10px;
			padding: 48px 12px;
			color: var(--text-muted);
			text-align: center;
		}
		.ssa-hist-empty svg {
			width: 32px;
			height: 32px;
			opacity: .4;
		}
	`;
	document.head.appendChild(style);
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
