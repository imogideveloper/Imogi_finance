frappe.ui.form.on('Transfer Application', {
  setup(frm) {
    load_reference_options(frm);
  },

  refresh(frm) {
    load_reference_options(frm);
    set_reference_query(frm);

    // Apply read-only to items with reference documents
    apply_readonly_to_fetched_items(frm);

    if (!frm.is_new() && frm.doc.docstatus !== 2) {
      add_payment_entry_button(frm);
      add_mark_printed_button(frm);
      add_export_excel_button(frm);
    }
  },

  reference_doctype(frm) {
    set_reference_query(frm);
  },
});

// Handle item changes to recalculate totals
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

  amount(frm, cdt, cdn) {
    calculate_totals(frm);
  },

  expected_amount(frm, cdt, cdn) {
    calculate_totals(frm);
  },

  items_remove(frm, cdt, cdn) {
    calculate_totals(frm);
  },

  items_add(frm, cdt, cdn) {
    calculate_totals(frm);
  }
});

function calculate_totals(frm) {
  let total_amount = 0;
  let total_expected = 0;

  frm.doc.items?.forEach(item => {
    total_amount += flt(item.amount);
    total_expected += flt(item.expected_amount || item.amount);
  });

  frm.set_value('amount', total_amount);
  frm.set_value('expected_amount', total_expected);
}

function load_reference_options(frm) {
  frappe.call({
    method: 'imogi_finance.imogi_finance.doctype.transfer_application.transfer_application.fetch_reference_doctype_options',
    callback: (r) => {
      if (Array.isArray(r.message)) {
        frm.set_df_property('reference_doctype', 'options', r.message.join('\n'));
      }
    },
  });
}

function set_reference_query(frm) {
  if (!frm.doc.reference_doctype || frm.doc.reference_doctype === 'Other') {
    frm.set_query('reference_name', null);
    return;
  }

  frm.set_query('reference_name', () => ({
    filters: { docstatus: 1 },
    doctype: frm.doc.reference_doctype,
  }));
}

function add_payment_entry_button(frm) {
  frm.add_custom_button(__('Create Payment Entries'), async () => {
    if (frm.is_dirty()) {
      await frm.save();
    }

    frm.call({
      doc: frm.doc,
      method: 'create_payment_entry',
      freeze: true,
      freeze_message: __('Creating Payment Entries...'),
      callback: (r) => {
        if (r?.message) {
          const { payment_entries, count, message } = r.message;

          frappe.show_alert({
            message: message || __('Created {0} Payment Entry(ies)', [count]),
            indicator: 'green'
          });

          frm.reload_doc().then(() => {
            // Show list of created PEs in dialog
            if (payment_entries && payment_entries.length > 0) {
              let html = '<div><b>' + __('Payment Entries Created:') + '</b><ul>';
              payment_entries.forEach(pe => {
                html += `<li><a href="/app/payment-entry/${pe}" target="_blank">${pe}</a></li>`;
              });
              html += '</ul></div>';

              frappe.msgprint({
                title: __('Payment Entries Created'),
                message: html,
                indicator: 'green'
              });
            }
          });
        }
      },
    });
  }, __('Transfer'));
}

function add_mark_printed_button(frm) {
  frm.add_custom_button(__('Mark as Printed'), () => {
    frm.call({
      doc: frm.doc,
      method: 'mark_as_printed',
      callback: () => {
        frappe.show_alert({ message: __('Marked as printed'), indicator: 'green' });
        frm.reload_doc();
      },
    });
  }, __('Transfer'));
}

function add_export_excel_button(frm) {
  // Only show for approved transfers and Finance Controller role
  if (!frm.doc.workflow_state) return;

  const allowed_states = ['Approved for Transfer', 'Awaiting Bank Confirmation', 'Paid'];
  if (!allowed_states.includes(frm.doc.workflow_state)) return;

  frm.add_custom_button(__('Export to Excel'), () => {
    frm.call({
      doc: frm.doc,
      method: 'export_to_excel',
      freeze: true,
      freeze_message: __('Generating Excel file...'),
      callback: (r) => {
        if (r.message && r.message.success) {
          frappe.show_alert({
            message: __('Excel file downloaded: {0}', [r.message.filename]),
            indicator: 'green'
          });
        }
      }
    });
  }, __('Transfer'));
}

function apply_readonly_to_fetched_items(frm) {
  // Apply read-only to items that have reference documents
  if (!frm.doc.items) return;

  frm.doc.items.forEach(item => {
    if (item.reference_name && item.reference_doctype) {
      let grid_row = frm.fields_dict.items.grid.grid_rows_by_docname[item.name];
      if (grid_row) {
        let fields = ['description', 'amount', 'party_type', 'party', 'beneficiary_name',
                      'bank_name', 'account_number', 'account_holder_name', 'bank_branch'];

        fields.forEach(field => {
          grid_row.toggle_editable(field, false);
        });
      }
    }
  });
}

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
        set_fields_readonly_in_grid(frm, row.name, true);
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

function set_fields_readonly_in_grid(frm, row_name, readonly) {
  // Set read-only for fields that were fetched from reference
  let fields = ['description', 'amount', 'party_type', 'party', 'beneficiary_name',
                'bank_name', 'account_number', 'account_holder_name', 'bank_branch'];

  let grid_row = frm.fields_dict.items.grid.grid_rows_by_docname[row_name];
  if (grid_row) {
    fields.forEach(field => {
      grid_row.toggle_editable(field, !readonly);
    });
  }
}
