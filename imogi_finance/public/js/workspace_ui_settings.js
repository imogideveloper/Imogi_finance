frappe.ui.form.on("Workspace UI Settings", {
	onload(frm) {
		if (frm.is_new()) {
			frm.set_value("enabled", 1);
		}
	},
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		install_access_studio_styles();
		refresh_access_studio_layout(frm);

		frm.add_custom_button(__("Sembunyikan Workspace"), () => {
			open_workspace_picker(frm);
		}, __("Aksi Cepat"));

		frm.add_custom_button(__("Sembunyikan Section"), () => {
			open_section_picker(frm);
		}, __("Aksi Cepat"));

		frm.add_custom_button(__("Pilih Field Form untuk Disembunyikan"), () => {
			open_form_field_picker(frm);
		}, __("Aksi Cepat"));

		frm.set_df_property("hidden_form_fields", "cannot_add_rows", true);

		frm.set_intro(
			__(
				"<b>Access Studio</b> membantu menyederhanakan tampilan Desk tanpa menghapus data. Gunakan tombol <b>Aksi Cepat</b>, lalu klik <b>Save & Reload Desk</b> setelah selesai."
			)
		);

		frm.add_custom_button(__("Save & Reload Desk"), () => {
			frm.save().then(() => {
				frappe.ui.toolbar.clear_cache();
				frappe.show_alert({
					message: __("Cache cleared. Halaman akan dimuat ulang."),
					indicator: "green",
				});
				setTimeout(() => window.location.reload(), 800);
			});
		});
	},
});

function install_access_studio_styles() {
	if ($("#imogi-access-studio-style").length) {
		return;
	}

	$(`<style id="imogi-access-studio-style">
		.imogi-access-studio-hero {
			border: 1px solid var(--border-color);
			border-radius: 14px;
			padding: 16px 18px;
			margin-bottom: 16px;
			background: linear-gradient(135deg, var(--fg-color), var(--control-bg));
		}
		.imogi-access-studio-hero h4 {
			margin: 0 0 6px;
			font-weight: 700;
		}
		.imogi-access-studio-stats {
			display: grid;
			grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
			gap: 10px;
			margin-top: 14px;
		}
		.imogi-access-studio-stat {
			border: 1px solid var(--border-color);
			border-radius: 12px;
			padding: 10px 12px;
			background: var(--card-bg);
		}
		.imogi-access-studio-stat strong {
			display: block;
			font-size: 18px;
			line-height: 1.2;
		}
		.imogi-access-studio-card {
			border: 1px solid var(--border-color);
			border-radius: 12px;
			padding: 12px 14px;
			margin-bottom: 12px;
			background: var(--fg-color);
		}
		.imogi-access-studio-card b {
			display: block;
			margin-bottom: 4px;
		}
		.imogi-access-studio-card .muted {
			color: var(--text-muted);
		}
		.imogi-access-studio-card .steps {
			margin: 8px 0 0;
			padding-left: 18px;
		}
		.imogi-access-studio-card .steps li {
			margin: 2px 0;
		}
		.imogi-field-option:hover,
		.imogi-workspace-option:hover,
		.imogi-section-option:hover {
			background: var(--control-bg);
		}
		.form-grid .grid-heading-row {
			background: var(--control-bg);
		}
	</style>`).appendTo("head");
}

function refresh_access_studio_layout(frm) {
	frm.set_df_property("per_user_help", "options", get_access_studio_hero(frm));
	frm.set_df_property("workspace_help", "options", get_workspace_help_card());
	frm.set_df_property("section_help_sections", "options", get_section_help_card());
	frm.set_df_property("form_field_help", "options", get_form_field_help_card());
	["per_user_help", "workspace_help", "section_help_sections", "form_field_help"].forEach((fieldname) => {
		frm.refresh_field(fieldname);
	});
}

function count_hidden(rows) {
	return (rows || []).filter((row) => cint(row.hidden)).length;
}

function get_access_studio_hero(frm) {
	const workspace_count = count_hidden(frm.doc.hidden_workspaces);
	const section_count = count_hidden(frm.doc.hidden_sections);
	const field_count = count_hidden(frm.doc.hidden_form_fields);
	return `
		<div class="imogi-access-studio-hero">
			<h4>${__("Access Studio")}</h4>
			<div class="text-muted">
				${__(
					"Atur menu dan field yang tampil untuk user tertentu. Kosongkan User jika aturan berlaku untuk semua user."
				)}
			</div>
			<div class="imogi-access-studio-stats">
				<div class="imogi-access-studio-stat">
					<strong>${workspace_count}</strong>
					<span class="text-muted">${__("Workspace disembunyikan")}</span>
				</div>
				<div class="imogi-access-studio-stat">
					<strong>${section_count}</strong>
					<span class="text-muted">${__("Section disembunyikan")}</span>
				</div>
				<div class="imogi-access-studio-stat">
					<strong>${field_count}</strong>
					<span class="text-muted">${__("Field form disembunyikan")}</span>
				</div>
			</div>
		</div>
	`;
}

function get_workspace_help_card() {
	return `
		<div class="imogi-access-studio-card">
			<b>${__("Hide Entire Workspace")}</b>
			<div class="muted">
				${__("Sembunyikan menu workspace dari sidebar. Cocok untuk membatasi akses tampilan per user tanpa menghapus workspace.")}
			</div>
			<ol class="steps">
				<li>${__("Klik Aksi Cepat > Sembunyikan Workspace.")}</li>
				<li>${__("Pilih user jika hanya berlaku untuk user tertentu.")}</li>
				<li>${__("Centang workspace, lalu simpan.")}</li>
			</ol>
		</div>
	`;
}

function get_section_help_card() {
	return `
		<div class="imogi-access-studio-card">
			<b>${__("Hide Section Inside Workspace")}</b>
			<div class="muted">
				${__("Sembunyikan grup menu atau shortcut di dalam satu workspace, misalnya section Items and Pricing di Selling.")}
			</div>
			<ol class="steps">
				<li>${__("Klik Aksi Cepat > Sembunyikan Section.")}</li>
				<li>${__("Pilih workspace, lalu centang section yang ingin disembunyikan.")}</li>
			</ol>
		</div>
	`;
}

function get_form_field_help_card() {
	return `
		<div class="imogi-access-studio-card">
			<b>${__("Hide Form Fields")}</b>
			<div class="muted">
				${__("User tidak perlu mengetik fieldname. Gunakan picker untuk memilih label field yang terlihat di form.")}
			</div>
			<ol class="steps">
				<li>${__("Klik Aksi Cepat > Pilih Field Form untuk Disembunyikan.")}</li>
				<li>${__("Pilih DocType, cari field, lalu centang field yang mau disembunyikan.")}</li>
				<li>${__("Save dan klik Save & Reload Desk agar perubahan langsung terasa.")}</li>
			</ol>
		</div>
	`;
}

function open_workspace_picker(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Sembunyikan Workspace"),
		fields: [
			{
				fieldname: "user",
				fieldtype: "Link",
				label: __("User (opsional)"),
				options: "User",
				description: __("Kosongkan = semua user. Isi mis. Yugo = hanya user itu."),
			},
			{
				fieldname: "workspaces_html",
				fieldtype: "HTML",
			},
		],
		primary_action_label: __("Sembunyikan Terpilih"),
		primary_action() {
			const user = dialog.get_value("user") || "";
			const selected = [];
			dialog.$wrapper.find("input.imogi-hide-workspace:checked").each(function () {
				selected.push($(this).data("name"));
			});

			if (!selected.length) {
				frappe.msgprint(__("Centang minimal satu workspace."));
				return;
			}

			const calls = selected.map((workspace) =>
				frappe.call({
					method: "imogi_finance.workspace_visibility.add_hidden_workspace",
					args: { workspace, user: user || null },
				})
			);

			Promise.all(calls).then(() => {
				dialog.hide();
				frm.reload_doc();
				const who = user
					? __("{0} workspace untuk user {1}.", [selected.length, user])
					: __("{0} workspace untuk semua user.", [selected.length]);
				frappe.show_alert({ message: who, indicator: "green" });
			});
		},
	});

	dialog.show();
	load_pickable_workspaces(dialog);
}

function load_pickable_workspaces(dialog) {
	const $wrap = dialog.fields_dict.workspaces_html.$wrapper;
	$wrap.html(`<p class="text-muted">${__("Loading workspaces...")}</p>`);

	frappe.call({
		method: "imogi_finance.workspace_visibility.get_pickable_workspaces",
		callback(r) {
			const rows = r.message || [];
			if (!rows.length) {
				$wrap.html(`<p class="text-muted">${__("No workspaces found.")}</p>`);
				return;
			}

			let html = `
				<div class="imogi-access-studio-card">
					<b>${__("Pilih Workspace")}</b>
					<div class="muted">${__(
						"Centang workspace yang tidak ingin ditampilkan di sidebar."
					)}</div>
				</div>
			`;
			html += '<div class="imogi-workspace-list" style="max-height:320px;overflow:auto;">';
			rows.forEach((row) => {
				const name = frappe.utils.escape_html(row.name);
				const title = frappe.utils.escape_html(row.title || row.name);
				const module = frappe.utils.escape_html(row.module || "");
				html += `
					<div class="imogi-workspace-option" style="padding:8px 10px;border-radius:6px;margin-bottom:4px;">
						<label style="display:flex;gap:10px;align-items:flex-start;margin:0;cursor:pointer;">
							<input type="checkbox" class="imogi-hide-workspace" data-name="${name}">
							<span>
								<strong>${title}</strong><br>
								<span class="text-muted small">${module}</span>
							</span>
						</label>
					</div>`;
			});
			html += "</div>";
			$wrap.html(html);
		},
	});
}

function open_section_picker(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Sembunyikan Section"),
		fields: [
			{
				fieldname: "user",
				fieldtype: "Link",
				label: __("User (opsional)"),
				options: "User",
				description: __("Kosongkan = semua user. Isi mis. Yugo = hanya user itu."),
			},
			{
				fieldname: "workspace",
				fieldtype: "Link",
				label: __("Workspace"),
				options: "Workspace",
				reqd: 1,
				onchange() {
					load_sections(dialog);
				},
			},
			{
				fieldname: "sections_html",
				fieldtype: "HTML",
			},
		],
		primary_action_label: __("Sembunyikan Terpilih"),
		primary_action() {
			const user = dialog.get_value("user") || "";
			const workspace = dialog.get_value("workspace");
			const selected = [];
			dialog.$wrapper.find("input.imogi-hide-section:checked").each(function () {
				selected.push($(this).data("label"));
			});

			if (!workspace || !selected.length) {
				frappe.msgprint(__("Pilih workspace dan minimal satu section."));
				return;
			}

			const calls = selected.map((section_label) =>
				frappe.call({
					method: "imogi_finance.workspace_visibility.add_hidden_section",
					args: { workspace, section_label, user: user || null },
				})
			);

			Promise.all(calls).then(() => {
				dialog.hide();
				frm.reload_doc();
				const who = user
					? __("{0} section(s) untuk user {1}.", [selected.length, user])
					: __("{0} section(s) untuk semua user.", [selected.length]);
				frappe.show_alert({ message: who, indicator: "green" });
			});
		},
	});

	dialog.show();
	dialog.fields_dict.sections_html.$wrapper.html(
		`<p class="text-muted">${__(
			"Pilih user (opsional), workspace, lalu centang section yang ingin disembunyikan."
		)}</p>`
	);
}

function load_sections(dialog) {
	const workspace = dialog.get_value("workspace");
	const $wrap = dialog.fields_dict.sections_html.$wrapper;

	if (!workspace) {
		$wrap.find(".imogi-section-list").remove();
		return;
	}

	$wrap.find(".imogi-section-list").remove();
	$wrap.append(`<p class="text-muted">${__("Loading sections...")}</p>`);

	frappe.call({
		method: "imogi_finance.workspace_visibility.get_workspace_sections",
		args: { workspace },
		callback(r) {
			$wrap.find("p.text-muted").remove();
			const rows = r.message || [];
			if (!rows.length) {
				$wrap.append(`<p class="text-muted">${__("No sections found.")}</p>`);
				return;
			}

			let html = '<div class="imogi-section-list" style="max-height:280px;overflow:auto;">';
			rows.forEach((row) => {
				const safe = frappe.utils.escape_html(row.label);
				html += `
					<div class="imogi-section-option" style="padding:8px 10px;border-radius:6px;margin-bottom:4px;">
						<label style="display:flex;gap:10px;align-items:flex-start;margin:0;cursor:pointer;">
							<input type="checkbox" class="imogi-hide-section" data-label="${safe}">
							<span>
								<strong>${safe}</strong><br>
								<span class="text-muted small">${frappe.utils.escape_html(row.section_type)}</span>
							</span>
						</label>
					</div>`;
			});
			html += "</div>";
			$wrap.append(html);
		},
	});
}

function open_form_field_picker(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Pilih Field Form untuk Disembunyikan"),
		fields: [
			{
				fieldname: "user",
				fieldtype: "Link",
				label: __("User (opsional)"),
				options: "User",
				description: __("Kosongkan jika aturan berlaku untuk semua user."),
			},
			{
				fieldname: "ref_doctype",
				fieldtype: "Link",
				label: __("DocType"),
				options: "DocType",
				reqd: 1,
				onchange() {
					load_form_fields(dialog);
				},
			},
			{
				fieldname: "fields_html",
				fieldtype: "HTML",
			},
		],
		primary_action_label: __("Sembunyikan Field Terpilih"),
		primary_action() {
			const user = dialog.get_value("user") || "";
			const ref_doctype = dialog.get_value("ref_doctype");
			const selected = [];
			dialog.$wrapper.find("input.imogi-hide-field:checked").each(function () {
				selected.push({
					fieldname: $(this).data("fieldname"),
					field_label: $(this).data("label"),
				});
			});

			if (!ref_doctype || !selected.length) {
				frappe.msgprint(__("Pilih DocType dan minimal satu field."));
				return;
			}

			const calls = selected.map((row) =>
				frappe.call({
					method: "imogi_finance.workspace_visibility.add_hidden_form_field",
					args: {
						ref_doctype,
						fieldname: row.fieldname,
						field_label: row.field_label,
						user: user || null,
					},
				})
			);

			Promise.all(calls).then(() => {
				dialog.hide();
				frm.reload_doc();
				const who = user
					? __("{0} field(s) untuk user {1}.", [selected.length, user])
					: __("{0} field(s) untuk semua user.", [selected.length]);
				frappe.show_alert({ message: who, indicator: "green" });
			});
		},
	});

	dialog.show();
	dialog.$wrapper.find(".modal-dialog").css("max-width", "820px");
	dialog.fields_dict.fields_html.$wrapper.html(
		`<div class="alert alert-info" style="margin-bottom: 10px;">
			<strong>${__("Langkah")}</strong><br>
			${__(
				"Pilih DocType, cari nama field yang terlihat di form, lalu centang field yang ingin disembunyikan. Nama teknis hanya ditampilkan kecil untuk referensi."
			)}
		</div>`
	);
}

function load_form_fields(dialog) {
	const ref_doctype = dialog.get_value("ref_doctype");
	const $wrap = dialog.fields_dict.fields_html.$wrapper;

	if (!ref_doctype) {
		$wrap.find(".imogi-field-list").remove();
		return;
	}

	$wrap.empty();
	$wrap.append(`
		<div class="text-muted" style="padding: 12px 0;">
			${__("Memuat daftar field...")}
		</div>
	`);

	frappe.call({
		method: "imogi_finance.workspace_visibility.get_doctype_form_fields",
		args: { doctype: ref_doctype },
		callback(r) {
			$wrap.empty();
			const rows = r.message || [];
			if (!rows.length) {
				$wrap.append(`<p class="text-muted">${__("Tidak ada field yang bisa disembunyikan.")}</p>`);
				return;
			}

			let html = `
				<div class="imogi-field-picker-toolbar" style="display:flex;gap:10px;align-items:center;margin-bottom:10px;">
					<div style="flex:1">
						<input type="text" class="form-control imogi-field-search"
							placeholder="${__("Cari field, mis. Include Payment, Return, Posting Date...")}">
					</div>
					<span class="badge bg-blue imogi-selected-count">0 ${__("dipilih")}</span>
				</div>
				<div class="text-muted" style="margin-bottom:8px;">
					${__("Centang field yang ingin disembunyikan dari form {0}.", [frappe.utils.escape_html(ref_doctype)])}
				</div>
				<div class="imogi-field-list" style="max-height:360px;overflow:auto;border:1px solid var(--border-color);border-radius:8px;padding:6px;background:var(--fg-color);">
			`;
			rows.forEach((row) => {
				const fieldname = frappe.utils.escape_html(row.fieldname);
				const label = frappe.utils.escape_html(row.label || row.fieldname);
				const fieldtype = frappe.utils.escape_html(row.fieldtype || "");
				const searchable = frappe.utils.escape_html(
					`${row.label || ""} ${row.fieldname || ""} ${row.fieldtype || ""}`.toLowerCase()
				);
				html += `
					<div class="imogi-field-option" data-search="${searchable}"
						style="padding:8px 10px;border-radius:6px;margin-bottom:4px;">
						<label style="display:flex;gap:10px;align-items:flex-start;margin:0;cursor:pointer;">
							<input type="checkbox" class="imogi-hide-field"
								data-fieldname="${fieldname}" data-label="${label}">
							<span>
								<strong>${label}</strong>
								<br>
								<span class="text-muted small">${fieldname} - ${fieldtype}</span>
							</span>
						</label>
					</div>`;
			});
			html += "</div>";
			$wrap.append(html);

			const update_count = () => {
				const count = $wrap.find("input.imogi-hide-field:checked").length;
				$wrap.find(".imogi-selected-count").text(__("{0} dipilih", [count]));
			};

			$wrap.find(".imogi-field-search").on("input", function () {
				const query = ($(this).val() || "").toLowerCase().trim();
				$wrap.find(".imogi-field-option").each(function () {
					const haystack = $(this).data("search") || "";
					$(this).toggle(!query || haystack.includes(query));
				});
			});
			$wrap.find("input.imogi-hide-field").on("change", update_count);
		},
	});
}
