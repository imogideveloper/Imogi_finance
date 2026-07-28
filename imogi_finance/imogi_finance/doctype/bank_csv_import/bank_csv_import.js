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
                        error: function(r) { frm.reload_doc(); }
                    });
                });
            }, __('Actions')).addClass('btn-primary');
        }

        if (frm.doc.status === 'Completed') {
            frm.page.set_indicator(__('Completed'), 'green');

            // Tombol buka Bank Reconciliation Tool — selalu tampil saat Completed
            frm.add_custom_button(__('🏦 Buka Bank Reconciliation Tool'), function() {
                let closing = frm.doc.closing_balance || 0;
                let from_date = frm.doc.statement_from_date || frappe.datetime.get_today();
                let to_date = frm.doc.statement_to_date || frappe.datetime.get_today();

                let msg = closing ? `
                    <div class="alert alert-info">
                        <b>Info Saldo dari CSV:</b><br>
                        Opening Balance: <b>${format_currency(frm.doc.opening_balance)}</b><br>
                        Closing Balance: <b>${format_currency(closing)}</b><br>
                        Periode: <b>${from_date} s/d ${to_date}</b>
                    </div>
                    <p>Setelah Bank Reconciliation Tool terbuka, masukkan nilai berikut ke field
                    <b>"Closing Balance as per Bank Statement"</b>:</p>
                    <h3 style="color: #4CAF50; text-align: center;">${format_currency(closing)}</h3>
                ` : `
                    <p>Buka Bank Reconciliation Tool untuk melakukan rekonsiliasi.</p>
                    <p>Bank Account: <b>${frm.doc.bank_account || '-'}</b></p>
                `;

                frappe.msgprint({
                    title: __('Panduan Bank Reconciliation'),
                    message: msg,
                    indicator: 'blue',
                    primary_action: {
                        label: __('Buka Bank Reconciliation Tool'),
                        action: function() {
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
        else if (frm.doc.status === 'Failed') frm.page.set_indicator(__('Failed'), 'red');
        else if (frm.doc.status === 'Processing') frm.page.set_indicator(__('Processing'), 'blue');

        function format_currency(value) {
            return 'Rp ' + (value || 0).toLocaleString('id-ID', {minimumFractionDigits: 2});
        }

        // ── Rapikan tampilan sesuai status ───────────────────────
        const has_results = frm.doc.status === 'Completed' || frm.doc.status === 'Failed';

        frm.toggle_display('section_break_result', has_results);
        frm.toggle_display('section_break_detail', has_results && frm.doc.import_rows && frm.doc.import_rows.length > 0);
        frm.toggle_display('import_log', frm.doc.status === 'Failed');

        frm.dashboard.clear_headline();
        frm.dashboard.reset(); // clear indicator pills from any previous refresh so they don't pile up
        if (frm.doc.status === 'Draft') {
            frm.set_intro(__('File CSV sudah terpasang. Klik tombol <b>Import CSV</b> di atas (menu Actions) untuk memproses dan menghasilkan Detail Transaksi.'), 'blue');
        } else if (frm.doc.status === 'Processing') {
            frm.set_intro(__('Sedang memproses import, mohon tunggu...'), 'orange');
        } else if (frm.doc.status === 'Completed') {
            frm.set_intro('');
            frm.dashboard.add_indicator(__('{0} Total Baris', [frm.doc.total_rows || 0]), 'blue');
            frm.dashboard.add_indicator(__('{0} Berhasil Dibuat', [frm.doc.created_rows || 0]), 'green');
            if (frm.doc.skipped_rows) {
                frm.dashboard.add_indicator(__('{0} Duplikat', [frm.doc.skipped_rows]), 'orange');
            }
            if (frm.doc.error_rows) {
                frm.dashboard.add_indicator(__('{0} Error', [frm.doc.error_rows]), 'red');
            }
        } else if (frm.doc.status === 'Failed') {
            frm.set_intro(__('Import gagal. Lihat <b>Import Log</b> di bagian bawah untuk detail error.'), 'red');
        }

        // ── Beri warna pada baris Detail Transaksi sesuai status ──
        if (has_results && frm.doc.import_rows && frm.doc.import_rows.length) {
            setTimeout(() => color_import_rows(frm), 300);
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

function color_import_rows(frm) {
    const grid = frm.fields_dict.import_rows && frm.fields_dict.import_rows.grid;
    if (!grid || !grid.grid_rows) return;

    const row_style = {
        'OK': { background: '#e6f4ea', color: '#1e7e34' },
        'Duplikat': { background: '#fff4e5', color: '#a3670e' },
        'Error': { background: '#fdecea', color: '#c62828' },
        'Dilewati': { background: '#f1f3f4', color: '#5f6368' },
    };

    grid.grid_rows.forEach(function(row) {
        const style = row_style[row.doc.status];
        if (style && row.row) {
            $(row.row).css('background-color', style.background);
            $(row.row).find('.data-row .col').css('color', style.color);
        }
    });
}
