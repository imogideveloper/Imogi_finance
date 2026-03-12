frappe.listview_settings["Tax Invoice OCR Upload"] = {
    add_fields: [
        "name",
        "custom_tanggal_faktur_pajak",
        "custom_display_supplier_text",
        "dpp",
        "verification_status",
        "custom_used_in",
        "custom_fp_status"
    ],

    onload(listview) {
        const original_render = listview.render;

        listview.render = function (...args) {
            original_render.apply(this, args);

            setTimeout(() => {
                render_tax_invoice_list(listview);
            }, 80);
        };
    }
};

function render_tax_invoice_list(listview) {
    const $rows = listview.$result.find(".list-row-container");
    if (!$rows.length || !listview.data || !listview.data.length) return;

    const $header = listview.$result.find(".list-row-head");
    $header.html(`
        <div style="
            display: flex;
            width: 100%;
            padding: 10px 12px;
            font-weight: 600;
            column-gap: 8px;
        ">
            <div style="flex: 2; white-space:nowrap;">ID</div>
            <div style="flex: 1; white-space:nowrap;">Date</div>
            <div style="flex: 2; white-space:nowrap;">Supplier</div>
            <div style="flex: 2; white-space:nowrap; text-align:left;">DPP</div>
            <div style="flex: 2; white-space:nowrap;">Verification Status</div>
            <div style="flex: 2; white-space:nowrap;">Used In</div>
            <div style="flex: 1; white-space:nowrap;">FP Status</div>
        </div>
    `);

    $rows.each(function (i) {
        const doc = listview.data[i];
        if (!doc) return;

        const html = `
            <div style="
                display: flex;
                width: 100%;
                padding: 10px 12px;
                column-gap: 8px;
                align-items: center;
            ">
                <div style="flex: 2; white-space:nowrap;">
                    <a href="/app/tax-invoice-ocr-upload/${doc.name}" style="font-weight:600;">
                        ${frappe.utils.escape_html(doc.name || "")}
                    </a>
                </div>

                <div style="flex: 1; white-space:nowrap;">
                    ${format_date_value(doc.custom_tanggal_faktur_pajak)}
                </div>

                <div style="flex: 2; white-space:nowrap;">
                    ${frappe.utils.escape_html(doc.custom_display_supplier_text || "-")}
                </div>

                <div style="flex: 2; white-space:nowrap; text-align:left; padding-right: 10px;">
                    ${format_currency(doc.dpp || 0)}
                </div>

                <div style="flex: 2; white-space:nowrap;">
                    ${get_verification_badge(doc.verification_status)}
                </div>

                <div style="flex: 2; white-space:nowrap;">
                    ${frappe.utils.escape_html(doc.custom_used_in || "-")}
                </div>

                <div style="flex: 1; white-space:nowrap;">
                    ${get_fp_status_badge(doc.custom_fp_status)}
                </div>
            </div>
        `;

        $(this).html(html);
    });
}

function format_date_value(value) {
    if (!value) return "-";
    return frappe.datetime.str_to_user(value);
}

function get_verification_badge(value) {
    if (!value) return "-";
    if (value === "Verified") return `<span class="indicator-pill green">Verified</span>`;
    if (value === "Needs Review") return `<span class="indicator-pill orange">Needs Review</span>`;
    return value;
}

function get_fp_status_badge(value) {
    if (!value) return "-";
    if (value === "Available") return `<span class="indicator-pill green">Available</span>`;
    if (value === "Used") return `<span class="indicator-pill orange">Used</span>`;
    if (value === "Released") return `<span class="indicator-pill blue">Released</span>`;
    return value;
}