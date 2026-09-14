// Restyles the Trial Balance report's filter bar to match production:
//   - Cost Center / Project / Finance Book / Currency are tucked behind a
//     collapsible "Advanced Filters (4)" link instead of cluttering the
//     main row.
//   - The report's Check filters (With Period Closing Entry, Show zero
//     values, etc.) render as toggle switches instead of plain checkboxes.
//
// Trial Balance is a standard ERPNext report, so instead of editing core
// files we patch QueryReport.prototype.setup_filters, the same approach
// trial_balance_automatic_entries.js uses for its "Automatic Entries" button.
// setup_filters() rebuilds the whole filter row (and wipes any DOM we add
// to it) on every report load/refresh, so we re-apply on each call.
(function () {
	const REPORT_NAME = "Trial Balance";
	const ADVANCED_FILTERS = ["cost_center", "project", "finance_book", "presentation_currency"];
	const STYLE_ID = "imogi-trial-balance-filter-style";

	function inject_style() {
		if (document.getElementById(STYLE_ID)) return;
		const style = document.createElement("style");
		style.id = STYLE_ID;
		style.textContent = `
			.imogi-toggle-switch .checkbox label {
				display: flex;
				align-items: center;
				gap: 8px;
				cursor: pointer;
				margin-bottom: 0;
			}
			.imogi-toggle-switch .checkbox .input-area {
				position: relative;
				display: inline-block;
				width: 34px;
				height: 18px;
				border-radius: 999px;
				background: var(--gray-300, #d1d8dd);
				flex: none;
				transition: background-color .15s ease-in-out;
			}
			.imogi-toggle-switch .checkbox .input-area::after {
				content: "";
				position: absolute;
				top: 2px;
				left: 2px;
				width: 14px;
				height: 14px;
				border-radius: 50%;
				background: #fff;
				box-shadow: 0 1px 2px rgba(0, 0, 0, .35);
				transition: transform .15s ease-in-out;
			}
			.imogi-toggle-switch .checkbox .input-area:has(input:checked) {
				background: var(--primary, #2490ef);
			}
			.imogi-toggle-switch .checkbox .input-area:has(input:checked)::after {
				transform: translateX(16px);
			}
			.imogi-toggle-switch .checkbox .input-area input[type="checkbox"] {
				position: absolute;
				inset: 0;
				opacity: 0;
				margin: 0;
				cursor: pointer;
			}
			.imogi-advanced-filters-toggle {
				flex: 0 0 100%;
				max-width: 100%;
				padding: 0 15px;
				margin-bottom: 6px;
			}
			.imogi-advanced-filters-toggle a {
				font-size: 12px;
				color: var(--text-muted, #8d99a6);
				text-decoration: none;
			}
			.imogi-advanced-filters-toggle a:hover {
				color: var(--primary, #2490ef);
			}
			.imogi-advanced-filters-toggle .imogi-caret {
				display: inline-block;
				margin-right: 4px;
				transition: transform .15s ease-in-out;
			}
			.imogi-advanced-filters-toggle.expanded .imogi-caret {
				transform: rotate(90deg);
			}
			.imogi-advanced-filters-group {
				flex: 0 0 100%;
				max-width: 100%;
				width: 100%;
				margin: 0 0 8px;
			}
		`;
		document.head.appendChild(style);
	}

	function apply_toggle_switch_style(report) {
		(report.filters || []).forEach((filter) => {
			if (filter.df && filter.df.fieldtype === "Check" && filter.$wrapper) {
				filter.$wrapper.addClass("imogi-toggle-switch");
			}
		});
	}

	function group_advanced_filters(report) {
		const fields = ADVANCED_FILTERS.map((fieldname) => report.get_filter(fieldname, false)).filter(
			Boolean
		);
		if (!fields.length) return;

		const $insertion_point = fields[0].$wrapper;
		const $toggle = $(`
			<div class="imogi-advanced-filters-toggle">
				<a href="#"><span class="imogi-caret">&#9656;</span>${__("Advanced Filters")} (${
			fields.length
		})</a>
			</div>
		`);
		const $group = $('<div class="imogi-advanced-filters-group row"></div>').hide();

		$insertion_point.before($toggle);
		$toggle.after($group);
		fields.forEach((f) => $group.append(f.$wrapper));

		$toggle.on("click", "a", function (e) {
			e.preventDefault();
			$group.slideToggle(150);
			$toggle.toggleClass("expanded");
		});
	}

	// Use the full page width (like frappe's Kanban view does via
	// page.container.addClass("full-width")) instead of the desk's default
	// centered, max-width container — the report table has enough columns
	// to need the room, and this only affects the Trial Balance page.
	function use_full_page_width(report) {
		report.page.container.addClass("full-width");
	}

	// The datatable's default "fixed" layout sizes every column to its
	// content and leaves the leftover width as blank space when the page is
	// wider than the sum of columns. "fluid" spreads that leftover width
	// back across the columns so the table always fills the container.
	function use_fluid_datatable_layout(report) {
		if (report.report_settings.__imogi_fluid_layout_applied) return;
		report.report_settings.__imogi_fluid_layout_applied = true;

		const original_get_datatable_options = report.report_settings.get_datatable_options;
		report.report_settings.get_datatable_options = function (options) {
			options = original_get_datatable_options
				? original_get_datatable_options(options)
				: options;
			options.layout = "fluid";
			return options;
		};
	}

	frappe.after_ajax(function () {
		if (!frappe.views || !frappe.views.QueryReport) return;

		const original = frappe.views.QueryReport.prototype.setup_filters;
		frappe.views.QueryReport.prototype.setup_filters = function (...args) {
			const result = original.apply(this, args);
			if (this.report_name === REPORT_NAME) {
				inject_style();
				apply_toggle_switch_style(this);
				group_advanced_filters(this);
				use_full_page_width(this);
				use_fluid_datatable_layout(this);
			}
			return result;
		};
	});
})();
