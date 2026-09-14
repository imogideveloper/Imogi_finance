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

        frm.toggle_display('section_break_warnings', frm.doc.status === 'Draft' && !!frm.doc.import_file);
        frm.toggle_display('section_break_preview', frm.doc.status === 'Draft' && !!frm.doc.import_file);
        refresh_preview(frm);
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
        refresh_preview(frm);
    },

    bank_account(frm) { refresh_preview(frm); },
    import_file(frm) { refresh_preview(frm); },
    custom_delimiters(frm) { refresh_preview(frm); },
    delimiter(frm) { refresh_preview(frm); },

    download_template(frm) {
        if (!frm.doc.bank) {
            frappe.msgprint(__('Pilih Bank terlebih dahulu.'));
            return;
        }
        window.open(
            '/api/method/imogi_finance.imogi_finance.doctype.bank_csv_import.bank_csv_import_api.download_template?bank='
            + encodeURIComponent(frm.doc.bank)
        );
    }
});

const DELIMITER_MAP = {
    'Comma (,)': ',',
    'Semicolon (;)': ';',
    'Tab': '\t',
};
const PREVIEW_PAGE_SIZE = 10;

function refresh_preview(frm) {
    if (frm.doc.status !== 'Draft' || frm.is_new()) return;
    if (!frm.doc.bank || !frm.doc.bank_account || !frm.doc.import_file) {
        set_warnings_html(frm, '');
        set_preview_html(frm, '');
        return;
    }

    clearTimeout(frm._preview_timer);
    frm._preview_timer = setTimeout(() => {
        const delimiter = frm.doc.custom_delimiters ? DELIMITER_MAP[frm.doc.delimiter] : null;

        set_warnings_html(frm, `<div class="text-muted">${__('Memeriksa file...')}</div>`);

        frappe.call({
            method: 'imogi_finance.imogi_finance.doctype.bank_csv_import.bank_csv_import_api.preview_import',
            args: { docname: frm.doc.name, delimiter },
            // frappe.call already pops up a msgprint dialog with the real
            // server error on failure, so we just need a short pointer here.
            error: function() {
                render_warnings(frm, null, __('Gagal membaca file CSV. Lihat pesan error di atas.'));
                set_preview_html(frm, '');
            },
            callback: function(r) {
                if (r.message) {
                    render_warnings(frm, r.message, null);
                    render_preview_table(frm, r.message.rows || []);
                }
            }
        });
    }, 400);
}

function set_warnings_html(frm, html) {
    frm.get_field('import_warnings_html') && frm.get_field('import_warnings_html').$wrapper.html(html);
}

function set_preview_html(frm, html) {
    frm.get_field('preview_html') && frm.get_field('preview_html').$wrapper.html(html);
}

function render_warnings(frm, result, error_message) {
    if (error_message) {
        set_warnings_html(frm, `
            <div class="alert alert-danger" style="margin-bottom: 0;">
                ${frappe.utils.escape_html(error_message)}
            </div>
        `);
        return;
    }

    if (result.errors > 0) {
        set_warnings_html(frm, `
            <div class="alert alert-warning" style="margin-bottom: 0;">
                ${__('{0} baris tidak bisa dibaca dengan benar. Cek kolom Status di Preview di bawah.', [result.errors])}
            </div>
        `);
    } else {
        set_warnings_html(frm, `
            <div class="alert alert-success" style="margin-bottom: 0;">
                ${__('Semua kolom berhasil dipetakan otomatis - tidak ada yang perlu diperbaiki.')}
            </div>
        `);
    }
}

function render_preview_table(frm, rows, page) {
    page = page || 1;
    frm._preview_rows = rows;

    const total_pages = Math.max(1, Math.ceil(rows.length / PREVIEW_PAGE_SIZE));
    page = Math.min(Math.max(page, 1), total_pages);
    const start = (page - 1) * PREVIEW_PAGE_SIZE;
    const page_rows = rows.slice(start, start + PREVIEW_PAGE_SIZE);

    const row_style = {
        'OK': '#e6f4ea',
        'Duplikat': '#fff4e5',
        'Error': '#fdecea',
        'Dilewati': '#f1f3f4',
    };

    const body_html = page_rows.map((row, i) => `
        <tr style="background-color: ${row_style[row.status] || ''}">
            <td>${start + i + 1}</td>
            <td>${row.date ? frappe.datetime.str_to_user(row.date) : '-'}</td>
            <td>${frappe.utils.escape_html(row.description || '')}</td>
            <td class="text-right">${row.deposit ? format_currency(row.deposit) : ''}</td>
            <td class="text-right">${row.withdrawal ? format_currency(row.withdrawal) : ''}</td>
            <td>${frm.doc.bank_account || ''}</td>
            <td class="text-right">${row.balance ? format_currency(row.balance) : ''}</td>
            <td>${row.status}</td>
        </tr>
    `).join('');

    set_preview_html(frm, `
        <div class="table-responsive">
            <table class="table table-bordered" style="margin-bottom: 8px;">
                <thead>
                    <tr>
                        <th>${__('SR')}</th>
                        <th>${__('Tanggal Transaksi')}</th>
                        <th>${__('Keterangan')}</th>
                        <th>${__('Deposit')}</th>
                        <th>${__('Withdrawal')}</th>
                        <th>${__('Bank Account')}</th>
                        <th>${__('Balance')}</th>
                        <th>${__('Status')}</th>
                    </tr>
                </thead>
                <tbody>${body_html || `<tr><td colspan="8" class="text-muted text-center">${__('Tidak ada baris untuk ditampilkan')}</td></tr>`}</tbody>
            </table>
        </div>
        <div class="flex justify-content-between align-center">
            <button class="btn btn-xs btn-default" data-action="prev" ${page <= 1 ? 'disabled' : ''}>${__('Previous')}</button>
            <span class="text-muted small">${__('Page {0} of {1} ({2} rows)', [page, total_pages, rows.length])}</span>
            <button class="btn btn-xs btn-default" data-action="next" ${page >= total_pages ? 'disabled' : ''}>${__('Next')}</button>
        </div>
    `);

    const $wrapper = frm.get_field('preview_html').$wrapper;
    $wrapper.find('[data-action="prev"]').on('click', () => render_preview_table(frm, frm._preview_rows, page - 1));
    $wrapper.find('[data-action="next"]').on('click', () => render_preview_table(frm, frm._preview_rows, page + 1));
}

function format_currency(value) {
    return (value || 0).toLocaleString('id-ID', { minimumFractionDigits: 2 });
}

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
