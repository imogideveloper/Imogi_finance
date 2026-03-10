// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('Customer Receipt', {
    refresh: function(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.outstanding_amount > 0) {
            frm.add_custom_button(__('Make Payment Entry'), function() {
                show_payment_dialog(frm);
            });
        }

        // Track print action removed - frm.page.on is not available in form context
        // Print tracking should be handled server-side if needed
    },

    onload: function(frm) {
        // Set query filter for Receipt Design - only show active designs
        frm.set_query('receipt_design', function() {
            return {
                filters: {
                    'is_active': 1
                }
            };
        });

        // Set query filter for Digital Stamp Template
        frm.set_query('digital_stamp_template', function() {
            return {
                filters: {
                    'is_active': 1
                }
            };
        });
    },

    receipt_purpose: function(frm) {
        // Clear items when receipt purpose changes
        frm.clear_table('items');
        frm.refresh_field('items');
        // Update query filters for future rows
        setup_item_query_filters(frm);
    },

    customer: function(frm) {
        // Clear items when customer changes
        frm.clear_table('items');
        frm.refresh_field('items');
        // Update query filters for future rows
        setup_item_query_filters(frm);
    },

    company: function(frm) {
        // Clear items when company changes
        frm.clear_table('items');
        frm.refresh_field('items');
        // Update query filters for future rows
        setup_item_query_filters(frm);
    }
});

// Helper function to setup query filters
function setup_item_query_filters(frm) {
    // Set up query filters for Sales Invoice
    if (frm.doc.receipt_purpose === 'Billing (Sales Invoice)') {
        frm.set_query('sales_invoice', 'items', function() {
            return {
                filters: {
                    'customer': frm.doc.customer || '',
                    'company': frm.doc.company || '',
                    'docstatus': 1,
                    'outstanding_amount': ['>', 0]
                }
            };
        });
        // Clear sales_order query
        frm.set_query('sales_order', 'items', function() {
            return { filters: { 'name': ['=', ''] } }; // Return empty to hide
        });
    }
    // Set up query filters for Sales Order
    else if (frm.doc.receipt_purpose === 'Before Billing (Sales Order)') {
        frm.set_query('sales_order', 'items', function() {
            return {
                filters: {
                    'customer': frm.doc.customer || '',
                    'company': frm.doc.company || '',
                    'docstatus': 1
                }
            };
        });
        // Clear sales_invoice query
        frm.set_query('sales_invoice', 'items', function() {
            return { filters: { 'name': ['=', ''] } }; // Return empty to hide
        });
    }
}

// Child table behavior: fetch reference data and populate fields
frappe.ui.form.on('Customer Receipt Item', {
    items_add: function(frm) {
        setup_item_query_filters(frm);
    },

    sales_invoice: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || !row.sales_invoice) return;

        // If purpose not set, assume Billing (Sales Invoice)
        if (!frm.doc.receipt_purpose) {
            frm.set_value('receipt_purpose', 'Billing (Sales Invoice)');
            setup_item_query_filters(frm);
        } else if (frm.doc.receipt_purpose !== 'Billing (Sales Invoice)') {
            frappe.msgprint(__('Please set Receipt Purpose to "Billing (Sales Invoice)" to use Sales Invoice'));
            row.sales_invoice = '';
            frm.refresh_field('items');
            return;
        }

        // Clear opposite reference if filled
        if (row.sales_order) {
            row.sales_order = '';
        }

        // Fetch reference data using custom API
        frappe.call({
            method: 'imogi_finance.imogi_finance.doctype.customer_receipt.customer_receipt.get_reference_data',
            args: {
                doctype: 'Sales Invoice',
                name: row.sales_invoice
            },
            callback: function(r) {
                if (!r.message) return;
                const data = r.message;
                const current_row = locals[cdt][cdn];
                if (!current_row) return;

                // Auto-fill customer/company if missing; else validate match
                if (!frm.doc.customer) {
                    frm.set_value('customer', data.customer);
                } else if (frm.doc.customer !== data.customer) {
                    frappe.msgprint(__('Sales Invoice customer does not match Customer Receipt customer'));
                    current_row.sales_invoice = '';
                    frm.refresh_field('items');
                    return;
                }

                if (!frm.doc.company) {
                    frm.set_value('company', data.company);
                } else if (frm.doc.company !== data.company) {
                    frappe.msgprint(__('Sales Invoice company does not match Customer Receipt company'));
                    current_row.sales_invoice = '';
                    frm.refresh_field('items');
                    return;
                }

                // Populate child row fields directly (no frappe.model.set_value)
                current_row.reference_date = data.reference_date;
                current_row.reference_outstanding = data.reference_outstanding;
                if (!current_row.amount_to_collect || current_row.amount_to_collect === 0) {
                    current_row.amount_to_collect = data.reference_outstanding;
                }

                // Refresh grid to show updated values
                frm.refresh_field('items');

                frappe.show_alert({
                    message: __('Data loaded: Outstanding {0}', [format_currency(data.reference_outstanding)]),
                    indicator: 'green'
                }, 3);
            },
            error: function() {
                const current_row = locals[cdt][cdn];
                if (current_row) {
                    current_row.sales_invoice = '';
                    frm.refresh_field('items');
                }
            }
        });
    },

    sales_order: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row || !row.sales_order) return;

        // If purpose not set, assume Before Billing (Sales Order)
        if (!frm.doc.receipt_purpose) {
            frm.set_value('receipt_purpose', 'Before Billing (Sales Order)');
            setup_item_query_filters(frm);
        } else if (frm.doc.receipt_purpose !== 'Before Billing (Sales Order)') {
            frappe.msgprint(__('Please set Receipt Purpose to "Before Billing (Sales Order)" to use Sales Order'));
            row.sales_order = '';
            frm.refresh_field('items');
            return;
        }

        // Clear opposite reference if filled
        if (row.sales_invoice) {
            row.sales_invoice = '';
        }

        // Fetch reference data using custom API
        frappe.call({
            method: 'imogi_finance.imogi_finance.doctype.customer_receipt.customer_receipt.get_reference_data',
            args: {
                doctype: 'Sales Order',
                name: row.sales_order
            },
            callback: function(r) {
                if (!r.message) return;
                const data = r.message;
                const current_row = locals[cdt][cdn];
                if (!current_row) return;

                // Auto-fill customer/company if missing; else validate match
                if (!frm.doc.customer) {
                    frm.set_value('customer', data.customer);
                } else if (frm.doc.customer !== data.customer) {
                    frappe.msgprint(__('Sales Order customer does not match Customer Receipt customer'));
                    current_row.sales_order = '';
                    frm.refresh_field('items');
                    return;
                }

                if (!frm.doc.company) {
                    frm.set_value('company', data.company);
                } else if (frm.doc.company !== data.company) {
                    frappe.msgprint(__('Sales Order company does not match Customer Receipt company'));
                    current_row.sales_order = '';
                    frm.refresh_field('items');
                    return;
                }

                // Populate child row fields directly (no frappe.model.set_value)
                current_row.reference_date = data.reference_date;
                current_row.reference_outstanding = data.reference_outstanding;
                if (!current_row.amount_to_collect || current_row.amount_to_collect === 0) {
                    current_row.amount_to_collect = data.reference_outstanding;
                }

                // Refresh grid to show updated values
                frm.refresh_field('items');

                frappe.show_alert({
                    message: __('Data loaded: Outstanding {0}', [format_currency(data.reference_outstanding)]),
                    indicator: 'green'
                }, 3);
            },
            error: function() {
                const current_row = locals[cdt][cdn];
                if (current_row) {
                    current_row.sales_order = '';
                    frm.refresh_field('items');
                }
            }
        });
    }
});

// Show dialog to select payment mode and account
function show_payment_dialog(frm) {
    let dialog = new frappe.ui.Dialog({
        title: __('Create Payment Entry'),
        fields: [
            {
                fieldname: 'paid_amount',
                fieldtype: 'Currency',
                label: __('Paid Amount'),
                default: frm.doc.outstanding_amount,
                reqd: 1
            },
            {
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'posting_date',
                fieldtype: 'Date',
                label: __('Posting Date'),
                default: frappe.datetime.get_today(),
                reqd: 1
            },
            {
                fieldtype: 'Section Break'
            },
            {
                fieldname: 'mode_of_payment',
                fieldtype: 'Link',
                label: __('Mode of Payment'),
                options: 'Mode of Payment',
                reqd: 1,
                onchange: function() {
                    let mode = dialog.get_value('mode_of_payment');
                    if (mode) {
                        // Fetch default account for this mode of payment using whitelisted method
                        frappe.call({
                            method: 'imogi_finance.imogi_finance.doctype.customer_receipt.customer_receipt.get_mode_of_payment_account',
                            args: {
                                mode_of_payment: mode,
                                company: frm.doc.company
                            },
                            callback: function(r) {
                                if (r.message && r.message.default_account) {
                                    dialog.set_value('paid_to_account', r.message.default_account);
                                }
                            }
                        });
                    }
                }
            },
            {
                fieldname: 'paid_to_account',
                fieldtype: 'Link',
                label: __('Paid To Account'),
                options: 'Account',
                reqd: 1,
                get_query: function() {
                    return {
                        filters: {
                            company: frm.doc.company,
                            is_group: 0,
                            account_type: ['in', ['Bank', 'Cash']]
                        }
                    };
                }
            },
            {
                fieldtype: 'Section Break'
            },
            {
                fieldname: 'reference_no',
                fieldtype: 'Data',
                label: __('Reference No')
            },
            {
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'reference_date',
                fieldtype: 'Date',
                label: __('Reference Date')
            }
        ],
        primary_action_label: __('Create'),
        primary_action: function(values) {
            frappe.call({
                method: 'make_payment_entry',
                doc: frm.doc,
                args: {
                    paid_amount: values.paid_amount,
                    mode_of_payment: values.mode_of_payment,
                    paid_to_account: values.paid_to_account,
                    posting_date: values.posting_date,
                    reference_no: values.reference_no,
                    reference_date: values.reference_date
                },
                callback: function(r) {
                    if (r.message) {
                        dialog.hide();
                        frappe.set_route('Form', 'Payment Entry', r.message.name);
                    }
                }
            });
        }
    });

    dialog.show();
}
