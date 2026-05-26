frappe.ui.form.on("Salary Structure Assignment", {
	refresh(frm) {
		if (frm.layout && frm.layout.message) {
			frm.layout.message.empty().addClass("hidden");
		}
		frm.layout.show_message(
			`<div>${__(
				"<strong>Assignment Contract</strong> — Kontrak penugasan gaji karyawan. "
				+ "Isi komponen di tabel <b>Komponen Gaji</b> (Add Row → Salary Component → Nilai). "
				+ "<b>Nilai = nominal bulanan</b> (bukan per hari)."
			)}</div>`,
			"blue",
			true
		);

		// Submitted: tetap boleh add/delete baris komponen
		if (frm.doc.docstatus === 1) {
			frm.set_df_property("salary_component_amounts", "cannot_add_rows", 0);
			frm.set_df_property("salary_component_amounts", "cannot_delete_rows", 0);
		}

		if (frm.doc.salary_structure) {
			frm.add_custom_button(__("Muat Komponen dari Struktur"), () =>
				load_from_salary_structure(frm)
			);
		}

		if (frm.fields_dict.status) {
			frm.set_df_property("status", "read_only", 1);
		}
	},

	from_date(frm) {
		validate_end_date(frm);
	},

	end_date(frm) {
		validate_end_date(frm);
		update_status_preview(frm);
	},
});

function validate_end_date(frm) {
	if (!frm.doc.from_date || !frm.doc.end_date) {
		return;
	}
	if (frappe.datetime.get_diff(frm.doc.end_date, frm.doc.from_date) < 0) {
		frappe.msgprint(__("End Date tidak boleh lebih kecil dari From Date."));
		frm.set_value("end_date", "");
	}
}

function update_status_preview(frm) {
	if (!frm.fields_dict.status) {
		return;
	}
	const expired =
		frm.doc.end_date && frappe.datetime.get_diff(frappe.datetime.get_today(), frm.doc.end_date) > 0;
	frm.set_value("status", expired ? "Expired" : "Active");
}

function load_from_salary_structure(frm) {
	if (!frm.doc.salary_structure) {
		frappe.msgprint(__("Pilih Salary Structure terlebih dahulu."));
		return;
	}

	if (frm.doc.salary_component_amounts?.length) {
		frappe.confirm(
			__("Tabel Komponen Gaji sudah berisi baris. Ganti dengan komponen dari struktur?"),
			() => fetch_structure_components(frm),
			() => {}
		);
		return;
	}

	fetch_structure_components(frm);
}

function fetch_structure_components(frm) {
	frappe.call({
		method: "frappe.client.get",
		args: { doctype: "Salary Structure", name: frm.doc.salary_structure },
		callback(r) {
			const struct = r.message;
			if (!struct) return;

			const rows = [];
			(struct.earnings || []).forEach((row) => {
				if (!row.salary_component) return;
				rows.push({
					salary_component: row.salary_component,
					amount: flt(row.amount) || 0,
				});
			});

			if (!rows.length) {
				frappe.msgprint(__("Tidak ada komponen earning di struktur ini."));
				return;
			}

			frm.clear_table("salary_component_amounts");
			rows.forEach((row) => {
				const child = frm.add_child("salary_component_amounts");
				child.salary_component = row.salary_component;
				child.amount = row.amount;
			});
			frm.refresh_field("salary_component_amounts");

			frappe.show_alert({
				message: __("Komponen dimuat dari {0}", [frm.doc.salary_structure]),
				indicator: "green",
			});
		},
	});
}
