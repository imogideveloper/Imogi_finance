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

        // Sembunyikan tombol Cancel bawaan ERPNext saat SO sudah submit
        // agar user pakai tombol "Cancel SO Towing" yang sudah ada validasinya
        if (frm.doc.docstatus === 1) {
            _hide_native_cancel_btn(frm);
        }

        _inject_generate_button_on_items_grid(frm);
        [250, 700, 1400].forEach(function(ms) {
            setTimeout(function() {
                _inject_generate_button_on_items_grid(frm);
            }, ms);
        });
        frm.fields_dict['custom_towing_kendaraan'].grid.wrapper.on(
            'click', '.grid-remove-rows', function() {
                setTimeout(function() { _update_item_qty(frm); }, 300);
            }
        );
    }
});

// Sembunyikan tombol "Cancel" bawaan Frappe/ERPNext
function _hide_native_cancel_btn(frm) {
    [100, 400, 800].forEach(function(ms) {
        setTimeout(function() {
            frm.page.wrapper.find('.page-actions .btn').filter(function() {
                return $(this).text().trim() === __('Cancel');
            }).hide();
        }, ms);
    });
}

// Sembunyikan tombol "Submit" bawaan — pakai workflow "Assign Driver" saja
function _hide_native_submit_btn(frm) {
    [100, 400, 800, 1500].forEach(function(ms) {
        setTimeout(function() {
            frm.page.wrapper.find('.page-actions .btn').filter(function() {
                const label = $(this).text().trim();
                return label === __('Submit') || label === 'Submit';
            }).hide();
        }, ms);
    });
}

// Fallback keyword (case-insensitive) untuk item lama yang belum ditandai
// flag custom_is_towing_rute. Penanda utama adalah field di master Item,
// jadi item baru cukup dicentang tanpa perlu ubah kode ini.
var TOWING_ITEM_KEYWORDS = ['TOWING', 'RDC', 'POOL'];

function _is_towing_item(item) {
    if (!item || !item.item_code) return false;
    // Penanda utama: flag dari master Item (di-fetch ke Sales Order Item).
    if (item.custom_is_towing_rute) return true;
    // Fallback: deteksi keyword untuk item yang belum ditandai.
    var code = item.item_code.toUpperCase();
    return TOWING_ITEM_KEYWORDS.some(function(kw) {
        return code.includes(kw);
    });
}

function _generate_detail_kendaraan(frm) {
    var towing_items = (frm.doc.items || []).filter(_is_towing_item);

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

function _inject_generate_button_on_items_grid(frm) {
    var items_grid = frm.fields_dict && frm.fields_dict.items && frm.fields_dict.items.grid;
    if (!items_grid || !items_grid.wrapper) return;

    var $wrapper = $(items_grid.wrapper);
    var $grid_buttons = $wrapper.find('.grid-buttons');
    if (!$grid_buttons.length) return;

    var button_class = 'btn-generate-detail-kendaraan-grid';
    $grid_buttons.find('.' + button_class).remove();

    var $button = $('<button class="btn btn-xs btn-secondary ' + button_class + '" type="button"></button>')
        .text(__('Generate Detail Kendaraan'));

    $button.on('click', function() {
        _generate_detail_kendaraan(frm);
    });

    var $add_multiple = $grid_buttons.find('.grid-add-multiple-rows');
    if ($add_multiple.length) {
        $button.insertAfter($add_multiple);
    } else {
        $grid_buttons.append($button);
    }
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

const DO_TOWING_STATUS_COLORS = {
	Draft: "red",
	Assigned: "orange",
	"Pick Up": "purple",
	Delivered: "green",
	"Awaiting Dokument": "yellow",
	Done: "darkgreen",
	Cancelled: "gray",
};

const INVOICE_DOC_FIELDS = ["attachment_invoice", "tanggal_invoice"];

function is_invoice_document_status(status) {
	return status === "Awaiting Dokument" || status === "Done";
}

function sync_invoice_document_fields(frm) {
	const show = is_invoice_document_status(frm.doc.status);

	INVOICE_DOC_FIELDS.forEach((fieldname) => {
		const field = frm.fields_dict[fieldname];
		if (!field) {
			return;
		}

		field.df.allow_on_submit = show ? 1 : 0;
		field.df.read_only = frm.doc.status === "Done" ? 1 : 0;
		if (show) {
			field.df.hidden = 0;
			field.df.hidden_due_to_dependency = 0;
		}
	});
}

function install_do_status_indicator(frm) {
	if (!frm.toolbar || frm._do_status_indicator_patched) {
		return;
	}
	frm._do_status_indicator_patched = true;

	const default_set_indicator = frm.toolbar.set_indicator.bind(frm.toolbar);
	frm.toolbar.set_indicator = function () {
		if (frm.doc.__unsaved) {
			frm.page.set_indicator(__("Not Saved"), "orange");
			return;
		}

		const status = frm.doc.status;
		if (status) {
			frm.page.set_indicator(
				__(status),
				DO_TOWING_STATUS_COLORS[status] || "gray"
			);
			return;
		}

		default_set_indicator();
	};
}

function set_do_status_indicator(frm) {
	install_do_status_indicator(frm);

	if (frm.doc.__unsaved) {
		frm.page.set_indicator(__("Not Saved"), "orange");
		return;
	}

	const status = frm.doc.status;
	if (status) {
		frm.page.set_indicator(__(status), DO_TOWING_STATUS_COLORS[status] || "gray");
	} else if (frm.toolbar) {
		frm.toolbar.set_indicator();
	}
}

function apply_do_workflow_action(frm, action, options = {}) {
	const { before_apply, after_apply } = options;

	return Promise.resolve(before_apply ? before_apply(frm) : null)
		.then(() => {
			if (frm.is_dirty()) {
				return frm.save();
			}
		})
		.then(() => {
			frappe.dom.freeze(__("Memproses..."));
			return frappe.xcall("frappe.model.workflow.apply_workflow", {
				doc: frm.doc,
				action,
			});
		})
		.then(() => (after_apply ? after_apply(frm) : null))
		.then(() => frm.reload_doc())
		.then(() => {
			sync_invoice_document_fields(frm);
			if (frm.layout) {
				frm.layout.refresh_dependency();
			}
			frm.refresh_fields();
			set_do_status_indicator(frm);
		})
		.finally(() => frappe.dom.unfreeze());
}

frappe.ui.form.on('Delivery Order Towing', {

    onload(frm) {
        install_do_status_indicator(frm);
    },

    onload_post_render(frm) {
        set_do_status_indicator(frm);
    },

    status(frm) {
        sync_invoice_document_fields(frm);
        if (frm.layout) {
            frm.layout.refresh_dependency();
        }
        frm.refresh_fields();
        set_do_status_indicator(frm);
    },

    // ── REFRESH FORM ──────────────────────────────────────────
    refresh: function(frm) {
     if (!frm.is_new()) {
    const editable_fields = ['driver', 'driver_nama', 'koordinator', 'kendaraan_towing'];
    sync_invoice_document_fields(frm);

    frm.fields.forEach(function(f) {
        const fn = f.df.fieldname;
        if (fn === 'harga_jasa') {
            f.df.hidden = 1;
            f.df.read_only = 1;
            f.df.allow_on_submit = 0;
        } else if (
            is_invoice_document_status(frm.doc.status) &&
            INVOICE_DOC_FIELDS.includes(fn)
        ) {
            // Field invoice ditangani sync_invoice_document_fields()
        } else if (!editable_fields.includes(fn) &&
            f.df.fieldtype !== 'Section Break' &&
            f.df.fieldtype !== 'Column Break') {
            f.df.read_only = 1;
            f.df.allow_on_submit = 0;
        } else if (editable_fields.includes(fn)) {
            f.df.read_only = 0;
        }
    });

    frm.refresh_fields();
    if (frm.layout) {
        frm.layout.refresh_dependency();
    }

    // Force hide harga_jasa via DOM
    setTimeout(function() {
        if (frm.fields_dict['harga_jasa']) {
            frm.fields_dict['harga_jasa'].$wrapper.hide();
        }
    }, 200);
}

        set_do_status_indicator(frm);
        frm.trigger('render_custom_buttons');
        frm.trigger('set_field_readonly_by_role');

        if (frm.doc.docstatus === 0) {
            _hide_native_submit_btn(frm);
        }

        // Tampilkan status invoice live dari Finance Imogi
        if (frm.doc.sales_invoice && frm.doc.status === 'Done') {
            frm.trigger('refresh_invoice_status');
        }

        // toolbar.refresh() dipanggil setelah handler ini — set ulang indikator workflow.
        frappe.after_ajax(() => set_do_status_indicator(frm));
    },

    // ── INDIKATOR STATUS ──────────────────────────────────────
    set_status_indicator: function(frm) {
        set_do_status_indicator(frm);
    },

    // ── TOMBOL CUSTOM ─────────────────────────────────────────
    render_custom_buttons: function(frm) {
        if (frm.is_new()) return;

        const status       = frm.doc.status;
        const roles        = frappe.user_roles;
        const isKoor       = roles.includes('Sales Manager') || roles.includes('Admin Towing');
        const isDrvr       = roles.includes('Towing Driver');
        const isDriverOnly = isDrvr && !isKoor;

        // ══════════════════════════════════════════════════════
        // MODE DRIVER (Towing Driver, bukan Admin/Koordinator)
        // Aturan:
        //  • Status Draft           → TIDAK ADA tombol
        //  • Belum di-assign driver → TIDAK ADA tombol
        //  • Sudah assigned, TAPI bukan driver tujuan DO ini → TIDAK ADA tombol
        //  • Sudah assigned DAN driver tujuan              → tampilkan aksi
        // ══════════════════════════════════════════════════════
        if (isDriverOnly) {
            // Hanya tampilkan "Lihat Invoice" jika ada
            if (frm.doc.sales_invoice) {
                frm.add_custom_button(__('Lihat Invoice'), () => {
                    frappe.set_route('Form', 'Sales Invoice', frm.doc.sales_invoice);
                });
            }

            // Status Draft atau belum ada driver → tidak ada tombol aksi
            if (status === 'Draft' || !frm.doc.driver) return;

            // Cek apakah user yang login adalah driver yang di-assign ke DO ini
            frappe.db.get_value('Driver', frm.doc.driver, 'user', function(r) {
                if (!r || r.user !== frappe.session.user) {
                    // Bukan driver tujuan → tidak tampilkan tombol aksi
                    return;
                }

                // Driver tujuan yang benar — tampilkan tombol sesuai status
                if (status === 'Assigned') {
                    frm.add_custom_button(__('Konfirmasi Pick Up'), () => {
                        frm.trigger('action_pickup');
                    }, __('Aksi')).addClass('btn-primary');
                }
                if (status === 'Pick Up') {
                    frm.add_custom_button(__('Konfirmasi Delivered'), () => {
                        frm.trigger('action_delivered');
                    }, __('Aksi')).addClass('btn-primary');
                }
                if (status === 'Delivered') {
                    frm.add_custom_button(__('Selesaikan DO'), () => {
                        frm.trigger('action_complete_do');
                    }, __('Aksi')).addClass('btn-success');
                }
                // Status Awaiting Dokument → tidak ada tombol untuk driver
            });
            return; // Stop — driver tidak perlu lihat tombol Koordinator
        }

        // ══════════════════════════════════════════════════════
        // MODE KOORDINATOR / ADMIN TOWING
        // ══════════════════════════════════════════════════════
        if (!isKoor) return;

        // ─ Draft: Assign & Submit
        if (status === 'Draft') {
            frm.add_custom_button(__('Assign Driver & Submit'), () => {
                frm.trigger('action_assign_submit');
            }, __('Aksi'));
        }

        // ─ Assigned: Buat Uang Jalan
        if (status === 'Assigned' && !frm.doc.expense_claim) {
            frm.add_custom_button(__('Buat Uang Jalan (Finance Imogi)'), () => {
                frm.trigger('action_create_uang_jalan');
            }, __('Aksi'));
        }

        // ─ Assigned: Konfirmasi Pick Up
        if (status === 'Assigned') {
            frm.add_custom_button(__('Konfirmasi Pick Up'), () => {
                frm.trigger('action_pickup');
            }, __('Aksi')).addClass('btn-primary');
        }

        // ─ Pick Up: Konfirmasi Delivered
        if (status === 'Pick Up') {
            frm.add_custom_button(__('Konfirmasi Delivered'), () => {
                frm.trigger('action_delivered');
            }, __('Aksi')).addClass('btn-primary');
        }

        // ─ Delivered: Selesaikan DO
        if (status === 'Delivered') {
            frm.add_custom_button(__('Selesaikan DO'), () => {
                frm.trigger('action_complete_do');
            }, __('Aksi')).addClass('btn-primary');
        }

        // ─ Awaiting Dokument: Konfirmasi Dokumen → Done
        if (status === 'Awaiting Dokument') {
            frm.add_custom_button(__('Konfirmasi Dokumen'), () => {
                frm.trigger('action_confirm_document');
            }, __('Aksi')).addClass('btn-success');
        }

        // ─ Delivered: shortcut selesaikan + buat invoice (2 langkah workflow)
        if (status === 'Delivered') {
            frm.add_custom_button(__('Selesaikan & Buat Invoice'), () => {
                frm.trigger('action_done_and_invoice');
            }, __('Aksi')).addClass('btn-success');
        }

        // ─ Done tanpa invoice: buat invoice manual
        if (status === 'Done' && !frm.doc.sales_invoice) {
            frm.add_custom_button(__('Buat Invoice ke Finance Imogi'), () => {
                frm.trigger('action_create_invoice_only');
            }, __('Aksi')).addClass('btn-warning');
        }

        // ─ Link ke Sales Invoice
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
                           !frappe.user_roles.includes('Sales Manager') &&
                           !frappe.user_roles.includes('Admin Towing');
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
                apply_do_workflow_action(frm, 'Assign Driver').then(() => {
                    frappe.show_alert({
                        message: __('Status DO diupdate ke Assigned'),
                        indicator: 'green',
                    }, 5);
                });
            }
        );
    },

    action_pickup: function(frm) {
        frappe.prompt([
            { label: 'Catatan Pick Up', fieldname: 'catatan', fieldtype: 'Small Text' }
        ], function(vals) {
            apply_do_workflow_action(frm, 'Konfirmasi Pick Up', {
                before_apply() {
                    if (vals.catatan) {
                        return frm.set_value('catatan_driver', vals.catatan);
                    }
                },
                after_apply() {
                    frappe.show_alert({ message: 'Status diupdate ke Pick Up', indicator: 'blue' });
                },
            });
        }, 'Konfirmasi Pick Up', 'Konfirmasi');
    },

    action_delivered: function(frm) {
        frappe.prompt([
            { label: 'Catatan Delivered', fieldname: 'catatan', fieldtype: 'Small Text' }
        ], function(vals) {
            apply_do_workflow_action(frm, 'Konfirmasi Delivered', {
                before_apply() {
                    if (!vals.catatan) {
                        return;
                    }
                    const prev = frm.doc.catatan_driver || '';
                    return frm.set_value('catatan_driver', prev + '\n[Delivered] ' + vals.catatan);
                },
                after_apply() {
                    frappe.show_alert({ message: 'Status diupdate ke Delivered', indicator: 'green' });
                },
            });
        }, 'Konfirmasi Delivered', 'Konfirmasi');
    },

    action_complete_do: function(frm) {
        frappe.confirm(
            __('Tandai DO <b>{0}</b> sebagai selesai?<br>'
               + '<small>Status akan berubah ke <b>Awaiting Dokument</b>.</small>', [frm.doc.name]),
            () => {
                apply_do_workflow_action(frm, 'Selesaikan DO', {
                    after_apply() {
                        frappe.show_alert({
                            message: __('Status DO diupdate ke Awaiting Dokument'),
                            indicator: 'orange',
                        }, 5);
                    },
                });
            }
        );
    },

    action_confirm_document: function(frm) {
        frappe.confirm(
            __('Konfirmasi dokumen DO <b>{0}</b> selesai?', [frm.doc.name]),
            () => {
                apply_do_workflow_action(frm, 'Konfirmasi Dokumen', {
                    after_apply() {
                        frappe.show_alert({
                            message: __('Status DO diupdate ke Done'),
                            indicator: 'green',
                        }, 5);
                    },
                });
            }
        );
    },

    action_done_and_invoice: function(frm) {
        frappe.confirm(
            'Selesaikan DO ini lalu lanjut ke Awaiting Dokument?',
            function() {
                apply_do_workflow_action(frm, 'Selesaikan DO').then(() => {
                    frappe.msgprint({
                        title: __('Langkah Berikutnya'),
                        message: __('Setelah dokumen lengkap, gunakan aksi <b>Konfirmasi Dokumen</b> untuk menandai Done.'),
                        indicator: 'blue',
                    });
                });
            }
        );
    },
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