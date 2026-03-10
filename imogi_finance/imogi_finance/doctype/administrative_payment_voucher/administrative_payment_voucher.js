frappe.ui.form.on("Administrative Payment Voucher", {
	refresh(frm) {
		const approved = ["Approved", "Posted"].includes(frm.doc.workflow_state || frm.doc.status);
		const can_create = approved && !frm.doc.payment_entry;

		if (can_create) {
			frm.add_custom_button(__("Create Payment Entry"), () => {
				frm.call("create_payment_entry_from_client").then((r) => {
					const name = r.message && r.message.payment_entry;
					if (name) {
						frappe.show_alert({ message: __("Payment Entry {0} created", [name]), indicator: "green" });
						frm.reload_doc();
						frappe.set_route("Form", "Payment Entry", name);
					}
				});
			});
		}

		if (frm.doc.payment_entry) {
			frm.add_custom_button(__("View Payment Entry"), () => {
				frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
			});
			frm.dashboard.add_indicator(
				__("Payment Entry {0}", [frm.doc.payment_entry]),
				"green",
				() => frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry)
			);
		}
	},
});
