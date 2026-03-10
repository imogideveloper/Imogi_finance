"""
Server-side Python code for creating Payment Entry DJP from Tax Payment Batch
This demonstrates how to properly map supplier from Tax Payment Batch to Payment Entry

PLACEMENT OPTIONS:

1. Add to Tax Payment Batch methods (tax_payment_batch.py):
   - Add create_payment_entry_djp() method to TaxPaymentBatch class

2. Create as standalone whitelisted API:
   - Add to imogi_finance/api/tax_payment.py
   - Call via frappe.call() from client-side

3. Use in hooks.py as doc_event:
   - Hook on Tax Payment Batch submission
   - Auto-create Payment Entry DJP

USAGE EXAMPLE:
    From Tax Payment Batch button:
    frappe.call({
        method: 'imogi_finance.api.tax_payment.create_payment_entry_from_batch',
        args: { batch_name: frm.doc.name },
        callback: function(r) { ... }
    });
"""

import frappe
from frappe import _
from frappe.utils import nowdate, flt


@frappe.whitelist()
def create_payment_entry_from_batch(batch_name):
    """
    Create Payment Entry (or Payment Entry DJP) from Tax Payment Batch
    
    Args:
        batch_name (str): Name of Tax Payment Batch document
        
    Returns:
        str: Name of created Payment Entry
        
    Best Practice Implementation:
    - Uses supplier from Tax Payment Batch dynamically
    - Fetches supplier_name from Supplier master
    - No hardcoding of IDs or names
    - Proper error handling
    """
    # Get Tax Payment Batch document
    batch = frappe.get_doc("Tax Payment Batch", batch_name)
    
    # Validate required fields
    if not batch.payable_account:
        frappe.throw(_("Payable Account is required in Tax Payment Batch"))
    
    if not batch.payment_account:
        frappe.throw(_("Payment Account is required in Tax Payment Batch"))
    
    if not batch.amount or batch.amount <= 0:
        frappe.throw(_("Payment Amount must be greater than 0"))
    
    # Get supplier - priority order:
    # 1. Use supplier from batch.party (if party_type is Supplier)
    # 2. Use batch.supplier (if custom field exists)
    # 3. Fallback to default tax authority supplier
    supplier = _get_supplier_from_batch(batch)
    
    # Fetch supplier name dynamically (DON'T hardcode)
    supplier_name = _get_supplier_name(supplier)
    
    # Create Payment Entry
    pe = frappe.new_doc("Payment Entry")  # or "Payment Entry DJP" if custom doctype
    
    # Basic details
    pe.company = batch.company
    pe.payment_type = "Pay"
    pe.posting_date = batch.payment_date or batch.posting_date or nowdate()
    pe.mode_of_payment = batch.payment_mode or "Bank"
    
    # Party details - KEY SECTION
    pe.party_type = "Supplier"
    pe.party = supplier
    # party_name is usually auto-fetched by ERPNext, but we can set it explicitly
    if hasattr(pe, 'party_name'):
        pe.party_name = supplier_name
    
    # Account details
    pe.paid_from = batch.payment_account  # Bank/Cash account
    pe.paid_to = batch.payable_account    # Tax liability account
    pe.paid_amount = flt(batch.amount)
    pe.received_amount = flt(batch.amount)
    
    # Reference back to Tax Payment Batch
    pe.reference_no = batch.name
    pe.reference_date = pe.posting_date
    
    # Set title/remarks
    title = _("Tax Payment {0} {1}/{2} - {3}").format(
        batch.tax_type or "Tax",
        batch.period_month or "",
        batch.period_year or "",
        supplier_name,
    )
    
    remarks = _("Tax payment for {0} - Period {1}/{2} - Batch {3} - Supplier: {4}").format(
        batch.tax_type or "Tax",
        batch.period_month or "",
        batch.period_year or "",
        batch.name,
        supplier_name,
    )
    
    if hasattr(pe, 'title'):
        pe.title = title
    
    pe.remarks = remarks
    
    # Insert Payment Entry
    pe.insert(ignore_permissions=True)
    
    # Optional: Auto-submit if batch is submitted
    if batch.docstatus == 1:
        pe.submit()
    
    # Update Tax Payment Batch with reference
    batch.db_set("payment_entry", pe.name, update_modified=False)
    if batch.docstatus == 1:
        batch.db_set("status", "Paid", update_modified=False)
    
    return pe.name


def _get_supplier_from_batch(batch):
    """
    Get supplier from Tax Payment Batch with fallback logic
    
    Priority:
    1. batch.party (if party_type == 'Supplier')
    2. batch.supplier (if custom field exists)
    3. Default tax authority supplier
    """
    # Method 1: Check party field (standard approach)
    if hasattr(batch, 'party_type') and batch.party_type == 'Supplier' and batch.party:
        return batch.party
    
    # Method 2: Check custom supplier field (if exists)
    if hasattr(batch, 'supplier') and batch.supplier:
        return batch.supplier
    
    # Method 3: Fallback to default tax authority supplier
    return _get_or_create_tax_authority_supplier()


def _get_supplier_name(supplier):
    """
    Fetch supplier_name from Supplier doctype dynamically
    
    Args:
        supplier (str): Supplier ID
        
    Returns:
        str: Supplier name (display name)
    """
    if not supplier:
        return "Unknown Supplier"
    
    try:
        supplier_name = frappe.db.get_value("Supplier", supplier, "supplier_name")
        return supplier_name or supplier
    except Exception:
        return supplier


def _get_or_create_tax_authority_supplier():
    """
    Get or create default supplier for tax authority payments
    This is the fallback when no supplier is specified in batch
    
    Returns:
        str: Supplier name
    """
    supplier_name = "Government - Tax Authority"
    
    # Check if supplier exists
    if frappe.db.exists("Supplier", supplier_name):
        return supplier_name
    
    # Create supplier if not exists
    try:
        supplier = frappe.new_doc("Supplier")
        supplier.supplier_name = supplier_name
        
        # Get default supplier group (non-group)
        supplier_group = frappe.db.get_value(
            "Supplier Group", 
            {"is_group": 0}, 
            "name"
        ) or "All Supplier Groups"
        
        supplier.supplier_group = supplier_group
        supplier.supplier_type = "Company"
        supplier.country = "Indonesia"
        supplier.insert(ignore_permissions=True)
        
        frappe.logger().info(f"Created default tax authority supplier: {supplier_name}")
        
        return supplier.name
    except Exception as e:
        frappe.log_error(f"Failed to create tax authority supplier: {str(e)}")
        frappe.throw(_("Failed to create default tax authority supplier"))


# ============================================================================
# ALTERNATIVE: Button in Tax Payment Batch Form
# ============================================================================

def add_payment_entry_button_to_tax_batch():
    """
    Add this to Tax Payment Batch Client Script or JS file
    
    PLACEMENT: 
    - Add to imogi_finance/public/js/tax_payment_batch.js
    - OR add as Client Script for Tax Payment Batch doctype
    """
    js_code = """
    frappe.ui.form.on('Tax Payment Batch', {
        refresh: function(frm) {
            if (frm.doc.docstatus === 1 && !frm.doc.payment_entry) {
                frm.add_custom_button(__('Create Payment Entry DJP'), function() {
                    frappe.call({
                        method: 'imogi_finance.api.tax_payment.create_payment_entry_from_batch',
                        args: {
                            batch_name: frm.doc.name
                        },
                        freeze: true,
                        freeze_message: __('Creating Payment Entry...'),
                        callback: function(r) {
                            if (r.message) {
                                frappe.msgprint({
                                    title: __('Success'),
                                    message: __('Payment Entry {0} created successfully', [r.message]),
                                    indicator: 'green'
                                });
                                
                                // Reload form to show payment_entry link
                                frm.reload_doc();
                                
                                // Navigate to Payment Entry
                                frappe.set_route('Form', 'Payment Entry', r.message);
                            }
                        },
                        error: function(r) {
                            frappe.msgprint({
                                title: __('Error'),
                                message: __('Failed to create Payment Entry'),
                                indicator: 'red'
                            });
                        }
                    });
                }, __('Actions'));
            }
        }
    });
    """
    return js_code


# ============================================================================
# ALTERNATIVE: Automatic creation on Tax Payment Batch submission
# ============================================================================

def on_tax_payment_batch_submit(doc, method=None):
    """
    Auto-create Payment Entry when Tax Payment Batch is submitted
    
    PLACEMENT: Add to hooks.py
    
    doc_events = {
        "Tax Payment Batch": {
            "on_submit": "imogi_finance.api.tax_payment.on_tax_payment_batch_submit"
        }
    }
    """
    if doc.amount and doc.amount > 0 and not doc.payment_entry:
        try:
            payment_entry_name = create_payment_entry_from_batch(doc.name)
            frappe.msgprint(
                _("Payment Entry {0} created successfully").format(payment_entry_name),
                indicator="green"
            )
        except Exception as e:
            frappe.log_error(
                message=str(e), 
                title=f"Tax Payment Batch {doc.name}: Failed to create Payment Entry"
            )
            # Don't throw - allow batch to be submitted even if PE creation fails
            frappe.msgprint(
                _("Warning: Failed to create Payment Entry: {0}").format(str(e)),
                indicator="orange"
            )
