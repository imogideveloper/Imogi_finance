frappe.ui.form.on('Driver Commission', {
    refresh(frm) {
        frm.trigger('toggle_buttons');
    },

    toggle_buttons(frm) {
        if (frm.is_new()) return;

        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__('Generate'), () => frm.trigger('do_generate'))
                .addClass('btn-primary');
        }

        if (frm.doc.docstatus === 1
            && frm.doc.status === 'Approved'
            && !frm.doc.payment_entry) {
            frm.add_custom_button(__('Create Payment Entry'),
                () => frm.trigger('do_create_payment_entry'))
                .addClass('btn-primary');
        }

        if (frm.doc.payment_entry) {
            frm.add_custom_button(__('Open Payment Entry'), () => {
                frappe.set_route('Form', 'Payment Entry', frm.doc.payment_entry);
            });
        }
    },

    do_generate(frm) {
        if (!frm.doc.driver || !frm.doc.from_date || !frm.doc.to_date) {
            frappe.msgprint(__('Driver, From Date, dan To Date wajib diisi.'));
            return;
        }
        if ((frm.doc.commissions || []).length) {
            frappe.confirm(
                __('Tabel komisi akan ditimpa. Lanjutkan?'),
                () => frm.trigger('_run_generate'),
            );
        } else {
            frm.trigger('_run_generate');
        }
    },

    _run_generate(frm) {
        frappe.call({
            method: 'imogi_finance.doctype.driver_commission.driver_commission.fetch_eligible_dos',
            args: {
                driver: frm.doc.driver,
                from_date: frm.doc.from_date,
                to_date: frm.doc.to_date,
                exclude_name: frm.doc.name || null,
            },
            freeze: true,
            freeze_message: __('Mengambil DO Towing & menghitung komisi...'),
            callback: (r) => {
                const rows = r.message || [];
                frm.clear_table('commissions');
                rows.forEach((row) => {
                    const child = frm.add_child('commissions');
                    Object.assign(child, row);
                });
                frm.refresh_field('commissions');
                frm.dirty();
                frappe.show_alert({
                    message: __('{0} baris diisi', [rows.length]),
                    indicator: rows.length ? 'green' : 'orange',
                });
            },
        });
    },

    do_create_payment_entry(frm) {
        frappe.call({
            method: 'imogi_finance.doctype.driver_commission.driver_commission.make_payment_entry',
            args: { name: frm.doc.name },
            freeze: true,
            freeze_message: __('Membuat Payment Entry...'),
            callback: (r) => {
                if (r.message && r.message.name) {
                    frappe.set_route('Form', 'Payment Entry', r.message.name);
                }
                frm.reload_doc();
            },
        });
    },
});


frappe.ui.form.on('Driver Commission Item', {
    komisi_amount(frm) {
        let total = 0;
        (frm.doc.commissions || []).forEach((r) => {
            total += flt(r.komisi_amount);
        });
        frm.set_value('total_komisi', total);
        frm.set_value('do_count', (frm.doc.commissions || []).length);
    },

    commissions_remove(frm) {
        let total = 0;
        (frm.doc.commissions || []).forEach((r) => {
            total += flt(r.komisi_amount);
        });
        frm.set_value('total_komisi', total);
        frm.set_value('do_count', (frm.doc.commissions || []).length);
    },
});
