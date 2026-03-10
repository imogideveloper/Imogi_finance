// Advanced Expense Request Item client-side script
frappe.ui.form.on('Advanced Expense Request Item', {
    deferred_start_date: function(frm, cdt, cdn) {
        calculate_deferred_end_date_multi_cc(frm, cdt, cdn);
    },

    deferred_periods: function(frm, cdt, cdn) {
        calculate_deferred_end_date_multi_cc(frm, cdt, cdn);
    }
});

function calculate_deferred_end_date_multi_cc(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (row.is_deferred_expense && row.deferred_start_date && row.deferred_periods) {
        frappe.call({
            method: 'frappe.utils.add_months',
            args: {
                date: row.deferred_start_date,
                months: row.deferred_periods
            },
            callback: function(r) {
                if (r.message) {
                    frappe.model.set_value(cdt, cdn, 'deferred_end_date', r.message);
                }
            }
        });
    } else {
        frappe.model.set_value(cdt, cdn, 'deferred_end_date', null);
    }
}
