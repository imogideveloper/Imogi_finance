frappe.ui.form.on('Transfer Application Item', {
  reference_name(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    
    if (!row.reference_name || !row.reference_doctype) {
      return;
    }
    
    // Fetch details from reference document
    fetch_reference_document_details(frm, row);
  },
  
  reference_doctype(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    // Clear reference name when doctype changes
    frappe.model.set_value(cdt, cdn, 'reference_name', '');
  },
  
  party(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    
    if (!row.party || !row.party_type) {
      return;
    }
    
    // Fetch party details based on party type
    if (row.party_type === 'Supplier') {
      fetch_supplier_details(frm, row);
    } else if (row.party_type === 'Employee') {
      fetch_employee_details(frm, row);
    }
  },
  
  party_type(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    // Clear party when party type changes
    frappe.model.set_value(cdt, cdn, 'party', '');
  }
});

function fetch_reference_document_details(frm, row) {
  frappe.call({
    method: 'frappe.client.get',
    args: {
      doctype: row.reference_doctype,
      name: row.reference_name
    },
    callback: (r) => {
      if (r.message) {
        let doc = r.message;
        
        // Fetch based on doctype
        if (row.reference_doctype === 'Expense Request') {
          fetch_from_expense_request(frm, row, doc);
        } else if (row.reference_doctype === 'Purchase Invoice') {
          fetch_from_purchase_invoice(frm, row, doc);
        } else if (row.reference_doctype === 'Purchase Order') {
          fetch_from_purchase_order(frm, row, doc);
        } else if (row.reference_doctype === 'Payment Entry') {
          fetch_from_payment_entry(frm, row, doc);
        }
        
        // Set fields as read-only after fetching
        set_fields_readonly(frm, row.name, true);
      }
    }
  });
}

function fetch_from_expense_request(frm, row, er_doc) {
  // Set description and amount
  frappe.model.set_value(row.doctype, row.name, 'description', er_doc.description || er_doc.name);
  frappe.model.set_value(row.doctype, row.name, 'amount', er_doc.total_amount || 0);
  
  // Fetch supplier details if available
  if (er_doc.supplier) {
    frappe.model.set_value(row.doctype, row.name, 'party_type', 'Supplier');
    frappe.model.set_value(row.doctype, row.name, 'party', er_doc.supplier);
    
    // Fetch bank details
    fetch_bank_details_for_party(frm, row, 'Supplier', er_doc.supplier);
  }
}

function fetch_from_purchase_invoice(frm, row, pi_doc) {
  // Set description and amount
  let desc = pi_doc.bill_no || pi_doc.title || pi_doc.name;
  frappe.model.set_value(row.doctype, row.name, 'description', desc);
  frappe.model.set_value(row.doctype, row.name, 'amount', pi_doc.outstanding_amount || pi_doc.grand_total || 0);
  
  // Fetch supplier details
  if (pi_doc.supplier) {
    frappe.model.set_value(row.doctype, row.name, 'party_type', 'Supplier');
    frappe.model.set_value(row.doctype, row.name, 'party', pi_doc.supplier);
    
    // Fetch bank details
    fetch_bank_details_for_party(frm, row, 'Supplier', pi_doc.supplier);
  }
}

function fetch_from_purchase_order(frm, row, po_doc) {
  // Set description and amount
  frappe.model.set_value(row.doctype, row.name, 'description', po_doc.title || po_doc.name);
  frappe.model.set_value(row.doctype, row.name, 'amount', po_doc.grand_total || 0);
  
  // Fetch supplier details
  if (po_doc.supplier) {
    frappe.model.set_value(row.doctype, row.name, 'party_type', 'Supplier');
    frappe.model.set_value(row.doctype, row.name, 'party', po_doc.supplier);
    
    // Fetch bank details
    fetch_bank_details_for_party(frm, row, 'Supplier', po_doc.supplier);
  }
}

function fetch_from_payment_entry(frm, row, pe_doc) {
  // Set description and amount
  frappe.model.set_value(row.doctype, row.name, 'description', pe_doc.remarks || pe_doc.name);
  frappe.model.set_value(row.doctype, row.name, 'amount', pe_doc.paid_amount || 0);
  
  // Fetch party details
  if (pe_doc.party_type && pe_doc.party) {
    frappe.model.set_value(row.doctype, row.name, 'party_type', pe_doc.party_type);
    frappe.model.set_value(row.doctype, row.name, 'party', pe_doc.party);
    
    // Fetch bank details
    fetch_bank_details_for_party(frm, row, pe_doc.party_type, pe_doc.party);
  }
}

function fetch_bank_details_for_party(frm, row, party_type, party_name) {
  frappe.call({
    method: 'frappe.client.get_list',
    args: {
      doctype: 'Bank Account',
      filters: {
        party_type: party_type,
        party: party_name,
        is_default: 1
      },
      fields: ['bank', 'bank_account_no', 'branch_code', 'account_name'],
      limit: 1
    },
    callback: (r) => {
      if (r.message && r.message.length > 0) {
        let bank = r.message[0];
        frappe.model.set_value(row.doctype, row.name, 'beneficiary_name', party_name);
        frappe.model.set_value(row.doctype, row.name, 'bank_name', bank.bank || '');
        frappe.model.set_value(row.doctype, row.name, 'account_number', bank.bank_account_no || '');
        frappe.model.set_value(row.doctype, row.name, 'account_holder_name', bank.account_name || '');
        frappe.model.set_value(row.doctype, row.name, 'bank_branch', bank.branch_code || '');
      } else {
        frappe.model.set_value(row.doctype, row.name, 'beneficiary_name', party_name);
      }
    }
  });
}

function set_fields_readonly(frm, row_name, readonly) {
  // Set read-only for fields that were fetched from reference
  let fields = ['description', 'amount', 'party_type', 'party', 'beneficiary_name', 
                'bank_name', 'account_number', 'account_holder_name', 'bank_branch'];
  
  fields.forEach(field => {
    let grid_row = frm.fields_dict.items.grid.grid_rows_by_docname[row_name];
    if (grid_row) {
      grid_row.toggle_editable(field, !readonly);
    }
  });
}

function fetch_supplier_details(frm, row) {
  frappe.call({
    method: 'frappe.client.get',
    args: {
      doctype: 'Supplier',
      name: row.party
    },
    callback: (r) => {
      if (r.message) {
        let supplier = r.message;
        
        // Try to get bank details from first bank account
        frappe.call({
          method: 'frappe.client.get_list',
          args: {
            doctype: 'Bank Account',
            filters: {
              party_type: 'Supplier',
              party: row.party,
              is_default: 1
            },
            fields: ['bank', 'bank_account_no', 'branch_code', 'account_name'],
            limit: 1
          },
          callback: (bank_res) => {
            if (bank_res.message && bank_res.message.length > 0) {
              let bank = bank_res.message[0];
              frappe.model.set_value(row.doctype, row.name, 'beneficiary_name', supplier.supplier_name || row.party);
              frappe.model.set_value(row.doctype, row.name, 'bank_name', bank.bank || '');
              frappe.model.set_value(row.doctype, row.name, 'account_number', bank.bank_account_no || '');
              frappe.model.set_value(row.doctype, row.name, 'account_holder_name', bank.account_name || '');
              frappe.model.set_value(row.doctype, row.name, 'bank_branch', bank.branch_code || '');
            } else {
              // No bank account, just set beneficiary name
              frappe.model.set_value(row.doctype, row.name, 'beneficiary_name', supplier.supplier_name || row.party);
            }
          }
        });
      }
    }
  });
}

function fetch_employee_details(frm, row) {
  frappe.call({
    method: 'frappe.client.get',
    args: {
      doctype: 'Employee',
      name: row.party
    },
    callback: (r) => {
      if (r.message) {
        let employee = r.message;
        
        // Try to get bank details
        frappe.call({
          method: 'frappe.client.get_list',
          args: {
            doctype: 'Bank Account',
            filters: {
              party_type: 'Employee',
              party: row.party
            },
            fields: ['bank', 'bank_account_no', 'branch_code', 'account_name'],
            limit: 1
          },
          callback: (bank_res) => {
            if (bank_res.message && bank_res.message.length > 0) {
              let bank = bank_res.message[0];
              frappe.model.set_value(row.doctype, row.name, 'beneficiary_name', employee.employee_name || row.party);
              frappe.model.set_value(row.doctype, row.name, 'bank_name', bank.bank || '');
              frappe.model.set_value(row.doctype, row.name, 'account_number', bank.bank_account_no || '');
              frappe.model.set_value(row.doctype, row.name, 'account_holder_name', bank.account_name || '');
              frappe.model.set_value(row.doctype, row.name, 'bank_branch', bank.branch_code || '');
            } else {
              // No bank account, just set beneficiary name
              frappe.model.set_value(row.doctype, row.name, 'beneficiary_name', employee.employee_name || row.party);
            }
          }
        });
      }
    }
  });
}
