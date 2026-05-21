// Sales Invoice list — toolbar (filter status, group by period/status)
// Load after sales_invoice_list.js

window.init_sales_invoice_list_toolbar = function(listview) {
	if (!listview || listview.doctype !== "Sales Invoice") return;

	window.__imogi_si_toolbar_active = true;

	const STORAGE_KEY_GROUP = "imogi_si_list_status_group_on";
	let selected_status_filters = [];
	let selected_period = [];
	let status_group_on = true;
	try {
		const stored = localStorage.getItem(STORAGE_KEY_GROUP);
		if (stored === null) {
			localStorage.setItem(STORAGE_KEY_GROUP, "1");
		} else {
			status_group_on = stored === "1";
		}
	} catch (e) {
		status_group_on = true;
	}
	window.__imogi_si_status_group_on = status_group_on;
	let collapsed_groups = {};
	let apply_timer = null;
	let is_rendering = false;

	const DATE_FIELD = "posting_date";

	function persist_group_toggle() {
		window.__imogi_si_status_group_on = status_group_on;
		try {
			localStorage.setItem(STORAGE_KEY_GROUP, status_group_on ? "1" : "0");
		} catch (e) {
			/* ignore */
		}
	}

	function activeGroups() {
		const groups = selected_period.slice();
		if (status_group_on) groups.push("Status");
		return groups;
	}

	function siColClass(col) {
		if (!col) return "";
		if (col.type === "Subject") return "si-col-subject";
		if (col.type === "Status") return "si-col-status";
		if (col.df?.fieldname) return `si-col-${col.df.fieldname}`;
		return "";
	}

	function injectColClass(html, col) {
		const cls = siColClass(col);
		if (!cls || !html) return html;
		return html.replace(/class="([^"]*)"/, `class="$1 ${cls}"`);
	}

	function tagListColumnClasses() {
		if (!listview.$result || !listview.columns?.length) return;
		const cols = listview.columns;

		listview.$result.find(".list-row-head .list-header-subject > .list-row-col").each(function (i) {
			const cls = siColClass(cols[i]);
			if (cls) $(this).addClass(cls);
		});

		listview.$result
			.find(".list-row-container .level-left, .erg-group-header .level-left")
			.each(function () {
				$(this)
					.children(".list-row-col")
					.each(function (i) {
						const cls = siColClass(cols[i]);
						if (cls) $(this).addClass(cls);
					});
			});
	}

	function scheduleTagListColumnClasses() {
		requestAnimationFrame(() => {
			tagListColumnClasses();
			requestAnimationFrame(tagListColumnClasses);
		});
	}

	function patchSiListColumnLayout() {
		if (listview.__si_col_layout_patched) return;
		listview.__si_col_layout_patched = true;

		const origGetColumnHtml = listview.get_column_html.bind(listview);
		listview.get_column_html = function (col, doc) {
			return injectColClass(origGetColumnHtml(col, doc), col);
		};

		const origGetHeaderHtml = listview.get_header_html.bind(listview);
		listview.get_header_html = function () {
			const header = origGetHeaderHtml();
			if (!header || !this.columns) return header;
			let colIdx = 0;
			return header.replace(/<div class="list-row-col([^"]*)"/g, (match, rest) => {
				const col = this.columns[colIdx++];
				const cls = siColClass(col);
				return cls ? `<div class="list-row-col${rest} ${cls}"` : match;
			});
		};
	}

	if (!document.getElementById("si-list-toolbar-style")) {
		const style = document.createElement("style");
		style.id = "si-list-toolbar-style";
		style.textContent =
			".standard-filter-section.flex{display:flex!important;flex-wrap:wrap!important;align-items:flex-end!important;gap:8px!important}" +
			".standard-filter-section .frappe-control[data-fieldname='status']{display:none!important}" +
			"#si-list-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;flex:0 0 auto;order:99}" +
			".si-erg-wrap{position:relative;flex:0 0 auto!important;min-width:148px;max-width:175px;margin:0!important}" +
			".si-erg-select{width:100%;height:30px;padding:0 28px 0 10px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;font-size:13px;color:#1e293b;display:flex;align-items:center;cursor:pointer;box-sizing:border-box;box-shadow:0 1px 2px rgba(15,23,42,.04);transition:border-color .15s ease,box-shadow .15s ease}" +
			".si-erg-select:hover{border-color:#cbd5e1;box-shadow:0 2px 6px rgba(15,23,42,.06)}" +
			".si-erg-text{display:block;width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1}" +
			".si-erg-text.is-placeholder{color:#8d99a6}" +
			".si-erg-chevron{position:absolute;right:8px;top:50%;transform:translateY(-50%);pointer-events:none;color:#8d99a6;display:flex;align-items:center;z-index:2}" +
			".si-erg-clr{display:none;position:absolute;right:24px;top:50%;transform:translateY(-50%);cursor:pointer;color:#8d99a6;font-size:13px;z-index:3;line-height:1}" +
			".si-erg-dd{display:none;position:absolute;top:calc(100% + 6px);left:0;background:#fff;border:1px solid #d1d8dd;border-radius:8px;min-width:210px;z-index:10000;padding:8px 0;box-shadow:0 4px 16px rgba(0,0,0,.12)}" +
			".si-erg-dd-title{padding:0 12px 8px;font-size:11px;font-weight:600;color:#8d99a6;border-bottom:1px solid #f0f4f7;margin-bottom:6px}" +
			".si-erg-opt{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;font-size:13px;color:#36414c}" +
			".si-erg-opt:hover{background:#f5f7fa}" +
			".si-erg-opt input{margin:0}" +
			".si-erg-dd-actions{display:flex;justify-content:space-between;gap:8px;padding:8px 12px 0;border-top:1px solid #f0f4f7;margin-top:6px;flex-wrap:wrap}" +
			".si-erg-dd-btn{flex:1;border:1px solid #d1d8dd;background:#fff;color:#36414c;font-size:11px;border-radius:6px;padding:6px 8px;cursor:pointer}" +
			".si-erg-dd-btn.primary{background:#2490ef;color:#fff;border-color:#2490ef}" +
			".si-erg-dd-btn:hover{background:#f5f7fa}" +
			".si-erg-dd-btn.primary:hover{background:#1a7fd4}" +
			"#si-status-filter-dd{max-height:340px;overflow-y:auto}" +
			"#si-status-filter-dd .si-erg-dd-actions{position:sticky;bottom:0;background:#fff}" +
			"[data-page-route^='List/Sales Invoice'] .frappe-list .result{padding:6px 0 20px}" +
			"[data-page-route^='List/Sales Invoice'] .list-row-head{background:#f8fafc;border-bottom:2px solid #e2e8f0;border-radius:8px 8px 0 0;margin-bottom:2px}" +
			"[data-page-route^='List/Sales Invoice'] .list-row-head .list-header-subject{font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:#64748b}" +
			"[data-page-route^='List/Sales Invoice'] .list-row-container{border-bottom:1px solid #f1f5f9}" +
			"[data-page-route^='List/Sales Invoice'] .list-row-container:last-child{border-bottom:none}" +
			".erg-group-separator{margin:24px 0 10px;border:0;height:0}" +
			".erg-group-header.list-row{position:relative;padding:10px 0;margin:0 0 8px;background:linear-gradient(90deg,#f8fafc 0%,#f1f5f9 100%);border:1px solid #e2e8f0;border-radius:10px;cursor:pointer;user-select:none;box-shadow:0 1px 2px rgba(15,23,42,.04);transition:background .18s ease,box-shadow .18s ease,border-color .18s ease}" +
			".erg-group-header.list-row:hover{background:linear-gradient(90deg,#f1f5f9 0%,#e8edf3 100%);box-shadow:0 2px 8px rgba(15,23,42,.06)}" +
			".erg-group-header--status{border-left-width:4px;border-left-style:solid}" +
			".erg-group-header[data-si-group='Unpaid']{border-left-color:#f97316;background:linear-gradient(90deg,#fff7ed 0%,#f8fafc 55%)}" +
			".erg-group-header[data-si-group='Partly Paid']{border-left-color:#eab308;background:linear-gradient(90deg,#fffbeb 0%,#f8fafc 55%)}" +
			".erg-group-header[data-si-group='Paid']{border-left-color:#10b981;background:linear-gradient(90deg,#ecfdf5 0%,#f8fafc 55%)}" +
			".erg-group-header .level-left{align-items:center}" +
			".erg-group-subject-col .erg-group-left{display:flex;align-items:center;gap:12px;min-width:0}" +
			".erg-group-icon-wrap{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:50%;flex-shrink:0;background:#e2e8f0;color:#475569}" +
			".erg-group-icon-wrap .erg-group-title-icon,.erg-group-icon-wrap svg{width:16px!important;height:16px!important;margin:0!important;display:block}" +
			".erg-group-header[data-si-group='Unpaid'] .erg-group-icon-wrap{background:#ffedd5;color:#ea580c}" +
			".erg-group-header[data-si-group='Partly Paid'] .erg-group-icon-wrap{background:#fef3c7;color:#ca8a04}" +
			".erg-group-header[data-si-group='Paid'] .erg-group-icon-wrap{background:#d1fae5;color:#059669}" +
			".erg-group-text{display:flex;flex-direction:column;justify-content:center;gap:1px;min-width:0}" +
			".erg-group-checkbox-spacer{visibility:hidden;pointer-events:none}" +
			"[data-page-route^='List/Sales Invoice'] .list-row-container>.level.list-row{display:flex!important;align-items:center!important;width:100%!important}" +
			"[data-page-route^='List/Sales Invoice'] .list-row-container .level-left," +
			"[data-page-route^='List/Sales Invoice'] .list-row-head .level-left{flex:1 1 0!important;min-width:0!important;max-width:calc(100% - 7.5rem)!important;width:0!important;overflow:hidden!important;padding-right:.35rem!important;justify-content:flex-start!important}" +
			"[data-page-route^='List/Sales Invoice'] .list-row-container .level-right," +
			"[data-page-route^='List/Sales Invoice'] .list-row-head .level-right{flex:0 0 7.5rem!important;min-width:7.5rem!important;max-width:7.5rem!important;margin-left:auto!important;justify-content:flex-end!important}" +
			"[data-page-route^='List/Sales Invoice'] .erg-group-header .level-left{justify-content:flex-start!important;max-width:calc(100% - 7.5rem)!important}" +
			"[data-page-route^='List/Sales Invoice'] .level-left>.list-row-col:not(.list-subject):not(.tag-col){flex:0 0 auto!important;margin-right:6px!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-subject{flex:1 1 7rem!important;min-width:5rem!important;max-width:10rem!important;width:auto!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-subject .level-item.ellipsis{font-weight:600;color:#1e293b}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-status{flex:0 0 100px!important;width:100px!important;max-width:100px!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-status.list-row-col{display:flex!important;align-items:center!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill{display:inline-flex!important;align-items:center!important;gap:5px;max-width:100%;padding:3px 10px 3px 8px;border-radius:999px;font-size:11px;font-weight:600;line-height:1;height:22px;box-sizing:border-box}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill .si-status-icon{width:12px!important;height:12px!important;min-width:12px!important;min-height:12px!important;flex-shrink:0;display:block!important;margin:0!important;padding:0!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill .si-status-label{display:block;line-height:14px;height:14px;padding:0;margin:0}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill[data-si-status='Unpaid'] .si-status-icon{color:#ea580c}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill[data-si-status='Partly Paid'] .si-status-icon{color:#ca8a04}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill[data-si-status='Paid'] .si-status-icon{color:#059669}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill.orange{background:#fff4e8;color:#b45309;border:1px solid #fed7aa}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill.yellow{background:#fffbeb;color:#92680d;border:1px solid #fde68a}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill.green{background:#ecfdf3;color:#166534;border:1px solid #bbf7d0}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill.red{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill.blue{background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill.grey{background:#f3f4f6;color:#4b5563;border:1px solid #e5e7eb}" +
			"[data-page-route^='List/Sales Invoice'] .si-status-pill{box-shadow:0 1px 2px rgba(15,23,42,.04)}" +
			"[data-page-route^='List/Sales Invoice'] .list-row-container .list-row{border-radius:8px;transition:background-color .15s ease,box-shadow .15s ease}" +
			"[data-page-route^='List/Sales Invoice'] .list-row-container:hover .list-row{background:#f8fafc!important;box-shadow:inset 3px 0 0 #94a3b8}" +
			"[data-page-route^='List/Sales Invoice'] .si-posting-date{color:#475569;font-size:12px}" +
			"[data-page-route^='List/Sales Invoice'] .si-due-date{color:#64748b;font-size:12px}" +
			"[data-page-route^='List/Sales Invoice'] .si-cell-muted{color:#94a3b8}" +
			"[data-page-route^='List/Sales Invoice'] .si-grand-total{font-variant-numeric:tabular-nums;font-weight:600;color:#1e293b;letter-spacing:-.01em}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-posting_date{flex:0 0 100px!important;width:100px!important;max-width:100px!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-name{flex:0 0 128px!important;width:128px!important;max-width:128px!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-imogi_late_days{flex:0 0 108px!important;width:108px!important;max-width:108px!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-grand_total{flex:0 0 9.5rem!important;width:9.5rem!important;max-width:9.5rem!important;text-align:right!important;padding-right:2px!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-grand_total .level-item{width:100%!important;text-align:right!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-col-imogi_late_days.list-row-col{display:flex!important;align-items:center!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-late-days-cell{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;line-height:1}" +
			"[data-page-route^='List/Sales Invoice'] .si-late-days-cell.si-late-overdue{display:inline-flex!important;align-items:center!important;justify-content:flex-start;gap:5px;line-height:1;vertical-align:middle;background:#fef2f2;border:1px solid #fecaca;border-radius:999px;padding:3px 10px 3px 8px;font-size:11px;font-weight:600;color:#b91c1c;height:22px;box-sizing:border-box}" +
			"[data-page-route^='List/Sales Invoice'] .si-late-icon-wrap{display:flex;align-items:center;justify-content:center;flex:0 0 14px;width:14px;height:14px;line-height:0}" +
			"[data-page-route^='List/Sales Invoice'] .si-late-icon-wrap svg.si-late-icon{width:12px!important;height:12px!important;min-width:12px!important;min-height:12px!important;display:block!important;margin:0!important;padding:0!important;vertical-align:middle!important}" +
			"[data-page-route^='List/Sales Invoice'] .si-late-icon-blink{--icon-stroke:#dc2626;--icon-fill:#fecaca}" +
			"@keyframes si-late-icon-blink{0%,100%{opacity:1}50%{opacity:.25}}" +
			"[data-page-route^='List/Sales Invoice'] .si-late-icon-wrap.si-late-icon-blink-wrap{animation:si-late-icon-blink 1s ease-in-out infinite}" +
			"[data-page-route^='List/Sales Invoice'] .si-late-days-cell.si-late-overdue .si-late-text{display:block;line-height:14px;height:14px;padding:0;margin:0}" +
			"@media (prefers-reduced-motion:reduce){[data-page-route^='List/Sales Invoice'] .si-late-icon-wrap.si-late-icon-blink-wrap{animation:none;opacity:1}}" +
			".erg-group-header .erg-group-total-col{overflow:visible;text-overflow:clip;flex-shrink:0}" +
			".erg-group-header .erg-group-total-col .erg-group-total{display:block;width:100%;box-sizing:border-box;text-align:right;padding-right:12px;white-space:nowrap;font-weight:700;font-size:13px;font-variant-numeric:tabular-nums;color:#0f172a;letter-spacing:-.02em}" +
			".erg-group-header .erg-group-right{display:flex;align-items:center;gap:8px;flex-shrink:0;padding-right:8px}" +
			".erg-group-left{display:flex;align-items:center;gap:10px;min-width:0}" +
			".erg-group-toggle{width:22px;height:22px;line-height:22px;text-align:center;color:#64748b;font-size:11px;flex:0 0 auto;border-radius:6px;background:#fff;border:1px solid #e2e8f0}" +
			".erg-group-header:hover .erg-group-toggle{color:#334155;border-color:#cbd5e1}" +
			".erg-group-title{font-size:13px;font-weight:700;color:#0f172a;line-height:1.25;letter-spacing:-.01em}" +
			".erg-group-header[data-si-group='Unpaid'] .erg-group-title{color:#9a3412}" +
			".erg-group-header[data-si-group='Partly Paid'] .erg-group-title{color:#854d0e}" +
			".erg-group-header[data-si-group='Paid'] .erg-group-title{color:#065f46}" +
			".erg-group-sub{font-size:11px;color:#64748b;line-height:1.3;margin-top:0}" +
			".erg-group-right{display:flex;align-items:center;gap:8px;flex-shrink:0}" +
			".erg-group-count{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:#475569;background:#fff;border:1px solid #e2e8f0;border-radius:999px;padding:4px 10px;white-space:nowrap;box-shadow:0 1px 2px rgba(15,23,42,.04)}" +
			".erg-group-count .erg-count-icon{width:12px;height:12px;flex-shrink:0;color:#64748b}" +
			".erg-group-badge{flex:0 0 auto;font-size:10px;font-weight:600;color:#64748b;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:999px;padding:4px 9px}" +
			".erg-lvl-1{margin-top:10px}" +
			".erg-lvl-2{margin-left:18px;background:#fbfcfd}" +
			".erg-lvl-3{margin-left:36px;background:#fcfdfe}" +
			".erg-lvl-4{margin-left:54px;background:#fff}" +
			".erg-lvl-5{margin-left:72px;background:#fff}" +
			".erg-lvl-6{margin-left:90px;background:#fff}" +
			".erg-hidden-by-collapse{display:none!important}";
		document.head.appendChild(style);
	}

	function updateStatusFilterDisplay() {
		const $text = $("#si-status-filter-text");
		const $clr = $("#si-status-filter-clr");
		if (selected_status_filters.length) {
			const label =
				selected_status_filters.length <= 2
					? selected_status_filters.join(" + ")
					: `${selected_status_filters.length} status`;
			$text.text(label).removeClass("is-placeholder");
			$clr.show();
		} else {
			$text.text(__("Status")).addClass("is-placeholder");
			$clr.hide();
		}
	}

	function syncStatusFilterChecks() {
		$(".si-status-filter-check").each(function () {
			$(this).prop("checked", selected_status_filters.includes($(this).val()));
		});
	}

	function parseStatusFilterValue(value) {
		if (!value) return [];
		if (Array.isArray(value)) return value.slice();
		if (typeof value === "string") {
			try {
				const parsed = JSON.parse(value);
				if (Array.isArray(parsed)) return parsed;
			} catch (e) {
				/* comma-separated */
			}
			return value
				.split(",")
				.map((v) => v.trim())
				.filter(Boolean);
		}
		return [String(value)];
	}

	function syncFromListviewFilters() {
		const filters = listview.filter_area ? listview.filter_area.get() : [];
		let found = [];
		(filters || []).forEach((f) => {
			if (!f || f[1] !== "status") return;
			if (f[2] === "in") found = parseStatusFilterValue(f[3]);
			else if (f[2] === "=" && f[3]) found = [f[3]];
		});
		selected_status_filters = found;
		updateStatusFilterDisplay();
		syncStatusFilterChecks();
	}

	function clearStatusFilters() {
		const fl = listview.filter_area.filter_list;
		fl.filters.slice().forEach((f) => {
			if (f.field && f.field.df && f.field.df.fieldname === "status") {
				f.remove();
			}
		});
		if (listview.page.fields_dict.status) {
			listview.page.fields_dict.status.set_value("");
		}
	}

	function applyStatusFilter() {
		const values = [];
		$(".si-status-filter-check:checked").each(function () {
			values.push($(this).val());
		});
		selected_status_filters = values;
		updateStatusFilterDisplay();
		$("#si-status-filter-dd").hide();

		clearStatusFilters();

		if (!values.length) {
			listview.filter_area.filter_list.update_filters();
			listview.refresh();
			return;
		}

		const fl = listview.filter_area.filter_list;
		const expanded = expandStatusesForListFilter(values);
		const add_promise = fl.add_filter(listview.doctype, "status", "in", expanded, true);

		Promise.resolve(add_promise).then(() => {
			const status_filter = fl.get_filter("status");
			if (status_filter && status_filter._filter_value_set) {
				return status_filter._filter_value_set;
			}
		}).then(() => {
			fl.update_filter_button();
			listview.refresh();
		});
	}

	function buildStatusFilterWidget() {
		const options = SI_STATUS_ORDER.map(
			(status) =>
				`<label class="si-erg-opt"><input type="checkbox" class="si-status-filter-check" value="${status}"><span>${__(status)}</span></label>`
		).join("");
		return $(
			`<div id="si-status-filter-wrap" class="si-erg-wrap">` +
				`<div class="si-erg-select" data-widget="status-filter"><span class="si-erg-text is-placeholder" id="si-status-filter-text">Status</span></div>` +
				`<div class="si-erg-chevron"><svg class="icon icon-xs" aria-hidden="true"><use href="#icon-select"></use></svg></div>` +
				`<span class="si-erg-clr" id="si-status-filter-clr">&times;</span>` +
				`<div class="si-erg-dd" id="si-status-filter-dd">` +
					`<div class="si-erg-dd-title">Pilih status (multi)</div>` +
					options +
					`<div class="si-erg-dd-actions">` +
						`<button type="button" class="si-erg-dd-btn" data-action="status-filter-all">All</button>` +
						`<button type="button" class="si-erg-dd-btn" data-action="status-filter-clear">Clear</button>` +
						`<button type="button" class="si-erg-dd-btn primary" data-action="status-filter-apply">Apply</button>` +
					`</div>` +
				`</div>` +
			`</div>`
		);
	}

	const MONTH_NAMES = [
		"Januari", "Februari", "Maret", "April", "Mei", "Juni",
		"Juli", "Agustus", "September", "Oktober", "November", "Desember",
	];

	function parseDate(value) {
		return value ? frappe.datetime.str_to_obj(value) : null;
	}

	function weekOfMonth(dt) {
		const first = new Date(dt.getFullYear(), dt.getMonth(), 1);
		return Math.ceil((dt.getDate() + first.getDay()) / 7);
	}

	function resolveStatus(doc) {
		if (!doc) return __("No Status");
		if (doc.docstatus === 2) return "Cancelled";
		if (doc.docstatus === 0 && (!doc.status || doc.status === "Draft")) return "Draft";
		return doc.status || __("No Status");
	}

	function statusRank(label) {
		const idx = SI_STATUS_ORDER.indexOf(label);
		return idx >= 0 ? idx : 999;
	}

	function groupValue(doc, mode) {
		if (mode === "Status") {
			const resolved = resolveStatus(doc);
			const key = statusGroupKey(resolved);
			return { key, label: key, badge: "Status" };
		}

		const dateValue = parseDate(doc ? doc[DATE_FIELD] : null);
		if (!dateValue) return { key: "NO_DATE", label: __("No Date"), badge: "Period" };

		const year = dateValue.getFullYear();
		const month = dateValue.getMonth();
		const day = dateValue.getDate();
		const quarter = Math.floor(month / 3) + 1;
		const week = weekOfMonth(dateValue);

		if (mode === "Year") return { key: String(year), label: String(year), badge: mode };
		if (mode === "Quarter") return { key: `${year}-Q${quarter}`, label: `Q${quarter} ${year}`, badge: mode };
		if (mode === "Month") {
			const key = `${year}-${String(month + 1).padStart(2, "0")}`;
			return { key, label: `${MONTH_NAMES[month]} ${year}`, badge: mode };
		}
		if (mode === "Week") {
			const key = `${year}-${String(month + 1).padStart(2, "0")}-W${week}`;
			return { key, label: `Minggu ${week} - ${MONTH_NAMES[month]} ${year}`, badge: mode };
		}
		if (mode === "Day") {
			const key = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
			return { key, label: `${String(day).padStart(2, "0")} ${MONTH_NAMES[month]} ${year}`, badge: mode };
		}
		return { key: "X", label: __("Unknown"), badge: mode };
	}

	function groupSubLabel(mode, chain, index) {
		if (index === 0) {
			return mode === "Status" ? __("Group by Status") : __("Group by Period");
		}
		return chain
			.slice(0, index)
			.map((part) => part.label)
			.join(" / ");
	}

	function escapeHtml(value) {
		return frappe.utils.escape_html(value == null ? "" : String(value));
	}

	function getRows() {
		if (!listview.$result) return $();
		return listview.$result.find(".list-row-container").filter(function () {
			return !!getDocName($(this));
		});
	}

	function getDocName($row) {
		return $row.attr("data-name") || $row.find("[data-name]").first().attr("data-name") || null;
	}

	function getDoc(name) {
		if (!Array.isArray(listview.data)) return null;
		return listview.data.find((row) => row.name === name) || null;
	}

	function removeArtifacts() {
		if (!listview.$result) return;
		listview.$result.find(".erg-group-header,.erg-group-separator").remove();
		listview.$result.find(".erg-hidden-by-collapse").removeClass("erg-hidden-by-collapse");
	}

	function makeSeparator() {
		return $('<div class="erg-group-separator">');
	}

	function getDocGrandTotal(doc) {
		if (!doc) return 0;
		const val = doc.grand_total != null ? doc.grand_total : doc.base_grand_total;
		return parseFloat(val) || 0;
	}

	function formatGroupTotal(amount) {
		let currency = frappe.defaults.get_default("currency");
		if (Array.isArray(listview.data)) {
			const row = listview.data.find((d) => d.currency);
			if (row) currency = row.currency;
		}
		return typeof format_currency === "function"
			? format_currency(amount, currency)
			: frappe.format(amount, { fieldtype: "Currency", options: "currency" });
	}

	function buildGroupHeaderColumns(group, sub, collapsed, totalAmount) {
		const leftBlock =
			`<div class="erg-group-left">` +
				`<div class="erg-group-toggle">${collapsed ? "&#9658;" : "&#9660;"}</div>` +
				`${siGroupIconWrapHtml(group.label)}` +
				`<div class="erg-group-text">` +
					`<div class="erg-group-title">${escapeHtml(group.label)}</div>` +
					`<div class="erg-group-sub">${escapeHtml(sub || "")}</div>` +
				`</div>` +
			`</div>`;

		if (!listview.columns || !listview.columns.length) {
			return leftBlock;
		}

		return listview.columns
			.map((col) => {
				if (col.type === "Subject") {
					return (
						`<div class="list-row-col list-subject level erg-group-subject-col si-col-subject">` +
							`<span class="level-item select-like erg-group-checkbox-spacer" aria-hidden="true"></span>` +
							`<span class="level-item ellipsis">${leftBlock}</span>` +
						`</div>`
					);
				}
				if (col.type === "Status") {
					return `<div class="list-row-col hidden-xs ellipsis si-col-status"></div>`;
				}
				if (col.df && col.df.fieldname === "posting_date") {
					return `<div class="list-row-col hidden-xs ellipsis si-col-posting_date"></div>`;
				}
				if (col.df && col.df.fieldname === "imogi_late_days") {
					return `<div class="list-row-col hidden-xs ellipsis si-col-imogi_late_days"></div>`;
				}
				if (col.df && col.df.fieldname === "grand_total") {
					const totalFormatted = formatGroupTotal(totalAmount || 0);
					return (
						`<div class="list-row-col hidden-xs text-right erg-group-total-col si-col-grand_total" title="${escapeHtml(totalFormatted)}">` +
							`<span class="erg-group-total">${escapeHtml(totalFormatted)}</span>` +
						`</div>`
					);
				}
				if (col.df && col.df.fieldname === "name") {
					return `<div class="list-row-col hidden-xs ellipsis si-col-name"></div>`;
				}
				return `<div class="list-row-col ellipsis hidden-xs"></div>`;
			})
			.join("");
	}

	function makeHeader(level, group, sub, chainKey, count, totalAmount) {
		const collapsed = !!collapsed_groups[chainKey];
		const colsHtml = buildGroupHeaderColumns(group, sub, collapsed, totalAmount);
		const siGroupAttr =
			group.mode === "Status" && group.label
				? ` data-si-group="${escapeHtml(group.label)}"`
				: "";
		const statusClass = group.mode === "Status" ? " erg-group-header--status" : "";
		const badgeHtml =
			group.mode !== "Status"
				? `<span class="erg-group-badge">${escapeHtml(group.badge || group.mode)}</span>`
				: "";
		return $(
			`<div class="erg-group-header list-row erg-lvl-${level}${statusClass}" data-group-level="${level}" data-chain-key="${escapeHtml(chainKey)}" data-collapsed="${collapsed ? "1" : "0"}"${siGroupAttr}>` +
				`<div class="level-left">${colsHtml}</div>` +
				`<div class="level-right text-muted ellipsis erg-group-right">` +
					`<span class="erg-group-count">${siCountBadgeHtml(count)}</span>` +
					badgeHtml +
				`</div>` +
			`</div>`
		);
	}


	function collapseHeader($header) {
		const level = parseInt($header.attr("data-group-level"), 10);
		collapsed_groups[$header.attr("data-chain-key")] = true;
		$header.attr("data-collapsed", "1").find(".erg-group-toggle").html("&#9658;");
		let $next = $header.next();
		while ($next.length) {
			if ($next.hasClass("erg-group-header") && parseInt($next.attr("data-group-level"), 10) <= level) break;
			$next.addClass("erg-hidden-by-collapse");
			$next = $next.next();
		}
	}

	function expandHeader($header) {
		const level = parseInt($header.attr("data-group-level"), 10);
		delete collapsed_groups[$header.attr("data-chain-key")];
		$header.attr("data-collapsed", "0").find(".erg-group-toggle").html("&#9660;");
		let $next = $header.next();
		while ($next.length) {
			if ($next.hasClass("erg-group-header")) {
				const nextLevel = parseInt($next.attr("data-group-level"), 10);
				if (nextLevel <= level) break;
				$next.removeClass("erg-hidden-by-collapse");
				if ($next.attr("data-collapsed") === "1") {
					let $sub = $next.next();
					while ($sub.length) {
						if ($sub.hasClass("erg-group-header") && parseInt($sub.attr("data-group-level"), 10) <= nextLevel) break;
						$sub.addClass("erg-hidden-by-collapse");
						$sub = $sub.next();
					}
				}
			} else {
				$next.removeClass("erg-hidden-by-collapse");
			}
			$next = $next.next();
		}
		listview.$result.find(".erg-group-header[data-collapsed='1']").each(function () {
			collapseHeader($(this));
		});
	}

	function bindCollapseEvents() {
		listview.$result.find(".erg-group-header").off("click.erg").on("click.erg", function (event) {
			event.stopPropagation();
			$(this).attr("data-collapsed") === "1" ? expandHeader($(this)) : collapseHeader($(this));
		});
	}

	function compareRows(a, b) {
		for (const mode of activeGroups()) {
			const ga = groupValue(a.doc, mode);
			const gb = groupValue(b.doc, mode);
			if (ga.key === gb.key) {
				if (mode === "Status" && ga.key === "Unpaid") {
					const oa = isDocPastDue(a.doc) ? 1 : 0;
					const ob = isDocPastDue(b.doc) ? 1 : 0;
					if (oa !== ob) return ob - oa;
					if (oa === 1 && ob === 1) {
						const la = siDaysPastDue(a.doc) ?? 0;
						const lb = siDaysPastDue(b.doc) ?? 0;
						if (la !== lb) return lb - la;
					}
					const da = parseDate(a.doc?.due_date)?.getTime() ?? 0;
					const db = parseDate(b.doc?.due_date)?.getTime() ?? 0;
					if (da !== db) return da - db;
				}
				continue;
			}
			if (mode === "Status") return statusRank(ga.key) - statusRank(gb.key);
			return String(ga.key).localeCompare(String(gb.key));
		}
		if (a.ts !== b.ts) return a.ts - b.ts;
		return a.name.localeCompare(b.name);
	}

	function applyGrouping() {
		const selected_groups = activeGroups();
		if (is_rendering || !listview.$result) return;
		if (!selected_groups.length) {
			removeArtifacts();
			return;
		}

		is_rendering = true;
		try {
			removeArtifacts();
			const rows = [];
			getRows().each(function () {
				const $row = $(this);
				const name = getDocName($row);
				if (!name) return;
				const doc = getDoc(name);
				const dateValue = parseDate(doc ? doc[DATE_FIELD] : null);
				rows.push({ $row, name, doc, ts: dateValue ? dateValue.getTime() : 0 });
			});

			rows.sort(compareRows);
			if (rows.length) {
				const $parent = rows[0].$row.parent();
				rows.forEach((row) => $parent.append(row.$row));
			}

			const countMap = {};
			const sumMap = {};
			/** chainKey → ringkasan invoice ERPNext Overdue di grup Unpaid (hari telat + JT terawal) */
			const unpaidOverdueMeta = {};
			rows.forEach((item) => {
				const chain = selected_groups.map((mode) => {
					const group = groupValue(item.doc, mode);
					return { mode, key: String(group.key), label: group.label, badge: group.badge };
				});
				const rowTotal = getDocGrandTotal(item.doc);
				chain.forEach((group, index) => {
					const chainKey = chain
						.slice(0, index + 1)
						.map((part) => `${part.mode}:${part.key}`)
						.join("||");
					countMap[chainKey] = (countMap[chainKey] || 0) + 1;
					sumMap[chainKey] = (sumMap[chainKey] || 0) + rowTotal;

					if (group.mode === "Status" && group.key === "Unpaid" && isDocPastDue(item.doc)) {
						const late = cint(item.doc.imogi_late_days) || siDaysPastDue(item.doc) || 0;
						const dueStr = item.doc.due_date || null;
						const prev = unpaidOverdueMeta[chainKey] || {
							hasOverdue: false,
							maxDaysLate: null,
							earliestDueStr: null,
						};
						prev.hasOverdue = true;
						if (late != null) {
							prev.maxDaysLate =
								prev.maxDaysLate == null ? late : Math.max(prev.maxDaysLate, late);
						}
						if (dueStr && (!prev.earliestDueStr || dueStr < prev.earliestDueStr)) {
							prev.earliestDueStr = dueStr;
						}
						unpaidOverdueMeta[chainKey] = prev;
					}
				});
			});

			let previousKeys = [];
			let previousTop = null;
			rows.forEach((item) => {
				const chain = selected_groups.map((mode) => {
					const group = groupValue(item.doc, mode);
					return { mode, key: String(group.key), label: group.label, badge: group.badge };
				});
				if (!chain.length) return;

				const topKey = `${chain[0].mode}:${chain[0].key}`;
				chain.forEach((group, index) => {
					const level = index + 1;
					const chainKey = chain
						.slice(0, level)
						.map((part) => `${part.mode}:${part.key}`)
						.join("||");
					if (previousKeys[index] !== chainKey) {
						if (index === 0 && previousTop !== null && topKey !== previousTop) {
							item.$row.before(makeSeparator());
						}
						let sub = groupSubLabel(group.mode, chain, index);
						const uo = unpaidOverdueMeta[chainKey];
						// if (uo && uo.hasOverdue) {
						// 	const bits = [];
						// 	if (uo.maxDaysLate != null && uo.maxDaysLate > 0) {
						// 		bits.push(
						// 			`${__("Maks.")} ${uo.maxDaysLate} ${__("hari lewat jatuh tempo")}`
						// 		);
						// 	}
						// 	if (uo.earliestDueStr) {
						// 		bits.push(
						// 			`${__("JT terawal")}: ${frappe.datetime.str_to_user(uo.earliestDueStr)}`
						// 		);
						// 	}
						// 	if (bits.length) {
						// 		sub = `${sub} · ${bits.join(" · ")}`;
						// 	} else {
						// 		sub = `${sub} · ${__("Ada invoice lewat jatuh tempo")}`;
						// 	}
						// }
						item.$row.before(
							makeHeader(
								level,
								group,
								sub,
								chainKey,
								countMap[chainKey] || 0,
								sumMap[chainKey] || 0
							)
						);
						previousKeys[index] = chainKey;
						for (let j = index + 1; j < previousKeys.length; j++) previousKeys[j] = null;
					}
				});
				previousTop = topKey;
			});

			bindCollapseEvents();
			if (!Object.keys(collapsed_groups).length) {
				listview.$result.find(".erg-group-header").each(function () {
					collapseHeader($(this));
				});
			} else {
				listview.$result.find(".erg-group-header[data-collapsed='1']").each(function () {
					collapseHeader($(this));
				});
			}
		} finally {
			is_rendering = false;
			scheduleTagListColumnClasses();
		}
	}

	function scheduleApply(delay) {
		clearTimeout(apply_timer);
		apply_timer = setTimeout(applyGrouping, delay || 400);
	}

	function closeAllDropdowns() {
		$(".si-erg-dd").hide();
	}

	function buildPeriodWidget() {
		const options = PERIOD_OPTIONS.map(
			(option) =>
				`<label class="si-erg-opt"><input type="checkbox" class="si-erg-period-check" value="${option}"><span>${option}</span></label>`
		).join("");
		return $(
			`<div class="si-erg-wrap" id="si-erg-period-wrap">` +
				`<div class="si-erg-select" data-widget="period"><span class="si-erg-text is-placeholder" id="si-erg-period-text">Group By Period</span></div>` +
				`<div class="si-erg-chevron"><svg class="icon icon-xs" aria-hidden="true"><use href="#icon-select"></use></svg></div>` +
				`<span class="si-erg-clr" id="si-erg-period-clr">&times;</span>` +
				`<div class="si-erg-dd" id="si-erg-period-dd">` +
					`<div class="si-erg-dd-title">Pilih periode</div>` +
					options +
					`<div class="si-erg-dd-actions">` +
						`<button type="button" class="si-erg-dd-btn" data-action="period-all">All</button>` +
						`<button type="button" class="si-erg-dd-btn" data-action="period-clear">Clear</button>` +
						`<button type="button" class="si-erg-dd-btn primary" data-action="period-apply">Apply</button>` +
					`</div>` +
				`</div>` +
			`</div>`
		);
	}

	function buildStatusWidget() {
		return $(
			`<div class="si-erg-wrap" id="si-erg-status-wrap">` +
				`<div class="si-erg-select" data-widget="status-group"><span class="si-erg-text is-placeholder" id="si-erg-status-text">Group By Status</span></div>` +
				`<div class="si-erg-chevron"><svg class="icon icon-xs" aria-hidden="true"><use href="#icon-select"></use></svg></div>` +
				`<span class="si-erg-clr" id="si-erg-status-clr">&times;</span>` +
				`<div class="si-erg-dd" id="si-erg-status-dd">` +
					`<div class="si-erg-dd-title">Grouping status invoice</div>` +
					`<label class="si-erg-opt"><input type="checkbox" class="si-erg-status-check" id="si-erg-status-check"><span>Aktifkan Group By Status</span></label>` +
					`<div class="si-erg-dd-actions">` +
						`<button type="button" class="si-erg-dd-btn primary" data-action="status-apply">Apply</button>` +
					`</div>` +
				`</div>` +
			`</div>`
		);
	}

	function updatePeriodDisplay() {
		const $text = $("#si-erg-period-text");
		const $clr = $("#si-erg-period-clr");
		if (selected_period.length) {
			$text.text(selected_period.join(" + ")).removeClass("is-placeholder");
			$clr.show();
		} else {
			$text.text(__("Group By Period")).addClass("is-placeholder");
			$clr.hide();
		}
	}

	function updateStatusDisplay() {
		const $text = $("#si-erg-status-text");
		const $clr = $("#si-erg-status-clr");
		if (status_group_on) {
			$text.text(__("Status: Aktif")).removeClass("is-placeholder");
			$clr.show();
		} else {
			$text.text(__("Group By Status")).addClass("is-placeholder");
			$clr.hide();
		}
	}

	function syncPeriodChecks() {
		$(".si-erg-period-check").each(function () {
			$(this).prop("checked", selected_period.includes($(this).val()));
		});
	}

	function syncStatusCheck() {
		$("#si-erg-status-check").prop("checked", status_group_on);
	}

	function attachToolbar($toolbar) {
		$toolbar.on("click", '[data-widget="status-filter"]', function (event) {
			event.stopPropagation();
			syncStatusFilterChecks();
			closeAllDropdowns();
			$("#si-status-filter-dd").toggle();
		});

		$toolbar.on("click", '[data-action="status-filter-all"]', function (event) {
			event.stopPropagation();
			$(".si-status-filter-check").prop("checked", true);
		});

		$toolbar.on("click", '[data-action="status-filter-clear"]', function (event) {
			event.stopPropagation();
			$(".si-status-filter-check").prop("checked", false);
		});

		$toolbar.on("click", '[data-action="status-filter-apply"]', function (event) {
			event.stopPropagation();
			applyStatusFilter();
		});

		$toolbar.on("click", "#si-status-filter-clr", function (event) {
			event.stopPropagation();
			selected_status_filters = [];
			syncStatusFilterChecks();
			updateStatusFilterDisplay();
			clearStatusFilters();
			listview.filter_area.filter_list.update_filters();
			listview.refresh();
		});

		$toolbar.on("click", '[data-widget="period"]', function (event) {
			event.stopPropagation();
			syncPeriodChecks();
			closeAllDropdowns();
			$("#si-erg-period-dd").toggle();
		});

		$toolbar.on("click", '[data-widget="status-group"]', function (event) {
			event.stopPropagation();
			syncStatusCheck();
			closeAllDropdowns();
			$("#si-erg-status-dd").toggle();
		});

		$toolbar.on("click", '[data-action="period-all"]', function (event) {
			event.stopPropagation();
			$(".si-erg-period-check").prop("checked", true);
		});

		$toolbar.on("click", '[data-action="period-clear"]', function (event) {
			event.stopPropagation();
			$(".si-erg-period-check").prop("checked", false);
		});

		$toolbar.on("click", '[data-action="period-apply"]', function (event) {
			event.stopPropagation();
			selected_period = PERIOD_OPTIONS.filter((option) =>
				$(`.si-erg-period-check[value='${option}']`).prop("checked")
			);
			collapsed_groups = {};
			updatePeriodDisplay();
			closeAllDropdowns();
			scheduleApply(300);
		});

		$toolbar.on("click", '[data-action="status-apply"]', function (event) {
			event.stopPropagation();
			status_group_on = $("#si-erg-status-check").prop("checked");
			persist_group_toggle();
			collapsed_groups = {};
			updateStatusDisplay();
			closeAllDropdowns();
			scheduleApply(300);
		});

		$toolbar.on("click", "#si-erg-period-clr", function (event) {
			event.stopPropagation();
			selected_period = [];
			collapsed_groups = {};
			updatePeriodDisplay();
			syncPeriodChecks();
			if (!activeGroups().length) removeArtifacts();
			else scheduleApply(200);
		});

		$toolbar.on("click", "#si-erg-status-clr", function (event) {
			event.stopPropagation();
			status_group_on = false;
			persist_group_toggle();
			collapsed_groups = {};
			updateStatusDisplay();
			syncStatusCheck();
			if (!activeGroups().length) removeArtifacts();
			else scheduleApply(200);
		});

		$toolbar.on("click", ".si-erg-dd", function (event) {
			event.stopPropagation();
		});

		$(document)
			.off("click.si-list-toolbar")
			.on("click.si-list-toolbar", closeAllDropdowns);
	}

	function find_filter_section() {
		let $section = listview.page?.page_form?.find(".standard-filter-section");
		if (!$section?.length && listview.$page) {
			$section = listview.$page.find(".standard-filter-section");
		}
		if (!$section?.length && listview.$filter_section?.length) {
			$section = listview.$filter_section.find(".standard-filter-section");
			if (!$section.length) {
				$section = listview.$filter_section;
			}
		}
		if (!$section?.length) {
			$section = $("[data-page-route*='sales-invoice'] .standard-filter-section").first();
		}
		if (!$section?.length) {
			$section = $(".layout-main-section .standard-filter-section").first();
		}
		return $section || $();
	}

	function injectToolbar() {
		if ($("#si-list-toolbar").length) return true;

		const $section = find_filter_section();
		if (!$section.length) return false;

		const $toolbar = $('<div id="si-list-toolbar"></div>');
		$toolbar
			.append(buildStatusFilterWidget())
			.append(buildPeriodWidget())
			.append(buildStatusWidget());
		$section.append($toolbar);

		const $erg = $section.find("#erg-wrap").last();
		if ($erg.length) {
			$toolbar.detach().insertAfter($erg);
		}

		attachToolbar($toolbar);
		updateStatusFilterDisplay();
		updatePeriodDisplay();
		updateStatusDisplay();
		syncStatusCheck();
		syncFromListviewFilters();
		if (status_group_on) {
			scheduleApply(400);
		}
		return true;
	}

	patchSiListColumnLayout();

	if (!listview.__si_list_toolbar_patched) {
		listview.__si_list_toolbar_patched = true;
		const originalRender = listview.render;
		const originalRefresh = listview.refresh;
		listview.render = function () {
			const result = originalRender.apply(this, arguments);
			scheduleApply(500);
			scheduleTagListColumnClasses();
			return result;
		};
		listview.refresh = function () {
			const result = originalRefresh.apply(this, arguments);
			setTimeout(syncFromListviewFilters, 100);
			scheduleApply(600);
			return result;
		};
	}

	function schedule_inject_toolbar() {
		if (injectToolbar()) return;
		let attempts = 0;
		const interval = setInterval(function () {
			attempts += 1;
			if (injectToolbar() || attempts > 30) clearInterval(interval);
		}, 200);
	}

	schedule_inject_toolbar();

	frappe.after_ajax(function () {
		schedule_inject_toolbar();
		scheduleApply(700);
	});
}

