frappe.listview_settings['Payroll Entry'] = {
    add_fields: ["periode", "total_karyawan", "total_amount", "currency"],

    onload: function(listview) {
        // Set default group by periode
        if (!listview.group_by) {
            listview.group_by = "periode";
            listview.refresh();
        }
    },

    formatters: {
        total_karyawan: function(value) {
            return value ? `${value} karyawan` : "-";
        },
        total_amount: function(value, df, doc) {
            if (!value) return "-";
            return frappe.format(value, {fieldtype: "Currency"});
        }
    },

    get_indicator: function(doc) {
        if (doc.docstatus == 0) {
            return [__("Draft"), "grey", "docstatus,=,0"];
        }
        if (doc.docstatus == 1) {
            return [__("Submitted"), "blue", "docstatus,=,1"];
        }
        if (doc.docstatus == 2) {
            return [__("Cancelled"), "red", "docstatus,=,2"];
        }
    }
};