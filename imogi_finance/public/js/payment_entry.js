/**
 * Payment Entry UI Enhancements
 * - Reverse Entry button for reversing payment entries included in printed reports
 * - Status indicators for reversed/reversal entries
 * - Custom cancel confirmation with clear messaging
 */

frappe.ui.form.on('Payment Entry', {
  refresh(frm) {
    // Override standard cancel to show better message
    if (frm.doc.docstatus === 1 && !frm.is_new()) {
      _setupCancelButton(frm);
    }

    // Show Reverse Entry button if PE is submitted and not already reversed
    if (frm.doc.docstatus === 1 && !frm.doc.is_reversed) {
      frm.add_custom_button(__('Reverse Entry'), () => {
        const d = new frappe.ui.Dialog({
          title: __('Reverse Payment Entry'),
          fields: [
            {
              label: __('Reversal Date'),
              fieldname: 'reversal_date',
              fieldtype: 'Date',
              default: frappe.datetime.get_today(),
              reqd: 1,
              description: __('The posting date for the reversal entry (typically today)')
            },
            {
              fieldtype: 'HTML',
              options: `
                <div class="alert alert-info" style="margin-top: 10px;">
                  <strong>${__('Note:')}</strong><br>
                  ${__('This creates a reversal entry with flipped accounts at the selected date.')}<br>
                  ${__('Use this when the original entry is included in a printed Cash/Bank Daily Report.')}
                </div>
              `
            }
          ],
          primary_action_label: __('Create Reversal'),
          primary_action(values) {
            d.hide();

            frappe.call({
              method: 'imogi_finance.events.payment_entry.reverse_payment_entry',
              args: {
                payment_entry_name: frm.doc.name,
                reversal_date: values.reversal_date
              },
              freeze: true,
              freeze_message: __('Creating reversal entry...'),
              callback: (r) => {
                if (r.message) {
                  frappe.show_alert({
                    message: __('Reversal Entry {0} created', [r.message.name]),
                    indicator: 'green'
                  });
                  frm.reload_doc().then(() => {
                    frappe.set_route('Form', 'Payment Entry', r.message.name);
                  });
                }
              },
              error: (r) => {
                frappe.msgprint({
                  title: __('Error Creating Reversal'),
                  indicator: 'red',
                  message: r.message || __('An error occurred while creating the reversal entry')
                });
              }
            });
          }
        });
        d.show();
      }, __('Actions'));
    }

    // Show indicator if this entry has been reversed
    if (frm.doc.is_reversed && frm.doc.reversal_entry) {
      frm.dashboard.add_indicator(
        __('Reversed by {0}', [frm.doc.reversal_entry]),
        'orange'
      );

      // Add button to view reversal entry
      frm.add_custom_button(__('View Reversal Entry'), () => {
        frappe.set_route('Form', 'Payment Entry', frm.doc.reversal_entry);
      }, __('Actions'));
    }

    // Show indicator if this is a reversal entry
    if (frm.doc.is_reversal && frm.doc.reversed_entry) {
      frm.dashboard.add_indicator(
        __('Reversal of {0}', [frm.doc.reversed_entry]),
        'blue'
      );

      // Add button to view original entry
      frm.add_custom_button(__('View Original Entry'), () => {
        frappe.set_route('Form', 'Payment Entry', frm.doc.reversed_entry);
      }, __('Actions'));
    }
  }
});

/**
 * Setup custom cancel button - bypass "Cancel All Documents" dialog
 */
function _setupCancelButton(frm) {
  // Remove standard cancel button more reliably
  setTimeout(() => {
    // Remove from main button area
    frm.page.wrapper.find('.btn-secondary').filter(function() {
      return $(this).text().trim() === __('Cancel') || $(this).attr('data-label') === 'Cancel';
    }).remove();

    // Remove from dropdown menu
    frm.page.wrapper.find('[data-label="Cancel"]').closest('li').remove();

    // Add custom cancel button in Actions dropdown
    if (!frm.custom_buttons[__('Cancel')]) {
      frm.add_custom_button(__('Cancel'), () => {
        _showSimpleCancelDialog(frm);
      }, __('Actions'));
    }
  }, 200);
}

/**
 * Show simple cancel dialog - no "Cancel All Documents" list
 */
function _showSimpleCancelDialog(frm) {
  // Validate document is submitted before allowing cancel
  if (frm.doc.docstatus !== 1) {
    frappe.msgprint({
      title: __('Cannot Cancel'),
      indicator: 'red',
      message: __('Only submitted documents can be cancelled. This document is in {0} status.',
        [frm.doc.docstatus === 0 ? __('Draft') : __('Cancelled')])
    });
    return;
  }

  let message = '<div style="padding: 10px;">';
  message += '<p style="font-size: 14px;">' + __('Are you sure you want to cancel this Payment Entry?') + '</p>';

  // Simple note about linked documents (if any)
  if (frm.doc.imogi_expense_request) {
    message += '<div class="alert alert-info" style="margin-top: 15px; font-size: 12px;">';
    message += '<strong>ℹ️ ' + __('Note:') + '</strong><br>';
    message += __('Linked documents will remain active for audit trail.');
    message += '<br>' + __('Only this Payment Entry will be cancelled.');
    message += '</div>';
  }

  message += '</div>';

  frappe.confirm(
    message,
    () => {
      // Direct cancel - backend will handle ignore_links flag
      frappe.call({
        method: 'frappe.client.cancel',
        args: {
          doctype: frm.doc.doctype,
          name: frm.doc.name
        },
        freeze: true,
        freeze_message: __('Cancelling Payment Entry...'),
        callback: (r) => {
          if (!r.exc) {
            frappe.show_alert({
              message: __('Payment Entry cancelled successfully'),
              indicator: 'orange'
            });
            frm.reload_doc();
          }
        }
      });
    }
  );
}



// Payment Entry List View Settings
frappe.listview_settings["Payment Entry"] = {
    add_fields: ["payment_type", "party", "paid_amount", "unallocated_amount", "references"],
    get_indicator: function(doc) {
        if (doc.docstatus === 2) {
            return [__("Cancelled"), "red", "docstatus,=,2"];
        }
        if (doc.docstatus === 0) {
            return [__("Draft"), "gray", "docstatus,=,0"];
        }

        const unalloc = parseFloat(doc.unallocated_amount || 0);

        if (unalloc > 0) {
            return [__("Unallocated"), "orange", "unallocated_amount,>,0"];
        }
        return [__("Allocated"), "green", "unallocated_amount,=,0"];
    },
    onload: function(listview) {
        // Add filter shortcuts
        listview.page.add_inner_button(__("Unallocated"), function() {
            listview.filter_area.add([[
                "Payment Entry", "unallocated_amount", ">", "0"
            ]]);
        }, __("Filter By"));

        listview.page.add_inner_button(__("Allocated"), function() {
            listview.filter_area.add([[
                "Payment Entry", "unallocated_amount", "=", "0"
            ]]);
        }, __("Filter By"));
    },
    formatters: {
        unallocated_amount: function(value, field, doc) {
            if (!value || value === 0) {
                return `<span style="color: green;">✓ ${format_currency(0)}</span>`;
            }
            return `<span style="color: orange; font-weight: bold;">⚠ ${format_currency(value)}</span>`;
        }
    }
};


// ─── TOWING: Auto Fetch Detail Kendaraan Towing ───────────────────────────

frappe.ui.form.on("Payment Entry", {
    delivery_order_towing(frm) {
        if (frm.doc.delivery_order_towing) {
            fetch_towing_data_pe(frm);
        } else {
            frm.clear_table("custom_towing_kendaraan");
            frm.refresh_field("custom_towing_kendaraan");
        }
    },
});

// Extend existing refresh — tambah tombol Fetch Towing Data
const _orig_pe_refresh = frappe.ui.form.on("Payment Entry", {});
frappe.ui.form.on("Payment Entry", {
    refresh(frm) {
        if (frm.doc.delivery_order_towing && frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Fetch Towing Data"), () => {
                fetch_towing_data_pe(frm);
            }, __("Tools"));
        }
    },
});

function fetch_towing_data_pe(frm) {
    frappe.db.get_value(
        "Delivery Order Towing",
        frm.doc.delivery_order_towing,
        "sales_order",
        (r) => {
            if (!r?.sales_order) {
                frappe.msgprint(__("Delivery Order ini tidak memiliki Sales Order Referensi."));
                return;
            }
            frappe.db.get_doc("Sales Order", r.sales_order).then((so_doc) => {
                const rows = so_doc.custom_towing_kendaraan || [];
                if (!rows.length) {
                    frappe.msgprint(
                        __("Sales Order {0} tidak memiliki data Detail Kendaraan Towing.", [r.sales_order])
                    );
                    return;
                }
                frm.clear_table("custom_towing_kendaraan");
                rows.forEach((row) => {
                    const new_row = frm.add_child("custom_towing_kendaraan");
                    new_row.so_item_code = row.so_item_code;
                    new_row.nomor_rangka = row.nomor_rangka;
                    new_row.nomor_polisi = row.nomor_polisi;
                    new_row.tipe_model   = row.tipe_model;
                    new_row.nomor_mesin  = row.nomor_mesin;
                });
                frm.refresh_field("custom_towing_kendaraan");
                frm.dirty();
                frappe.show_alert({
                    message: __("Detail Kendaraan Towing berhasil diambil dari SO {0}", [r.sales_order]),
                    indicator: "green",
                });
            });
        }
    );
}
