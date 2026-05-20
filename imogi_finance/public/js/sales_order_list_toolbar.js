// Sales Order list — status multi-filter + group by status (selaras Sales Invoice)

const SO_LIST_STATUS_ORDER = [
	"Draft",
	"Submitted",
	"SI Created",
	"Outstanding Invoice",
	"Paid",
	"Cancelled",
];

const SO_GROUP_ICON = {
	"Outstanding Invoice": "es-solid-dot",
	"SI Created": "es-line-inbox",
	Paid: "es-solid-success",
	Submitted: "es-line-inbox",
	Draft: "es-line-edit",
	Cancelled: "es-solid-close-circle",
};

const SO_GROUP_HEADER_STYLE = {
	"Outstanding Invoice": { border: "#f97316", bg: "linear-gradient(90deg,#fff7ed 0%,#f8fafc 55%)", title: "#9a3412" },
	Paid: { border: "#10b981", bg: "linear-gradient(90deg,#ecfdf5 0%,#f8fafc 55%)", title: "#065f46" },
	Submitted: { border: "#3b82f6", bg: "linear-gradient(90deg,#eff6ff 0%,#f8fafc 55%)", title: "#1e40af" },
	"SI Created": { border: "#6366f1", bg: "linear-gradient(90deg,#eef2ff 0%,#f8fafc 55%)", title: "#3730a3" },
	Draft: { border: "#94a3b8", bg: "linear-gradient(90deg,#f8fafc 0%,#f1f5f9 100%)", title: "#475569" },
	Cancelled: { border: "#ef4444", bg: "linear-gradient(90deg,#fef2f2 0%,#f8fafc 55%)", title: "#b91c1c" },
};

frappe.provide("imogi_finance.so_list");

window.init_imogi_so_status_toolbar = function (listview) {
	if (!listview || listview.doctype !== "Sales Order") return;

	const STORAGE_KEY = "imogi_so_list_status_group_on";
	let selected_status_filters = [];
	let status_group_on = false;
	try {
		status_group_on = localStorage.getItem(STORAGE_KEY) === "1";
	} catch (e) {
		status_group_on = false;
	}
	window.__imogi_so_status_group_on = status_group_on;
	let collapsed_groups = {};
	let apply_timer = null;
	let is_rendering = false;

	const FILTER_FIELD = "custom_payment_status";

	function resolve_so_status(doc) {
		if (typeof get_business_status === "function") {
			return get_business_status(doc);
		}
		if (cint(doc.docstatus) === 2) return "Cancelled";
		if (cint(doc.docstatus) === 0) return "Draft";
		const v = (doc.custom_payment_status || "").trim();
		return v === "Partial Paid" ? "Outstanding Invoice" : v || "Submitted";
	}

	function expand_status_filter(values) {
		const out = new Set();
		values.forEach((v) => {
			out.add(v);
			if (v === "Outstanding Invoice") out.add("Partial Paid");
		});
		return Array.from(out);
	}

	function parse_status_filter_value(value) {
		if (Array.isArray(value)) return value.filter(Boolean);
		if (value == null || value === "") return [];
		if (typeof value === "string") {
			try {
				const parsed = JSON.parse(value);
				if (Array.isArray(parsed)) return parsed.filter(Boolean);
			} catch (e) {
				return value
					.split(",")
					.map((s) => s.trim())
					.filter(Boolean);
			}
		}
		return [String(value)];
	}

	function sync_status_filters_from_listview() {
		const filters = listview.filter_area?.get?.() || [];
		const found = [];
		filters.forEach((f) => {
			if (!f || f[1] !== FILTER_FIELD) return;
			if (f[2] === "in") {
				parse_status_filter_value(f[3]).forEach((v) => {
					if (v === "Partial Paid") found.push("Outstanding Invoice");
					else found.push(v);
				});
			} else if (f[2] === "=" && f[3]) {
				found.push(f[3] === "Partial Paid" ? "Outstanding Invoice" : f[3]);
			}
		});
		selected_status_filters = [...new Set(found)];
		update_filter_display();
		sync_filter_checks();
	}

	function inject_styles() {
		if (document.getElementById("so-list-toolbar-style")) return;
		const style = document.createElement("style");
		style.id = "so-list-toolbar-style";
		style.textContent =
			".standard-filter-section.flex{display:flex!important;flex-wrap:wrap!important;align-items:flex-end!important;gap:8px!important}" +
			`.standard-filter-section .frappe-control[data-fieldname='${FILTER_FIELD}']{display:none!important}` +
			"#so-list-toolbar{display:inline-flex;flex-wrap:wrap;align-items:center;gap:8px;flex:0 0 auto;margin:0 4px 0 0;vertical-align:middle}" +
			".so-erg-wrap{position:relative;display:inline-flex;align-items:center;min-width:148px;max-width:175px;vertical-align:middle}" +
			".so-erg-select{width:100%;height:30px;padding:0 28px 0 10px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;font-size:13px;color:#1e293b;display:flex;align-items:center;cursor:pointer;box-sizing:border-box;box-shadow:0 1px 2px rgba(15,23,42,.04)}" +
			".so-erg-text{display:block;width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.so-erg-text.is-placeholder{color:#8d99a6}" +
			".so-erg-chevron{position:absolute;right:8px;top:50%;transform:translateY(-50%);pointer-events:none;color:#8d99a6;z-index:2}" +
			".so-erg-clr{display:none;position:absolute;right:24px;top:50%;transform:translateY(-50%);cursor:pointer;color:#8d99a6;font-size:13px;z-index:3;line-height:1}" +
			".so-erg-dd{display:none;position:absolute;top:calc(100% + 6px);left:0;background:#fff;border:1px solid #d1d8dd;border-radius:8px;min-width:220px;z-index:10000;padding:8px 0;box-shadow:0 4px 16px rgba(0,0,0,.12)}" +
			".so-erg-dd-title{padding:0 12px 8px;font-size:11px;font-weight:600;color:#8d99a6;border-bottom:1px solid #f0f4f7;margin-bottom:6px}" +
			".so-erg-opt{display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;font-size:13px}.so-erg-opt:hover{background:#f5f7fa}" +
			".so-erg-dd-actions{display:flex;justify-content:space-between;gap:8px;padding:8px 12px 0;border-top:1px solid #f0f4f7;margin-top:6px}" +
			".so-erg-dd-btn{flex:1;border:1px solid #d1d8dd;background:#fff;font-size:11px;border-radius:6px;padding:6px 8px;cursor:pointer}" +
			".so-erg-dd-btn.primary{background:#2490ef;color:#fff;border-color:#2490ef}" +
			"[data-page-route^='List/Sales Order'] .so-group-separator{margin:20px 0 8px;border:0;height:0}" +
			"[data-page-route^='List/Sales Order'] .so-group-header.list-row{position:relative;padding:10px 0;margin:0 0 8px;border:1px solid #e2e8f0;border-radius:10px;cursor:pointer;user-select:none;box-shadow:0 1px 2px rgba(15,23,42,.04)}" +
			"[data-page-route^='List/Sales Order'] .so-group-header--status{border-left-width:4px;border-left-style:solid}" +
			"[data-page-route^='List/Sales Order'] .so-group-header .level-left{align-items:center}" +
			"[data-page-route^='List/Sales Order'] .erg-group-icon-wrap{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:50%;flex-shrink:0;background:#e2e8f0;color:#475569}" +
			"[data-page-route^='List/Sales Order'] .erg-group-title{font-size:13px;font-weight:700;line-height:1.25}" +
			"[data-page-route^='List/Sales Order'] .erg-group-sub{font-size:11px;color:#64748b;margin-top:2px}" +
			"[data-page-route^='List/Sales Order'] .erg-group-count{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:#475569;background:#fff;border:1px solid #e2e8f0;border-radius:999px;padding:4px 10px}" +
			"[data-page-route^='List/Sales Order'] .erg-group-total{font-weight:700;font-size:13px;font-variant-numeric:tabular-nums;color:#0f172a}" +
			"[data-page-route^='List/Sales Order'] .erg-hidden-by-collapse{display:none!important}" +
			"[data-page-route^='List/Sales Order'] .list-row-head .list-header-subject," +
			"[data-page-route^='List/Sales Order'] .list-row-container .level-left," +
			"[data-page-route^='List/Sales Order'] .so-group-header .level-left{display:flex!important;justify-content:flex-start!important;flex-wrap:nowrap!important;align-items:center!important}" +
			"[data-page-route^='List/Sales Order'] .level-left>.list-row-col{margin-right:8px!important;flex-shrink:0}" +
			"[data-page-route^='List/Sales Order'] .so-col-subject{flex:1 1 0!important;min-width:5rem!important;max-width:none!important;width:auto!important}" +
			"[data-page-route^='List/Sales Order'] .so-col-name{flex:0 0 128px!important;width:128px!important;max-width:128px!important}" +
			"[data-page-route^='List/Sales Order'] .so-col-custom_payment_status," +
			"[data-page-route^='List/Sales Order'] .so-col-status{flex:0 0 130px!important;width:130px!important;max-width:130px!important}" +
			"[data-page-route^='List/Sales Order'] .so-col-delivery_date," +
			"[data-page-route^='List/Sales Order'] .so-col-transaction_date{flex:0 0 100px!important;width:100px!important;max-width:100px!important}" +
			"[data-page-route^='List/Sales Order'] .so-col-grand_total{flex:0 0 152px!important;width:152px!important;max-width:152px!important;text-align:right!important}" +
			"[data-page-route^='List/Sales Order'] .so-col-outstanding_amount," +
			"[data-page-route^='List/Sales Order'] .so-col-outstanding{flex:0 0 136px!important;width:136px!important;max-width:136px!important;text-align:right!important}" +
			"[data-page-route^='List/Sales Order'] .so-group-header .level-left{flex:1 1 auto;min-width:0}" +
			"[data-page-route^='List/Sales Order'] .so-group-header .erg-group-right{flex:0 0 auto;padding-right:8px}" +
			"[data-page-route^='List/Sales Order'] .so-group-header .erg-group-total-col{overflow:visible!important;text-overflow:clip;flex-shrink:0!important}" +
			"[data-page-route^='List/Sales Order'] .so-group-header .erg-group-total-col .erg-group-total{display:block;width:100%;box-sizing:border-box;text-align:right;padding-right:12px;white-space:nowrap!important;overflow:visible}" +
			"[data-page-route^='List/Sales Order'] .erg-group-subject-col .erg-group-left{display:flex;align-items:center;gap:10px;min-width:0}" +
			"[data-page-route^='List/Sales Order'] .erg-group-checkbox-spacer{visibility:hidden;pointer-events:none;flex:0 0 15px;width:15px}";
		document.head.appendChild(style);
	}

	function soColClass(col) {
		if (!col) return "";
		if (col.type === "Subject") return "so-col-subject";
		if (col.type === "Status") return "so-col-status";
		if (col.df?.fieldname) return `so-col-${col.df.fieldname}`;
		return "";
	}

	function tagSoColumnClasses() {
		if (!listview.$result || !listview.columns?.length) return;
		const cols = listview.columns;

		listview.$result.find(".list-row-head .list-header-subject > .list-row-col").each(function (i) {
			const cls = soColClass(cols[i]);
			if (cls) $(this).addClass(cls);
		});

		listview.$result
			.find(".list-row-container .level-left, .so-group-header .level-left")
			.each(function () {
				$(this)
					.children(".list-row-col")
					.each(function (i) {
						const cls = soColClass(cols[i]);
						if (cls) $(this).addClass(cls);
					});
			});
	}

	function scheduleTagSoColumnClasses() {
		requestAnimationFrame(() => {
			tagSoColumnClasses();
			requestAnimationFrame(tagSoColumnClasses);
		});
	}

	function patchSoListColumnLayout() {
		if (listview.__so_col_layout_patched) return;
		listview.__so_col_layout_patched = true;

		const origGetColumnHtml = listview.get_column_html.bind(listview);
		listview.get_column_html = function (col, doc) {
			const html = origGetColumnHtml(col, doc);
			const cls = soColClass(col);
			if (!cls || !html) return html;
			return html.replace(/class="([^"]*)"/, `class="$1 ${cls}"`);
		};

		const origGetHeaderHtml = listview.get_header_html.bind(listview);
		listview.get_header_html = function () {
			const header = origGetHeaderHtml();
			if (!header || !this.columns) return header;
			let colIdx = 0;
			return header.replace(/<div class="list-row-col([^"]*)"/g, (match, rest) => {
				const col = this.columns[colIdx++];
				const cls = soColClass(col);
				return cls ? `<div class="list-row-col${rest} ${cls}"` : match;
			});
		};
	}

	function so_group_icon_html(label) {
		const icon = SO_GROUP_ICON[label] || "es-line-status";
		if (typeof frappe.utils.icon === "function") {
			return frappe.utils.icon(icon, "sm", "", "", "erg-group-title-icon");
		}
		return "";
	}

	function so_count_badge(count) {
		const label = count === 1 ? __("1 order") : __("{0} orders", [String(count)]);
		let icon = "";
		if (typeof frappe.utils.icon === "function") {
			icon = frappe.utils.icon("es-line-filetype", "xs", "", "", "erg-count-icon");
		}
		return icon + frappe.utils.escape_html(label);
	}

	function status_rank(label) {
		const idx = SO_LIST_STATUS_ORDER.indexOf(label);
		return idx >= 0 ? idx : 999;
	}

	function get_row_name($row) {
		return $row.attr("data-name") || $row.find("[data-name]").first().attr("data-name") || null;
	}

	function get_rows() {
		if (!listview.$result) return $();
		return listview.$result.find(".list-row-container").filter(function () {
			return !!get_row_name($(this));
		});
	}

	function get_doc(name) {
		return (listview.data || []).find((r) => r.name === name) || null;
	}

	function format_group_total(amount, doc) {
		const currency = doc?.currency || frappe.defaults.get_default("currency");
		return typeof format_currency === "function"
			? format_currency(amount, currency)
			: frappe.format(amount, { fieldtype: "Currency", options: currency });
	}

	function build_group_columns(group, sub, collapsed, totalAmount) {
		const left =
			`<div class="erg-group-left">` +
			`<div class="erg-group-toggle">${collapsed ? "&#9658;" : "&#9660;"}</div>` +
			`<span class="erg-group-icon-wrap">${so_group_icon_html(group.label)}</span>` +
			`<div class="erg-group-text"><div class="erg-group-title">${frappe.utils.escape_html(group.label)}</div>` +
			`<div class="erg-group-sub">${frappe.utils.escape_html(sub)}</div></div></div>`;

		if (!listview.columns?.length) return left;

		return listview.columns
			.map((col) => {
				const cls = soColClass(col);
				const clsAttr = cls ? ` ${cls}` : "";
				if (col.type === "Subject") {
					return (
						`<div class="list-row-col list-subject level erg-group-subject-col${clsAttr}">` +
						`<span class="level-item select-like erg-group-checkbox-spacer" aria-hidden="true"></span>` +
						`<span class="level-item ellipsis">${left}</span></div>`
					);
				}
				if (col.type === "Status" || col.df?.fieldname === FILTER_FIELD) {
					return `<div class="list-row-col hidden-xs${clsAttr || " so-col-status"}"></div>`;
				}
				if (col.df?.fieldname === "grand_total") {
					const t = format_group_total(totalAmount || 0);
					return (
						`<div class="list-row-col hidden-xs text-right erg-group-total-col${clsAttr}" title="${frappe.utils.escape_html(t)}">` +
						`<span class="erg-group-total">${frappe.utils.escape_html(t)}</span></div>`
					);
				}
				if (col.df?.fieldname === "outstanding_amount") {
					return `<div class="list-row-col hidden-xs${clsAttr || " so-col-outstanding"}"></div>`;
				}
				return `<div class="list-row-col hidden-xs${clsAttr}"></div>`;
			})
			.join("");
	}

	function make_header(group, chainKey, count, total) {
		const collapsed = !!collapsed_groups[chainKey];
		const cols = build_group_columns(group, __("Group by Status"), collapsed, total);
		const st = SO_GROUP_HEADER_STYLE[group.label] || {};
		const attr = group.label ? ` data-so-group="${frappe.utils.escape_html(group.label)}"` : "";
		const style = [
			st.border ? `border-left-color:${st.border}` : "",
			st.bg ? `background:${st.bg}` : "",
		]
			.filter(Boolean)
			.join(";");
		const titleStyle = st.title ? `color:${st.title}` : "";
		return $(
			`<div class="so-group-header list-row so-group-header--status" data-chain-key="${frappe.utils.escape_html(chainKey)}" data-collapsed="${collapsed ? 1 : 0}"${attr}${style ? ` style="${style}"` : ""}>` +
			`<div class="level-left">${cols.replace('class="erg-group-title"', `class="erg-group-title" style="${titleStyle}"`)}</div>` +
			`<div class="level-right erg-group-right"><span class="erg-group-count">${so_count_badge(count)}</span></div>` +
			`</div>`
		);
	}

	function make_separator() {
		return $('<div class="so-group-separator">');
	}

	function remove_artifacts() {
		if (!listview.$result) return;
		listview.$result.find(".so-group-header,.so-group-separator").remove();
		listview.$result.find(".erg-hidden-by-collapse").removeClass("erg-hidden-by-collapse");
	}

	function collapse_header($header) {
		const chainKey = $header.attr("data-chain-key");
		collapsed_groups[chainKey] = true;
		$header.attr("data-collapsed", "1").find(".erg-group-toggle").html("&#9658;");
		let $next = $header.next();
		while ($next.length && !$next.hasClass("so-group-header")) {
			$next.addClass("erg-hidden-by-collapse");
			$next = $next.next();
		}
	}

	function expand_header($header) {
		const chainKey = $header.attr("data-chain-key");
		delete collapsed_groups[chainKey];
		$header.attr("data-collapsed", "0").find(".erg-group-toggle").html("&#9660;");
		let $next = $header.next();
		while ($next.length && !$next.hasClass("so-group-header")) {
			$next.removeClass("erg-hidden-by-collapse");
			$next = $next.next();
		}
	}

	function apply_grouping() {
		window.__imogi_so_status_group_on = status_group_on;

		// Period + Status: satu pipeline di Client Script (nested seperti Sales Invoice)
		if (typeof window.__imogi_so_cs_sched === "function") {
			if (!status_group_on) {
				remove_artifacts();
				window.__imogi_so_cs_sched(350);
				return;
			}
			window.__imogi_so_cs_sched(80);
			// Fallback: Client Script lama cek selected_groups saja, bukan activeGroups()
			setTimeout(() => {
				if (!listview.$result) return;
				const hasHeaders =
					listview.$result.find(".erg-group-header,.so-group-header").length > 0;
				if (!hasHeaders) apply_grouping_native();
			}, 220);
			return;
		}

		apply_grouping_native();
	}

	function apply_grouping_native() {
		if (is_rendering || !listview.$result) return;
		if (!status_group_on) {
			remove_artifacts();
			return;
		}

		is_rendering = true;
		try {
			remove_artifacts();
			const rows = [];
			get_rows().each(function () {
				const $row = $(this);
				const name = get_row_name($row);
				const doc = get_doc(name);
				if (!doc) return;
				rows.push({ $row, doc, name, status: resolve_so_status(doc) });
			});

			rows.sort((a, b) => {
				const r = status_rank(a.status) - status_rank(b.status);
				return r !== 0 ? r : a.name.localeCompare(b.name);
			});

			if (rows.length) {
				const $parent = rows[0].$row.parent();
				rows.forEach((r) => $parent.append(r.$row));
			}

			const countMap = {};
			const sumMap = {};
			rows.forEach((item) => {
				countMap[item.status] = (countMap[item.status] || 0) + 1;
				sumMap[item.status] = (sumMap[item.status] || 0) + (parseFloat(item.doc.grand_total) || 0);
			});

			let prev = null;
			rows.forEach((item) => {
				if (item.status !== prev) {
					if (prev !== null) {
						item.$row.before(make_separator());
					}
					item.$row.before(
						make_header(
							{ label: item.status },
							item.status,
							countMap[item.status],
							sumMap[item.status]
						)
					);
					prev = item.status;
				}
			});

			listview.$result.find(".so-group-header").off("click.soerg").on("click.soerg", function (e) {
				e.stopPropagation();
				const $h = $(this);
				if ($h.attr("data-collapsed") === "1") expand_header($h);
				else collapse_header($h);
			});

			listview.$result.find(".so-group-header").each(function () {
				if ($(this).attr("data-collapsed") === "1") collapse_header($(this));
			});
		} finally {
			is_rendering = false;
			scheduleTagSoColumnClasses();
		}
	}

	function schedule_apply(delay) {
		clearTimeout(apply_timer);
		apply_timer = setTimeout(apply_grouping, delay || 400);
	}

	function persist_group_toggle() {
		window.__imogi_so_status_group_on = status_group_on;
		try {
			localStorage.setItem(STORAGE_KEY, status_group_on ? "1" : "0");
		} catch (e) {
			/* ignore quota / private mode */
		}
	}

	function update_filter_display() {
		const $t = $("#so-status-filter-text");
		const $c = $("#so-status-filter-clr");
		if (selected_status_filters.length) {
			$t.text(
				selected_status_filters.length <= 2
					? selected_status_filters.join(" + ")
					: `${selected_status_filters.length} status`
			).removeClass("is-placeholder");
			$c.show();
		} else {
			$t.text(__("Status")).addClass("is-placeholder");
			$c.hide();
		}
	}

	function update_group_display() {
		$("#so-group-status-text")
			.text(status_group_on ? __("Status: Aktif") : __("Group By Status"))
			.toggleClass("is-placeholder", !status_group_on);
		$("#so-group-status-clr").toggle(!!status_group_on);
		$("#so-group-status-check").prop("checked", status_group_on);
	}

	function sync_filter_checks() {
		$(".so-status-filter-check").each(function () {
			const val = $(this).val();
			$(this).prop(
				"checked",
				selected_status_filters.includes(val) ||
					(val === "Outstanding Invoice" && selected_status_filters.includes("Partial Paid"))
			);
		});
	}

	function clear_status_filters() {
		const std = listview.page?.fields_dict?.[FILTER_FIELD];
		if (std) {
			std.set_value("");
		}
		const fl = listview.filter_area?.filter_list;
		if (!fl) return;
		fl.filters.slice().forEach((f) => {
			if (f.field?.df?.fieldname === FILTER_FIELD) {
				f.remove();
			}
		});
	}

	function apply_status_filter() {
		const values = [];
		$(".so-status-filter-check:checked").each(function () {
			values.push($(this).val());
		});
		selected_status_filters = values;
		update_filter_display();
		$("#so-status-filter-dd").hide();
		clear_status_filters();

		if (!values.length) {
			listview.filter_area.filter_list.update_filter_button();
			listview.refresh();
			return;
		}

		const expanded = expand_status_filter(values);
		const fl = listview.filter_area.filter_list;
		const add_promise = fl.add_filter(listview.doctype, FILTER_FIELD, "in", expanded, true);

		Promise.resolve(add_promise)
			.then(() => {
				const f = fl.get_filter(FILTER_FIELD);
				if (f && f._filter_value_set) {
					return f._filter_value_set;
				}
			})
			.then(() => {
				fl.update_filter_button();
				return listview.refresh();
			});
	}

	function build_filter_widget() {
		const opts = SO_LIST_STATUS_ORDER.map(
			(s) =>
				`<label class="so-erg-opt"><input type="checkbox" class="so-status-filter-check" value="${s}"><span>${__(s)}</span></label>`
		).join("");
		return $(
			`<div id="so-status-filter-wrap" class="so-erg-wrap">` +
			`<div class="so-erg-select" data-widget="status-filter"><span class="so-erg-text is-placeholder" id="so-status-filter-text">${__("Status")}</span></div>` +
			`<div class="so-erg-chevron"><svg class="icon icon-xs"><use href="#icon-select"></use></svg></div>` +
			`<span class="so-erg-clr" id="so-status-filter-clr">&times;</span>` +
			`<div class="so-erg-dd" id="so-status-filter-dd"><div class="so-erg-dd-title">${__("Pilih status (multi)")}</div>${opts}` +
			`<div class="so-erg-dd-actions">` +
			`<button type="button" class="so-erg-dd-btn" data-action="sf-all">${__("All")}</button>` +
			`<button type="button" class="so-erg-dd-btn" data-action="sf-clear">${__("Clear")}</button>` +
			`<button type="button" class="so-erg-dd-btn primary" data-action="sf-apply">${__("Apply")}</button>` +
			`</div></div></div>`
		);
	}

	function build_group_widget() {
		return $(
			`<div id="so-group-status-wrap" class="so-erg-wrap">` +
			`<div class="so-erg-select" data-widget="status-group"><span class="so-erg-text is-placeholder" id="so-group-status-text">${__("Group By Status")}</span></div>` +
			`<div class="so-erg-chevron"><svg class="icon icon-xs"><use href="#icon-select"></use></svg></div>` +
			`<span class="so-erg-clr" id="so-group-status-clr">&times;</span>` +
			`<div class="so-erg-dd" id="so-group-status-dd">` +
			`<div class="so-erg-dd-title">${__("Grouping status Sales Order")}</div>` +
			`<label class="so-erg-opt"><input type="checkbox" id="so-group-status-check"><span>${__("Aktifkan Group By Status")}</span></label>` +
			`<div class="so-erg-dd-actions"><button type="button" class="so-erg-dd-btn primary" data-action="sg-apply">${__("Apply")}</button></div>` +
			`</div></div>`
		);
	}

	function find_filter_section() {
		let $section = listview.page?.page_form?.find(".standard-filter-section");
		if (!$section?.length && listview.$page) {
			$section = listview.$page.find(".standard-filter-section");
		}
		if (!$section?.length) {
			$section = $("[data-page-route*='sales-order'] .standard-filter-section").first();
		}
		return $section || $();
	}

	function attach_toolbar_events($tb) {
		$tb.on("click", '[data-widget="status-filter"]', (e) => {
			e.stopPropagation();
			sync_filter_checks();
			$(".so-erg-dd").hide();
			$("#so-status-filter-dd").toggle();
		});
		$tb.on("click", '[data-action="sf-all"]', (e) => {
			e.stopPropagation();
			$(".so-status-filter-check").prop("checked", true);
		});
		$tb.on("click", '[data-action="sf-clear"]', (e) => {
			e.stopPropagation();
			$(".so-status-filter-check").prop("checked", false);
		});
		$tb.on("click", '[data-action="sf-apply"]', (e) => {
			e.stopPropagation();
			apply_status_filter();
		});
		$tb.on("click", "#so-status-filter-clr", (e) => {
			e.stopPropagation();
			selected_status_filters = [];
			update_filter_display();
			clear_status_filters();
			listview.filter_area.filter_list.update_filter_button();
			listview.refresh();
		});
		$tb.on("click", '[data-widget="status-group"]', (e) => {
			e.stopPropagation();
			update_group_display();
			$(".so-erg-dd").hide();
			$("#so-group-status-dd").toggle();
		});
		$tb.on("click", '[data-action="sg-apply"]', (e) => {
			e.stopPropagation();
			status_group_on = $("#so-group-status-check").prop("checked");
			persist_group_toggle();
			update_group_display();
			$(".so-erg-dd").hide();
			schedule_apply(700);
		});
		$tb.on("click", "#so-group-status-clr", (e) => {
			e.stopPropagation();
			status_group_on = false;
			collapsed_groups = {};
			persist_group_toggle();
			update_group_display();
			remove_artifacts();
		});
		$tb.on("click", ".so-erg-dd", (e) => e.stopPropagation());
	}

	function inject_toolbar() {
		$("#so-list-toolbar").remove();
		const $section = find_filter_section();
		if (!$section.length) return false;

		const $tb = $('<div id="so-list-toolbar"></div>');
		$tb.append(build_filter_widget()).append(build_group_widget());

		$section.append($tb);
		const $erg = $section.find("#erg-wrap").last();
		if ($erg.length) {
			$tb.detach().insertAfter($erg);
		}

		attach_toolbar_events($tb);
		update_filter_display();
		update_group_display();
		$(document).off("click.so-list-toolbar").on("click.so-list-toolbar", () => $(".so-erg-dd").hide());
		return true;
	}

	inject_styles();
	patchSoListColumnLayout();

	if (!listview.__so_toolbar_render_patched) {
		listview.__so_toolbar_render_patched = true;
		const orig_render = listview.render.bind(listview);
		const orig_refresh = listview.refresh?.bind(listview);
		listview.render = function () {
			const r = orig_render();
			scheduleTagSoColumnClasses();
			if (status_group_on) schedule_apply(700);
			return r;
		};
		if (orig_refresh) {
			listview.refresh = function () {
				const r = orig_refresh();
				if (status_group_on) schedule_apply(750);
				return r;
			};
		}
	}

	function try_inject() {
		if (inject_toolbar()) {
			sync_status_filters_from_listview();
			if (status_group_on) schedule_apply(400);
			return;
		}
		let n = 0;
		const iv = setInterval(() => {
			n += 1;
			if (inject_toolbar() || n > 25) {
				clearInterval(iv);
				if (status_group_on) schedule_apply(400);
			}
		}, 200);
	}

	frappe.after_ajax(() => try_inject());
	try_inject();
};

imogi_finance.so_list.init_toolbar = window.init_imogi_so_status_toolbar;
