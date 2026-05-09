// File  : imogi_finance/public/js/transaction_price_lock.js
// Fungsi: Lock visual field harga di SO, SI, PO, PI, PE.
// Yang boleh edit: Administrator + Finance Manager.

(function() {
    "use strict";

    const UNLOCK_ROLES = ["Administrator", "Finance Manager"];

    // Header field per doctype
    const HEADER_FIELDS = {
        "Sales Order":      ["selling_price_list"],
        "Sales Invoice":    ["selling_price_list"],
        "Purchase Order":   ["buying_price_list"],
        "Purchase Invoice": ["buying_price_list"],
        "Payment Entry":    ["paid_amount", "received_amount"],
    };

    // Item child table fields
    const ITEM_FIELDS = [
        "rate",
        "price_list_rate",
        "discount_amount",
        "discount_percentage",
        "amount",
        "base_rate",
        "base_amount",
        "base_price_list_rate",
    ];

    // Mapping doctype → child fieldname (di parent doc)
    const ITEM_CHILD_FIELDNAME = {
        "Sales Order":      "items",
        "Sales Invoice":    "items",
        "Purchase Order":   "items",
        "Purchase Invoice": "items",
    };

    // ─────────────────────────────────────────────────────────────
    // Cek apakah user boleh unlock
    // ─────────────────────────────────────────────────────────────
    function user_can_unlock() {
        if (frappe.session.user === "Administrator") return true;
        return UNLOCK_ROLES.some(role => frappe.user_roles.includes(role));
    }

    // ─────────────────────────────────────────────────────────────
    // Apply lock ke form
    // ─────────────────────────────────────────────────────────────
    function apply_price_lock(frm) {
        const doctype = frm.doctype;

        // New doc → tidak lock (boleh isi rate manual saat create)
        if (frm.is_new()) return;

        // Bypass kalau user punya unlock role
        if (user_can_unlock()) return;

        const should_lock = true;

        // ─── Lock HEADER fields ───────────────────────────────
        const header_fields = HEADER_FIELDS[doctype] || [];
        header_fields.forEach(fieldname => {
            if (frm.fields_dict[fieldname]) {
                frm.set_df_property(fieldname, "read_only", 1);
            }
        });

        // ─── Lock ITEMS child table fields ────────────────────
        const child_fieldname = ITEM_CHILD_FIELDNAME[doctype];
        if (child_fieldname && frm.fields_dict[child_fieldname]) {
            const grid = frm.fields_dict[child_fieldname].grid;
            if (grid) {
                ITEM_FIELDS.forEach(fieldname => {
                    if (grid.get_docfield(fieldname)) {
                        grid.update_docfield_property(fieldname, "read_only", 1);
                    }
                });
                // Refresh grid supaya read-only state update
                grid.refresh();
            }
        }

        // ─── Lock PE references (allocated_amount) ────────────
        if (doctype === "Payment Entry" && frm.fields_dict["references"]) {
            const ref_grid = frm.fields_dict["references"].grid;
            if (ref_grid && ref_grid.get_docfield("allocated_amount")) {
                ref_grid.update_docfield_property("allocated_amount", "read_only", 1);
                ref_grid.refresh();
            }
        }

        // ─── Tampilkan banner info ────────────────────────────
        frm.dashboard.clear_headline();
        frm.dashboard.set_headline_alert(
            __("🔒 Field harga (rate, price list, discount, amount) tidak bisa diubah. " +
               "Harga mengikuti master <b>Item Price</b>. " +
               "Hanya <b>Administrator</b> atau <b>Finance Manager</b> yang bisa override."),
            "blue"
        );
    }

    // ─────────────────────────────────────────────────────────────
    // Register event handler untuk semua doctype
    // ─────────────────────────────────────────────────────────────
    const TARGET_DOCTYPES = [
        "Sales Order",
        "Sales Invoice",
        "Purchase Order",
        "Purchase Invoice",
        "Payment Entry",
    ];

    TARGET_DOCTYPES.forEach(doctype => {
        frappe.ui.form.on(doctype, {
            refresh(frm) {
                apply_price_lock(frm);
            },
            onload(frm) {
                apply_price_lock(frm);
            },
        });
    });
})();