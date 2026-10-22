/**
 * Pusat Approval - one place to clear every approval queue, reachable from Dashboard Manager.
 *
 * Left: a menu of queues with their waiting counts. Right: the documents in the selected queue,
 * each with the actions frappe would actually allow this user (from the workflow transitions),
 * so a button is never offered that the backend would then refuse.
 *
 * Route: /app/approval-center, or /app/approval-center/<doctype slug> to open one queue
 * directly - that is what the Dashboard Manager's approval rows link to.
 */

const AC_STYLE_ID = "ac-approval-center-style-v1";

const AC_ICONS = {
	check: '<polyline points="20 6 9 17 4 12"/>',
	x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
	external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
	inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
	back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
	user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
	alert: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
};

function ac_icon(name, size) {
	return `<svg class="ac-icon" width="${size || 14}" height="${size || 14}" viewBox="0 0 24 24"
		fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
		stroke-linejoin="round" aria-hidden="true">${AC_ICONS[name] || ""}</svg>`;
}

function ac_slug(doctype) {
	return frappe.router.slug ? frappe.router.slug(doctype) : doctype.toLowerCase().replace(/ /g, "-");
}

frappe.pages["approval-center"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Pusat Approval"),
		single_column: true,
	});

	ac_inject_styles();
	$(wrapper).addClass("ac-full-width");

	const state = { page, $wrap: $(ac_shell()).appendTo(page.main), active: null, queues: [] };
	wrapper.__ac_state = state;

	page.set_primary_action(__("Refresh"), () => ac_load_overview(state, state.active), "refresh");
	page.add_inner_button(__("Dashboard Manager"), () => frappe.set_route("dashboard-manager"));

	state.$wrap.on("click", "[data-queue]", function () {
		ac_select(state, $(this).data("queue"));
	});

	ac_load_overview(state, ac_route_doctype(state));
};

frappe.pages["approval-center"].on_page_show = function (wrapper) {
	const state = wrapper.__ac_state;
	if (!state) return;
	const wanted = ac_route_doctype(state);
	// Returning to an already-built page: honour a new route segment, else just refresh counts.
	ac_load_overview(state, wanted || state.active);
};

/** Reads /app/approval-center/<slug> and maps it back to a doctype name. */
function ac_route_doctype(state) {
	const route = frappe.get_route() || [];
	const slug = route[1];
	if (!slug) return null;
	const match = (state.queues || []).find((q) => ac_slug(q.doctype) === slug);
	return match ? match.doctype : null;
}

// ---------------------------------------------------------------------------
// Load
// ---------------------------------------------------------------------------

function ac_load_overview(state, prefer) {
	state.$wrap.addClass("is-loading");
	const done = () => state.$wrap.removeClass("is-loading");
	return frappe
		.call({ method: "imogi_finance.api.approval_center.get_overview" })
		.then((r) => {
			const data = r.message || { queues: [], total_pending: 0 };
			state.queues = data.queues;
			state.user = data.user;
			ac_render_menu(state, data);

			const routed = ac_route_doctype(state);
			const target =
				routed ||
				prefer ||
				(data.queues.find((q) => q.pending_count > 0) || data.queues[0] || {}).doctype;

			if (!target) {
				state.$wrap.find("#ac-list").html(ac_empty(__("Tidak ada antrean approval yang bisa diakses.")));
				return;
			}
			return ac_select(state, target, { skipRoute: true });
		})
		.then(done, done);
}

function ac_select(state, doctype, opts) {
	if (!doctype) return;
	state.active = doctype;
	state.$wrap.find("[data-queue]").each(function () {
		$(this).toggleClass("is-active", $(this).data("queue") === doctype);
	});

	if (!(opts && opts.skipRoute)) {
		// Keep the URL in step so the queue can be linked to / reloaded / bookmarked.
		frappe.set_route("approval-center", ac_slug(doctype));
	}

	state.$wrap.addClass("is-loading");
	const done = () => state.$wrap.removeClass("is-loading");
	return frappe
		.call({ method: "imogi_finance.api.approval_center.get_pending", args: { doctype } })
		.then((r) => {
			if (state.active !== doctype) return; // a newer selection won
			ac_render_list(state, r.message || {});
		})
		.then(done, done);
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

function ac_render_menu(state, data) {
	const rows = data.queues
		.map(
			(q) => `
		<button type="button" class="ac-menu-item" data-queue="${frappe.utils.escape_html(q.doctype)}"
			title="${frappe.utils.escape_html(q.label)}">
			<span class="ac-menu-label">${frappe.utils.escape_html(q.label)}</span>
			<span class="ac-count ${q.pending_count ? "is-waiting" : ""}">${q.pending_count}</span>
		</button>`
		)
		.join("");

	state.$wrap.find("#ac-menu").html(rows);
	state.$wrap.find("#ac-total").text(
		data.total_pending
			? __("{0} dokumen menunggu", [data.total_pending])
			: __("Semua antrean bersih")
	);
}

function ac_render_list(state, data) {
	const items = data.items || [];
	state.$wrap.find("#ac-list-title").text(data.label || "");
	state.$wrap.find("#ac-list-meta").text(
		items.length ? __("{0} menunggu", [items.length]) : __("tidak ada yang menunggu")
	);

	if (!items.length) {
		state.$wrap.find("#ac-list").html(
			ac_empty(__("Tidak ada {0} yang menunggu approval.", [data.label || ""]))
		);
		return;
	}

	const html = items.map((item) => ac_card(state, data, item)).join("");
	const $list = state.$wrap.find("#ac-list").html(html);

	$list.find("[data-act]").on("click", function () {
		const $btn = $(this);
		ac_act(state, data.doctype, $btn.data("name"), $btn.data("act"));
	});
	$list.find("[data-open]").on("click", function () {
		frappe.set_route("Form", data.doctype, $(this).data("open"));
	});

	state.$wrap
		.find("#ac-truncated")
		.text(data.truncated ? __("Menampilkan {0} teratas — selesaikan dulu, sisanya menyusul.", [items.length]) : "");
}

function ac_card(state, data, item) {
	const subtitle = (item.subtitle || [])
		.map(
			(s) =>
				`<span class="ac-chip"><span class="ac-chip-label">${frappe.utils.escape_html(s.label)}</span>${frappe.utils.escape_html(s.value)}</span>`
		)
		.join("");

	// A named approver that isn't the current user is the single most common reason an
	// Approve click would fail, so say it up front instead of after the attempt.
	let approver = "";
	if (item.expected_approver) {
		const mine = item.expected_approver === state.user;
		approver = `<span class="ac-approver ${mine ? "is-mine" : ""}">
			${ac_icon("user", 12)}${mine ? __("Giliran Anda") : __("Menunggu {0}", [frappe.utils.escape_html(item.expected_approver)])}
		</span>`;
	}

	const actions = (item.actions || [])
		.map((a) => {
			const kind = /reject|cancel|tolak/i.test(a.action) ? "danger" : "primary";
			const ico = kind === "danger" ? "x" : "check";
			return `<button type="button" class="ac-btn ac-btn-${kind}"
				data-act="${frappe.utils.escape_html(a.action)}" data-name="${frappe.utils.escape_html(item.name)}"
				title="${frappe.utils.escape_html(a.action)} → ${frappe.utils.escape_html(a.next_state || "")}">
				${ac_icon(ico, 13)}${frappe.utils.escape_html(a.action)}
			</button>`;
		})
		.join("");

	const no_actions = !(item.actions || []).length
		? `<span class="ac-note">${ac_icon("alert", 12)}${__("Tidak ada aksi yang tersedia untuk Anda")}</span>`
		: "";

	return `
	<div class="ac-card">
		<div class="ac-card-main">
			<div class="ac-card-head">
				<span class="ac-name" data-open="${frappe.utils.escape_html(item.name)}">${frappe.utils.escape_html(item.name)}</span>
				<span class="ac-state">${frappe.utils.escape_html(item.state || "")}</span>
				${item.level ? `<span class="ac-level">${__("Level {0}", [item.level])}</span>` : ""}
			</div>
			<div class="ac-amount">${item.amount === null || item.amount === undefined ? "—" : ac_rupiah(item.amount)}</div>
			<div class="ac-sub">
				${item.date ? `<span class="ac-chip"><span class="ac-chip-label">${__("Tanggal")}</span>${frappe.datetime.str_to_user(item.date)}</span>` : ""}
				${subtitle}
			</div>
			${item.detail ? `<div class="ac-detail">${frappe.utils.escape_html(item.detail)}</div>` : ""}
			<div class="ac-foot">${approver}${no_actions}</div>
		</div>
		<div class="ac-card-actions">
			${actions}
			<button type="button" class="ac-btn ac-btn-ghost" data-open="${frappe.utils.escape_html(item.name)}">
				${ac_icon("external", 13)}${__("Buka")}
			</button>
		</div>
	</div>`;
}

function ac_empty(text) {
	return `<div class="ac-empty">${ac_icon("inbox", 24)}<span>${frappe.utils.escape_html(text)}</span></div>`;
}

// ---------------------------------------------------------------------------
// Act
// ---------------------------------------------------------------------------

function ac_act(state, doctype, name, action) {
	frappe.confirm(
		__("Jalankan <b>{0}</b> untuk {1}?", [frappe.utils.escape_html(action), frappe.utils.escape_html(name)]),
		() => {
			frappe
				.call({
					method: "imogi_finance.api.approval_center.act",
					args: { doctype, name, action },
					freeze: true,
					freeze_message: __("Memproses {0}...", [action]),
				})
				.then((r) => {
					if (!r.message) return;
					frappe.show_alert({
						message: __("{0}: {1} → {2}", [name, action, r.message.state || "-"]),
						indicator: "green",
					});
					// Counts and the list both move, so reload both rather than patching the DOM.
					ac_load_overview(state, doctype);
				});
			// Errors surface through frappe's own error dialog (the backend throws with a
			// readable message, e.g. "You are not authorized to approve at level 1").
		}
	);
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ac_rupiah(n) {
	const v = Math.round(flt(n));
	return (v < 0 ? "−" : "") + "Rp " + Math.abs(v).toLocaleString("id-ID");
}

function ac_shell() {
	return `
	<div class="ac-root">
		<div class="ac-head">
			<div>
				<div class="ac-title">${__("Pusat Approval")}</div>
				<div class="ac-total" id="ac-total"></div>
			</div>
		</div>
		<div class="ac-body">
			<aside class="ac-side">
				<div class="ac-side-title">${__("Antrean")}</div>
				<div id="ac-menu"></div>
			</aside>
			<section class="ac-main">
				<div class="ac-main-head">
					<span class="ac-main-title" id="ac-list-title"></span>
					<span class="ac-main-meta" id="ac-list-meta"></span>
				</div>
				<div id="ac-list"></div>
				<div class="ac-foot-note" id="ac-truncated"></div>
			</section>
		</div>
	</div>`;
}

// ---------------------------------------------------------------------------
// Styles - same token set as Dashboard Manager so the two pages read as one product
// ---------------------------------------------------------------------------

const AC_TOKENS_LIGHT = `
		--ac-plane:#f6f6f4;
		--ac-surface:#ffffff;
		--ac-surface-2:#f1f0ec;
		--ac-surface-3:#e9e8e3;
		--ac-ink-1:#0b0b0b;
		--ac-ink-2:#52514e;
		--ac-ink-3:#898781;
		--ac-hairline:#e6e5e0;
		--ac-shadow:0 1px 2px rgba(11,11,11,.04),0 10px 26px -14px rgba(11,11,11,.14);
		--ac-accent:#2a78d6;
		--ac-good:#0ca30c;
		--ac-good-ink:#006300;
		--ac-crit:#d03b3b;
		--ac-crit-ink:#a32020;
		--ac-warn:#fab219;
		--ac-warn-ink:#845408;
`;

const AC_TOKENS_DARK = `
		--ac-plane:#141413;
		--ac-surface:#1e1e1d;
		--ac-surface-2:#282826;
		--ac-surface-3:#323230;
		--ac-ink-1:#ffffff;
		--ac-ink-2:#c3c2b7;
		--ac-ink-3:#898781;
		--ac-hairline:#2c2c2a;
		--ac-shadow:0 1px 2px rgba(0,0,0,.40),0 10px 26px -14px rgba(0,0,0,.60);
		--ac-accent:#3987e5;
		--ac-good:#0ca30c;
		--ac-good-ink:#0ca30c;
		--ac-crit:#d03b3b;
		--ac-crit-ink:#e66767;
		--ac-warn:#fab219;
		--ac-warn-ink:#fab219;
`;

const AC_CSS = `
	.ac-full-width > .page-head > .container,
	.ac-full-width > .container.page-body{max-width:none;width:100%;}
	.ac-root{${AC_TOKENS_LIGHT}
		color-scheme:light;background:var(--ac-plane);color:var(--ac-ink-1);
		border:1px solid var(--ac-hairline);border-radius:14px;padding:18px;font-size:13px;line-height:1.45;
		font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}
	[data-theme="dark"] .ac-root{${AC_TOKENS_DARK} color-scheme:dark;}
	@media (prefers-color-scheme: dark){
		:root:not([data-theme="light"]) .ac-root{${AC_TOKENS_DARK} color-scheme:dark;}
	}
	.ac-root *{box-sizing:border-box;}
	.ac-root.is-loading,.ac-root .is-loading{opacity:.55;pointer-events:none;}
	.ac-icon{flex:none;}

	.ac-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;}
	.ac-title{font-size:16px;font-weight:650;letter-spacing:-.01em;}
	.ac-total{font-size:12px;color:var(--ac-ink-3);margin-top:2px;}

	.ac-body{display:grid;grid-template-columns:minmax(200px,248px) minmax(0,1fr);gap:14px;align-items:start;}
	.ac-side{background:var(--ac-surface);border:1px solid var(--ac-hairline);border-radius:12px;
		box-shadow:var(--ac-shadow);padding:10px;position:sticky;top:12px;}
	.ac-side-title{font-size:10px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
		color:var(--ac-ink-3);padding:4px 8px 8px;}
	.ac-menu-item{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;
		appearance:none;border:0;background:transparent;color:var(--ac-ink-2);font:inherit;font-size:12.5px;
		text-align:left;padding:8px 9px;border-radius:8px;cursor:pointer;transition:background .14s,color .14s;}
	.ac-menu-item:hover{background:var(--ac-surface-2);color:var(--ac-ink-1);}
	.ac-menu-item.is-active{background:var(--ac-surface-3);color:var(--ac-ink-1);font-weight:600;}
	.ac-menu-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
	.ac-count{flex:none;min-width:22px;text-align:center;font-size:11px;font-weight:700;padding:1px 6px;
		border-radius:999px;background:var(--ac-surface-2);color:var(--ac-ink-3);font-variant-numeric:tabular-nums;}
	.ac-menu-item.is-active .ac-count{background:var(--ac-surface);}
	.ac-count.is-waiting{background:color-mix(in srgb,var(--ac-warn) 20%,transparent);color:var(--ac-warn-ink);}

	.ac-main{min-width:0;}
	.ac-main-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:2px 2px 10px;}
	.ac-main-title{font-size:13px;font-weight:650;}
	.ac-main-meta{font-size:11px;color:var(--ac-ink-3);font-variant-numeric:tabular-nums;}

	.ac-card{display:flex;gap:14px;align-items:flex-start;background:var(--ac-surface);
		border:1px solid var(--ac-hairline);border-radius:12px;box-shadow:var(--ac-shadow);
		padding:14px 15px;margin-bottom:10px;}
	.ac-card-main{flex:1 1 auto;min-width:0;}
	.ac-card-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:5px;}
	.ac-name{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:var(--ac-ink-2);
		cursor:pointer;}
	.ac-name:hover{color:var(--ac-accent);text-decoration:underline;}
	.ac-state{font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:999px;
		background:color-mix(in srgb,var(--ac-warn) 18%,transparent);color:var(--ac-warn-ink);white-space:nowrap;}
	.ac-level{font-size:10.5px;color:var(--ac-ink-3);}
	.ac-amount{font-size:19px;font-weight:650;letter-spacing:-.01em;margin-bottom:6px;}
	.ac-sub{display:flex;flex-wrap:wrap;gap:6px;}
	.ac-chip{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--ac-ink-2);
		background:var(--ac-surface-2);border-radius:7px;padding:2px 8px;max-width:100%;overflow:hidden;
		text-overflow:ellipsis;white-space:nowrap;}
	.ac-chip-label{color:var(--ac-ink-3);}
	.ac-detail{font-size:11.5px;color:var(--ac-ink-3);margin-top:7px;
		display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
	.ac-foot{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:9px;}
	.ac-approver{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--ac-ink-3);}
	.ac-approver.is-mine{color:var(--ac-good-ink);font-weight:650;}
	.ac-note{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--ac-crit-ink);}

	.ac-card-actions{flex:none;display:flex;flex-direction:column;gap:6px;min-width:132px;}
	.ac-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;appearance:none;
		border:1px solid transparent;border-radius:8px;font:inherit;font-size:12px;font-weight:600;
		padding:6px 11px;cursor:pointer;transition:filter .14s,background .14s;white-space:nowrap;}
	.ac-btn-primary{background:var(--ac-accent);color:#fff;}
	.ac-btn-danger{background:color-mix(in srgb,var(--ac-crit) 14%,transparent);color:var(--ac-crit-ink);}
	.ac-btn-ghost{background:var(--ac-surface-2);color:var(--ac-ink-2);}
	.ac-btn:hover{filter:brightness(1.06);}
	.ac-btn-ghost:hover{background:var(--ac-surface-3);color:var(--ac-ink-1);}

	.ac-empty{display:flex;flex-direction:column;align-items:center;gap:9px;padding:46px 12px;
		color:var(--ac-ink-3);font-size:12.5px;text-align:center;background:var(--ac-surface);
		border:1px solid var(--ac-hairline);border-radius:12px;}
	.ac-foot-note{font-size:11px;color:var(--ac-ink-3);margin-top:8px;}

	/* minmax(0,...) not 1fr: a long supplier chip in a card would otherwise set the track's
	   minimum width and push the whole page past the viewport. */
	@media (max-width:860px){
		.ac-body{grid-template-columns:minmax(0,1fr);}
		.ac-side{position:static;}
		.ac-card{flex-direction:column;}
		.ac-card-actions{flex-direction:row;width:100%;min-width:0;}
		.ac-card-actions .ac-btn{flex:1 1 auto;}
	}

	/* ---- phone ---- */
	@media (max-width:640px){
		.ac-root{padding:12px 10px 16px;border-radius:12px;}
		.ac-title{font-size:15px;}
		.ac-head{margin-bottom:12px;}
		.ac-body{gap:10px;}

		/* the queue menu becomes one scrollable row of chips - a 7-item vertical list
		   otherwise fills the whole first screen before any document is visible */
		.ac-side{padding:0;background:transparent;border:0;box-shadow:none;}
		.ac-side-title{display:none;}
		#ac-menu{display:flex;gap:6px;overflow-x:auto;padding:1px;
			-webkit-overflow-scrolling:touch;scrollbar-width:none;}
		#ac-menu::-webkit-scrollbar{display:none;}
		.ac-menu-item{flex:0 0 auto;width:auto;background:var(--ac-surface);
			border:1px solid var(--ac-hairline);padding:7px 11px;}
		.ac-menu-item.is-active{background:var(--ac-accent);color:#fff;border-color:transparent;}
		.ac-menu-item.is-active .ac-menu-label{color:#fff;}
		.ac-menu-label{max-width:150px;}
		.ac-menu-item.is-active .ac-count{background:rgba(255,255,255,.22);color:#fff;}

		.ac-card{padding:12px;border-radius:11px;}
		.ac-amount{font-size:17px;}
		.ac-card-head{gap:6px;}
		.ac-chip{max-width:100%;}
		.ac-btn{padding:9px 10px;}
		.ac-empty{padding:34px 12px;}
	}
	@media (prefers-reduced-motion: reduce){ .ac-root *{transition:none !important;} }
`;

function ac_inject_styles() {
	if (document.getElementById(AC_STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = AC_STYLE_ID;
	style.textContent = AC_CSS;
	document.head.appendChild(style);
}
