// Adds "Load Template" / "Save as Template" controls to the standard
// Frappe "Export Data" dialog for Sales Invoice, so users can save a
// set of checked export fields (per-user) and re-apply them later
// instead of re-checking fields manually every time.

(function () {
	if (frappe.__export_template_patch_applied) return;
	frappe.__export_template_patch_applied = true;

	const TARGET_DOCTYPE = "Sales Invoice";

	frappe.require("data_import_tools.bundle.js").then(patch_data_exporter);

	function patch_data_exporter() {
		if (!frappe.data_import || !frappe.data_import.DataExporter) return;

		const original_make_dialog = frappe.data_import.DataExporter.prototype.make_dialog;

		frappe.data_import.DataExporter.prototype.make_dialog = function () {
			original_make_dialog.call(this);
			if (this.doctype === TARGET_DOCTYPE) {
				setup_export_template_controls(this);
			}
		};
	}

	function get_multicheck_fieldnames(exporter) {
		return exporter.dialog.fields
			.filter((df) => df.fieldtype === "MultiCheck")
			.map((df) => df.fieldname);
	}

	function get_selected_field_map(exporter) {
		let map = {};
		get_multicheck_fieldnames(exporter).forEach((fieldname) => {
			map[fieldname] = exporter.dialog.get_field(fieldname).get_value();
		});
		return map;
	}

	function apply_field_map(exporter, field_map) {
		exporter.unselect_all();
		get_multicheck_fieldnames(exporter).forEach((fieldname) => {
			let values = field_map[fieldname] || [];
			if (!values.length) return;
			let field = exporter.dialog.get_field(fieldname);
			values.forEach((value) => {
				field.$wrapper
					.find(`:checkbox[data-unit="${frappe.utils.escape_html(value)}"]`)
					.prop("checked", true)
					.trigger("change");
			});
		});
	}

	function setup_export_template_controls(exporter) {
		let $host = $(`
			<div class="mb-3 export-template-controls">
				<div class="d-flex align-items-center flex-wrap" style="gap: 6px;">
					<select class="form-control" style="max-width: 220px; display: inline-block;">
						<option value="">${__("Load Template...")}</option>
					</select>
					<button class="btn btn-default btn-xs" data-action="load_template">
						${__("Load")}
					</button>
					<button class="btn btn-default btn-xs" data-action="save_template">
						${__("Save as Template")}
					</button>
					<button class="btn btn-default btn-xs text-danger" data-action="delete_template" style="display:none;">
						${__("Delete")}
					</button>
				</div>
			</div>
		`);

		exporter.dialog.get_field("select_all_buttons").$wrapper.before($host);

		let $select = $host.find("select");
		let $delete_btn = $host.find('[data-action="delete_template"]');

		function refresh_options(select_name) {
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: "Export Template",
					filters: { reference_doctype: exporter.doctype },
					fields: ["name", "template_name"],
					order_by: "template_name asc",
					limit_page_length: 0,
				},
			}).then((r) => {
				let templates = r.message || [];
				$select.find("option:not(:first)").remove();
				templates.forEach((t) => {
					$select.append(
						`<option value="${frappe.utils.escape_html(t.name)}">${frappe.utils.escape_html(
							t.template_name
						)}</option>`
					);
				});
				if (select_name) $select.val(select_name);
				$delete_btn.toggle(!!$select.val());
			});
		}

		$select.on("change", () => {
			$delete_btn.toggle(!!$select.val());
		});

		$host.find('[data-action="load_template"]').on("click", () => {
			let template_name = $select.val();
			if (!template_name) {
				frappe.msgprint(__("Please select a template to load"));
				return;
			}
			frappe.db.get_doc("Export Template", template_name).then((doc) => {
				let field_map = {};
				try {
					field_map = JSON.parse(doc.fields_json || "{}");
				} catch (e) {
					field_map = {};
				}
				apply_field_map(exporter, field_map);
				exporter.update_primary_action();
			});
		});

		$host.find('[data-action="save_template"]').on("click", () => {
			let field_map = get_selected_field_map(exporter);
			let has_any = Object.values(field_map).some((v) => v && v.length);
			if (!has_any) {
				frappe.msgprint(__("Please select at least one field before saving a template"));
				return;
			}
			frappe.prompt(
				[
					{
						fieldtype: "Data",
						fieldname: "template_name",
						label: __("Template Name"),
						reqd: 1,
					},
				],
				(values) => {
					frappe.call({
						method: "frappe.client.insert",
						args: {
							doc: {
								doctype: "Export Template",
								template_name: values.template_name,
								reference_doctype: exporter.doctype,
								fields_json: JSON.stringify(field_map),
							},
						},
					}).then((r) => {
						frappe.show_alert({ message: __("Template saved"), indicator: "green" });
						refresh_options(r.message && r.message.name);
					});
				},
				__("Save as Template"),
				__("Save")
			);
		});

		$host.find('[data-action="delete_template"]').on("click", () => {
			let template_name = $select.val();
			if (!template_name) return;
			frappe.confirm(__("Delete this template?"), () => {
				frappe.call({
					method: "frappe.client.delete",
					args: { doctype: "Export Template", name: template_name },
				}).then(() => {
					frappe.show_alert({ message: __("Template deleted"), indicator: "green" });
					refresh_options();
				});
			});
		});

		refresh_options();
	}
})();
