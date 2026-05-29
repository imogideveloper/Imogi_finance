const SSA_LIST_INTRO =
	"<strong>Assignment Contract</strong> — Daftar kontrak penugasan gaji karyawan. " +
	"Contract submitted menjadi riwayat dan <b>Komponen Gaji</b> terkunci. " +
	"Gunakan <b>Buat Contract Baru</b> untuk perubahan atau perpanjangan.";

/** Hanya filter ini yang ditampilkan di baris atas list. */
const SSA_ALLOWED_FILTER_FIELDS = new Set([
	"name",
	"employee",
	"salary_structure",
	"from_date",
	"end_date",
	"status",
]);

frappe.listview_settings["Salary Structure Assignment"] = {
	add_fields: ["employee", "employee_name", "salary_structure", "from_date", "end_date", "status", "renewed_by_assignment_contract"],
	onload(listview) {
		set_ssa_list_intro(listview);
		patch_ssa_filter_area(listview);
		schedule_rebuild_ssa_standard_filters(listview);
	},
	refresh(listview) {
		set_ssa_list_intro(listview);
		schedule_rebuild_ssa_standard_filters(listview);
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

function patch_ssa_filter_area(listview) {
	if (!listview?.filter_area || listview.filter_area._ssa_patched) {
		return;
	}
	listview.filter_area._ssa_patched = true;
	listview.filter_area.make_standard_filters = function () {
		rebuild_ssa_standard_filters(listview);
	};
}

function schedule_rebuild_ssa_standard_filters(listview) {
	[0, 200, 600].forEach((ms) => {
		setTimeout(() => rebuild_ssa_standard_filters(listview), ms);
	});
}

function rebuild_ssa_standard_filters(listview) {
	const $wrapper = listview?.page?.page_form?.find(".standard-filter-section");
	if (!$wrapper?.length || !listview.filter_area) {
		return;
	}

	// Bersihkan semua filter standar lalu bangun ulang (hindari duplikat).
	Object.keys(listview.page.fields_dict || {}).forEach((key) => {
		const field = listview.page.fields_dict[key];
		if (!field?.df?.is_filter) {
			return;
		}
		field.$wrapper?.remove();
		delete listview.page.fields_dict[key];
	});

	$wrapper.empty();

	const onchange = () => listview.filter_area.debounced_refresh_list_view();
	const fields = [
		{
			fieldtype: "Data",
			label: __("ID"),
			fieldname: "name",
			condition: "like",
			onchange,
			is_filter: 1,
		},
		{
			fieldtype: "Link",
			label: __("Employee"),
			fieldname: "employee",
			options: "Employee",
			condition: "=",
			onchange,
			is_filter: 1,
		},
		{
			fieldtype: "Link",
			label: __("Salary Structure"),
			fieldname: "salary_structure",
			options: "Salary Structure",
			condition: "=",
			onchange,
			is_filter: 1,
		},
		{
			fieldtype: "Date",
			label: __("From Date"),
			fieldname: "from_date",
			condition: "=",
			onchange,
			is_filter: 1,
		},
		{
			fieldtype: "Date",
			label: __("End Date"),
			fieldname: "end_date",
			condition: "=",
			onchange,
			is_filter: 1,
		},
		{
			fieldtype: "Select",
			label: __("Status"),
			fieldname: "status",
			options: "\nActivate\nExpired Soon\nExpired",
			condition: "=",
			onchange,
			is_filter: 1,
		},
	];

	fields.forEach((df) => listview.page.add_field(df, $wrapper));
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
