frappe.listview_settings['Payment Entry'] = {
    add_fields: ["paid_amount", "received_amount", "payment_type", "unallocated_amount", "party", "posting_date"],
    get_indicator: function(doc) {
        if (doc.docstatus == 2) {
            return [__("Cancelled"), "red", "docstatus,=,2"];
        }
        if (doc.docstatus == 0) {
            return [__("Draft"), "grey", "docstatus,=,0"];
        }
        const unalloc = parseFloat(doc.unallocated_amount || 0);
        if (unalloc > 0) {
            return [__("Unallocated"), "orange", "unallocated_amount,>,0"];
        }
        return [__("Allocated"), "green", "unallocated_amount,=,0"];
    },
    formatters: {
        paid_amount: function(value, df, doc) {
            if (doc.payment_type === "Pay") {
                return frappe.format(value, {fieldtype: "Currency", options: "currency"});
            }
            return "";
        },
        received_amount: function(value, df, doc) {
            if (doc.payment_type === "Receive") {
                return frappe.format(value, {fieldtype: "Currency", options: "currency"});
            }
            return "";
        },
        unallocated_amount: function(value, df, doc) {
            if (doc.docstatus !== 1) return "";
            const unalloc = parseFloat(value || 0);
            if (unalloc > 0) {
                return `<span style="color: orange; font-weight: bold;">⚠ ${frappe.format(unalloc, {fieldtype: "Currency"})}</span>`;
            }
            return `<span style="color: green;">✓ Allocated</span>`;
        }
    },
    onload: function(listview) {
        listview.page.add_inner_button(__("Unallocated"), function() {
            listview.filter_area.add([
                ["Payment Entry", "unallocated_amount", ">", "0"],
                ["Payment Entry", "docstatus", "=", "1"]
            ]);
        }, __("Filter By"));

        listview.page.add_inner_button(__("Allocated"), function() {
            listview.filter_area.add([
                ["Payment Entry", "unallocated_amount", "=", "0"],
                ["Payment Entry", "docstatus", "=", "1"]
            ]);
        }, __("Filter By"));
    },
    hide_name_column: false
};
