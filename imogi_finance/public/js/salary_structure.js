frappe.ui.form.on("Salary Structure", {
	refresh(frm) {
		if (!frm.fields_dict.employer_contributions) {
			return;
		}
		frm.set_df_property("employer_contributions", "cannot_add_rows", true);
		frm.set_df_property("employer_contributions", "cannot_delete_rows", true);
	},
});
