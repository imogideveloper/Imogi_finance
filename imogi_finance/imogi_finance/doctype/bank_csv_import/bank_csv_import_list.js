frappe.listview_settings['Bank Statement'] = {
    add_fields: ['opening_balance', 'closing_balance', 'status'],

    get_indicator(doc) {
        const map = {
            Draft: 'grey',
            Processing: 'blue',
            Completed: 'green',
            Failed: 'red',
        };
        return [__(doc.status), map[doc.status] || 'grey', `status,=,${doc.status}`];
    },

    onload(listview) {
        const patch_columns = () => {
            if (!listview.columns || !Array.isArray(listview.columns)) return;

            // Hide "Created" system column from list view.
            listview.columns = listview.columns.filter((col) => {
                const key = col?.df?.fieldname || col?.id || '';
                return !['creation', 'created'].includes(key);
            });

            // Move status column to the right-most position.
            const idx = listview.columns.findIndex((col) => col?.df?.fieldname === 'status');
            if (idx >= 0) {
                const [status_col] = listview.columns.splice(idx, 1);
                listview.columns.push(status_col);
            }
        };

        const original_render = listview.render.bind(listview);
        listview.render = function () {
            patch_columns();
            return original_render();
        };
    },
};

frappe.listview_settings['Bank CSV Import'] = frappe.listview_settings['Bank Statement'];
