frappe.ui.form.on('Bank Statement', {
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

                                if (res.opening_balance && res.opening_balance > 0) {
                                    frappe.msgprint({
                                        title: __('⚠️ Opening Balance Terdeteksi'),
                                        message: `
                                            <b>Opening Balance dari CSV:</b> Rp ${res.opening_balance.toLocaleString('id-ID')}<br><br>
                                            Silakan buat <b>Opening Entry</b> manual di:<br>
                                            <b>Accounting → Journal Entry → New</b><br><br>
                                            Gunakan tanggal sebelum <b>${res.statement_from_date || '-'}</b><br>
                                            dan akun bank <b>${frm.doc.bank_account}</b>.
                                        `,
                                        indicator: 'orange',
                                    });
                                }

                                frm.reload_doc();
                            }
                        },
                        error: function() { frm.reload_doc(); }
                    });
                });
            }, __('Actions')).addClass('btn-primary');
        }

        if (frm.doc.status === 'Completed') {
            frm.page.set_indicator(__('Completed'), 'green');

            frm.add_custom_button(__('Auto Reconcile Statement Detail'), function() {
                frappe.call({
                    method: 'imogi_finance.imogi_finance.doctype.bank_statement.bank_statement.auto_reconcile_statement_details',
                    args: { docname: frm.doc.name },
                    freeze: true,
                    freeze_message: __('Mencocokkan transaksi statement dengan GL Entry...'),
                    callback: function(r) {
                        const info = r.message || {};
                        frappe.msgprint({
                            title: __('Auto Reconcile Selesai'),
                            indicator: 'green',
                            message: __('Reconciled: {0}<br>Unmatched: {1}<br>Total Row: {2}', [
                                info.reconciled || 0,
                                info.unmatched || 0,
                                info.total || 0
                            ])
                        });
                        frm.reload_doc();
                    }
                });
            }, __('Actions')).addClass('btn-primary');

            frm.add_custom_button(__('Reset Reconcile'), function() {
                frappe.confirm(__('Reset semua status reconcile pada Statement Detail?'), function() {
                    frappe.call({
                        method: 'imogi_finance.imogi_finance.doctype.bank_statement.bank_statement.reset_reconcile_statement_details',
                        args: { docname: frm.doc.name },
                        freeze: true,
                        freeze_message: __('Mereset status reconcile...'),
                        callback: function(r) {
                            frappe.show_alert({
                                message: __('Berhasil reset {0} row reconcile', [r.message?.reset || 0]),
                                indicator: 'orange'
                            });
                            frm.reload_doc();
                        }
                    });
                });
            }, __('Actions'));
        } else if (frm.doc.status === 'Failed') {
            frm.page.set_indicator(__('Failed'), 'red');
        } else if (frm.doc.status === 'Processing') {
            frm.page.set_indicator(__('Processing'), 'blue');
        }
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
    },
});
