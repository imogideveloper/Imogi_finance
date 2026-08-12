/**
 * Payment Entry UI Enhancements
 */

frappe.ui.form.on('Payment Entry', {
  refresh(frm) {
    if (frm.doc.docstatus === 1 && !frm.is_new()) {
      _setupCancelButton(frm);
    }

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

    if (frm.doc.is_reversed && frm.doc.reversal_entry) {
      frm.dashboard.add_indicator(
        __('Reversed by {0}', [frm.doc.reversal_entry]),
        'orange'
      );
      frm.add_custom_button(__('View Reversal Entry'), () => {
        frappe.set_route('Form', 'Payment Entry', frm.doc.reversal_entry);
      }, __('Actions'));
    }

    if (frm.doc.is_reversal && frm.doc.reversed_entry) {
      frm.dashboard.add_indicator(
        __('Reversal of {0}', [frm.doc.reversed_entry]),
        'blue'
      );
      frm.add_custom_button(__('View Original Entry'), () => {
        frappe.set_route('Form', 'Payment Entry', frm.doc.reversed_entry);
      }, __('Actions'));
    }

    // ✅ Tombol Fetch Towing Data — hanya saat draft
    if (frm.doc.docstatus === 0) {
      frm.add_custom_button(__("Fetch Towing Data"), () => {
        _resolve_do_from_pe(frm, (do_name) => {
          if (!do_name) {
            frappe.msgprint(__("Tidak ada Delivery Order yang terhubung ke Payment Entry ini."));
            return;
          }
          fetch_towing_data_pe(frm, do_name);
        });
      }, __("Tools"));
    }
  }
});

function _setupCancelButton(frm) {
  setTimeout(() => {
    frm.page.wrapper.find('.btn-secondary').filter(function() {
      return $(this).text().trim() === __('Cancel') || $(this).attr('data-label') === 'Cancel';
    }).remove();
    frm.page.wrapper.find('[data-label="Cancel"]').closest('li').remove();
    if (!frm.custom_buttons[__('Cancel')]) {
      frm.add_custom_button(__('Cancel'), () => {
        _showSimpleCancelDialog(frm);
      }, __('Actions'));
    }
  }, 200);
}

function _showSimpleCancelDialog(frm) {
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
  if (frm.doc.imogi_expense_request) {
    message += '<div class="alert alert-info" style="margin-top: 15px; font-size: 12px;">';
    message += '<strong>ℹ️ ' + __('Note:') + '</strong><br>';
    message += __('Linked documents will remain active for audit trail.');
    message += '<br>' + __('Only this Payment Entry will be cancelled.');
    message += '</div>';
  }
  message += '</div>';

  frappe.confirm(message, () => {
    frappe.call({
      method: 'frappe.client.cancel',
      args: { doctype: frm.doc.doctype, name: frm.doc.name },
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
  });
}

// List View badge/indicator settings for Payment Entry live in
// public/js/payment_entry_list.js — that file is loaded via BOTH doctype_js
// (so the Form page-title badge is correct) and doctype_list_js (so the List
// View row badge is correct), since frappe.get_indicator() reads the same
// frappe.listview_settings[doctype].get_indicator either way, but doctype_js
// only executes on Form views and doctype_list_js only on List views.

// ── TOWING ───────────────────────────────────────────────────────────────────

frappe.ui.form.on("Payment Entry", {
  delivery_order_towing(frm) {
    if (frm.doc.delivery_order_towing) {
      // ✅ Hanya fetch jika tabel masih kosong
      const has_data = (frm.doc.custom_towing_kendaraan || []).length > 0;
      if (!has_data) {
        fetch_towing_data_pe(frm, frm.doc.delivery_order_towing);
      }
    } else {
      frm.clear_table("custom_towing_kendaraan");
      frm.refresh_field("custom_towing_kendaraan");
    }
  },
});

frappe.ui.form.on("Payment Entry Reference", {
  reference_name(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (!row.reference_name) return;
    if (row.reference_doctype !== "Purchase Invoice" &&
        row.reference_doctype !== "Purchase Order") return;

    // ✅ Hanya fetch jika tabel kendaraan masih kosong
    const has_data = (frm.doc.custom_towing_kendaraan || []).length > 0;
    if (has_data) return;

    setTimeout(() => {
      _resolve_do_from_reference_row(row, (do_name) => {
        if (do_name) fetch_towing_data_pe(frm, do_name);
      });
    }, 500);
  },
});

/**
 * Cari DO dari baris reference (PI atau PO)
 */
function _resolve_do_from_reference_row(ref_row, callback) {
  if (!ref_row.reference_name) { callback(null); return; }
  frappe.db.get_value(
    ref_row.reference_doctype,
    ref_row.reference_name,
    "custom_delivery_order",
    (r) => callback(r?.custom_delivery_order || null)
  );
}

/**
 * Cari DO dari seluruh PE:
 * 1. Field delivery_order_towing langsung
 * 2. Via references PI / PO
 */
function _resolve_do_from_pe(frm, callback) {
  if (frm.doc.delivery_order_towing) {
    callback(frm.doc.delivery_order_towing);
    return;
  }
  const refs = frm.doc.references || [];
  const ref = refs.find(r =>
    r.reference_doctype === "Purchase Invoice" ||
    r.reference_doctype === "Purchase Order"
  );
  if (!ref || !ref.reference_name) { callback(null); return; }
  _resolve_do_from_reference_row(ref, callback);
}

/**
 * ✅ Fetch 1 baris kendaraan dari PI dulu, fallback ke DO langsung.
 * Copy dari PI supaya konsisten dengan data yang sudah tersimpan di PI.
 */
function fetch_towing_data_pe(frm, do_name) {
    const pi_ref = (frm.doc.references || []).find(r => r.reference_doctype === "Purchase Invoice");

    if (pi_ref && pi_ref.reference_name) {
        // ✅ Copy dari PI via whitelisted API — tidak ada PermissionError
        frappe.call({
            method: "imogi_finance.overrides.delivery_order_towing.get_towing_kendaraan_from_pi",
            args: { pi_name: pi_ref.reference_name },
            callback(r) {
                const rows = r.message || [];
                if (!rows.length) {
                    _fetch_from_do(frm, do_name);
                    return;
                }
                frm.clear_table("custom_towing_kendaraan");
                rows.forEach((row) => {
                    const new_row = frm.add_child("custom_towing_kendaraan");
                    new_row.so_item_code = row.so_item_code || "";
                    new_row.nomor_rangka = row.nomor_rangka || "";
                    new_row.nomor_polisi = row.nomor_polisi || "";
                    new_row.tipe_model   = row.tipe_model   || "";
                    new_row.nomor_mesin  = row.nomor_mesin  || "";
                });
                frm.refresh_field("custom_towing_kendaraan");
                frm.dirty();
                frappe.show_alert({
                    message: __("Detail Kendaraan diambil dari PI {0}", [pi_ref.reference_name]),
                    indicator: "green",
                });
            },
            error() { _fetch_from_do(frm, do_name); }
        });
    } else {
        _fetch_from_do(frm, do_name);
    }
}

function _fetch_from_do(frm, do_name) {
    // ✅ Pakai whitelisted API — tidak ada PermissionError
    frappe.call({
        method: "imogi_finance.overrides.delivery_order_towing.get_towing_kendaraan_from_do",
        args: { do_name: do_name },
        callback(r) {
            const row_data = r.message;
            if (!row_data) {
                frappe.msgprint(__("Data kendaraan tidak ditemukan untuk DO {0}", [do_name]));
                return;
            }
            frm.clear_table("custom_towing_kendaraan");
            const new_row = frm.add_child("custom_towing_kendaraan");
            new_row.so_item_code = row_data.so_item_code || "";
            new_row.nomor_rangka = row_data.nomor_rangka || "";
            new_row.nomor_polisi = row_data.nomor_polisi || "";
            new_row.tipe_model   = row_data.tipe_model   || "";
            new_row.nomor_mesin  = row_data.nomor_mesin  || "";
            frm.refresh_field("custom_towing_kendaraan");
            frm.dirty();
            frappe.show_alert({
                message: __("Detail Kendaraan diambil dari DO {0}", [do_name]),
                indicator: "green",
            });
        },
        error() {
            frappe.msgprint(__("Delivery Order Towing tidak ditemukan."));
        }
    });
}