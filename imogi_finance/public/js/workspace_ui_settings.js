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

		frm.add_custom_button(__("Load Sections from Workspace"), () => {
			open_section_picker(frm);
		});

		frm.set_intro(
			__(
				"Setelah Save, tekan Ctrl+Shift+R di halaman workspace (mis. Selling) agar perubahan langsung terlihat."
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

		frm.add_custom_button(__("Example: Hide Selling → Point of Sale"), () => {
			frappe.call({
				method: "imogi_finance.workspace_visibility.add_hidden_section",
				args: {
					workspace: "Selling",
					section_label: "Point of Sale",
				},
				callback() {
					frm.reload_doc();
					frappe.show_alert({
						message: __("Point of Sale hidden on Selling workspace."),
						indicator: "green",
					});
				},
			});
		});
	},
});

function open_section_picker(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Hidden Section"),
		fields: [
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
					args: { workspace, section_label },
				})
			);

			Promise.all(calls).then(() => {
				dialog.hide();
				frm.reload_doc();
				frappe.show_alert({
					message: __("{0} section(s) added. Muat ulang halaman (Ctrl+Shift+R).", [
						selected.length,
					]),
					indicator: "green",
				});
			});
		},
	});

	dialog.show();
	dialog.fields_dict.sections_html.$wrapper.html(
		`<p class="text-muted">${__(
			"Pilih workspace lalu centang section yang ingin disembunyikan."
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
			html += "</div>";
			$wrap.append(html);
		},
	});
}
