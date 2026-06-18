// towing_admin_tools.js
// Tombol tersembunyi untuk Administrator — hapus riwayat transaksi towing
// Muncul hanya di halaman profil "Administrator" dan hanya jika login sebagai Administrator

frappe.ui.form.on('User', {
    refresh(frm) {
        // Hanya tampilkan jika:
        // 1. User yang login adalah Administrator
        // 2. Dokumen User yang sedang dibuka adalah "Administrator"
        if (frappe.session.user !== 'Administrator') return;
        if (frm.doc.name !== 'Administrator') return;

        frm.add_custom_button(__('🗑️ Purge Towing History'), function() {
            _towing_purge_dialog(frm);
        }, __('🔧 Towing Admin'));

        frm.add_custom_button(__('💣 Purge Semua Transaksi Towing'), function() {
            _towing_purge_all_dialog(frm);
        }, __('🔧 Towing Admin')).addClass('btn-danger');
    }
});


function _towing_purge_dialog(frm) {
    // Step 1: Preview dulu berapa record yang akan dihapus
    frappe.dom.freeze(__('Menghitung riwayat towing...'));

    frappe.call({
        method: 'imogi_finance.api.towing_admin.preview_towing_history',
        callback(r) {
            frappe.dom.unfreeze();
            if (!r.message) return;

            const data   = r.message;
            const total  = data.total;
            const summary = data.summary;

            // Buat tabel ringkasan
            let rows = '';
            for (const [doctype, counts] of Object.entries(summary)) {
                if (counts.total === 0) continue;
                rows += `
                    <tr>
                        <td style="padding:4px 8px">${doctype}</td>
                        <td style="padding:4px 8px;text-align:right">${counts.version}</td>
                        <td style="padding:4px 8px;text-align:right">${counts.comment}</td>
                        <td style="padding:4px 8px;text-align:right">${counts.communication}</td>
                        <td style="padding:4px 8px;text-align:right">${counts.activity_log}</td>
                        <td style="padding:4px 8px;text-align:right"><b>${counts.total}</b></td>
                    </tr>`;
            }

            const table_html = total > 0 ? `
                <table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:12px">
                    <thead>
                        <tr style="background:#f5f5f5">
                            <th style="padding:4px 8px;text-align:left">DocType</th>
                            <th style="padding:4px 8px">Version</th>
                            <th style="padding:4px 8px">Comment</th>
                            <th style="padding:4px 8px">Komun.</th>
                            <th style="padding:4px 8px">Activity</th>
                            <th style="padding:4px 8px">Total</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                    <tfoot>
                        <tr style="border-top:2px solid #ccc">
                            <td style="padding:4px 8px"><b>TOTAL</b></td>
                            <td colspan="4"></td>
                            <td style="padding:4px 8px;text-align:right"><b>${total}</b></td>
                        </tr>
                    </tfoot>
                </table>` : '<p style="color:green">✅ Tidak ada riwayat yang perlu dihapus.</p>';

            if (total === 0) {
                frappe.msgprint({
                    title: __('Tidak Ada Riwayat'),
                    message: __('Semua riwayat transaksi towing sudah bersih.'),
                    indicator: 'green'
                });
                return;
            }

            // Step 2: Dialog konfirmasi dengan input teks
            const d = new frappe.ui.Dialog({
                title: __('⚠️ Konfirmasi Hapus Riwayat Towing'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        options: `
                            <div style="padding:8px 0">
                                <p>Akan menghapus <b>${total} record riwayat</b> dari semua dokumen towing.</p>
                                <p style="color:#666;font-size:12px">
                                    ℹ️ Dokumen asli (SO, DO, PO, PI, PE) <b>TIDAK dihapus</b>.<br>
                                    Yang dihapus hanya: Version, Comment, Communication, Activity Log.
                                </p>
                                ${table_html}
                                <p style="margin-top:12px;color:#d44">
                                    Ketik <b>HAPUS</b> di bawah untuk konfirmasi:
                                </p>
                            </div>`
                    },
                    {
                        fieldtype: 'Data',
                        fieldname: 'konfirmasi',
                        label: 'Konfirmasi',
                        placeholder: 'Ketik: HAPUS'
                    }
                ],
                primary_action_label: __('🗑️ Hapus Riwayat Sekarang'),
                primary_action(values) {
                    if (values.konfirmasi !== 'HAPUS') {
                        frappe.show_alert({
                            message: __('Ketik "HAPUS" (huruf kapital semua) untuk konfirmasi'),
                            indicator: 'red'
                        }, 4);
                        return;
                    }
                    d.hide();
                    _execute_purge();
                }
            });
            d.show();
        },
        error() {
            frappe.dom.unfreeze();
        }
    });
}


function _execute_purge() {
    frappe.dom.freeze(__('Menghapus riwayat transaksi towing...'));

    frappe.call({
        method: 'imogi_finance.api.towing_admin.purge_towing_history',
        args: { confirm: 'HAPUS' },
        callback(r) {
            frappe.dom.unfreeze();
            if (!r.message) return;

            const res = r.message;
            if (res.success) {
                let detail_html = '<ul style="margin-top:8px">';
                for (const [doctype, count] of Object.entries(res.detail)) {
                    if (count > 0) {
                        detail_html += `<li>${doctype}: <b>${count}</b> record</li>`;
                    }
                }
                detail_html += '</ul>';

                frappe.msgprint({
                    title: __('✅ Riwayat Berhasil Dihapus'),
                    message: `
                        <b>${res.total_deleted} record riwayat</b> berhasil dihapus dari dokumen towing.
                        ${detail_html}
                        <p style="color:#666;font-size:12px;margin-top:8px">
                            Log operasi ini telah dicatat di Error Log.
                        </p>`,
                    indicator: 'green'
                });
            }
        },
        error() {
            frappe.dom.unfreeze();
        }
    });
}


function _towing_purge_all_dialog(frm) {
    frappe.dom.freeze(__('Menghitung dokumen towing...'));

    frappe.call({
        method: 'imogi_finance.api.towing_admin.preview_towing_purge_all',
        callback(r) {
            frappe.dom.unfreeze();
            if (!r.message) return;

            const data = r.message;
            const counts = data.documents || {};
            const total = data.total_documents || 0;

            let rows = '';
            for (const [doctype, count] of Object.entries(counts)) {
                if (!count) continue;
                rows += `
                    <tr>
                        <td style="padding:4px 8px">${doctype}</td>
                        <td style="padding:4px 8px;text-align:right"><b>${count}</b></td>
                    </tr>`;
            }

            if (total === 0) {
                frappe.msgprint({
                    title: __('Tidak Ada Data'),
                    message: __('Tidak ada dokumen transaksi towing yang bisa dihapus.'),
                    indicator: 'green'
                });
                return;
            }

            const d = new frappe.ui.Dialog({
                title: __('⚠️ HAPUS SEMUA Transaksi Towing'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        options: `
                            <div style="padding:8px 0">
                                <p style="color:#c00;font-weight:bold">
                                    PERINGATAN: Operasi ini TIDAK BISA dibatalkan!
                                </p>
                                <p>Akan menghapus permanen <b>${total} dokumen</b> transaksi towing:</p>
                                <table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:12px">
                                    <thead>
                                        <tr style="background:#f5f5f5">
                                            <th style="padding:4px 8px;text-align:left">DocType</th>
                                            <th style="padding:4px 8px;text-align:right">Jumlah</th>
                                        </tr>
                                    </thead>
                                    <tbody>${rows}</tbody>
                                </table>
                                <p style="margin-top:10px;font-size:12px;color:#666">
                                    Termasuk <b>semua</b> Payment Entry, Sales Invoice, Purchase Invoice,
                                    Sales Order, Purchase Order, Delivery Order Towing, Expense Claim,
                                    dan Driver Commission di site ini, plus riwayat Version/Comment/Activity Log.
                                </p>
                                <p style="margin-top:12px;color:#d44">
                                    Ketik <b>HAPUS SEMUA</b> untuk konfirmasi:
                                </p>
                            </div>`
                    },
                    {
                        fieldtype: 'Data',
                        fieldname: 'konfirmasi',
                        label: 'Konfirmasi',
                        placeholder: 'Ketik: HAPUS SEMUA'
                    }
                ],
                primary_action_label: __('💣 Hapus Semua Sekarang'),
                primary_action(values) {
                    if (values.konfirmasi !== 'HAPUS SEMUA') {
                        frappe.show_alert({
                            message: __('Ketik "HAPUS SEMUA" (huruf kapital semua) untuk konfirmasi'),
                            indicator: 'red'
                        }, 4);
                        return;
                    }
                    d.hide();
                    _execute_purge_all();
                }
            });
            d.show();
        },
        error() {
            frappe.dom.unfreeze();
        }
    });
}


function _execute_purge_all() {
    frappe.dom.freeze(__('Menghapus semua transaksi towing...'));

    frappe.call({
        method: 'imogi_finance.api.towing_admin.purge_towing_transactions',
        args: { confirm: 'HAPUS SEMUA' },
        callback(r) {
            frappe.dom.unfreeze();
            if (!r.message) return;

            const res = r.message;
            let detail_html = '<ul style="margin-top:8px">';
            for (const [doctype, count] of Object.entries(res.documents || {})) {
                if (count > 0) {
                    detail_html += `<li>${doctype}: <b>${count}</b> dokumen</li>`;
                }
            }
            detail_html += '</ul>';

            let failed_html = '';
            if (res.failed && res.failed.length) {
                failed_html = '<p style="color:#c00;margin-top:8px"><b>Beberapa dokumen gagal dihapus:</b><br>'
                    + res.failed.join('<br>') + '</p>';
            }

            frappe.msgprint({
                title: res.success ? __('✅ Purge Selesai') : __('⚠️ Purge Selesai dengan Error'),
                message: `
                    <b>${res.total_documents_deleted} dokumen</b> dihapus.
                    <b>${res.history_deleted || 0} record riwayat</b> dibersihkan.
                    ${detail_html}
                    ${failed_html}
                    <p style="color:#666;font-size:12px;margin-top:8px">
                        Log operasi dicatat di Error Log.
                    </p>`,
                indicator: res.success ? 'green' : 'orange'
            });
        },
        error() {
            frappe.dom.unfreeze();
        }
    });
}
