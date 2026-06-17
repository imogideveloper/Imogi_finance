// DO Towing: badge form harus ikuti field status, bukan docstatus "Submitted"
(function () {
	if (frappe._do_towing_get_indicator_patched) {
		return;
	}
	frappe._do_towing_get_indicator_patched = true;

	const DO_TOWING_STATUS_COLORS = {
		Draft: "red",
		Assigned: "orange",
		"Pick Up": "purple",
		Delivered: "green",
		"Awaiting Dokument": "yellow",
		Done: "darkgreen",
		Cancelled: "gray",
		Submitted: "blue",
	};

	const original_get_indicator = frappe.get_indicator;
	frappe.get_indicator = function (doc, doctype, show_workflow_state) {
		const dt = doctype || (doc && doc.doctype);
		if (dt === "Delivery Order Towing" && doc && !doc.__unsaved) {
			const status = doc.status;
			if (status) {
				return [
					__(status, null, dt),
					DO_TOWING_STATUS_COLORS[status] || "gray",
					"status,=," + status,
				];
			}
		}
		return original_get_indicator(doc, doctype, show_workflow_state);
	};
})();

frappe.after_ajax(function() {
    const _original = frappe.views.ListView.prototype.setup_defaults;
    frappe.views.ListView.prototype.setup_defaults = async function() {
        await _original.call(this);
        this.page_length = 2500;
    };
});

frappe.after_ajax(function() {
    if (frappe.listview_settings) {
        frappe.listview_settings["Payroll Entry"] = {
            add_fields: ["name", "status", "docstatus", "periode", "total_karyawan", "total_amount", "currency", "start_date"],

            onload: function(listview) {
                listview.page.add_inner_button(__("Reload Dropdown View"), function() {
                    render_payroll_dropdown(listview);
                });
            },

            refresh: function(listview) {
                render_payroll_dropdown(listview);
            }
        };
    }
});

function get_month_name(month) {
    var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return months[month] || "-";
}

function format_period_label(doc) {
    if (doc.periode) return doc.periode;
    if (!doc.start_date) return "-";
    var d = frappe.datetime.str_to_obj(doc.start_date);
    return get_month_name(d.getMonth()) + " " + d.getFullYear();
}

function get_status_label(doc) {
    if (doc.docstatus === 2) return __("Cancelled");
    if (doc.docstatus === 1) return __("Submitted");
    return __("Draft");
}

function group_docs_for_dropdown(docs) {
    var grouped = {};
    (docs || []).forEach(function(doc) {
        var baseDate = doc.start_date ? frappe.datetime.str_to_obj(doc.start_date) : null;
        var year = baseDate ? String(baseDate.getFullYear()) : __("No Year");
        var monthKey = baseDate ? String(baseDate.getMonth() + 1).padStart(2, "0") + "-" + get_month_name(baseDate.getMonth()) : __("No Month");
        var status = get_status_label(doc);
        if (!grouped[year]) grouped[year] = {};
        if (!grouped[year][monthKey]) grouped[year][monthKey] = {};
        if (!grouped[year][monthKey][status]) grouped[year][monthKey][status] = [];
        grouped[year][monthKey][status].push(doc);
    });
    return grouped;
}

function render_payroll_dropdown(listview) {
    if (!listview.$custom_dropdown_view) {
        listview.$custom_dropdown_view = $('<div class="payroll-entry-dropdown-view" style="padding:16px;"></div>');
        listview.$result.after(listview.$custom_dropdown_view);
    }
    listview.$result.hide();
    var grouped = group_docs_for_dropdown(listview.data || []);
    var years = Object.keys(grouped).sort(function(a, b) { return b.localeCompare(a); });
    if (!years.length) {
        listview.$custom_dropdown_view.html('<div class="text-muted" style="padding:12px;">' + __("No Payroll Entry data found.") + '</div>');
        return;
    }
    var html = '<div style="display:flex;flex-direction:column;gap:10px;">';
    years.forEach(function(year) {
        var yearBuckets = grouped[year];
        var yearCount = Object.values(yearBuckets).reduce(function(acc, statuses) {
            return acc + Object.values(statuses).reduce(function(x, arr) { return x + arr.length; }, 0);
        }, 0);
        html += '<details open><summary><b>' + __("Year") + ' ' + year + '</b> (' + yearCount + ')</summary>';
        var months = Object.keys(yearBuckets).sort(function(a, b) { return b.localeCompare(a); });
        months.forEach(function(monthKey) {
            var monthStatuses = yearBuckets[monthKey];
            var monthCount = Object.values(monthStatuses).reduce(function(acc, arr) { return acc + arr.length; }, 0);
            html += '<details style="margin-left:14px;" open><summary>' + __("Month") + ' ' + monthKey + ' (' + monthCount + ')</summary>';
            Object.keys(monthStatuses).forEach(function(status) {
                var rows = monthStatuses[status];
                html += '<details style="margin-left:18px;" open><summary>' + __("Status") + ': ' + status + ' (' + rows.length + ')</summary>';
                html += '<div style="margin-left:22px;margin-top:6px;display:flex;flex-direction:column;gap:6px;">';
                rows.forEach(function(doc) {
                    var amount = doc.total_amount ? frappe.format(doc.total_amount, {fieldtype: "Currency", options: doc.currency}) : "-";
                    var period = format_period_label(doc);
                    var employees = doc.total_karyawan || 0;
                    html += '<div class="list-row-container" style="padding:8px 10px;border:1px solid var(--border-color);border-radius:8px;">';
                    html += '<a href="#" data-name="' + frappe.utils.escape_html(doc.name) + '" class="payroll-entry-open-link">';
                    html += '<b>' + frappe.utils.escape_html(doc.name) + '</b></a>';
                    html += '<div class="text-muted small" style="margin-top:4px;">';
                    html += __("Period") + ': ' + frappe.utils.escape_html(period) + ' | ';
                    html += __("Employees") + ': ' + employees + ' | ';
                    html += __("Total") + ': ' + amount;
                    html += '</div></div>';
                });
                html += '</div></details>';
            });
            html += '</details>';
        });
        html += '</details>';
    });
    html += '</div>';
    listview.$custom_dropdown_view.html(html);
    listview.$custom_dropdown_view.find(".payroll-entry-open-link").on("click", function(e) {
        e.preventDefault();
        frappe.set_route("Form", "Payroll Entry", $(this).data("name"));
    });
}
