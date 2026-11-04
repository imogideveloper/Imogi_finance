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

	// garage_desk.css's own stylesheet fix (trial_balance_automatic_entries.
	// css, scoped under .ier-automatic-entries-dialog) still lost to garage
	// even after being made more specific - some garage script (not
	// identified, not worth chasing further) evidently forces these same
	// properties via inline style.setProperty(..., 'important'), and an
	// inline !important declaration always wins over a stylesheet rule's
	// !important regardless of selector specificity, full stop. Forcing
	// the SAME properties the same way here, after garage's own code has
	// had its turn, is the only way to reliably win that fight - this is
	// the exact technique garage's own files (bank_reconciliation_tool.js,
	// bca_bank_statement_import.js, purchase_invoice_list.js, ...) already
	// rely on everywhere else in this app for the identical reason.
	function force_dialog_layout(dialog) {
		const root = dialog.$wrapper && dialog.$wrapper[0];
		if (!root) return;

		root.querySelectorAll(".frappe-control").forEach((control) => {
			const form_group = control.querySelector(":scope > .form-group");
			if (!form_group) return;

			form_group.style.setProperty("display", "block", "important");
			form_group.style.setProperty("margin-bottom", "10px", "important");

			const clearfix = form_group.querySelector(":scope > .clearfix");
			if (clearfix) {
				clearfix.style.setProperty("flex", "none", "important");
				clearfix.style.setProperty("min-width", "0", "important");
				clearfix.style.setProperty("width", "100%", "important");
				clearfix.style.setProperty("margin-bottom", "4px", "important");
			}

			const label = form_group.querySelector(":scope > .clearfix > .control-label");
			if (label) {
				label.style.setProperty("white-space", "normal", "important");
			}

			const input_wrapper = form_group.querySelector(":scope > .control-input-wrapper");
			if (input_wrapper) {
				input_wrapper.style.setProperty("width", "100%", "important");
				input_wrapper.style.setProperty("flex", "none", "important");
			}

			control.querySelectorAll('input:not([type="checkbox"]), select, textarea').forEach((el) => {
				el.style.setProperty("width", "100%", "important");
				el.style.setProperty("box-sizing", "border-box", "important");
			});
		});
	}

	function open_automatic_entries_dialog(report) {
		const company = get_filter_value(report, "company") || frappe.defaults.get_default("company");
		const from_date = get_filter_value(report, "from_date") || frappe.datetime.year_start();
		const to_date = get_filter_value(report, "to_date") || frappe.datetime.get_today();
		const cost_center = get_filter_value(report, "cost_center");

		// root_type is tracked purely to render the live effect preview
		// below. account_type additionally decides whether Party Type/Party
		// need to show at all (PARTY_ACCOUNT_TYPES) - neither restricts
		// which accounts can be picked.
		let from_account_root_type = null;
		let to_account_root_type = null;
		let from_account_type = null;
		let to_account_type = null;
		const PARTY_ACCOUNT_TYPES = new Set(["Receivable", "Payable"]);

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
				// Hidden tracker, not shown to the user - toggled in
				// on_from_account_change()/on_to_account_change() below
				// whenever either side turns out to be a Receivable/Payable
				// account, and used only to show/hide section_party further
				// down. Kept at the top level (outside every section) so it
				// never counts toward any section's own column-balancing -
				// a hidden:1 field placed INSIDE "Reclass" below previously
				// shifted how Frappe paired that section's real fields into
				// rows, moving Amount up next to From/To Account instead of
				// staying paired with Cost Center as it originally was.
				{
					fieldname: "party_required",
					fieldtype: "Check",
					hidden: 1,
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
				// Own section, not folded into "Reclass" above - core
				// ERPNext requires a Party on any Journal Entry accounting
				// row that uses a Receivable/Payable account, and this
				// dialog never collected one at all until it hit "Party
				// Type and Party is required" on an actual Payable account.
				// Hidden via the whole section's own depends_on (not just
				// hiding the fields inside it) so it takes no space at all
				// - not even an empty header - when neither account needs
				// one.
				{
					fieldname: "section_party",
					fieldtype: "Section Break",
					label: __("Party"),
					depends_on: "eval:doc.party_required",
				},
				{
					fieldname: "party_type",
					label: __("Party Type"),
					fieldtype: "Link",
					options: "DocType",
					mandatory_depends_on: "eval:doc.party_required",
					get_query: () => ({
						filters: { name: ["in", Object.keys(frappe.boot.party_account_types || {})] },
					}),
				},
				{
					fieldname: "col_break_party",
					fieldtype: "Column Break",
				},
				{
					fieldname: "party",
					label: __("Party"),
					fieldtype: "Dynamic Link",
					options: "party_type",
					mandatory_depends_on: "eval:doc.party_required",
				},
				{
					fieldname: "party_note_html",
					fieldtype: "HTML",
					options: `<div class="text-muted small">${__(
						"Required: one of the accounts above is a Receivable/Payable account, which ERPNext always ties to a specific Party."
					)}</div>`,
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
						party_type: values.party_type,
						party: values.party,
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

		async function get_account_meta(account) {
			if (!account) return { root_type: null, account_type: null };
			const r = await frappe.db.get_value("Account", account, ["root_type", "account_type"]);
			return (r && r.message) || { root_type: null, account_type: null };
		}

		function update_party_required() {
			const required = PARTY_ACCOUNT_TYPES.has(from_account_type) || PARTY_ACCOUNT_TYPES.has(to_account_type);
			dialog.set_value("party_required", required ? 1 : 0);
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
			const meta = await get_account_meta(dialog.get_value("from_account"));
			from_account_root_type = meta.root_type;
			from_account_type = meta.account_type;
			render_effect_preview();
			update_party_required();
			fetch_balance();
		}

		async function on_to_account_change() {
			const meta = await get_account_meta(dialog.get_value("to_account"));
			to_account_root_type = meta.root_type;
			to_account_type = meta.account_type;
			render_effect_preview();
			update_party_required();
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

		dialog.$wrapper.addClass("ier-automatic-entries-dialog");
		force_dialog_layout(dialog);

		// Re-applies whenever the dialog's own DOM changes (e.g. set_value()
		// inside fetch_balance()/on_from_account_change() above can touch a
		// field's rendered value) - same MutationObserver + re-apply idiom
		// already used throughout this app's other dialogs/tables for the
		// identical "garage keeps re-asserting its own style" problem.
		// childList/subtree only, deliberately NOT attributes - this
		// function's own style.setProperty() calls are themselves attribute
		// mutations, and watching attributes too would make every call
		// retrigger the observer synchronously (a MutationObserver fires
		// for every attribute write regardless of whether the value
		// actually changed), spinning forever instead of settling.
		const observer = new MutationObserver(() => force_dialog_layout(dialog));
		observer.observe(dialog.$wrapper[0], { childList: true, subtree: true });
		dialog.$wrapper.on("hidden.bs.modal", () => observer.disconnect());

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
