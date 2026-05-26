const SSA_LIST_INTRO =
	"<strong>Assignment Contract</strong> — Daftar kontrak penugasan gaji karyawan. " +
	"Buka baris untuk mengisi <b>Komponen Gaji</b> (Add Row → Salary Component → Nilai).";

frappe.listview_settings["Salary Structure Assignment"] = {
	add_fields: ["from_date", "end_date", "status"],
	onload(listview) {
		set_ssa_list_intro(listview);
	},
	refresh(listview) {
		set_ssa_list_intro(listview);
	},
	get_indicator(doc) {
		if (doc.docstatus === 2) {
			return [__("Cancelled"), "red", "docstatus,=,2"];
		}
		if (doc.docstatus === 0) {
			return [__("Draft"), "gray", "docstatus,=,0"];
		}
		if (is_expired(doc)) {
			return [__("Expired"), "red", "end_date,<,Today"];
		}
		return [__("Active"), "green", "status,=,Active"];
	},
};

function set_ssa_list_intro(listview) {
	if (!listview?.page?.set_intro) {
		return;
	}
	listview.page.set_intro(__(SSA_LIST_INTRO), true);
}

function is_expired(doc) {
	if (doc.status === "Expired") {
		return true;
	}
	return doc.end_date && frappe.datetime.get_diff(frappe.datetime.get_today(), doc.end_date) > 0;
}
