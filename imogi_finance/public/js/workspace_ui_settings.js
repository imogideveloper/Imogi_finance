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

		frm.add_custom_button(__("Add Hidden Workspace"), () => {
			open_workspace_picker(frm);
		});

		frm.add_custom_button(__("Load Sections from Workspace"), () => {
			open_section_picker(frm);
		});

		frm.add_custom_button(__("Add Hidden Form Field"), () => {
			open_form_field_picker(frm);
		});

		frm.set_intro(
			__(
				"Sembunyikan workspace (Hidden Workspaces), section di workspace (Hidden Sections), atau field di form DocType (Hidden Form Fields). Kolom User kosong = semua user. Setelah Save, gunakan Save & Reload Desk."
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

function open_workspace_picker(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Hidden Workspace"),
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
		primary_action_label: __("Add Selected"),
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

			let html = `<p class="text-muted">${__(
				"Pilih user (opsional), lalu centang workspace yang ingin disembunyikan dari sidebar."
			)}</p>`;
			html += '<div class="imogi-workspace-list" style="max-height:320px;overflow:auto;">';
			rows.forEach((row) => {
				const name = frappe.utils.escape_html(row.name);
				const title = frappe.utils.escape_html(row.title || row.name);
				const module = frappe.utils.escape_html(row.module || "");
				html += `
					<div class="checkbox" style="margin:6px 0;">
						<label>
							<input type="checkbox" class="imogi-hide-workspace" data-name="${name}">
							<strong>${title}</strong>
							<span class="text-muted"> — ${module}</span>
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
		title: __("Add Hidden Section"),
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
		primary_action_label: __("Add Selected"),
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
					<div class="checkbox" style="margin:6px 0;">
						<label>
							<input type="checkbox" class="imogi-hide-section" data-label="${safe}">
							<strong>${safe}</strong>
							<span class="text-muted"> (${frappe.utils.escape_html(row.section_type)})</span>
						</label>
					</div>`;
			});
			html += "</motion>";
			$wrap.append(html);
		},
	});
}

function open_form_field_picker(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Hidden Form Field"),
		fields: [
			{
				fieldname: "user",
				fieldtype: "Link",
				label: __("User (opsional)"),
				options: "User",
				description: __("Kosongkan = semua user."),
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
		primary_action_label: __("Add Selected"),
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
	dialog.fields_dict.fields_html.$wrapper.html(
		`<p class="text-muted">${__(
			"Pilih DocType, lalu centang field yang ingin disembunyikan dari form."
		)}</p>`
	);
}

function load_form_fields(dialog) {
	const ref_doctype = dialog.get_value("ref_doctype");
	const $wrap = dialog.fields_dict.fields_html.$wrapper;

	if (!ref_doctype) {
		$wrap.find(".imogi-field-list").remove();
		return;
	}

	$wrap.find(".imogi-field-list").remove();
	$wrap.append(`<p class="text-muted">${__("Loading fields...")}</p>`);

	frappe.call({
		method: "imogi_finance.workspace_visibility.get_doctype_form_fields",
		args: { doctype: ref_doctype },
		callback(r) {
			$wrap.find("p.text-muted").remove();
			const rows = r.message || [];
			if (!rows.length) {
				$wrap.append(`<p class="text-muted">${__("No fields found.")}</p>`);
				return;
			}

			let html = '<div class="imogi-field-list" style="max-height:320px;overflow:auto;">';
			rows.forEach((row) => {
				const fieldname = frappe.utils.escape_html(row.fieldname);
				const label = frappe.utils.escape_html(row.label || row.fieldname);
				const fieldtype = frappe.utils.escape_html(row.fieldtype || "");
				html += `
					<div class="checkbox" style="margin:6px 0;">
						<label>
							<input type="checkbox" class="imogi-hide-field"
								data-fieldname="${fieldname}" data-label="${label}">
							<strong>${label}</strong>
							<span class="text-muted"> (${fieldname}, ${fieldtype})</span>
						</label>
					</div>`;
			});
			html += "</div>";
			$wrap.append(html);
		},
	});
}
