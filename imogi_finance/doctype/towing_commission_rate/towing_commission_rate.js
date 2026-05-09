frappe.ui.form.on('Towing Commission Rate', {
    rate_type(frm) {
        const desc = frm.doc.rate_type === 'Percent'
            ? '% dari Harga Jasa di Delivery Order Towing.'
            : 'Nominal Rp per trip.';
        frm.set_df_property('rate_value', 'description', desc);
    },
});
