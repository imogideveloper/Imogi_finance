// File  : imogi_finance/public/js/item_price.js
// Fungsi: Lock field harga di Item Price.
// Yang boleh edit: Administrator + Finance Manager.

frappe.ui.form.on("Item Price", {
    refresh(frm) {
        lock_price_fields(frm);
    },

    onload(frm) {
        lock_price_fields(frm);
    },
});


function lock_price_fields(frm) {
    // ─────────────────────────────────────────────────────────────
    // Role yang boleh edit field harga
    // ─────────────────────────────────────────────────────────────
    const UNLOCK_ROLES = ["Administrator", "Finance Manager"];

    const is_administrator = frappe.session.user === "Administrator";
    const has_unlock_role = UNLOCK_ROLES.some(role => frappe.user_roles.includes(role));
    const user_can_unlock = is_administrator || has_unlock_role;

    // Field yang mau di-lock
    const LOCKED_FIELDS = [
        "price_list_rate",   // Rate (harga utama)
        "price_list",        // Price List (selling/buying)
    ];

    const should_lock = !frm.is_new() && !user_can_unlock;

    LOCKED_FIELDS.forEach(fieldname => {
        frm.set_df_property(fieldname, "read_only", should_lock ? 1 : 0);
    });

    if (should_lock) {
        frm.dashboard.clear_headline();
        frm.dashboard.set_headline_alert(
            __("🔒 Field <b>Rate</b> dan <b>Price List</b> tidak bisa diubah. " +
               "Hanya <b>Administrator</b> atau <b>Finance Manager</b> yang bisa mengubah harga."),
            "blue"
        );
    }
}