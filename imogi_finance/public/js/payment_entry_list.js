// Loaded via BOTH hooks.py doctype_js["Payment Entry"] and
// doctype_list_js["Payment Entry"]. frappe.get_indicator() (used for the List
// View row badge AND the Form page-title badge) reads
// frappe.listview_settings[doctype].get_indicator — but doctype_js only runs
// on Form views (frappe.ui.form.ScriptManager) and doctype_list_js only runs
// on List views (frappe.model.with_doctype -> init_doctype), so this needs
// both hooks to reliably show the right badge regardless of which page loads first.

frappe.listview_settings["Payment Entry"] = {
    add_fields: ["payment_type", "party", "paid_amount", "received_amount", "unallocated_amount", "clearance_date", "posting_date", "status"],
    get_indicator: function(doc) {
        // Trust the server-computed `status` (see CustomPaymentEntry.set_status in
        // overrides/payment_entry.py) instead of re-deriving it from clearance_date
        // here -- that duplicated the Cash-mode-is-always-Reconciled rule, and this
        // copy didn't know about it, so Cash entries showed "Unreconciled" forever.
        const status_colors = {
            Cancelled: "red",
            Draft: "gray",
            Reconciled: "green",
            Unreconciled: "orange",
        };
        return [__(doc.status), status_colors[doc.status] || "gray", "status,=," + doc.status];
    },
    onload: function(listview) {
        listview.page.add_inner_button(__("Unreconciled"), function() {
            listview.filter_area.add([
                ["Payment Entry", "clearance_date", "is", "not set"],
                ["Payment Entry", "docstatus", "=", "1"]
            ]);
        }, __("Filter By"));
        listview.page.add_inner_button(__("Reconciled"), function() {
            listview.filter_area.add([
                ["Payment Entry", "clearance_date", "is", "set"],
                ["Payment Entry", "docstatus", "=", "1"]
            ]);
        }, __("Filter By"));
    },
    formatters: {
        paid_amount: function(value, df, doc) {
            if (doc.payment_type === "Pay") return frappe.format(value, {fieldtype: "Currency", options: "currency"});
            return "";
        },
        received_amount: function(value, df, doc) {
            if (doc.payment_type === "Receive") return frappe.format(value, {fieldtype: "Currency", options: "currency"});
            return "";
        },
        unallocated_amount: function(value, field, doc) {
            if (doc.docstatus !== 1) return "";
            const unalloc = parseFloat(value || 0);
            if (unalloc > 0) {
                return `<span style="color: orange; font-weight: bold;">⚠ ${format_currency(unalloc)}</span>`;
            }
            return `<span style="color: green;">✓ Fully Allocated</span>`;
        }
    }
};
