frappe.ui.form.on('Bank Reconciliation Tool', {
    refresh(frm) {
        const prefill = localStorage.getItem('bci_prefill');
        if (!prefill) return;

        try {
            const data = JSON.parse(prefill);
            localStorage.removeItem('bci_prefill');

            // Set nilai satu per satu dengan await dan delay cukup
            const do_prefill = async () => {
                await frm.set_value('company', data.company);
                await frappe.timeout(0.3);

                await frm.set_value('bank_account', data.bank_account);
                await frappe.timeout(0.3);

                await frm.set_value('bank_statement_from_date', data.from_date);
                await frm.set_value('bank_statement_to_date', data.to_date);
                await frappe.timeout(0.2);

                // Set closing balance sebagai float
                const closing = parseFloat(data.closing_balance) || 0;
                frm.doc.bank_statement_closing_balance = closing;
                frm.refresh_field('bank_statement_closing_balance');
                await frappe.timeout(0.3);

                // Klik Get Unreconciled Entries
                const btns = document.querySelectorAll('.page-actions .btn');
                let clicked = false;
                btns.forEach(btn => {
                    if (btn.innerText && btn.innerText.includes('Get Unreconciled')) {
                        btn.click();
                        clicked = true;
                    }
                });

                if (!clicked) {
                    // Fallback: trigger langsung
                    frm.trigger('get_unreconciled_entries');
                }

                frappe.show_alert({
                    message: __('Prefill dari Bank CSV Import selesai'),
                    indicator: 'green'
                }, 4);
            };

            do_prefill();

        } catch(e) {
            localStorage.removeItem('bci_prefill');
            console.error('BCI prefill error:', e);
        }
    }
});
