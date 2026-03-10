/**
 * Payment Reconciliation Helper
 * Provides user guidance for unreconciling payments when documents are cancelled
 */

frappe.provide("imogi_finance.payment_reconciliation");

// Client action handler for payment reconciliation help
window.show_payment_reconciliation_help = function() {
    frappe.set_route("Form", "Payment Reconciliation", "Payment Reconciliation");
    
    frappe.show_alert({
        message: __("Payment Reconciliation tool opened. Select party and click 'Get Unreconciled Entries' to manage reconciliations."),
        indicator: "blue"
    }, 7);
};

/**
 * Add helper button to cancelled documents with reconciled payments
 */
imogi_finance.payment_reconciliation.add_unreconcile_button = function(frm) {
    // Only show on cancelled documents
    if (frm.doc.docstatus !== 2) {
        return;
    }
    
    // Check if document has reconciled payments
    // NOTE: Old advance_payment.api module deleted - native Payment Ledger Entry used instead
    // This functionality is now handled by ERPNext's native Payment Reconciliation tool
    /* 
    frappe.call({
        method: "imogi_finance.advance_payment.api.get_reconciled_payments_for_cancelled_doc",
        args: {
            doctype: frm.doc.doctype,
            docname: frm.doc.name
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                // Add warning indicator
                frm.dashboard.add_indicator(
                    __("Has {0} Reconciled Payment(s) - Manual Unlink Required", [r.message.length]),
                    "orange"
                );
                
                // Add custom button to show reconciled payments
                frm.add_custom_button(__("View Reconciled Payments"), function() {
                    show_reconciled_payments_dialog(frm, r.message);
                }, __("Actions"));
                
                // Add quick unlink button if ERPNext standard method available
                if (frappe.boot.user.can_write.includes("Payment Entry")) {
                    frm.add_custom_button(__("Unlink All Payments"), function() {
                        unlink_all_payments(frm, r.message);
                    }, __("Actions"));
                }
            }
        }
    });
    */
};

/**
 * Show dialog with list of reconciled payments and unlink options
 */
function show_reconciled_payments_dialog(frm, payments) {
    const fields = [
        {
            fieldname: "info",
            fieldtype: "HTML",
            options: `
                <div class="alert alert-warning">
                    <p><b>⚠️ This ${frm.doc.doctype} has ${payments.length} reconciled payment(s) that need to be manually unlinked.</b></p>
                    <p>Choose a payment below and click "Open Payment Entry" to unlink it.</p>
                </div>
            `
        },
        {
            fieldname: "payments_table",
            fieldtype: "HTML",
            options: generate_payments_table_html(payments)
        }
    ];
    
    const dialog = new frappe.ui.Dialog({
        title: __("Reconciled Payments Requiring Unlink"),
        fields: fields,
        size: "large"
    });
    
    dialog.show();
    
    // Add click handlers for payment links
    dialog.$wrapper.find('[data-payment-entry]').on('click', function(e) {
        e.preventDefault();
        const voucher_type = $(this).data('voucher-type');
        const voucher_no = $(this).data('payment-entry');
        frappe.set_route("Form", voucher_type, voucher_no);
        dialog.hide();
    });
}

/**
 * Generate HTML table of reconciled payments
 */
function generate_payments_table_html(payments) {
    let html = `
        <table class="table table-bordered" style="margin-top: 10px;">
            <thead>
                <tr>
                    <th>${__("Payment Entry")}</th>
                    <th>${__("Date")}</th>
                    <th>${__("Amount")}</th>
                    <th>${__("Account")}</th>
                    <th>${__("Action")}</th>
                </tr>
            </thead>
            <tbody>
    `;
    
    payments.forEach(payment => {
        const amount = frappe.format(Math.abs(payment.amount), {
            fieldtype: "Currency",
            currency: payment.currency
        });
        const date = frappe.format(payment.posting_date, {fieldtype: "Date"});
        
        html += `
            <tr>
                <td><b>${payment.voucher_type}</b><br>${payment.voucher_no}</td>
                <td>${date}</td>
                <td>${amount}</td>
                <td><small>${payment.account}</small></td>
                <td>
                    <button class="btn btn-xs btn-primary" 
                            data-voucher-type="${payment.voucher_type}"
                            data-payment-entry="${payment.voucher_no}">
                        ${__("Open Payment Entry")}
                    </button>
                </td>
            </tr>
        `;
    });
    
    html += `
            </tbody>
        </table>
        <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 4px;">
            <h5>${__("How to Unlink:")}</h5>
            <ol style="margin-bottom: 0;">
                <li>${__("Click 'Open Payment Entry' for each payment above")}</li>
                <li>${__("In the Payment Entry, go to the 'References' table")}</li>
                <li>${__("Find and remove the row for this cancelled document")}</li>
                <li>${__("Click 'Update' to save changes")}</li>
            </ol>
        </div>
    `;
    
    return html;
}

/**
 * Attempt to unlink all payments (requires Payment Entry write permission)
 * NOTE: This function is disabled - old advance_payment.api module was deleted.
 * Native Payment Ledger Entry is used instead via ERPNext's Payment Reconciliation tool.
 */
/*
function unlink_all_payments(frm, payments) {
    frappe.confirm(
        __("This will attempt to automatically unlink {0} payment(s) from this cancelled {1}. Continue?", 
           [payments.length, frm.doc.doctype]),
        function() {
            // Show progress
            const progress_dialog = frappe.show_progress(
                __("Unlinking Payments"),
                0,
                payments.length,
                __("Processing...")
            );
            
            let completed = 0;
            let errors = [];
            
            payments.forEach((payment, index) => {
                frappe.call({
                    method: "imogi_finance.advance_payment.api.unlink_single_payment",
                    args: {
                        voucher_type: payment.voucher_type,
                        voucher_no: payment.voucher_no,
                        reference_doctype: frm.doc.doctype,
                        reference_name: frm.doc.name
                    },
                    callback: function(r) {
                        completed++;
                        
                        if (r.message && r.message.success) {
                            frappe.show_progress(
                                __("Unlinking Payments"),
                                completed,
                                payments.length,
                                __("{0} of {1} completed", [completed, payments.length])
                            );
                        } else {
                            errors.push(`${payment.voucher_no}: ${r.message?.error || "Unknown error"}`);
                        }
                        
                        // All completed
                        if (completed === payments.length) {
                            progress_dialog.hide();
                            
                            if (errors.length === 0) {
                                frappe.show_alert({
                                    message: __("All payments successfully unlinked!"),
                                    indicator: "green"
                                }, 5);
                                frm.reload_doc();
                            } else {
                                frappe.msgprint({
                                    title: __("Partial Success"),
                                    message: __("Some payments could not be unlinked:<br>") + errors.join("<br>"),
                                    indicator: "orange"
                                });
                            }
                        }
                    }
                });
            });
        }
    );
}
*/
