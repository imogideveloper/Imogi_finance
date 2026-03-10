/**
 * Client Script for Payment Entry DJP
 * Auto-fills party_type, party, and party_name from Tax Payment Batch
 * 
 * PLACEMENT: 
 * This client script should be added via:
 * 1. ERPNext UI: Setup > Client Script > New
 *    - DocType: Payment Entry (or Payment Entry DJP if custom doctype)
 *    - Enabled: Yes
 *    - Copy the frappe.ui.form.on code below
 * 
 * OR
 * 
 * 2. Add to hooks.py:
 *    doctype_js = {
 *        "Payment Entry": "public/js/payment_entry_djp.js"
 *    }
 */

frappe.ui.form.on('Payment Entry', {
    /**
     * When form is loaded/refreshed
     */
    onload: function(frm) {
        _setup_tax_payment_batch_listener(frm);
    },

    /**
     * When reference_no field changes (Tax Payment Batch name)
     * This triggers when Payment Entry is created from Tax Payment Batch
     */
    reference_no: function(frm) {
        _fetch_supplier_from_tax_batch(frm);
    },

    /**
     * When party field changes manually
     * Fetch party_name from Supplier
     */
    party: function(frm) {
        if (frm.doc.party_type === 'Supplier' && frm.doc.party) {
            _fetch_supplier_name(frm);
        }
    },

    /**
     * Alternative: Listen to custom field if Tax Payment Batch link exists
     * Uncomment if you have a direct Link field to Tax Payment Batch
     */
    // tax_payment_batch: function(frm) {
    //     _fetch_supplier_from_tax_batch(frm);
    // }
});

/**
 * Setup listener for Tax Payment Batch context
 * Detects when Payment Entry is created from Tax Payment Batch
 */
function _setup_tax_payment_batch_listener(frm) {
    // Check if opened from Tax Payment Batch (via reference_no or URL params)
    const urlParams = new URLSearchParams(window.location.search);
    const taxBatch = urlParams.get('tax_payment_batch');
    
    if (taxBatch && !frm.doc.reference_no) {
        frm.set_value('reference_no', taxBatch);
    }
    
    // If reference_no exists and matches Tax Payment Batch pattern
    if (frm.doc.reference_no && frm.doc.reference_no.startsWith('TXPAY-')) {
        _fetch_supplier_from_tax_batch(frm);
    }
}

/**
 * Fetch Supplier from Tax Payment Batch and populate party fields
 */
function _fetch_supplier_from_tax_batch(frm) {
    // Skip if already has party set
    if (frm.doc.party && frm.doc.party_type === 'Supplier') {
        return;
    }
    
    const batch_name = frm.doc.reference_no;
    
    if (!batch_name || !batch_name.startsWith('TXPAY-')) {
        return;
    }
    
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Tax Payment Batch',
            filters: { name: batch_name },
            fieldname: ['party_type', 'party', 'company']
        },
        callback: function(r) {
            if (r.message) {
                const batch = r.message;
                
                // Set party_type to Supplier
                frm.set_value('party_type', batch.party_type || 'Supplier');
                
                // Set party from Tax Payment Batch
                if (batch.party) {
                    frm.set_value('party', batch.party);
                    
                    // Fetch and set party_name
                    _fetch_supplier_name(frm);
                } else {
                    // Fallback: Use default tax authority supplier
                    _use_default_tax_supplier(frm);
                }
                
                frappe.show_alert({
                    message: __('Supplier auto-filled from Tax Payment Batch'),
                    indicator: 'green'
                }, 3);
            }
        },
        error: function() {
            // If Tax Payment Batch not found, use default
            _use_default_tax_supplier(frm);
        }
    });
}

/**
 * Fetch supplier_name from Supplier doctype and set party_name
 */
function _fetch_supplier_name(frm) {
    if (!frm.doc.party || frm.doc.party_type !== 'Supplier') {
        return;
    }
    
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Supplier',
            filters: { name: frm.doc.party },
            fieldname: 'supplier_name'
        },
        callback: function(r) {
            if (r.message && r.message.supplier_name) {
                // Set party_name field (if exists in your Payment Entry)
                if (frm.fields_dict.party_name) {
                    frm.set_value('party_name', r.message.supplier_name);
                }
                
                // Also update the title if field exists
                if (frm.fields_dict.title && !frm.doc.title) {
                    const title = __('Tax Payment - {0}', [r.message.supplier_name]);
                    frm.set_value('title', title);
                }
            }
        }
    });
}

/**
 * Use default tax authority supplier as fallback
 */
function _use_default_tax_supplier(frm) {
    const default_supplier = 'Government - Tax Authority';
    
    frm.set_value('party_type', 'Supplier');
    frm.set_value('party', default_supplier);
    
    frappe.show_alert({
        message: __('Using default tax authority supplier'),
        indicator: 'blue'
    }, 3);
}
