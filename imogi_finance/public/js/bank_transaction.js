frappe.ui.form.on('Bank Transaction', {
  refresh(frm) {
    if (frm.doc.docstatus !== 1 || frm.doc.status !== 'Unreconciled') return;
    if (frm.page.btn_secondary && frm.page.btn_secondary.get(0)?.innerText?.trim() === __('Cancel')) {
      frm.page.btn_secondary.hide();
    }
    (frm.page.secondary_actions || [])
      .filter((action) => action && action.label === __('Cancel'))
      .forEach((action) => action.hide && action.hide());

    frm.add_custom_button(__('Reconcile'), function() {
      localStorage.setItem('imogi_reconcile_bank_account', frm.doc.bank_account);
      localStorage.setItem('imogi_reconcile_company', frm.doc.company);
      frappe.set_route('Form', 'Bank Reconciliation Tool', 'Bank Reconciliation Tool');
    }, __('Actions')).addClass('btn-primary');

    frm.add_custom_button(__('Create Journal Entry'), function() {
      frappe.model.with_doctype('Journal Entry', function() {
        var jv = frappe.model.get_new_doc('Journal Entry');
        jv.voucher_type = 'Bank Entry';
        jv.posting_date = frm.doc.date;
        jv.cheque_no = frm.doc.reference_number || (frm.doc.description || '').substring(0, 40);
        jv.cheque_date = frm.doc.date;
        jv.user_remark = frm.doc.description;
        frappe.db.get_value('Bank Account', frm.doc.bank_account, 'account').then(r => {
          var row1 = frappe.model.add_child(jv, 'Journal Entry Account', 'accounts');
          row1.account = r.message.account;
          row1.bank_account = frm.doc.bank_account;
          row1.debit_in_account_currency = frm.doc.deposit || 0;
          row1.credit_in_account_currency = frm.doc.withdrawal || 0;
          frappe.set_route('Form', 'Journal Entry', jv.name);
        });
      });
    }, __('Actions'));
  },
});
