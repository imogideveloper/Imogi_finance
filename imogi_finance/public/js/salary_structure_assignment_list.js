const SSA_LIST_INTRO =
	"<strong>Assignment Contract</strong> — Daftar kontrak penugasan gaji karyawan. " +
	"Contract submitted menjadi riwayat dan <b>Komponen Gaji</b> terkunci. " +
	"Gunakan <b>Buat Contract Baru</b> untuk perubahan atau perpanjangan.";

frappe.listview_settings["Salary Structure Assignment"] = {
	add_fields: ["employee", "salary_structure", "from_date", "end_date", "status", "renewed_by_assignment_contract"],
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
		if (is_expired_soon(doc)) {
			return [__("Expired Soon"), "orange", "status,=,Expired Soon"];
		}
		return [__("Activate"), "green", "status,=,Activate"];
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
	if (doc.renewed_by_assignment_contract) {
		return true;
	}
	return doc.end_date && frappe.datetime.get_diff(frappe.datetime.get_today(), doc.end_date) > 0;
}

function is_expired_soon(doc) {
	if (doc.status === "Expired Soon") {
		return true;
	}
	if (!doc.end_date || doc.renewed_by_assignment_contract) {
		return false;
	}
	const days_until_end = frappe.datetime.get_diff(doc.end_date, frappe.datetime.get_today());
	return days_until_end >= 0 && days_until_end <= 30;
}
