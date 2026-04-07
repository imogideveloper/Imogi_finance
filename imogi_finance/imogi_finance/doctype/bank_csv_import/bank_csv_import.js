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

        if (frm.doc.status === 'Completed') {
            frm.page.set_indicator(__('Completed'), 'green');

            // Tampilkan info balance jika ada
            if (frm.doc.closing_balance) {
                // Tombol buka Bank Reconciliation Tool dengan closing balance prefilled
                frm.add_custom_button(__('🏦 Buka Bank Reconciliation Tool'), function() {
                    // Format angka
                    let closing = frm.doc.closing_balance || 0;
                    let from_date = frm.doc.statement_from_date || frappe.datetime.get_today();
                    let to_date = frm.doc.statement_to_date || frappe.datetime.get_today();

                    // Tampilkan dialog konfirmasi dengan info balance
                    let msg = `
                        <div class="alert alert-info">
                            <b>Info Saldo dari CSV:</b><br>
                            Opening Balance: <b>${format_currency(frm.doc.opening_balance)}</b><br>
                            Closing Balance: <b>${format_currency(closing)}</b><br>
                            Periode: <b>${from_date} s/d ${to_date}</b>
                        </div>
                        <p>Setelah Bank Reconciliation Tool terbuka, masukkan nilai berikut ke field 
                        <b>"Closing Balance as per Bank Statement"</b>:</p>
                        <h3 style="color: #4CAF50; text-align: center;">${format_currency(closing)}</h3>
                    `;

                    frappe.msgprint({
                        title: __('Panduan Bank Reconciliation'),
                        message: msg,
                        indicator: 'blue',
                        primary_action: {
                            label: __('Buka Bank Reconciliation Tool'),
                            action: function() {
                                // Simpan ke localStorage agar bisa dibaca Bank Reconciliation Tool
                                localStorage.setItem('bci_prefill', JSON.stringify({
                                    company: frm.doc.company,
                                    bank_account: frm.doc.bank_account,
                                    from_date: from_date,
                                    to_date: to_date,
                                    closing_balance: closing,
                                }));
                                frappe.set_route('Form', 'Bank Reconciliation Tool');
                            }
                        }
                    });
                }, __('Actions'));
            }
        }
        else if (frm.doc.status === 'Failed') frm.page.set_indicator(__('Failed'), 'red');
        else if (frm.doc.status === 'Processing') frm.page.set_indicator(__('Processing'), 'blue');

function format_currency(value) {
    return 'Rp ' + (value || 0).toLocaleString('id-ID', {minimumFractionDigits: 2});
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
    }
});
