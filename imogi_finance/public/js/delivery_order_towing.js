// delivery_order_towing.js  — VERSI INTEGRASI FINANCE IMOGI
// Letakkan di: [app]/[app]/doctype/delivery_order_towing/delivery_order_towing.js


// Event handler untuk child table SO Towing Kendaraan
frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
         if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Generate Detail Kendaraan'), function() {
                _generate_detail_kendaraan(frm);
            }, __('Towing'));
        }
        frm.fields_dict['custom_towing_kendaraan'].grid.wrapper.on(
            'click', '.grid-remove-rows', function() {
                setTimeout(function() { _update_item_qty(frm); }, 300);
            }
        );
    }
});

function _generate_detail_kendaraan(frm) {
    var towing_items = (frm.doc.items || []).filter(function(item) {
        return item.item_code && (
            item.item_code.toUpperCase().includes('TOWING') ||
            item.item_code.toUpperCase().includes('RDC')
        );
    });

    if (towing_items.length === 0) {
        frappe.msgprint({
            title: 'Tidak Ada Item Towing',
            message: 'Tambahkan item towing terlebih dahulu di tabel Items.',
            indicator: 'orange'
        });
        return;
    }

    var total_kendaraan = towing_items.reduce(function(a, b) { return a + (b.qty || 1); }, 0);

    frappe.confirm(
        'Generate <b>' + total_kendaraan + '</b> baris kendaraan dari ' + towing_items.length + ' item towing?<br>' +
        '<small>Baris yang sudah ada akan dihapus.</small>',
        function() {
            // Clear existing
            frm.doc.custom_towing_kendaraan = [];
            frm.refresh_field('custom_towing_kendaraan');

            // Generate per item sesuai qty
            towing_items.forEach(function(item) {
                var qty = Math.floor(item.qty) || 1;
                for (var i = 0; i < qty; i++) {
                    var row = frm.add_child('custom_towing_kendaraan');
                    row.so_item_code = item.item_code;
                }
            });

            frm.refresh_field('custom_towing_kendaraan');
            frappe.show_alert({
                message: '✅ ' + frm.doc.custom_towing_kendaraan.length + ' baris kendaraan berhasil digenerate',
                indicator: 'green'
            }, 5);
        }
    );
}

frappe.ui.form.on('SO Towing Kendaraan', {
    so_item_code: function(frm, cdt, cdn) {
        _update_item_qty(frm);
    },
    nomor_polisi: function(frm, cdt, cdn) {
        _update_item_qty(frm);
    },
    custom_towing_kendaraan_add: function(frm) {
        _update_item_qty(frm);
    },
    custom_towing_kendaraan_remove: function(frm) {
        _update_item_qty(frm);
    }
});

var _update_item_qty = function(frm) {
    var kendaraan_list = frm.doc.custom_towing_kendaraan || [];
    var qty_per_item = {};

    kendaraan_list.forEach(function(k) {
        if (k.so_item_code) {
            qty_per_item[k.so_item_code] = (qty_per_item[k.so_item_code] || 0) + 1;
        }
    });

    (frm.doc.items || []).forEach(function(item) {
        var new_qty = qty_per_item[item.item_code] || 0;
        if (new_qty > 0) {
            frappe.model.set_value(item.doctype, item.name, 'qty', new_qty);
        }
    });

    frm.refresh_field('items');
};

frappe.ui.form.on('Delivery Order Towing', {

    // ── REFRESH FORM ──────────────────────────────────────────
    refresh: function(frm) {
        frm.trigger('set_status_indicator');
        frm.trigger('render_custom_buttons');
        frm.trigger('set_field_readonly_by_role');

        // Tampilkan status invoice live dari Finance Imogi
        if (frm.doc.sales_invoice && frm.doc.status === 'Done') {
            frm.trigger('refresh_invoice_status');
        }
    },

    // ── INDIKATOR STATUS ──────────────────────────────────────
    set_status_indicator: function(frm) {
        const map = {
            Draft: 'gray', Assigned: 'orange', 'Pick Up': 'blue',
            Delivered: 'green', Done: 'darkgreen', Cancelled: 'red'
        };
        frm.page.set_indicator(frm.doc.status, map[frm.doc.status] || 'gray');
    },

    // ── TOMBOL CUSTOM ─────────────────────────────────────────
    render_custom_buttons: function(frm) {
        if (frm.is_new()) return;

        const status = frm.doc.status;
        const roles  = frappe.user_roles;
        const isKoor = roles.includes('Towing Koordinator') || roles.includes('Sales Manager');
        const isDrvr = roles.includes('Towing Driver');

        // ─ Draft: Assign & Submit
        if (status === 'Draft' && isKoor) {
            frm.add_custom_button(__('Assign Driver & Submit'), () => {
                frm.trigger('action_assign_submit');
            }, __('Aksi'));
        }

        // ─ Assigned: Buat Uang Jalan via Finance Imogi
        if (status === 'Assigned' && isKoor && !frm.doc.expense_claim) {
            frm.add_custom_button(__('Buat Uang Jalan (Finance Imogi)'), () => {
                frm.trigger('action_create_uang_jalan');
            }, __('Aksi'));
        }

        // ─ Assigned: Konfirmasi Pick Up
        if (status === 'Assigned' && (isDrvr || isKoor)) {
            frm.add_custom_button(__('Konfirmasi Pick Up'), () => {
                frm.trigger('action_pickup');
            }, __('Aksi')).addClass('btn-primary');
        }

        // ─ Pick Up: Konfirmasi Delivered
        if (status === 'Pick Up' && (isDrvr || isKoor)) {
            frm.add_custom_button(__('Konfirmasi Delivered'), () => {
                frm.trigger('action_delivered');
            }, __('Aksi')).addClass('btn-primary');
        }

        // ─ Delivered: Done + Auto Invoice ke Finance Imogi
        if (status === 'Delivered' && isKoor) {
            frm.add_custom_button(__('Selesaikan & Buat Invoice'), () => {
                frm.trigger('action_done_and_invoice');
            }, __('Aksi')).addClass('btn-success');
        }

        // ─ Done tanpa invoice: tombol buat invoice manual
        if (status === 'Done' && isKoor && !frm.doc.sales_invoice) {
            frm.add_custom_button(__('Buat Invoice ke Finance Imogi'), () => {
                frm.trigger('action_create_invoice_only');
            }, __('Aksi')).addClass('btn-warning');
        }

        // ─ Link ke Sales Invoice Finance Imogi
        if (frm.doc.sales_invoice) {
            frm.add_custom_button(__('Lihat Invoice'), () => {
                frappe.set_route('Form', 'Sales Invoice', frm.doc.sales_invoice);
            });
        }

        // ─ Link ke Expense Claim
        if (frm.doc.expense_claim) {
            frm.add_custom_button(__('Lihat Uang Jalan'), () => {
                frappe.set_route('Form', 'Expense Claim', frm.doc.expense_claim);
            });
        }
    },

    // ── READ-ONLY BERDASARKAN ROLE ────────────────────────────
    set_field_readonly_by_role: function(frm) {
        const isDrvrOnly = frappe.user_roles.includes('Towing Driver') &&
                           !frappe.user_roles.includes('Towing Koordinator') &&
                           !frappe.user_roles.includes('Sales Manager');
        if (isDrvrOnly) {
            const editable = ['catatan_driver', 'foto_kendaraan', 'foto_delivered', 'kondisi_tabel'];
            frm.fields.forEach(f => {
                if (!editable.includes(f.df.fieldname)) {
                    frm.set_df_property(f.df.fieldname, 'read_only', 1);
                }
            });
        }
    },

    // ── ACTION: ASSIGN & SUBMIT ───────────────────────────────
    action_assign_submit: function(frm) {
        if (!frm.doc.driver) {
            frappe.msgprint({ title: 'Driver Belum Dipilih',
                message: 'Pilih driver sebelum submit.', indicator: 'orange' });
            frm.set_focus('driver');
            return;
        }
        if (!frm.doc.harga_jasa || frm.doc.harga_jasa <= 0) {
            frappe.msgprint({ title: 'Harga Jasa Kosong',
                message: 'Isi harga jasa sebelum submit.', indicator: 'orange' });
            return;
        }
        frappe.confirm(
            `Submit DO dan assign ke driver <b>${frm.doc.driver_nama || frm.doc.driver}</b>?`,
            () => {
                frm.set_value('status', 'Assigned');
                frm.save('Submit');
            }
        );
    },

    // ── ACTION: BUAT UANG JALAN via FINANCE IMOGI ────────────
    action_create_uang_jalan: function(frm) {
        if (!frm.doc.driver) {
            frappe.msgprint('Pilih driver terlebih dahulu.');
            return;
        }

        // Ambil employee dari driver
        frappe.db.get_value('Driver', frm.doc.driver, 'employee', function(val) {
            const employee = val.employee;
            if (!employee) {
                frappe.msgprint({
                    title: 'Driver belum terhubung ke Employee',
                    message: `Driver <b>${frm.doc.driver}</b> belum memiliki Employee record. ` +
                             `Buka master Driver dan isi field Employee.`,
                    indicator: 'red'
                });
                return;
            }

            frappe.prompt([
                {
                    label: 'Employee',
                    fieldname: 'employee',
                    fieldtype: 'Data',
                    default: employee,
                    read_only: 1,
                },
                {
                    label: 'Nominal Uang Jalan (IDR)',
                    fieldname: 'amount',
                    fieldtype: 'Currency',
                    default: frm.doc.uang_jalan_amount || 0,
                    reqd: 1,
                }
            ], function(values) {
                frappe.show_progress('Menghubungi Finance Imogi...', 30, 100);

                frappe.call({
                    method: 'imogi_finance.overrides.delivery_order_towing.trigger_create_expense_claim',
                    args: {
                        do_name: frm.doc.name,
                        employee: employee,
                        amount: values.amount,
                    },
                    callback: function(r) {
                        frappe.hide_progress();
                        if (r.message && r.message.expense_claim) {
                            frappe.show_alert({
                                message: `Expense Claim ${r.message.expense_claim} dibuat di Finance Imogi!`,
                                indicator: 'green'
                            }, 5);
                            frm.reload_doc();
                        }
                    },
                    error: function(err) {
                        frappe.hide_progress();
                        frappe.msgprint({
                            title: 'Gagal Buat Uang Jalan',
                            message: err.message || 'Cek Error Log untuk detail.',
                            indicator: 'red'
                        });
                    }
                });
            }, 'Buat Uang Jalan via Finance Imogi', 'Buat');
        });
    },

    // ── ACTION: KONFIRMASI PICK UP ────────────────────────────
    action_pickup: function(frm) {
        frappe.prompt([
            { label: 'Catatan Pick Up', fieldname: 'catatan', fieldtype: 'Small Text' }
        ], function(vals) {
            frm.set_value('status', 'Pick Up');
            if (vals.catatan) frm.set_value('catatan_driver', vals.catatan);
            frm.save().then(() =>
                frappe.show_alert({ message: 'Status diupdate ke Pick Up', indicator: 'blue' })
            );
        }, 'Konfirmasi Pick Up', 'Konfirmasi');
    },

    // ── ACTION: KONFIRMASI DELIVERED ─────────────────────────
    action_delivered: function(frm) {
        frappe.prompt([
            { label: 'Catatan Delivered', fieldname: 'catatan', fieldtype: 'Small Text' }
        ], function(vals) {
            frm.set_value('status', 'Delivered');
            if (vals.catatan) {
                const prev = frm.doc.catatan_driver || '';
                frm.set_value('catatan_driver', prev + '\n[Delivered] ' + vals.catatan);
            }
            frm.save().then(() =>
                frappe.show_alert({ message: 'Status diupdate ke Delivered', indicator: 'green' })
            );
        }, 'Konfirmasi Delivered', 'Konfirmasi');
    },

    // ── ACTION: DONE + AUTO INVOICE ke FINANCE IMOGI ─────────
    action_done_and_invoice: function(frm) {
        frappe.confirm(
            'Selesaikan DO ini? Sales Invoice akan otomatis dibuat di <b>Finance Imogi</b> dan ' +
            'dikirim ke Direktur untuk approval.',
            function() {
                frm.set_value('status', 'Done');
                frm.save().then(() => {
                    frm.trigger('call_create_invoice');
                });
            }
        );
    },

    // ── ACTION: BUAT INVOICE MANUAL (jika sudah Done tapi belum ada invoice) ──
    action_create_invoice_only: function(frm) {
        frappe.confirm(
            `Buat Sales Invoice untuk DO <b>${frm.doc.name}</b> di Finance Imogi?`,
            () => frm.trigger('call_create_invoice')
        );
    },

    // ── SHARED: PANGGIL API CREATE INVOICE ───────────────────
    call_create_invoice: function(frm) {
        frappe.show_progress('Membuat invoice di Finance Imogi...', 50, 100);

        frappe.call({
            method: 'imogi_finance.overrides.delivery_order_towing.trigger_create_invoice',
            args: { do_name: frm.doc.name },
            callback: function(r) {
                frappe.hide_progress();
                if (r.message) {
                    if (r.message.status === 'created') {
                        frappe.show_alert({
                            message: `Invoice ${r.message.invoice} berhasil dibuat di Finance Imogi!`,
                            indicator: 'green'
                        }, 7);
                    } else if (r.message.status === 'already_exists') {
                        frappe.show_alert({
                            message: `Invoice sudah ada: ${r.message.invoice}`,
                            indicator: 'blue'
                        }, 5);
                    }
                    frm.reload_doc();
                }
            },
            error: function(err) {
                frappe.hide_progress();
                frappe.msgprint({
                    title: 'Gagal Buat Invoice',
                    message: (err.message || 'Cek Error Log') +
                             '<br><br>Kemungkinan penyebab:<ul>' +
                             '<li>Item JASA-TOWING-001 belum ada di Finance Imogi</li>' +
                             '<li>API key Finance Imogi belum dikonfigurasi di site_config.json</li>' +
                             '<li>Koneksi ke Finance Imogi gagal</li></ul>',
                    indicator: 'red'
                });
            }
        });
    },

    // ── REFRESH STATUS INVOICE DARI FINANCE IMOGI ────────────
    refresh_invoice_status: function(frm) {
        if (!frm.doc.sales_invoice) return;

        frappe.call({
            method: 'imogi_finance.overrides.delivery_order_towing.get_invoice_status_from_imogi',
            args: { invoice_name: frm.doc.sales_invoice },
            callback: function(r) {
                if (r.message) {
                    const inv = r.message;
                    const statusColor = {
                        'Paid': 'green', 'Unpaid': 'orange', 'Overdue': 'red',
                        'Draft': 'gray', 'Cancelled': 'red', 'Submitted': 'blue'
                    }[inv.status] || 'gray';

                    // Tampilkan badge status invoice di samping field
                    const badge = `<span class="indicator-pill ${statusColor}" 
                        style="font-size:11px;padding:2px 8px;border-radius:10px">
                        ${inv.status}</span>`;

                    frm.set_df_property('sales_invoice', 'description',
                        `Status: ${badge} | ` +
                        `Outstanding: <b>Rp ${(inv.outstanding_amount || 0).toLocaleString('id-ID')}</b>`
                    );
                }
            }
        });
    },

    // ── FIELD TRIGGERS ───────────────────────────────────────
    customer: function(frm) {
        if (frm.doc.customer) {
            frappe.db.get_value('Customer', frm.doc.customer, 'customer_name', v => {
                frm.set_value('customer_name', v.customer_name);
            });
        }
    },

    driver: function(frm) {
        if (frm.doc.driver) {
            frappe.db.get_value('Driver', frm.doc.driver, 'full_name', v => {
                frm.set_value('driver_nama', v.full_name || '');
            });
        }
    },
});