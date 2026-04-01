frappe.ui.form.on('Bank CSV Import', {
    refresh(frm) {
        if (frm.doc.status !== 'Processing') {
            frm.add_custom_button(__('Import CSV'), function() {
                if (!frm.doc.bank) { frappe.msgprint(__('Pilih Bank terlebih dahulu.')); return; }
                if (!frm.doc.bank_account) { frappe.msgprint(__('Pilih Bank Account terlebih dahulu.')); return; }
                if (!frm.doc.import_file) { frappe.msgprint(__('Upload file CSV terlebih dahulu.')); return; }
                if (frm.is_new()) { frappe.msgprint(__('Simpan dokumen terlebih dahulu.')); return; }

                frappe.confirm(__('Mulai import CSV dari bank {0}?', [frm.doc.bank]), function() {
                    frappe.show_alert({ message: __('Memproses import...'), indicator: 'blue' });
                    frappe.call({
                        method: 'imogi_finance.imogi_finance.doctype.bank_csv_import.bank_csv_import_api.run_import',
                        args: { docname: frm.doc.name },
                        freeze: true,
                        freeze_message: __('Sedang mengimport data bank...'),
                        callback: function(r) {
                            if (r.message) {
                                let res = r.message;
                                frappe.show_alert({
                                    message: __('Import selesai: {0} dibuat, {1} duplikat, {2} error', [res.created, res.skipped, res.errors]),
                                    indicator: res.errors > 0 ? 'orange' : 'green'
                                }, 10);
                                frm.reload_doc();
                            }
                        },
                        error: function(r) { frm.reload_doc(); }
                    });
                });
            }, __('Actions')).addClass('btn-primary');
        }

        if (frm.doc.status === 'Completed') frm.page.set_indicator(__('Completed'), 'green');
        else if (frm.doc.status === 'Failed') frm.page.set_indicator(__('Failed'), 'red');
        else if (frm.doc.status === 'Processing') frm.page.set_indicator(__('Processing'), 'blue');
    },

    bank(frm) {
        if (frm.doc.bank) {
            frappe.db.get_value('Bank Statement Bank List', frm.doc.bank, 'bank').then(r => {
                if (r.message && r.message.bank) {
                    frm.set_query('bank_account', function() {
                        return { filters: { bank: r.message.bank } };
                    });
                }
            });
        }
    }
});
