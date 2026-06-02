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

    frm.add_custom_button(__('🏦 Buka Bank Reconciliation Tool'), function() {
      // Cari closing balance dari Bank Statement terakhir untuk bank account ini
      // Cari import yang periodenya mencakup tanggal transaksi ini
      const trx_date = frm.doc.date;
      frappe.db.get_list('Bank Statement', {
        filters: {
          bank_account: frm.doc.bank_account,
          status: 'Completed',
          statement_from_date: ['<=', trx_date],
          statement_to_date: ['>=', trx_date],
        },
        fields: ['name', 'closing_balance', 'opening_balance', 'statement_from_date', 'statement_to_date'],
        order_by: 'statement_to_date desc',
        limit: 1
      }).then(results => {
        // Fallback: kalau tidak ada yang cocok periodenya, ambil yang terdekat
        const get_import = results && results.length > 0
          ? Promise.resolve(results)
          : frappe.db.get_list('Bank Statement', {
              filters: {bank_account: frm.doc.bank_account, status: 'Completed'},
              fields: ['name', 'closing_balance', 'opening_balance', 'statement_from_date', 'statement_to_date'],
              order_by: 'statement_to_date desc',
              limit: 1
            });

        get_import.then(imports => {
          if (imports && imports.length > 0) {
            const matched = imports[0];
            localStorage.setItem('bci_prefill', JSON.stringify({
              company: frm.doc.company,
              bank_account: frm.doc.bank_account,
              from_date: matched.statement_from_date,
              to_date: matched.statement_to_date,
              closing_balance: matched.closing_balance,
            }));
            frappe.show_alert({
              message: __('Closing Balance dari import periode {0} s/d {1}: Rp {2}', [
                matched.statement_from_date,
                matched.statement_to_date,
                (matched.closing_balance || 0).toLocaleString('id-ID')
              ]),
              indicator: 'blue'
            }, 5);
          }
          frappe.set_route('Form', 'Bank Reconciliation Tool', 'Bank Reconciliation Tool');
        });
      });
    }, __('Actions'));

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
