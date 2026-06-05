// Tarik DO Towing dari satu atau banyak Sales Order (penagihan bulk)

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.doc.is_return) {
			return;
		}

		frm.add_custom_button(
			__("Tarik DO Towing dari SO"),
			() => pull_towing_from_sales_orders(frm),
			__("Towing")
		);
	},
});

function pull_towing_from_sales_orders(frm) {
	if (!frm.doc.company) {
		frappe.msgprint({
			title: __("Company Belum Diisi"),
			message: __("Isi Company terlebih dahulu."),
			indicator: "orange",
		});
		return;
	}

	const setters = { company: frm.doc.company };
	const read_only_setters = ["company"];

	if (frm.doc.customer) {
		setters.customer = frm.doc.customer;
		read_only_setters.push("customer");
	}

	new frappe.ui.form.MultiSelectDialog({
		doctype: "Sales Order",
		target: frm,
		setters,
		read_only_setters,
		size: "large",
		primary_action_label: __("Tarik DO"),
		get_query() {
			const filters = { company: frm.doc.company };
			if (frm.doc.customer) {
				filters.customer = frm.doc.customer;
			}
			return {
				query: "imogi_finance.overrides.sales_invoice_towing.get_towing_sales_order_query",
				filters,
			};
		},
		action(selections) {
			if (!selections || !selections.length) {
				frappe.msgprint(__("Pilih minimal 1 Sales Order."));
				return;
			}
			load_towing_items_into_invoice(frm, selections);
		},
	});
}

function load_towing_items_into_invoice(frm, sales_orders) {
	frappe.dom.freeze(__("Mengambil DO Towing dari Sales Order..."));

	frappe.call({
		method: "imogi_finance.overrides.sales_invoice_towing.get_towing_invoice_items",
		args: {
			sales_orders,
			company: frm.doc.company,
			customer: frm.doc.customer || null,
			exclude_invoiced: 1,
			posting_date: frm.doc.posting_date || null,
		},
		callback(r) {
			frappe.dom.unfreeze();
			if (!r.message) {
				return;
			}

			const data = r.message;

			if (!frm.doc.customer && data.customer) {
				frm.set_value("customer", data.customer);
			}
			if (data.payment_terms_template) {
				frm.set_value("payment_terms_template", data.payment_terms_template);
			}
			if (data.due_date) {
				frm.set_value("due_date", data.due_date);
			}

			frm.clear_table("items");
			(data.items || []).forEach((row) => {
				const child = frm.add_child("items");
				Object.assign(child, row);
			});
			frm.refresh_field("items");

			let message = __("✅ {0} baris DO Towing dimuat dari {1} Sales Order.", [
				data.do_count,
				(data.so_summaries || []).length,
			]);

			if (data.skipped && data.skipped.length) {
				message += "<br><br><b>" + __("Dilewati:") + "</b><br>";
				data.skipped.forEach((row) => {
					message += `• ${frappe.utils.escape_html(row.sales_order)} — ${frappe.utils.escape_html(row.reason)}<br>`;
				});
			}

			frappe.msgprint({
				title: __("Towing"),
				message,
				indicator: "green",
			});
		},
		error() {
			frappe.dom.unfreeze();
		},
	});
}
