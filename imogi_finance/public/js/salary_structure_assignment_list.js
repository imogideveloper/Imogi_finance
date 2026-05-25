const SSA_LIST_INTRO =
	"<strong>Assignment Contract</strong> — Daftar kontrak penugasan gaji karyawan. " +
	"Buka baris untuk mengisi <b>Komponen Gaji</b> (Add Row → Salary Component → Nilai).";

frappe.listview_settings["Salary Structure Assignment"] = {
	onload(listview) {
		set_ssa_list_intro(listview);
	},
	refresh(listview) {
		set_ssa_list_intro(listview);
	},
};

function set_ssa_list_intro(listview) {
	if (!listview?.page?.set_intro) {
		return;
	}
	listview.page.set_intro(__(SSA_LIST_INTRO), true);
}
