frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        relocate_generate_detail_button(frm);
        setup_imogi_sales_invoice_button(frm);
        setup_so_payment_status_indicator(frm);
        setTimeout(() => {
            relocate_generate_detail_button(frm);
            setup_imogi_sales_invoice_button(frm);
            setup_so_payment_status_indicator(frm);
        }, 300);
    },
});

const SO_FORM_STATUS_COLORS = {
    Draft: "grey",
    Submitted: "blue",
    "SI Created": "blue",
    "Outstanding Invoice": "orange",
    "Partial Paid": "orange",
    Paid: "green",
    Cancelled: "red",
};

function normalize_so_form_payment_status(status) {
    const value = (status || "").trim();
    if (value === "Partial Paid") return "Outstanding Invoice";
    return value || "Submitted";
}

function setup_so_payment_status_indicator(frm) {
    if (!frm.page) return;
    inject_so_form_status_styles();

    if (frm.doc.docstatus === 2) {
        frm.page.set_indicator(__("Cancelled"), "red");
        return;
    }
    if (frm.doc.docstatus === 0) {
        frm.page.set_indicator(__("Draft"), "grey");
        return;
    }

    const status = normalize_so_form_payment_status(frm.doc.custom_payment_status);
    const color = SO_FORM_STATUS_COLORS[status] || "blue";
    frm.page.set_indicator(__(status), color);
}

function setup_imogi_sales_invoice_button(frm) {
    if (frm.doc.docstatus !== 1 || flt(frm.doc.per_billed) >= 100) return;
    if (!frappe.model.can_create("Sales Invoice")) return;

    frm.remove_custom_button(__("Sales Invoice"), __("Create"));
    frm.add_custom_button(
        __("Sales Invoice"),
        () => show_imogi_create_sales_invoice_dialog(frm),
        __("Create")
    );
}

function show_imogi_create_sales_invoice_dialog(frm) {
    frappe.call({
        method: "imogi_finance.sales_invoice_from_so.get_so_billing_summary",
        args: { sales_order: frm.doc.name },
        freeze: true,
        freeze_message: __("Loading…"),
        callback(r) {
            const summary = r.message || {};
            if (flt(summary.remaining_amount) <= 0) {
                frappe.msgprint(__("This Sales Order is already fully billed."));
                return;
            }
            open_imogi_create_sales_invoice_dialog(frm, summary);
        },
    });
}

function open_imogi_create_sales_invoice_dialog(frm, summary) {
    const currency = summary.currency || frm.doc.currency;
    const remaining_fmt = format_currency(summary.remaining_amount, currency);
    const grand_fmt = format_currency(summary.grand_total, currency);

    const d = new frappe.ui.Dialog({
        title: __("Create Sales Invoice"),
        fields: [
            {
                fieldtype: "HTML",
                fieldname: "intro_html",
                options: `<p class="text-muted small" style="margin-bottom:12px">${__(
                    "Invoices are created as draft so you can review before submit."
                )}</p>
                <p style="margin:0 0 4px"><strong>${__("Order Total")}:</strong> ${grand_fmt}</p>
                <p style="margin:0 0 12px"><strong>${__("Remaining to Bill")}:</strong> ${remaining_fmt}</p>
                <p class="text-muted small" style="margin:0">${__(
                    "Down payment keeps Qty from the Sales Order; Rate and Amount are reduced."
                )}</p>`,
            },
            {
                fieldtype: "Data",
                fieldname: "invoice_mode",
                hidden: 1,
                default: "regular",
            },
            {
                fieldtype: "HTML",
                fieldname: "invoice_mode_radios",
                label: __("Create Invoice"),
                options: build_imogi_invoice_mode_radios_html(),
            },
            {
                fieldtype: "Int",
                fieldname: "percentage",
                label: __("Down Payment (%)"),
                default: 50,
                depends_on: 'eval:doc.invoice_mode=="percentage"',
            },
            {
                fieldtype: "Currency",
                fieldname: "fixed_amount",
                label: __("Down Payment Amount"),
                options: currency,
                default: summary.remaining_amount,
                depends_on: 'eval:doc.invoice_mode=="fixed_amount"',
            },
            {
                fieldtype: "HTML",
                fieldname: "preview_html",
                options: "",
            },
        ],
        primary_action_label: __("Create Invoice"),
        primary_action(values) {
            const mode = get_imogi_invoice_mode_from_dialog(d) || values.invoice_mode;
            const pct = normalize_imogi_down_payment_percent(
                d.get_value("percentage") ?? values.percentage
            );
            if (mode === "percentage" && pct <= 0) {
                frappe.msgprint(__("Enter a valid percentage."));
                return;
            }
            if (mode === "percentage" && pct > 100) {
                frappe.msgprint(__("Percentage cannot be greater than 100."));
                return;
            }
            if (mode === "fixed_amount" && flt(values.fixed_amount) <= 0) {
                frappe.msgprint(__("Enter a valid fixed amount."));
                return;
            }
            if (mode === "fixed_amount" && flt(values.fixed_amount) > flt(summary.remaining_amount)) {
                frappe.msgprint(
                    __("Fixed amount cannot exceed remaining billable amount {0}.", [remaining_fmt])
                );
                return;
            }

            d.hide();
            const mapper_args = {
                invoice_mode: mode,
                percentage: pct,
                fixed_amount: values.fixed_amount,
            };
            frappe.model.open_mapped_doc({
                method: "imogi_finance.sales_invoice_from_so.make_sales_invoice_with_payment_terms",
                frm: frm,
                freeze_message: __("Creating Sales Invoice…"),
                args: mapper_args,
            });
        },
    });

    bind_imogi_invoice_mode_radios(d, summary);
    toggle_imogi_si_dialog_fields(d, summary);
    d.show();
}

function build_imogi_invoice_mode_radios_html() {
    return `
        <div class="imogi-so-inv-modes" style="display:flex;flex-direction:column;gap:10px;margin-top:4px">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
                <input type="radio" name="imogi_so_inv_mode" value="regular" checked>
                <span>${__("Regular invoice")}</span>
            </label>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
                <input type="radio" name="imogi_so_inv_mode" value="percentage">
                <span>${__("Down payment (percentage)")}</span>
            </label>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
                <input type="radio" name="imogi_so_inv_mode" value="fixed_amount">
                <span>${__("Down payment (fixed amount)")}</span>
            </label>
        </div>`;
}

function normalize_imogi_down_payment_percent(value) {
    let pct = Math.round(flt(value));
    if (pct > 0 && pct <= 1) {
        pct = pct * 100;
    }
    return pct;
}

function get_imogi_invoice_mode_from_dialog(dialog) {
    const $checked = dialog.$wrapper.find('input[name="imogi_so_inv_mode"]:checked');
    return ($checked.val() || "regular").trim();
}

function bind_imogi_invoice_mode_radios(dialog, summary) {
    dialog.set_value("invoice_mode", "regular");
    dialog.$wrapper.find('input[name="imogi_so_inv_mode"]').on("change", function () {
        dialog.set_value("invoice_mode", $(this).val());
        toggle_imogi_si_dialog_fields(dialog, summary);
    });
}

function toggle_imogi_si_dialog_fields(dialog, summary) {
    const mode = get_imogi_invoice_mode_from_dialog(dialog) || dialog.get_value("invoice_mode") || "regular";
    dialog.set_value("invoice_mode", mode);
    const currency = summary.currency;
    let invoice_amount = flt(summary.remaining_amount);

    if (mode === "percentage") {
        const pct = normalize_imogi_down_payment_percent(dialog.get_value("percentage"));
        invoice_amount = (flt(summary.remaining_amount) * pct) / 100;
    } else if (mode === "fixed_amount") {
        invoice_amount = flt(dialog.get_value("fixed_amount"));
    }

    const remaining_after = Math.max(0, flt(summary.remaining_amount) - invoice_amount);
    const preview = `
        <div class="small" style="margin-top:8px;padding:10px;background:var(--subtle-fg);border-radius:8px">
            <div><strong>${__("This invoice")}:</strong> ${format_currency(invoice_amount, currency)}</div>
            <div style="margin-top:4px"><strong>${__("Remaining on SO after this invoice")}:</strong>
            ${format_currency(remaining_after, currency)}</div>
        </div>`;
    dialog.fields_dict.preview_html.$wrapper.html(preview);

    const pct_field = dialog.fields_dict.percentage;
    const fix_field = dialog.fields_dict.fixed_amount;
    if (pct_field) {
        pct_field.df.onchange = () => toggle_imogi_si_dialog_fields(dialog, summary);
    }
    if (fix_field) {
        fix_field.df.onchange = () => toggle_imogi_si_dialog_fields(dialog, summary);
    }
}

function relocate_generate_detail_button(frm) {
    const grid_field = frm.fields_dict?.custom_towing_kendaraan;
    const grid = grid_field?.grid;

    if (!grid || !grid.wrapper) return;

    const $wrapper = $(grid.wrapper);
    const $grid_buttons = $wrapper.find(".grid-buttons");
    if (!$grid_buttons.length) return;

    const label = __("Generate Detail Kendaraan");
    const button_class = "btn-generate-detail-kendaraan";

    $grid_buttons.find(`.${button_class}`).remove();

    const $existing_form_button = find_existing_generate_button(frm, label);
    if (!$existing_form_button.length) return;

    const $button = $(
        `<button class="btn btn-xs btn-secondary ${button_class}" type="button"></button>`
    ).text(label);

    $button.on("click", () => {
        $existing_form_button.trigger("click");
    });

    const $add_multiple_btn = $grid_buttons.find(".grid-add-multiple-rows");
    if ($add_multiple_btn.length) {
        $button.insertAfter($add_multiple_btn);
    } else {
        $grid_buttons.append($button);
    }

    $existing_form_button.hide();
}

function find_existing_generate_button(frm, label) {
    // Covers custom button in form actions/group button in toolbar.
    const selectors = [
        ".page-form .custom-actions button",
        ".inner-toolbar button",
        ".menu-btn-group button",
    ];

    for (const selector of selectors) {
        const $match = frm.page.wrapper
            .find(selector)
            .filter((_, el) => ($(el).text() || "").trim() === label);
        if ($match.length) return $match.first();
    }

    return $();
}

function inject_so_form_status_styles() {
    if (document.getElementById("so-form-status-style")) return;
    const style = document.createElement("style");
    style.id = "so-form-status-style";
    style.textContent =
        ".form-page .indicator-pill.orange{background:#fff4e8!important;color:#b45309!important;border:1px solid #fed7aa}" +
        ".form-page .indicator-pill.green{background:#ecfdf3!important;color:#166534!important;border:1px solid #bbf7d0}";
    document.head.appendChild(style);
}
