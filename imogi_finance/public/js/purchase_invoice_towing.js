// File  : imogi_finance/public/js/purchase_invoice_towing.js
// Fungsi: Tambah tombol Fetch Towing Data + auto-fetch ke Purchase Invoice

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
            fetch_towing_data_pi(frm);
        } else {
            frm.clear_table("custom_towing_kendaraan");
            frm.refresh_field("custom_towing_kendaraan");
        }
    },
});

function fetch_towing_data_pi(frm) {
    frappe.db.get_value(
        "Delivery Order Towing",
        frm.doc.custom_delivery_order,
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
