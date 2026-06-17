// Tarik DO Towing langsung dari Delivery Order (penagihan bulk)

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.doc.is_return) {
			return;
		}

		frm.add_custom_button(
			__("Tarik DO Towing"),
			() => pull_towing_from_delivery_orders(frm),
			__("Towing")
		);
	},

	posting_date(frm) {
		recalc_towing_payment_terms(frm);
	},
});

function get_invoice_company(frm) {
	return frm.doc.company || frappe.defaults.get_user_default("Company");
}

function ensure_invoice_company(frm) {
	const company = get_invoice_company(frm);
	if (!company) {
		frappe.msgprint({
			title: __("Company Belum Ter-set"),
			message: __(
				"Sales Invoice butuh Company (perusahaan penerbit invoice), bukan Customer. " +
				"Field Company mungkin tersembunyi — cek tab More Info, atau set Default Company di User Settings."
			),
			indicator: "orange",
		});
		return null;
	}

	if (!frm.doc.company) {
		frm.set_value("company", company);
	}
	return company;
}

function pull_towing_from_delivery_orders(frm) {
	const company = ensure_invoice_company(frm);
	if (!company) {
		return;
	}

	open_towing_delivery_order_dialog(frm, company);
}

function open_towing_delivery_order_dialog(frm, company) {
	let ms_dialog;

	const setters = [
		{
			fieldname: "billing_company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: company,
			reqd: 1,
			onchange() {
				frappe.flags.auto_scroll = false;
			},
		},
	];

	if (frm.doc.customer) {
		setters.push({
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
			default: frm.doc.customer,
			read_only: 1,
		});
	}

	ms_dialog = new frappe.ui.form.MultiSelectDialog({
		doctype: "Delivery Order Towing",
		target: frm,
		setters,
		size: "large",
		primary_action_label: __("Tarik DO"),
		columns: [
			"name",
			"company",
			"nomor_polisi",
			"status",
			"customer_name",
			"tanggal_do",
			"sales_order",
		],
		get_query() {
			const selected_company =
				ms_dialog?.dialog?.fields_dict?.billing_company?.get_value() || company;

			return {
				query: "imogi_finance.overrides.sales_invoice_towing.get_towing_delivery_order_query",
				filters: {
					company: selected_company,
					customer: frm.doc.customer || null,
				},
			};
		},
		action(delivery_orders, opts) {
			if (!delivery_orders || !delivery_orders.length) {
				frappe.msgprint(__("Pilih minimal 1 Delivery Order Towing."));
				return;
			}

			const dialog_company = opts?.billing_company || company;
			const pull = () => load_towing_items_into_invoice(frm, delivery_orders);

			// Tutup modal segera setelah user konfirmasi tarik DO.
			if (ms_dialog?.dialog) {
				ms_dialog.dialog.hide();
			}

			if (dialog_company && frm.doc.company !== dialog_company) {
				frm.set_value("company", dialog_company).then(pull);
				return;
			}
			pull();
		},
	});

	// Link field default kadang belum ter-set saat get_results() pertama dipanggil.
	setTimeout(() => ms_dialog.get_results(), 200);
}

function is_towing_invoice(frm) {
	return (frm.doc.items || []).some(
		(row) =>
			(row.item_name || "").startsWith("Jasa Towing") ||
			(row.description || "").includes("Jasa Towing")
	);
}

function get_towing_sales_orders(frm) {
	return [
		...new Set((frm.doc.items || []).map((row) => row.sales_order).filter(Boolean)),
	];
}

function apply_towing_payment_terms(frm, prefetched) {
	const company = get_invoice_company(frm);
	if (!frm.doc.customer || !company) {
		return Promise.resolve();
	}

	const sales_orders = get_towing_sales_orders(frm);
	if (!sales_orders.length && !prefetched?.payment_terms_template) {
		return Promise.resolve();
	}

	return frappe
		.call({
			method: "imogi_finance.overrides.sales_invoice_towing.get_towing_payment_info",
			args: {
				sales_orders,
				company,
				customer: frm.doc.customer,
				posting_date: frm.doc.posting_date || null,
				payment_terms_template:
					prefetched?.payment_terms_template || frm.doc.payment_terms_template || null,
				grand_total: frm.doc.rounded_total || frm.doc.grand_total || 0,
				base_grand_total: frm.doc.base_rounded_total || frm.doc.base_grand_total || 0,
			},
		})
		.then((r) => apply_payment_terms_response(frm, r.message));
}

function apply_payment_terms_response(frm, data) {
	if (!data) {
		return Promise.resolve();
	}

	const tasks = [];

	if (data.payment_terms_template) {
		tasks.push(frm.set_value("payment_terms_template", data.payment_terms_template));
	}

	return Promise.all(tasks).then(() => {
		if (data.payment_schedule?.length) {
			frm.set_value("payment_schedule", data.payment_schedule);
		}
		if (data.due_date) {
			frm.set_value("due_date", data.due_date);
		}
	});
}

function recalc_towing_payment_terms(frm) {
	if (!is_towing_invoice(frm)) {
		return;
	}
	apply_towing_payment_terms(frm);
}

function load_towing_items_into_invoice(frm, delivery_orders) {
	const company = get_invoice_company(frm);
	if (!company) {
		return;
	}

	frappe.dom.freeze(__("Mengambil data Delivery Order Towing..."));

	frappe.call({
		method: "imogi_finance.overrides.sales_invoice_towing.get_towing_invoice_items",
		args: {
			delivery_orders,
			company,
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

			const after_customer = !frm.doc.customer && data.customer
				? frm.set_value("customer", data.customer)
				: Promise.resolve();

			after_customer.then(() => {
				frm.clear_table("items");
				(data.items || []).forEach((row) => {
					const child = frm.add_child("items");
					Object.assign(child, row);
				});
				frm.refresh_field("items");

				return apply_towing_payment_terms(frm, data);
			}).then(() => {
				let message = __("✅ {0} baris DO Towing dimuat.", [data.do_count]);

				if (data.skipped && data.skipped.length) {
					message += "<br><br><b>" + __("Dilewati:") + "</b><br>";
					data.skipped.forEach((row) => {
						const label = row.delivery_order || row.sales_order || "-";
						message += `• ${frappe.utils.escape_html(label)} — ${frappe.utils.escape_html(row.reason)}<br>`;
					});
				}

				frappe.msgprint({
					title: __("Towing"),
					message,
					indicator: "green",
				});
			});
		},
		error() {
			frappe.dom.unfreeze();
		},
	});
}
