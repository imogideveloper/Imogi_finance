frappe.ui.form.on('Tax Invoice OCR Upload', {
    refresh(frm) {
        if (frm.is_new() || !frm.doc.dpp || frm.doc.verification_status !== 'Verified') return;

        frm.add_custom_button(__('🧾 Create Purchase Invoice'), async () => {
            const dialog = new frappe.ui.Dialog({
                title: __('Create Purchase Invoice'),
                fields: [
                    { fieldname: 'supplier', fieldtype: 'Link', options: 'Supplier', label: __('Supplier'), reqd: 1 },
                    { fieldname: 'scenario', fieldtype: 'Select', label: __('Purchase Type'), options: 'expense\nasset\ninventory', reqd: 1, default: 'expense' },
                    { fieldname: 'item_code', fieldtype: 'Link', options: 'Item', label: __('Item'), reqd: 1 },
                    { fieldname: 'qty', fieldtype: 'Float', label: __('Qty'), reqd: 1, default: 1 },
                ],
                primary_action_label: __('Create PI'),
                primary_action: async (values) => {
                    dialog.hide();
                    const r = await frappe.call({
                        method: 'imogi_finance.api.tax_invoice.create_purchase_invoice_from_ocr',
                        args: {
                            upload_name: frm.doc.name,
                            supplier: values.supplier,
                            item_code: values.item_code,
                            qty: values.qty,
                            scenario: values.scenario,
                        },
                        freeze: true,
                        freeze_message: __('Creating Purchase Invoice...'),
                    });
                    if (r.message) {
                        frappe.show_alert({ message: __('✅ ' + r.message.purchase_invoice + ' created!'), indicator: 'green' }, 5);
                        frappe.set_route('Form', 'Purchase Invoice', r.message.purchase_invoice);
                    }
                },
            });
            dialog.show();
        }, __('Tax Invoice OCR'));
    }
});
