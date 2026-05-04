function get_month_name(month) {
    const months = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    return months[month] || "-";
}

function format_period_label(doc) {
    if (doc.periode) return doc.periode;
    if (!doc.start_date) return "-";
    const d = frappe.datetime.str_to_obj(doc.start_date);
    return `${get_month_name(d.getMonth())} ${d.getFullYear()}`;
}

function get_status_label(doc) {
    if (doc.docstatus === 2) return __("Cancelled");
    if (doc.docstatus === 1) return __("Submitted");
    return __("Draft");
}

function group_docs_for_dropdown(docs) {
    const grouped = {};

    (docs || []).forEach((doc) => {
        const baseDate = doc.start_date ? frappe.datetime.str_to_obj(doc.start_date) : null;
        const year = baseDate ? `${baseDate.getFullYear()}` : __("No Year");
        const monthKey = baseDate ? `${String(baseDate.getMonth() + 1).padStart(2, "0")}-${get_month_name(baseDate.getMonth())}` : __("No Month");
        const status = get_status_label(doc);

        if (!grouped[year]) grouped[year] = {};
        if (!grouped[year][monthKey]) grouped[year][monthKey] = {};
        if (!grouped[year][monthKey][status]) grouped[year][monthKey][status] = [];

        grouped[year][monthKey][status].push(doc);
    });

    return grouped;
}

function render_dropdown_view(listview) {
    if (!listview.$custom_dropdown_view) {
        listview.$custom_dropdown_view = $(`<div class="payroll-entry-dropdown-view"></div>`);
        listview.$result.after(listview.$custom_dropdown_view);
    }

    // Hide the standard table body to force dropdown-like UX.
    listview.$result.hide();

    const grouped = group_docs_for_dropdown(listview.data || []);
    const years = Object.keys(grouped).sort((a, b) => b.localeCompare(a));

    if (!years.length) {
        listview.$custom_dropdown_view.html(
            `<div class="text-muted" style="padding: 12px;">${__("No Payroll Entry data found.")}</div>`
        );
        return;
    }

    let html = `<div style="display:flex;flex-direction:column;gap:10px;">`;
    years.forEach((year) => {
        const yearBuckets = grouped[year];
        const yearCount = Object.values(yearBuckets).reduce(
            (acc, statuses) => acc + Object.values(statuses).reduce((x, arr) => x + arr.length, 0),
            0
        );

        html += `<details open><summary><b>${__("Year")} ${year}</b> (${yearCount})</summary>`;

        const months = Object.keys(yearBuckets).sort((a, b) => b.localeCompare(a));
        months.forEach((monthKey) => {
            const monthStatuses = yearBuckets[monthKey];
            const monthCount = Object.values(monthStatuses).reduce((acc, arr) => acc + arr.length, 0);

            html += `<details style="margin-left:14px;" open><summary>${__("Month")} ${monthKey} (${monthCount})</summary>`;

            Object.keys(monthStatuses).forEach((status) => {
                const rows = monthStatuses[status];
                html += `<details style="margin-left:18px;" open><summary>${__("Status")}: ${status} (${rows.length})</summary>`;
                html += `<div style="margin-left:22px;margin-top:6px;display:flex;flex-direction:column;gap:6px;">`;

                rows.forEach((doc) => {
                    const amount = doc.total_amount
                        ? frappe.format(doc.total_amount, { fieldtype: "Currency", options: doc.currency })
                        : "-";
                    const period = format_period_label(doc);
                    const employees = doc.total_karyawan || 0;

                    html += `
                        <div class="list-row-container" style="padding:8px 10px;border:1px solid var(--border-color);border-radius:8px;">
                            <a href="#" data-name="${frappe.utils.escape_html(doc.name)}" class="payroll-entry-open-link">
                                <b>${frappe.utils.escape_html(doc.name)}</b>
                            </a>
                            <div class="text-muted small" style="margin-top:4px;">
                                ${__("Period")}: ${frappe.utils.escape_html(period)} | ${__("Employees")}: ${employees} | ${__("Total")}: ${amount}
                            </div>
                        </div>`;
                });

                html += `</div></details>`;
            });

            html += `</details>`;
        });

        html += `</details>`;
    });
    html += `</div>`;

    listview.$custom_dropdown_view.html(html);
    listview.$custom_dropdown_view.find(".payroll-entry-open-link").on("click", function (e) {
        e.preventDefault();
        const name = $(this).data("name");
        frappe.set_route("Form", "Payroll Entry", name);
    });
}

frappe.listview_settings["Payroll Entry"] = {
    add_fields: ["name", "status", "docstatus", "periode", "total_karyawan", "total_amount", "currency", "start_date"],

    onload: function (listview) {
        listview.page.add_inner_button(__("Reload Dropdown View"), () => render_dropdown_view(listview));
    },

    refresh: function (listview) {
        render_dropdown_view(listview);
    },
};