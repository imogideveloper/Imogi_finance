frappe.listview_settings["Budget"] = {
	add_fields: ["name", "cost_center", "fiscal_year", "custom_akun", "custom_budget_amount"],

	onload(listview) {
		const original_render = listview.render;

		listview.render = function (...args) {
			original_render.apply(this, args);

			setTimeout(() => {
				render_budget_list(listview);
			}, 80);
		};
	},
};

function render_budget_list(listview) {
	const $rows = listview.$result.find(".list-row-container");
	if (!$rows.length || !listview.data || !listview.data.length) return;

	// header
	const $header = listview.$result.find(".list-row-head");
	$header.html(`
       <div style="
    display:flex;
    width:100%;
    padding:10px 12px;
    font-weight:600;
    column-gap: 8px;
">
    <div style="flex: 2; white-space:nowrap;">ID</div>
    <div style="flex: 2; white-space:nowrap;">Cost Center</div>
    <div style="flex: 1; white-space:nowrap;">Fiscal Year</div>
    <div style="flex: 3; white-space:nowrap;">Akun</div>
    <div style="flex: 2; white-space:nowrap; text-align:right;">Budget Amount</div>
</div>
    `);

	// rows
	$rows.each(function (i) {
		const doc = listview.data[i];
		if (!doc) return;

		const html = `
            <div style="
               display:flex;
    width:100%;
    padding:10px 12px;
    column-gap: 8px;
            ">
                <div style="flex: 2; white-space:nowrap;">
                    <a href="/app/budget/${doc.name}" style="font-weight:600;">
                        ${frappe.utils.escape_html(doc.name || "")}
                    </a>
                </div>

                <div style="flex: 2; white-space:nowrap;">
                    ${frappe.utils.escape_html(doc.cost_center || "-")}
                </div>

                <div style="flex: 1; white-space:nowrap;">
                    ${frappe.utils.escape_html(doc.fiscal_year || "-")}
                </div>

                <div style="flex: 3; white-space:nowrap;">
                    ${frappe.utils.escape_html(doc.custom_akun || "-")}
                </div>

                <div style="flex: 2; white-space:nowrap; text-align:right;padding-right: 10px;">
                    ${format_currency(doc.custom_budget_amount || 0)}
                </div>
            </div>
        `;

		$(this).html(html);
	});
}
