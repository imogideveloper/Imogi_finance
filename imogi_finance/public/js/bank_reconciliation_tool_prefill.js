frappe.ui.form.on('Bank Reconciliation Tool', {
    refresh(frm) {
        // Cek apakah ada prefill data dari Bank CSV Import
        const prefill = localStorage.getItem('bci_prefill');
        if (!prefill) return;

        try {
            const data = JSON.parse(prefill);
            // Hapus dari localStorage agar tidak ter-apply lagi
            localStorage.removeItem('bci_prefill');

            // Set nilai ke form
            setTimeout(async () => {
                await frm.set_value('company', data.company);
                await frm.set_value('bank_account', data.bank_account);
                await frm.set_value('bank_statement_from_date', data.from_date);
                await frm.set_value('bank_statement_to_date', data.to_date);
                await frm.set_value('bank_statement_closing_balance', data.closing_balance);

                frappe.show_alert({
                    message: __('Data dari Bank CSV Import sudah ter-prefill. Klik "Get Unreconciled Entries" untuk melanjutkan.'),
                    indicator: 'green'
                }, 8);
            }, 500);
        } catch(e) {
            localStorage.removeItem('bci_prefill');
        }
    }
});
