/**
 * Item Tax Mapping — Auto-inject akun pajak ke transaksi
 * Cover: Sales Invoice, Sales Order, Quotation, Purchase Invoice, Purchase Order
 */
frappe.provide("imogi_finance.item_tax_mapping");

// ─── Core: Inject tax rows ke form ───────────────────────────────────────────

imogi_finance.item_tax_mapping.inject = function (frm, tax_rows, child_doctype) {
    if (!tax_rows || !tax_rows.length) return;

    const existing = (frm.doc.taxes || []).map((t) => t.account_head);
    let changed = false;

    tax_rows.forEach((row) => {
        if (existing.includes(row.account_head)) return;

        const child = frappe.model.add_child(frm.doc, child_doctype, "taxes");
        child.charge_type    = row.charge_type || "On Net Total";
        child.account_head   = row.account_head;
        child.rate           = flt(row.tax_rate);
        child.description    = row.description || row.account_head;
        child.add_deduct_tax = row.add_deduct_tax || "Add";
        child.category       = "Total";
        existing.push(row.account_head);
        changed = true;
    });

    if (changed) {
        imogi_finance.item_tax_mapping.recalculate(frm);
    }
};

imogi_finance.item_tax_mapping.recalculate = function (frm) {
    if (!frm) return;

    frm.refresh_field("taxes");

    const calculate = () => {
        const controller = frm.cscript || cur_frm?.cscript;
        if (controller?.calculate_taxes_and_totals) {
            controller.calculate_taxes_and_totals();
        } else if (frm.trigger) {
            frm.trigger("calculate_taxes_and_totals");
        }

        frm.refresh_fields([
            "taxes",
            "total_taxes_and_charges",
            "grand_total",
            "rounded_total",
        ]);
    };

    if (frappe.after_ajax) {
        frappe.after_ajax(calculate);
    } else {
        setTimeout(calculate, 0);
    }
};

imogi_finance.item_tax_mapping.apply_all = function (frm, transaction_type, child_doctype) {
    if (!frm.doc.company || !(frm.doc.items || []).length) return;

    (frm.doc.items || []).forEach((row) => {
        if (row.item_code) {
            imogi_finance.item_tax_mapping.apply(
                frm, row.item_code, transaction_type, child_doctype
            );
        }
    });

    setTimeout(() => imogi_finance.item_tax_mapping.recalculate(frm), 800);
};

// ─── Core: Fetch dari server lalu inject ──────────────────────────────────────

imogi_finance.item_tax_mapping.apply = function (frm, item_code, transaction_type, child_doctype) {
    if (!item_code || !frm.doc.company) return;

    frappe.call({
        method: "imogi_finance.api.item_tax_mapping.get_taxes_for_item",
        args: {
            item_code:        item_code,
            company:          frm.doc.company,
            transaction_type: transaction_type,
            customer:         frm.doc.customer || null,
        },
        callback: (r) => {
            if (r.message?.length) {
                imogi_finance.item_tax_mapping.inject(frm, r.message, child_doctype);
            }
        },
    });
};

// ─── Sales Invoice ────────────────────────────────────────────────────────────

frappe.ui.form.on("Sales Invoice Item", {
    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_code) return;
        setTimeout(() => {
            imogi_finance.item_tax_mapping.apply(
                frm, row.item_code, "Sales", "Sales Taxes and Charges"
            );
        }, 300);
    },
    qty(frm) {
        setTimeout(() => imogi_finance.item_tax_mapping.recalculate(frm), 100);
    },
    rate(frm) {
        setTimeout(() => imogi_finance.item_tax_mapping.recalculate(frm), 100);
    },
    amount(frm) {
        setTimeout(() => imogi_finance.item_tax_mapping.recalculate(frm), 100);
    },
});

frappe.ui.form.on("Sales Invoice", {
    refresh(frm) {
        if (frm.doc.docstatus !== 0) return;

        frm.add_custom_button(__("Apply Item Tax Mapping"), () => {
            imogi_finance.item_tax_mapping.apply_all(
                frm, "Sales", "Sales Taxes and Charges"
            );
        }, __("Taxes"));
    },
});

// ─── Sales Order ──────────────────────────────────────────────────────────────

frappe.ui.form.on("Sales Order Item", {
    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_code) return;
        setTimeout(() => {
            imogi_finance.item_tax_mapping.apply(
                frm, row.item_code, "Sales", "Sales Taxes and Charges"
            );
        }, 300);
    },
});

// ─── Quotation ────────────────────────────────────────────────────────────────

frappe.ui.form.on("Quotation Item", {
    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_code) return;
        setTimeout(() => {
            imogi_finance.item_tax_mapping.apply(
                frm, row.item_code, "Sales", "Sales Taxes and Charges"
            );
        }, 300);
    },
});

// ─── Purchase Invoice ─────────────────────────────────────────────────────────

frappe.ui.form.on("Purchase Invoice Item", {
    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_code) return;
        setTimeout(() => {
            imogi_finance.item_tax_mapping.apply(
                frm, row.item_code, "Purchase", "Purchase Taxes and Charges"
            );
        }, 300);
    },
});

// ─── Purchase Order ───────────────────────────────────────────────────────────

frappe.ui.form.on("Purchase Order Item", {
    item_code(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.item_code) return;
        setTimeout(() => {
            imogi_finance.item_tax_mapping.apply(
                frm, row.item_code, "Purchase", "Purchase Taxes and Charges"
            );
        }, 300);
    },
});

// ─── Item Tax Mapping Form (Preview & Test Lookup) ────────────────────────────

frappe.ui.form.on("Item Tax Mapping", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("Preview"), () => {
            frappe.call({
                method: "imogi_finance.api.item_tax_mapping.get_mapping_preview",
                args: { name: frm.doc.name },
                callback: (r) => {
                    if (!r.message) return;
                    const rows = r.message.taxes.map((t) =>
                        `<tr>
                            <td>${t.account_head}</td>
                            <td style="text-align:right">${t.tax_rate}%</td>
                            <td>${t.charge_type}</td>
                            <td>${t.add_deduct_tax}</td>
                        </tr>`
                    ).join("");
                    frappe.msgprint({
                        title: frm.doc.name,
                        indicator: "blue",
                        message: `
                            <b>Company:</b> ${r.message.company}<br>
                            <b>Item:</b> ${r.message.item_code || "-"} &nbsp;
                            <b>Item Group:</b> ${r.message.item_group || "-"}<br>
                            <b>Customer Group:</b> ${r.message.customer_group || "-"} &nbsp;
                            <b>Urutan Aturan:</b> ${r.message.priority}<br><br>
                            <table class="table table-bordered table-sm">
                                <thead><tr>
                                    <th>Account Head</th>
                                    <th>Rate</th>
                                    <th>Charge Type</th>
                                    <th>Add/Deduct</th>
                                </tr></thead>
                                <tbody>${rows}</tbody>
                            </table>`,
                    });
                },
            });
        });

        frm.add_custom_button(__("Test Lookup"), () => {
            frappe.prompt(
                [
                    {
                        fieldname: "item_code",
                        fieldtype: "Link",
                        options:   "Item",
                        label:     "Item",
                        reqd:      1,
                    },
                    {
                        fieldname: "transaction_type",
                        fieldtype: "Select",
                        options:   "Sales\nPurchase",
                        label:     "Transaction Type",
                        default:   frm.doc.transaction_type || "Sales",
                    },
                ],
                (v) => {
                    frappe.call({
                        method: "imogi_finance.api.item_tax_mapping.get_taxes_for_item",
                        args: {
                            item_code:        v.item_code,
                            company:          frm.doc.company,
                            transaction_type: v.transaction_type,
                        },
                        callback: (r) => {
                            if (r.message?.length) {
                                const rows = r.message.map((t) =>
                                    `<tr>
                                        <td>${t.account_head}</td>
                                        <td style="text-align:right">${t.tax_rate}%</td>
                                        <td>${t.charge_type}</td>
                                    </tr>`
                                ).join("");
                                frappe.msgprint({
                                    title:     __("Hasil untuk {0}", [v.item_code]),
                                    indicator: "green",
                                    message: `
                                        <table class="table table-bordered table-sm">
                                            <thead><tr>
                                                <th>Account Head</th>
                                                <th>Rate</th>
                                                <th>Charge Type</th>
                                            </tr></thead>
                                            <tbody>${rows}</tbody>
                                        </table>`,
                                });
                            } else {
                                frappe.msgprint({
                                    title:     __("Tidak Ada Mapping"),
                                    indicator: "orange",
                                    message:   __("Tidak ditemukan mapping untuk item <b>{0}</b> di company <b>{1}</b>.", [v.item_code, frm.doc.company]),
                                });
                            }
                        },
                    });
                },
                __("Test Lookup Item Tax Mapping"),
                __("Test")
            );
        });
    },
});