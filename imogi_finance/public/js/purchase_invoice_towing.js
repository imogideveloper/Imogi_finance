frappe.ui.form.on("Purchase Invoice", {

    refresh(frm) {
        if (frm.doc.custom_delivery_order && frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Fetch Towing Data"), () => {
                fetch_towing_data_pi(frm);
            }, __("Tools"));
        }
    },

    custom_delivery_order(frm) {
        if (frm.doc.custom_delivery_order) {
            // ✅ Hanya auto-fetch jika tabel kendaraan masih kosong
            const has_data = (frm.doc.custom_towing_kendaraan || []).length > 0;
            if (!has_data) {
                fetch_towing_data_pi(frm);
            }
        } else {
            frm.clear_table("custom_towing_kendaraan");
            frm.refresh_field("custom_towing_kendaraan");
        }
    },
});

function fetch_towing_data_pi(frm) {
    frappe.db.get_doc("Delivery Order Towing", frm.doc.custom_delivery_order)
        .then((do_doc) => {
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