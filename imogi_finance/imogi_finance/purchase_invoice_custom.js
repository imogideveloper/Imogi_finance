/**
 * Custom script untuk Purchase Invoice
 * Tambahkan button "Generate Deferred Amortization"
 */

frappe.ui.form.on('Purchase Invoice', {
    refresh: function(frm) {
        // Cek jika PI sudah submitted dan punya deferred items
        if (frm.doc.docstatus === 1) {
            // Cek apakah ada deferred items
            let has_deferred = frm.doc.items.some(item => item.deferred_expense_account);

            if (has_deferred) {
                // Tambah button "Generate Amortization"
                frm.add_custom_button(__('Generate Amortization'), function() {
                    frappe.call({
                        method: 'imogi_finance.services.amortization_processor.create_amortization_schedule_for_pi',
                        args: { pi_name: frm.doc.name },
                        callback: function(r) {
                            if (r.message.status === 'success') {
                                frappe.msgprint({
                                    title: __('Amortization Generated'),
                                    message: `
                                        <p><strong>Schedules:</strong> ${r.message.total_schedules}</p>
                                        <p><strong>Journal Entries Created:</strong> ${r.message.journal_entries.length}</p>
                                        <p><strong>Total Amount:</strong> Rp ${r.message.total_amount.toLocaleString('id-ID')}</p>
                                    `,
                                    indicator: 'green'
                                });
                            } else {
                                frappe.msgprint({
                                    title: __('Failed'),
                                    message: `No deferred items found or error occurred`,
                                    indicator: 'red'
                                });
                            }
                        }
                    });
                }, __('Deferred'));
            }
        }
    }
});
