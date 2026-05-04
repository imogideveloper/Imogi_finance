frappe.listview_settings['Payroll Entry'] = {
    add_fields: ["periode", "total_karyawan", "total_amount", "currency", "start_date"],

    onload: function(listview) {
        // Default group by: Status (lebih mirip grouped list).
        const default_group_by = "status";
        if (!listview.group_by && listview.meta?.fields) {
            listview.group_by = default_group_by;
            listview.refresh();
        }

        // Build dynamic group-by options:
        // - selalu ada granularity Year/Month/Day
        // - tambah kolom nyata dari meta doctype Payroll Entry
        const original_get_group_by_fields = listview.get_group_by_fields;
        if (original_get_group_by_fields) {
            listview.get_group_by_fields = function() {
                const fields = (listview.meta?.fields || []);
                const dynamic = [];
                const seen = new Set();

                const pushOption = (label, fieldname) => {
                    if (!fieldname || seen.has(fieldname)) return;
                    seen.add(fieldname);
                    dynamic.push({ label, fieldname });
                };

                // Date fields in this doctype + core dates for grouping
                const dateCandidates = ["start_date", "end_date", "posting_date", "creation", "modified"];
                dateCandidates.forEach((base) => {
                    pushOption(__(`${frappe.model.unscrub(base)} (Year)`), `${base}:Year`);
                    pushOption(__(`${frappe.model.unscrub(base)} (Month)`), `${base}:Month`);
                    pushOption(__(`${frappe.model.unscrub(base)} (Day)`), `${base}:Day`);
                });

                // Add doctype columns dynamically (only commonly groupable fieldtypes)
                const allowedFieldtypes = new Set([
                    "Data", "Link", "Select", "Dynamic Link", "Check",
                    "Date", "Datetime", "Int", "Float", "Currency",
                ]);

                fields.forEach((df) => {
                    if (!df || !df.fieldname) return;
                    if (["Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold"].includes(df.fieldtype)) return;
                    if (!allowedFieldtypes.has(df.fieldtype)) return;

                    // For Date/Datetime, prefer granularity options above.
                    if (["Date", "Datetime"].includes(df.fieldtype)) {
                        pushOption(__(`${df.label || frappe.model.unscrub(df.fieldname)} (Year)`), `${df.fieldname}:Year`);
                        pushOption(__(`${df.label || frappe.model.unscrub(df.fieldname)} (Month)`), `${df.fieldname}:Month`);
                        pushOption(__(`${df.label || frappe.model.unscrub(df.fieldname)} (Day)`), `${df.fieldname}:Day`);
                    } else {
                        pushOption(__(df.label || frappe.model.unscrub(df.fieldname)), df.fieldname);
                    }
                });

                // Keep a few important defaults on top.
                const prioritized = [];
                const priorityFields = ["status", "company", "department", "branch"];
                priorityFields.forEach((f) => {
                    const item = dynamic.find((d) => d.fieldname === f);
                    if (item) prioritized.push(item);
                });

                const rest = dynamic.filter((d) => !priorityFields.includes(d.fieldname));
                return [...prioritized, ...rest];
            };
        }
    },

    formatters: {
        total_karyawan: function(value) {
            return value ? `${value} karyawan` : "-";
        },
        total_amount: function(value, df, doc) {
            if (!value) return "-";
            return frappe.format(value, {fieldtype: "Currency"});
        },
        start_date: function(value) {
            if (!value) return "-";
            const d = frappe.datetime.str_to_obj(value);
            const bulan = ["Jan","Feb","Mar","Apr","May","Jun",
                          "Jul","Aug","Sep","Oct","Nov","Dec"];
            return `${bulan[d.getMonth()]} ${d.getFullYear()}`;
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