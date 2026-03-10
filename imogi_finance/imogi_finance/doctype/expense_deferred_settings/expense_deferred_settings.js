// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('Expense Deferred Settings', {
  setup: function(frm) {
    // Set query for Prepaid Account in child table - filter to Asset accounts
    frm.set_query('prepaid_account', 'deferrable_accounts', function() {
      return {
        filters: {
          'root_type': 'Asset',
          'is_group': 0
        }
      };
    });
    
    // Set query for Expense Account in child table - filter to Expense accounts
    frm.set_query('expense_account', 'deferrable_accounts', function() {
      return {
        filters: {
          'root_type': 'Expense',
          'is_group': 0
        }
      };
    });
  },
  
  refresh: function(frm) {
    // Add help message
    if (!frm.doc.enable_deferred_expense) {
      frm.dashboard.add_comment(
        __('Deferred Expense is currently disabled. Enable it to use deferred expense features in Expense Requests.'),
        'yellow'
      );
    }
  }
});

// Child table event handlers
frappe.ui.form.on('Deferrable Account', {
  deferrable_accounts_add: function(frm, cdt, cdn) {
    // Set default values for new rows
    frappe.model.set_value(cdt, cdn, 'is_active', 1);
  }
});
