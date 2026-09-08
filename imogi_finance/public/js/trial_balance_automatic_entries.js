// Adds an "Automatic Entries" button to the Trial Balance report's Actions
// menu, opening a dialog to reclass a balance from one account to another
// (creates & submits a Journal Entry: Debit destination, Credit source).
//
// Trial Balance is a standard ERPNext report, so instead of editing core
// files we patch QueryReport.prototype.add_card_button_to_toolbar — the same
// place Frappe itself adds the "Create Card" button — which only runs once
// per report load, right after the Actions toolbar is (re)built.
(function () {
	const REPORT_NAME = "Trial Balance";

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

		// A reclass is only a valid "move a balance" operation when both accounts
		// sit on the same normal-balance side (e.g. two Expense accounts). Mixing
		// e.g. Income and Expense would increase both instead of moving anything,
		// so To Account is restricted to the same root_type as From Account.
		let from_account_root_type = null;

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
						filters: Object.assign(
							{ company: dialog.get_value("company"), is_group: 0 },
							from_account_root_type ? { root_type: from_account_root_type } : {}
						),
					}),
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
						"The system will Debit the destination account and Credit the source account for the amount above, then create & submit a Journal Entry. Both accounts must be the same type (e.g. two Expense accounts) — otherwise this would increase both balances instead of moving one to the other."
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
		dialog.fields_dict.from_date.df.onchange = fetch_balance;
		dialog.fields_dict.to_date.df.onchange = fetch_balance;
		dialog.fields_dict.cost_center.df.onchange = fetch_balance;
		dialog.refresh();

		async function on_from_account_change() {
			const from_account = dialog.get_value("from_account");
			from_account_root_type = null;

			if (from_account) {
				const r = await frappe.db.get_value("Account", from_account, "root_type");
				from_account_root_type = (r && r.message && r.message.root_type) || null;
			}

			dialog.fields_dict.to_account.df.description = from_account_root_type
				? __("Only showing {0} accounts — same type as From Account.", [__(from_account_root_type)])
				: "";
			dialog.fields_dict.to_account.refresh();

			// If the previously picked To Account no longer matches, clear it
			// instead of silently leaving an invalid pair selected.
			const to_account = dialog.get_value("to_account");
			if (to_account && from_account_root_type) {
				const r2 = await frappe.db.get_value("Account", to_account, "root_type");
				const to_root_type = r2 && r2.message && r2.message.root_type;
				if (to_root_type && to_root_type !== from_account_root_type) {
					dialog.set_value("to_account", "");
				}
			}

			fetch_balance();
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
