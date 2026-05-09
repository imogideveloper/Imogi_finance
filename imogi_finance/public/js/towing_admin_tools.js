// towing_admin_tools.js
// Tombol tersembunyi untuk Administrator — hapus semua data transaksi towing
// Muncul hanya di halaman profil "Administrator" dan hanya jika login sebagai Administrator

frappe.ui.form.on('User', {
    refresh(frm) {
        if (frappe.session.user !== 'Administrator') return;
        if (frm.doc.name !== 'Administrator') return;

        frm.add_custom_button(__('🗑️ Hapus Semua Data Towing'), function() {
            _towing_purge_dialog(frm);
        }, __('🔧 Towing Admin'));
    }
});


function _towing_purge_dialog(frm) {
    frappe.dom.freeze(__('Menghitung data towing...'));

    frappe.call({
        method: 'imogi_finance.api.towing_admin.preview_towing_data',
        callback(r) {
            frappe.dom.unfreeze();
            if (!r.message) return;

            const data    = r.message;
            const total   = data.total;
            const summary = data.summary;

            if (total === 0) {
                frappe.msgprint({
                    title: __('Tidak Ada Data'),
                    message: __('Tidak ada dokumen transaksi towing yang ditemukan.'),
                    indicator: 'green'
                });
                return;
            }

            // Buat tabel ringkasan
            let rows = '';
            const order = [
                'Payment Entry',
                'Purchase Invoice',
                'Purchase Order',
                'Sales Invoice',
                'Delivery Order Towing',
                'Sales Order'
            ];
            order.forEach(dt => {
                const cnt = summary[dt] || 0;
                if (cnt === 0) return;
                rows += `<tr>
                    <td style="padding:4px 10px">${dt}</td>
                    <td style="padding:4px 10px;text-align:right;color:#d44"><b>${cnt} dokumen</b></td>
                </tr>`;
            });

            const table_html = `
                <table style="width:100%;border-collapse:collapse;margin-top:10px;font-size:13px">
                    <thead>
                        <tr style="background:#f5f5f5">
                            <th style="padding:6px 10px;text-align:left">DocType</th>
                            <th style="padding:6px 10px;text-align:right">Jumlah</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                    <tfoot>
                        <tr style="border-top:2px solid #ccc">
                            <td style="padding:6px 10px"><b>TOTAL</b></td>
                            <td style="padding:6px 10px;text-align:right;color:#d44"><b>${total} dokumen</b></td>
                        </tr>
                    </tfoot>
                </table>`;

            const d = new frappe.ui.Dialog({
                title: __('⚠️ Hapus Semua Data Transaksi Towing'),
                fields: [
                    {
                        fieldtype: 'HTML',
                        options: `
                            <div style="padding:8px 0">
                                <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:10px;margin-bottom:10px">
                                    ⚠️ <b>Perhatian:</b> Operasi ini akan menghapus <b>${total} dokumen</b> secara permanen.
                                    Dokumen yang Submitted akan di-cancel terlebih dahulu, lalu dihapus.
                                    <b>Tidak bisa di-undo!</b>
                                </div>
                                ${table_html}
                                <p style="margin-top:14px;color:#d44;font-weight:bold">
                                    Ketik <code>HAPUS</code> di bawah untuk konfirmasi:
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
                primary_action_label: __('🗑️ Hapus Semua Sekarang'),
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
    frappe.dom.freeze(__('Menghapus semua data towing... Mohon tunggu.'));

    frappe.call({
        method: 'imogi_finance.api.towing_admin.purge_towing_data',
        args: { confirm: 'HAPUS' },
        timeout: 300,  // 5 menit untuk data banyak
        callback(r) {
            frappe.dom.unfreeze();
            if (!r.message) return;

            const res = r.message;
            if (res.success) {
                let detail_html = '<ul style="margin-top:8px">';
                const order = [
                    'Payment Entry', 'Purchase Invoice', 'Purchase Order',
                    'Sales Invoice', 'Delivery Order Towing', 'Sales Order'
                ];
                order.forEach(dt => {
                    const cnt = res.detail[dt] || 0;
                    if (cnt > 0) detail_html += `<li>${dt}: <b>${cnt}</b> dokumen dihapus</li>`;
                });
                detail_html += '</ul>';

                let failed_html = '';
                if (res.failed && Object.keys(res.failed).length > 0) {
                    failed_html = '<div style="color:#d44;margin-top:8px"><b>Gagal:</b><ul>';
                    for (const [dt, items] of Object.entries(res.failed)) {
                        items.forEach(f => {
                            failed_html += `<li>${dt} ${f.name}: ${f.error}</li>`;
                        });
                    }
                    failed_html += '</ul></div>';
                }

                frappe.msgprint({
                    title: __('✅ Data Towing Berhasil Dihapus'),
                    message: `
                        <b>${res.total_deleted} dokumen</b> berhasil dihapus.
                        ${detail_html}
                        ${failed_html}
                        <p style="color:#666;font-size:12px;margin-top:8px">
                            Detail operasi tercatat di Error Log.
                        </p>`,
                    indicator: res.total_deleted > 0 ? 'green' : 'orange'
                });

                // Reload halaman setelah hapus
                setTimeout(() => frm.reload_doc(), 2000);
            }
        },
        error() {
            frappe.dom.unfreeze();
        }
    });
}
