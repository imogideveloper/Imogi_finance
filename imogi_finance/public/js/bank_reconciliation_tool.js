frappe.ui.form.on('Bank Reconciliation Tool', {
    onload: function(frm) {
        var bank_account = localStorage.getItem('imogi_reconcile_bank_account');
        var company = localStorage.getItem('imogi_reconcile_company');

        if (!bank_account) return;

        localStorage.removeItem('imogi_reconcile_bank_account');
        localStorage.removeItem('imogi_reconcile_company');

        if (company) frm.set_value('company', company);

        setTimeout(function() {
            frm.set_value('bank_account', bank_account).then(function() {
                frm.trigger('bank_account');
                setTimeout(function() {
                    $('button.btn').filter(function() {
                        return $(this).text().trim() === __('Get Unreconciled Entries');
                    }).trigger('click');
                }, 1000);
            });
        }, 500);
    }
});
