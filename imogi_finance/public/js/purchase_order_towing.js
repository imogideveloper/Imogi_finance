// File  : imogi_finance/public/js/purchase_order_towing.js
// Fungsi: Fetch Detail Kendaraan Towing dari DO + tombol cancel custom

frappe.ui.form.on("Purchase Order", {

    refresh(frm) {
        // ─────────────────────────────────────────────────────────────
        // Tombol existing: Fetch Towing Data (untuk PO Draft)
        // ─────────────────────────────────────────────────────────────
        if (frm.doc.custom_delivery_order && frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Fetch Towing Data"), () => {
                fetch_towing_data_po(frm);
            }, __("Tools"));
        }

        // ─────────────────────────────────────────────────────────────
        // Tombol BARU: Cancel PO Uang Jalan
        // Muncul kalau:
        //   - PO sudah Submitted (docstatus=1)
        //   - PO punya custom_delivery_order (artinya PO Uang Jalan towing)
        // ─────────────────────────────────────────────────────────────
        if (frm.doc.custom_delivery_order && frm.doc.docstatus === 1) {
            frm.add_custom_button(__("Cancel PO Uang Jalan"), () => {
                cancel_po_uang_jalan_custom(frm);
            }).addClass("btn-danger");
        }
    },

    custom_delivery_order(frm) {
        if (frm.doc.custom_delivery_order) {
            fetch_towing_data_po(frm);
        } else {
            frm.clear_table("custom_towing_kendaraan");
            frm.refresh_field("custom_towing_kendaraan");
        }
    },
});


// ════════════════════════════════════════════════════════════════════
// CANCEL PO UANG JALAN dengan cleanup link DO duluan
// (skip dialog "Cancel All Documents" Frappe)
// ════════════════════════════════════════════════════════════════════

function cancel_po_uang_jalan_custom(frm) {
    frappe.confirm(
        __("Yakin ingin cancel Purchase Order ini?<br><br>" +
           "<b>Catatan:</b><br>" +
           "• Purchase Invoice <b>Draft</b> yang ter-link akan ikut di-cancel<br>" +
           "• Kalau ada PI <b>Submitted</b> atau Payment Entry, akan diblokir<br>" +
           "• Status uang jalan di DO akan di-reset ke <b>Belum Diajukan</b>"),
        function() {
            frappe.dom.freeze(__("Membatalkan Purchase Order..."));

            frappe.call({
                method: "imogi_finance.overrides.delivery_order_towing.cancel_po_uang_jalan_with_cleanup",
                args: {
                    po_name: frm.doc.name
                },
                callback: function(r) {
                    frappe.dom.unfreeze();

                    if (r.message && r.message.success) {
                        let msg = __("✅ Purchase Order {0} berhasil di-cancel.", [r.message.po_name]);

                        if (r.message.cancelled_pis && r.message.cancelled_pis.length > 0) {
                            msg += "<br><br><b>" + __("Purchase Invoice (Draft) yang ikut di-cancel:") + "</b><br>";
                            r.message.cancelled_pis.forEach(function(pi_name) {
                                msg += "• " + pi_name + "<br>";
                            });
                        }

                        if (r.message.do_name) {
                            msg += "<br>" + __("Status uang jalan di DO {0} di-reset ke 'Belum Diajukan'.",
                                [r.message.do_name]);
                        }

                        frappe.msgprint({
                            title: __("PO Uang Jalan Cancelled"),
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
// FETCH TOWING DATA (existing function, tidak diubah)
// ════════════════════════════════════════════════════════════════════

function fetch_towing_data_po(frm) {
    // ✅ Ambil langsung dari DO, bukan melalui SO
    frappe.db.get_doc("Delivery Order Towing", frm.doc.custom_delivery_order)
        .then((do_doc) => {
            // Ambil so_item_code dari SO Towing Kendaraan yang linked ke DO ini
            frappe.db.get_value(
                "SO Towing Kendaraan",
                { delivery_order: do_doc.name },
                "so_item_code",
                (r) => {
                    frm.clear_table("custom_towing_kendaraan");
                    const new_row = frm.add_child("custom_towing_kendaraan");
                    new_row.so_item_code = r?.so_item_code || "";
                    new_row.nomor_rangka = do_doc.nomor_rangka || "";
                    new_row.nomor_polisi = do_doc.nomor_polisi || "";
                    new_row.tipe_model   = do_doc.tipe_kendaraan || "";
                    new_row.nomor_mesin  = do_doc.nomor_mesin || "";
                    frm.refresh_field("custom_towing_kendaraan");
                    frm.dirty();
                    frappe.show_alert({
                        message: __("Detail Kendaraan diambil dari DO {0}", [do_doc.name]),
                        indicator: "green",
                    });
                }
            );
        })
        .catch(() => {
            frappe.msgprint(__("Delivery Order Towing tidak ditemukan."));
        });
}