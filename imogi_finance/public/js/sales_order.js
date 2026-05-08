// File  : imogi_finance/public/js/sales_order.js
// Fungsi: Generate Detail Kendaraan Towing + tombol Cancel SO custom

frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        relocate_generate_detail_button(frm);
        // Toolbar/grid can render asynchronously in different phases.
        [250, 700, 1400].forEach((ms) => {
            setTimeout(() => relocate_generate_detail_button(frm), ms);
        });

        // ─────────────────────────────────────────────────────────────
        // Tombol Cancel SO Towing (skip dialog "Cancel All Documents")
        // Muncul kalau:
        //   - SO sudah Submitted (docstatus=1)
        //   - SO punya child table custom_towing_kendaraan (artinya SO Towing)
        // ─────────────────────────────────────────────────────────────
        if (frm.doc.docstatus === 1 && has_towing_kendaraan(frm)) {
            frm.add_custom_button(__("Cancel SO Towing"), () => {
                cancel_so_towing_custom(frm);
            }).addClass("btn-danger");
        }
    },
});


function has_towing_kendaraan(frm) {
    const kendaraan = frm.doc.custom_towing_kendaraan || [];
    return kendaraan.length > 0;
}


// ════════════════════════════════════════════════════════════════════
// CANCEL SO TOWING dengan cleanup link DO duluan
// (skip dialog "Cancel All Documents" Frappe)
// ════════════════════════════════════════════════════════════════════

function cancel_so_towing_custom(frm) {
    frappe.confirm(
        __("Yakin ingin cancel Sales Order ini?<br><br>" +
           "<b>Catatan:</b><br>" +
           "• Delivery Order Towing yang ter-link akan ikut di-cancel<br>" +
           "• Kalau ada DO yang punya turunan (PO/PI/PE/dll) <b>aktif</b>, akan diblokir<br>" +
           "• Anda harus cancel turunan DO tersebut terlebih dahulu"),
        function() {
            frappe.dom.freeze(__("Membatalkan Sales Order..."));

            frappe.call({
                method: "imogi_finance.overrides.delivery_order_towing.cancel_so_with_cleanup",
                args: {
                    so_name: frm.doc.name
                },
                callback: function(r) {
                    frappe.dom.unfreeze();

                    if (r.message && r.message.success) {
                        let msg = __("✅ Sales Order {0} berhasil di-cancel.", [r.message.so_name]);

                        if (r.message.cancelled_dos && r.message.cancelled_dos.length > 0) {
                            msg += "<br><br><b>" + __("Delivery Order Towing yang ikut di-cancel:") + "</b><br>";
                            r.message.cancelled_dos.forEach(function(do_name) {
                                msg += "• " + do_name + "<br>";
                            });
                        }

                        frappe.msgprint({
                            title: __("SO Towing Cancelled"),
                            message: msg,
                            indicator: "orange"
                        });

                        // Reload form supaya status update
                        frm.reload_doc();
                    }
                },
                error: function(err) {
                    frappe.dom.unfreeze();
                    // Frappe akan otomatis tampilkan error message dari frappe.throw()
                }
            });
        }
    );
}


// ════════════════════════════════════════════════════════════════════
// EXISTING FUNCTIONS (tidak diubah)
// ════════════════════════════════════════════════════════════════════

function relocate_generate_detail_button(frm) {
    const grid_field = frm.fields_dict?.custom_towing_kendaraan;
    const grid = grid_field?.grid;

    if (!grid || !grid.wrapper) return;

    const $wrapper = $(grid.wrapper);
    const $grid_buttons = $wrapper.find(".grid-buttons");
    if (!$grid_buttons.length) return;

    const label = __("Generate Detail Kendaraan");
    const button_class = "btn-generate-detail-kendaraan";

    $grid_buttons.find(`.${button_class}`).remove();

    const $existing_form_button = find_existing_generate_button(frm);
    if (!$existing_form_button.length) return;

    const $button = $(
        `<button class="btn btn-xs btn-secondary ${button_class}" type="button"></button>`
    ).text(label);

    $button.on("click", () => {
        $existing_form_button.trigger("click");
    });

    const $add_multiple_btn = $grid_buttons.find(".grid-add-multiple-rows");
    if ($add_multiple_btn.length) {
        $button.insertAfter($add_multiple_btn);
    } else {
        $grid_buttons.append($button);
    }

    $existing_form_button.hide();
}

function find_existing_generate_button(frm) {
    const labels = [
        __("Generate Detail Kendaraan"),
        __("Generate Detail Towing"),
    ];

    // Covers custom button as direct button, dropdown item, or menu link.
    const selectors = [
        ".page-form .custom-actions button",
        ".page-form .custom-actions a",
        ".inner-toolbar button",
        ".inner-toolbar a",
        ".menu-btn-group button",
        ".menu-btn-group a",
        ".dropdown-menu a",
    ];

    for (const selector of selectors) {
        const $match = frm.page.wrapper
            .find(selector)
            .filter((_, el) => labels.includes((($(el).text() || "").trim())));
        if ($match.length) return $match.first();
    }

    return $();
}