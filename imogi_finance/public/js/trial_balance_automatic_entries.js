// Adds an "Automatic Entries" button to the Trial Balance report's Actions
// menu, opening a dialog to reclass a balance from one account to another
// (creates & submits a Journal Entry: Debit destination, Credit source).
//
// Any two accounts can be picked (no type restriction) — whether debiting
// one and crediting the other increases or decreases each of them depends
// on that account's own normal balance side, so the dialog shows a live
// preview of that effect for both accounts instead of guessing what the
// user meant.
//
// Trial Balance is a standard ERPNext report, so instead of editing core
// files we patch QueryReport.prototype.add_card_button_to_toolbar — the same
// place Frappe itself adds the "Create Card" button — which only runs once
// per report load, right after the Actions toolbar is (re)built.
(function () {
	const REPORT_NAME = "Trial Balance";

	// Asset/Expense accounts normally sit in Debit; Liability/Equity/Income
	// normally sit in Credit. Debiting or crediting an account moves its
	// balance up or down depending on which side is its normal side.
	const NORMAL_DEBIT_ROOT_TYPES = new Set(["Asset", "Expense"]);

	function effect_label(root_type, side) {
		if (!root_type) return "";
		const normal_debit = NORMAL_DEBIT_ROOT_TYPES.has(root_type);
		const increases = (side === "debit") === normal_debit;
		return increases ? __("increases") : __("decreases");
	}

	function get_filter_value(report, fieldname) {
		try {
			return report.get_filter_value(fieldname, false);
		} catch (e) {
			return null;
		}
	}

	function open_automatic_entries_dialog(report) {
		const company = get_filter_value(report, "company") || frappe.defaults.get_default("company");
		const from_date = get_filter_value(report, "from_date") || frappe.datetime.year_start();
		const to_date = get_filter_value(report, "to_date") || frappe.datetime.get_today();
		const cost_center = get_filter_value(report, "cost_center");

		// Tracked purely to render the live effect preview below — no longer
		// used to restrict which accounts can be picked.
		let from_account_root_type = null;
		let to_account_root_type = null;

		const dialog = new frappe.ui.Dialog({
			title: __("Automatic Entries — Account Reclass"),
			fields: [
				{
					fieldname: "company",
					label: __("Company"),
					fieldtype: "Link",
					options: "Company",
					default: company,
					reqd: 1,
				},
				{
					fieldname: "posting_date",
					label: __("Posting Date"),
					fieldtype: "Date",
					default: frappe.datetime.get_today(),
					reqd: 1,
				},
				{
					fieldname: "section_period",
					fieldtype: "Section Break",
					label: __("Period to Reclass"),
				},
				{
					fieldname: "from_date",
					label: __("From Date"),
					fieldtype: "Date",
					default: from_date,
					reqd: 1,
				},
				{
					fieldname: "col_break_period",
					fieldtype: "Column Break",
				},
				{
					fieldname: "to_date",
					label: __("To Date"),
					fieldtype: "Date",
					default: to_date,
					reqd: 1,
				},
				{
					fieldname: "section_accounts",
					fieldtype: "Section Break",
					label: __("Reclass"),
				},
				{
					fieldname: "from_account",
					label: __("From Account (source)"),
					fieldtype: "Link",
					options: "Account",
					reqd: 1,
					get_query: () => ({
						filters: { company: dialog.get_value("company"), is_group: 0 },
					}),
				},
				{
					fieldname: "col_break_accounts",
					fieldtype: "Column Break",
				},
				{
					fieldname: "to_account",
					label: __("To Account (destination)"),
					fieldtype: "Link",
					options: "Account",
					reqd: 1,
					get_query: () => ({
						filters: { company: dialog.get_value("company"), is_group: 0 },
					}),
				},
				{
					fieldname: "effect_html",
					fieldtype: "HTML",
				},
				{
					fieldname: "cost_center",
					label: __("Cost Center"),
					fieldtype: "Link",
					options: "Cost Center",
					default: cost_center,
					get_query: () => ({
						filters: { company: dialog.get_value("company") },
					}),
				},
				{
					fieldname: "col_break_amount",
					fieldtype: "Column Break",
				},
				{
					fieldname: "amount",
					label: __("Amount"),
					fieldtype: "Currency",
					reqd: 1,
					description: __(
						"Auto-filled from the source account's balance for the period above — edit if needed."
					),
				},
				{
					fieldname: "section_remark",
					fieldtype: "Section Break",
				},
				{
					fieldname: "remark",
					label: __("Remark"),
					fieldtype: "Small Text",
				},
				{
					fieldname: "note_html",
					fieldtype: "HTML",
					options: `<div class="text-muted small">${__(
						"The system will Debit the destination account and Credit the source account for the amount above, then create & submit a Journal Entry. Check the effect preview above the accounts — whether that increases or decreases each balance depends on that account's own type."
					)}</div>`,
				},
			],
			primary_action_label: __("Create Journal Entry"),
			primary_action: (values) => {
				frappe.call({
					method: "imogi_finance.account_reclass.automatic_entries.create_reclass_entry",
					args: {
						company: values.company,
						from_account: values.from_account,
						to_account: values.to_account,
						amount: values.amount,
						posting_date: values.posting_date,
						cost_center: values.cost_center,
						remark: values.remark,
					},
					freeze: true,
					freeze_message: __("Creating Journal Entry..."),
					callback: (r) => {
						if (!r.exc && r.message) {
							dialog.hide();
							frappe.show_alert(
								{
									message: __("Journal Entry {0} created.", [
										`<a href="/app/journal-entry/${r.message}">${r.message}</a>`,
									]),
									indicator: "green",
								},
								7
							);
							report.refresh && report.refresh();
						}
					},
				});
			},
		});

		dialog.fields_dict.from_account.df.onchange = on_from_account_change;
		dialog.fields_dict.to_account.df.onchange = on_to_account_change;
		dialog.fields_dict.from_date.df.onchange = fetch_balance;
		dialog.fields_dict.to_date.df.onchange = fetch_balance;
		dialog.fields_dict.cost_center.df.onchange = fetch_balance;
		dialog.refresh();

		async function get_root_type(account) {
			if (!account) return null;
			const r = await frappe.db.get_value("Account", account, "root_type");
			return (r && r.message && r.message.root_type) || null;
		}

		function render_effect_preview() {
			const $el = dialog.fields_dict.effect_html.$wrapper;
			const from_account = dialog.get_value("from_account");
			const to_account = dialog.get_value("to_account");
			const rows = [];

			if (from_account && from_account_root_type) {
				rows.push(
					`<div>${__("From")}: <strong>${frappe.utils.escape_html(from_account)}</strong> ` +
						`(${__(from_account_root_type)}) → ${__("Credited")}, ${__("balance")} ` +
						`<strong>${effect_label(from_account_root_type, "credit")}</strong></div>`
				);
			}
			if (to_account && to_account_root_type) {
				rows.push(
					`<div>${__("To")}: <strong>${frappe.utils.escape_html(to_account)}</strong> ` +
						`(${__(to_account_root_type)}) → ${__("Debited")}, ${__("balance")} ` +
						`<strong>${effect_label(to_account_root_type, "debit")}</strong></div>`
				);
			}

			$el.html(
				rows.length
					? `<div class="text-muted small" style="line-height:1.7">${rows.join("")}</div>`
					: ""
			);
		}

		async function on_from_account_change() {
			from_account_root_type = await get_root_type(dialog.get_value("from_account"));
			render_effect_preview();
			fetch_balance();
		}

		async function on_to_account_change() {
			to_account_root_type = await get_root_type(dialog.get_value("to_account"));
			render_effect_preview();
		}

		function fetch_balance() {
			const args = {
				company: dialog.get_value("company"),
				account: dialog.get_value("from_account"),
				from_date: dialog.get_value("from_date"),
				to_date: dialog.get_value("to_date"),
				cost_center: dialog.get_value("cost_center"),
			};
			if (!(args.company && args.account && args.from_date && args.to_date)) return;

			frappe.call({
				method: "imogi_finance.account_reclass.automatic_entries.get_account_balance",
				args,
				callback: (r) => {
					if (r.message !== undefined) {
						dialog.set_value("amount", Math.abs(r.message));
					}
				},
			});
		}

		dialog.show();
	}

	frappe.after_ajax(function () {
		if (!frappe.views || !frappe.views.QueryReport) return;

		const original = frappe.views.QueryReport.prototype.add_card_button_to_toolbar;
		frappe.views.QueryReport.prototype.add_card_button_to_toolbar = function (...args) {
			original && original.apply(this, args);
			if (this.report_name === REPORT_NAME) {
				this.page.add_inner_button(
					__("Automatic Entries"),
					() => open_automatic_entries_dialog(this),
					__("Actions")
				);
			}
		};
	});
})();
