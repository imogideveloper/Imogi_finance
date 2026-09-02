// Shows a running total of the checked vouchers' Remaining amount in the
// "Reconcile the Bank Transaction" dialog, next to the Unallocated Amount,
// so it's obvious at a glance whether the selection adds up before Submit.
// Patches erpnext's DialogManager (public/js/bank_reconciliation_tool/dialog_manager.js)
// instead of editing it directly, since that file gets overwritten on app updates.
(function () {
    frappe.provide("erpnext.accounts.bank_reconciliation");

    function patch_dialog_manager() {
        const DM = erpnext.accounts.bank_reconciliation.DialogManager;
        if (!DM) return false;
        if (DM.prototype.__imogi_selection_total_patched) return true;
        DM.prototype.__imogi_selection_total_patched = true;

        const original_get_linked_vouchers = DM.prototype.get_linked_vouchers;
        DM.prototype.get_linked_vouchers = function (document_types) {
            // Reset before the (async) refetch repopulates it via format_row below.
            this.__imogi_raw_amounts = [];
            return original_get_linked_vouchers.apply(this, arguments);
        };

        const original_format_row = DM.prototype.format_row;
        DM.prototype.format_row = function (row) {
            this.__imogi_raw_amounts = this.__imogi_raw_amounts || [];
            this.__imogi_raw_amounts.push(flt(row["paid_amount"]));
            return original_format_row.apply(this, arguments);
        };

        const original_get_datatable = DM.prototype.get_datatable;
        DM.prototype.get_datatable = function (proposals_wrapper) {
            original_get_datatable.apply(this, arguments);
            // The library's own "N rows selected" toast floats over the table body
            // and covers the Remaining column -- our total bar below already shows
            // the selected count, so turn the toast off instead of fighting its position.
            this.datatable.options.checkedRowStatus = false;
            setup_selection_total_bar(this, proposals_wrapper);
        };
        return true;
    }

    function setup_selection_total_bar(dm, proposals_wrapper) {
        let $bar = proposals_wrapper.next(".imogi-selection-total-bar");
        if (!$bar.length) {
            $bar = $('<div class="imogi-selection-total-bar" style="margin-top:8px;padding:8px 12px;border-radius:6px;font-size:13px;display:none;"></div>');
            proposals_wrapper.after($bar);
        }

        function render() {
            const checked_rows = dm.datatable.rowmanager.getCheckedRows();
            if (!checked_rows.length) {
                $bar.hide();
                return;
            }

            const amounts = dm.__imogi_raw_amounts || [];
            let total = 0;
            checked_rows.forEach((row_index) => {
                total += flt(amounts[row_index]);
            });

            const currency = dm.bank_transaction && dm.bank_transaction.currency;
            const unallocated = flt(dm.bank_transaction && dm.bank_transaction.unallocated_amount);
            const diff = total - unallocated;
            const is_match = Math.abs(diff) < 0.5;

            $bar
                .css({
                    background: is_match ? "#e6f4ea" : "#fff4e5",
                    color: is_match ? "#1e7e34" : "#9a6700",
                })
                .show()
                .html(
                    (is_match ? "✅ " : "⚠️ ") +
                        __("{0} dipilih", [checked_rows.length]) +
                        " &nbsp;|&nbsp; " +
                        __("Total") + ": <b>" + format_currency(total, currency) + "</b>" +
                        " &nbsp;|&nbsp; " +
                        __("Unallocated Amount") + ": <b>" + format_currency(unallocated, currency) + "</b>" +
                        (is_match
                            ? " &nbsp;— " + __("sudah sama")
                            : " &nbsp;— " + __("selisih") + " " + format_currency(Math.abs(diff), currency))
                );
        }

        if (!dm.__imogi_total_bar_bound) {
            dm.__imogi_total_bar_bound = true;
            dm.datatable.on("onCheckRow", render);
        }
        render();
    }

    // erpnext's own DialogManager class may not be defined yet at the point this
    // doctype_js file executes (load order between core's bundle and hook-registered
    // extras isn't guaranteed), so retry for a few seconds instead of patching once.
    if (!patch_dialog_manager()) {
        let attempts = 0;
        const retry = setInterval(function () {
            attempts++;
            if (patch_dialog_manager() || attempts > 50) clearInterval(retry);
        }, 200);
    }
})();

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
