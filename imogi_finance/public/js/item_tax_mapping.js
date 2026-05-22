frappe.provide("imogi_finance.item_tax_mapping");

// Inject tax rows ke Sales Invoice
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
        changed = true;
    });

    if (changed) {
        frm.refresh_field("taxes");
        frm.taxes_and_totals?.calculate_taxes_and_totals?.();
    }
};

// Fetch dari server lalu inject
imogi_finance.item_tax_mapping.apply = function (frm, item_code, transaction_type, child_doctype) {
    if (!item_code || !frm.doc.company) return;
    frappe.call({
        method: "imogi_finance.api.item_tax_mapping.get_taxes_for_item",
        args: {
            item_code: item_code,
            company: frm.doc.company,
            transaction_type: transaction_type,
            customer: frm.doc.customer || null,
        },
        callback: (r) => {
            if (r.message?.length) {
                imogi_finance.item_tax_mapping.inject(frm, r.message, child_doctype);
            }
        },
    });
};

// ── Sales Invoice ─────────────────────────────────────────────────────────────
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
});

// ── Purchase Invoice ──────────────────────────────────────────────────────────
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

// ── Form Buttons (Preview & Test) ─────────────────────────────────────────────
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
                        `<tr><td>${t.account_head}</td><td>${t.tax_rate}%</td><td>${t.charge_type}</td></tr>`
                    ).join("");
                    frappe.msgprint({
                        title: frm.doc.name,
                        indicator: "blue",
                        message: `
                            <b>Item:</b> ${r.message.item_code || "-"} &nbsp;
                            <b>Item Group:</b> ${r.message.item_group || "-"}<br><br>
                            <table class="table table-bordered table-sm">
                                <thead><tr><th>Account</th><th>Rate</th><th>Type</th></tr></thead>
                                <tbody>${rows}</tbody>
                            </table>`,
                    });
                },
            });
        });

        frm.add_custom_button(__("Test Lookup"), () => {
            frappe.prompt(
                [{ fieldname: "item_code", fieldtype: "Link", options: "Item", label: "Item", reqd: 1 }],
                (v) => {
                    frappe.call({
                        method: "imogi_finance.api.item_tax_mapping.get_taxes_for_item",
                        args: { item_code: v.item_code, company: frm.doc.company, transaction_type: frm.doc.transaction_type },
                        callback: (r) => {
                            if (r.message?.length) {
                                const rows = r.message.map((t) =>
                                    `<tr><td>${t.account_head}</td><td>${t.tax_rate}%</td></tr>`
                                ).join("");
                                frappe.msgprint({
                                    title: __("Hasil untuk {0}", [v.item_code]),
                                    indicator: "green",
                                    message: `<table class="table table-bordered table-sm">
                                        <thead><tr><th>Account</th><th>Rate</th></tr></thead>
                                        <tbody>${rows}</tbody></table>`,
                                });
                            } else {
                                frappe.msgprint({ title: "Tidak Ada Mapping", indicator: "orange",
                                    message: __("Tidak ditemukan mapping untuk item {0}.", [v.item_code]) });
                            }
                        },
                    });
                }, "Test Lookup", "Test"
            );
        });
    },
});