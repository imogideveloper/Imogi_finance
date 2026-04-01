frappe.listview_settings['BCA Bank Statement Import'] = {
    get_indicator: function(doc) {
        const map = {
            'Draft': 'grey',
            'Processing': 'blue',
            'Completed': 'green',
            'Failed': 'red'
        };
        return [__(doc.status), map[doc.status] || 'grey', 'status,=,' + doc.status];
    }
};
