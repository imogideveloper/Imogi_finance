// Peningkatan UX + tampilan minimalis untuk Salary Structure Assignment.
// File ini ADDITIF terhadap salary_structure_assignment.js (boleh ada banyak
// frappe.ui.form.on untuk doctype yang sama). CSS di-inject terscope ke
// kelas .ssa-form sehingga tidak memengaruhi doctype lain.

frappe.ui.form.on("Salary Structure Assignment", {
	setup(frm) {
		inject_ssa_styles();
	},

	onload(frm) {
		// From Date default hari ini untuk dokumen baru.
		if (frm.is_new() && !frm.doc.from_date) {
			frm.set_value("from_date", frappe.datetime.get_today());
		}
	},

	refresh(frm) {
		frm.$wrapper.addClass("ssa-form");
		render_total_bar(frm);
	},

	salary_structure(frm) {
		// Auto-muat komponen dari struktur HANYA jika tabel masih kosong &
		// dokumen masih draft -> tidak menimpa input yang sudah ada.
		if (
			frm.doc.docstatus === 0 &&
			frm.doc.salary_structure &&
			!(frm.doc.salary_component_amounts || []).length
		) {
			auto_load_components(frm);
		}
	},

	currency(frm) {
		render_total_bar(frm);
	},
});

// Recompute total setiap nilai komponen berubah.
frappe.ui.form.on("Salary Structure Assignment Component", {
	amount(frm) {
		render_total_bar(frm);
	},
	salary_component(frm) {
		render_total_bar(frm);
	},
	salary_component_amounts_remove(frm) {
		render_total_bar(frm);
	},
	salary_component_amounts_add(frm) {
		render_total_bar(frm);
	},
});

// --------------------------------------------------------------------------- //
// Baris Total                                                                 //
// --------------------------------------------------------------------------- //
function render_total_bar(frm) {
	const field = frm.fields_dict.salary_component_amounts;
	if (!field || !field.$wrapper) {
		return;
	}

	const rows = frm.doc.salary_component_amounts || [];
	const total = rows.reduce((sum, row) => sum + flt(row.amount), 0);

	field.$wrapper.find(".ssa-total-bar").remove();
	if (!rows.length) {
		return;
	}

	const formatted = format_currency(total, frm.doc.currency || "IDR");
	const $bar = $(`
		<div class="ssa-total-bar">
			<span class="ssa-total-label">${__("Total Komponen Gaji")}</span>
			<span class="ssa-total-value">${frappe.utils.escape_html(formatted)}</span>
		</div>
	`);
	field.$wrapper.append($bar);
}

// --------------------------------------------------------------------------- //
// Auto-muat komponen dari Salary Structure                                    //
// --------------------------------------------------------------------------- //
function auto_load_components(frm) {
	frappe.db.get_doc("Salary Structure", frm.doc.salary_structure).then((struct) => {
		const earnings = (struct.earnings || []).filter((row) => row.salary_component);
		if (!earnings.length) {
			return;
		}
		frm.clear_table("salary_component_amounts");
		earnings.forEach((row) => {
			const child = frm.add_child("salary_component_amounts");
			child.salary_component = row.salary_component;
			child.amount = flt(row.amount) || 0;
		});
		frm.refresh_field("salary_component_amounts");
		render_total_bar(frm);
		frappe.show_alert({
			message: __("Komponen otomatis dimuat dari {0}", [frm.doc.salary_structure]),
			indicator: "green",
		});
	});
}

// --------------------------------------------------------------------------- //
// CSS minimalis (scoped .ssa-form)                                            //
// --------------------------------------------------------------------------- //
function inject_ssa_styles() {
	if (document.getElementById("ssa-form-styles")) {
		return;
	}
	const css = `
.ssa-form .form-message {
	border: none;
	border-left: 3px solid var(--blue-500, #2490ef);
	border-radius: 0;
	background: var(--blue-50, #f0f8ff);
	padding: 11px 16px;
	font-size: var(--text-sm);
}
.ssa-form .form-section { padding-top: 6px; padding-bottom: 6px; }
.ssa-form .section-head {
	font-size: 11px;
	font-weight: 600;
	letter-spacing: 0.06em;
	text-transform: uppercase;
	color: var(--text-muted);
	padding-bottom: 8px;
	margin-bottom: 14px;
	border-bottom: 1px solid var(--border-color);
}
.ssa-form .form-column .frappe-control { margin-bottom: 12px; }
.ssa-form .control-label { font-size: var(--text-sm); color: var(--text-muted); }
.ssa-form .grid-heading-row {
	background: var(--subtle-fg, var(--gray-50));
	font-size: 11px;
	letter-spacing: 0.03em;
	text-transform: uppercase;
}
.ssa-form .grid-body .grid-row { border-color: var(--border-color); }
.ssa-form .grid-row [data-fieldname="amount"] .static-area,
.ssa-form .grid-row [data-fieldname="amount"] input {
	text-align: right;
	font-variant-numeric: tabular-nums;
}
.ssa-form .ssa-total-bar {
	display: flex;
	justify-content: space-between;
	align-items: center;
	padding: 14px 8px 4px;
	margin-top: 6px;
	border-top: 1.5px solid var(--border-color);
}
.ssa-form .ssa-total-label { font-size: var(--text-md); color: var(--text-muted); }
.ssa-form .ssa-total-value {
	font-size: var(--text-lg);
	font-weight: 600;
	font-variant-numeric: tabular-nums;
	color: var(--text-color);
}
`;
	const style = document.createElement("style");
	style.id = "ssa-form-styles";
	style.textContent = css;
	document.head.appendChild(style);
}