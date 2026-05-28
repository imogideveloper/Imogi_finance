/**
 * Pastikan pajak dari Item Tax Template tertarik ke Sales Invoice (dan transaksi penjualan lain).
 * Perbaikan: baca setting dari boot.sysdefaults + isi rate dari template (bukan selalu 0).
 */
frappe.provide("imogi_finance.sales_invoice_tax");

imogi_finance.sales_invoice_tax.is_enabled = function () {
	return cint(
		frappe.boot?.sysdefaults?.add_taxes_from_item_tax_template ??
			frappe.defaults.get_default("add_taxes_from_item_tax_template")
	);
};

imogi_finance.sales_invoice_tax.patch_add_taxes_from_item = function (proto) {
	if (!proto || proto.__imogi_item_tax_patched) {
		return;
	}
	const original = proto.add_taxes_from_item_tax_template;
	proto.add_taxes_from_item_tax_template = function (item_tax_map) {
		if (!item_tax_map || !imogi_finance.sales_invoice_tax.is_enabled()) {
			return;
		}

		if (typeof item_tax_map === "string") {
			try {
				item_tax_map = JSON.parse(item_tax_map);
			} catch (e) {
				return;
			}
		}

		const keys = Object.keys(item_tax_map || {});
		if (!keys.length) {
			return;
		}

		let changed = false;
		$.each(item_tax_map, function (account_head, rate) {
			const found = (this.frm.doc.taxes || []).find((d) => d.account_head === account_head);
			if (found) {
				return;
			}
			const child = frappe.model.add_child(this.frm.doc, "taxes");
			child.charge_type = "On Net Total";
			child.account_head = account_head;
			child.rate = flt(rate);
			child.description = account_head;
			child.add_deduct_tax = "Add";
			child.category = "Total";
			changed = true;
		}.bind(this));

		if (changed) {
			this.frm.refresh_field("taxes");
			if (typeof this.calculate_taxes_and_totals === "function") {
				this.calculate_taxes_and_totals();
			}
		}
	};
	proto.__imogi_item_tax_patched = true;
};

function imogi_apply_item_tax_patches() {
	if (typeof erpnext === "undefined") {
		return false;
	}
	if (erpnext.taxes_and_totals?.prototype) {
		imogi_finance.sales_invoice_tax.patch_add_taxes_from_item(erpnext.taxes_and_totals.prototype);
	}
	return true;
}

if (typeof frappe !== "undefined" && typeof frappe.ready === "function") {
	frappe.ready(function () {
		if (!imogi_apply_item_tax_patches()) {
			setTimeout(imogi_apply_item_tax_patches, 500);
		}
	});
}

frappe.ui.form.on("Sales Invoice Item", {
	item_code(frm, cdt, cdn) {
		setTimeout(() => imogi_finance.sales_invoice_tax.sync_row_taxes(frm, cdt, cdn), 400);
	},
});

frappe.ui.form.on("Sales Invoice", {
	onload(frm) {
		imogi_finance.sales_invoice_tax.warn_company_mismatch(frm);
	},
	company(frm) {
		imogi_finance.sales_invoice_tax.warn_company_mismatch(frm);
	},
});

imogi_finance.sales_invoice_tax.sync_row_taxes = function (frm, cdt, cdn) {
	if (!frm || frm.doc.doctype !== "Sales Invoice") {
		return;
	}
	const row = locals[cdt]?.[cdn];
	if (!row?.item_tax_rate || row.item_tax_rate === "{}") {
		if (row?.item_code && row.item_tax_template) {
			frappe.show_alert({
				message: __(
					"Item Tax Template {0} tidak menghasilkan akun pajak. Cek Company SI sama dengan Company template, dan akun pajak di template.",
					[row.item_tax_template]
				),
				indicator: "orange",
			}, 8);
		}
		return;
	}
	const taxes_and_totals = frm.taxes_and_totals;
	if (taxes_and_totals?.add_taxes_from_item_tax_template) {
		taxes_and_totals.add_taxes_from_item_tax_template(row.item_tax_rate);
	}
};

imogi_finance.sales_invoice_tax.warn_company_mismatch = function (frm) {
	if (!frm?.doc?.company || !frm.doc.items?.length) {
		return;
	}
	for (const row of frm.doc.items) {
		if (!row.item_tax_template) {
			continue;
		}
		frappe.db.get_value("Item Tax Template", row.item_tax_template, "company", (r) => {
			const tpl_company = r?.message?.company;
			if (tpl_company && tpl_company !== frm.doc.company) {
				frappe.msgprint({
					title: __("Company tidak cocok"),
					indicator: "orange",
					message: __(
						"Item <b>{0}</b> memakai template <b>{1}</b> (Company: {2}). Sales Invoice memakai Company: <b>{3}</b>. Pajak tidak akan tertarik.",
						[row.item_code, row.item_tax_template, tpl_company, frm.doc.company]
					),
				});
			}
		});
	}
};
