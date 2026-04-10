console.log("SALES ORDER LIST JS LOADED");

frappe.listview_settings["Sales Order"] = {
    add_fields: ["custom_payment_status", "docstatus"],

    get_indicator(doc) {
        const status = get_business_status(doc);

        const status_map = {
            "Draft": ["Draft", "grey"],
            "Submitted": ["Submitted", "blue"],
            "SI Created": ["SI Created", "blue"],
            "Partial Paid": ["Partial Paid", "orange"],
            "Paid": ["Paid", "green"],
            "Cancelled": ["Cancelled", "red"]
        };

        return status_map[status] || [status, "grey"];
    },

    formatters: {
        custom_payment_status(value, df, doc) {
            const status = get_business_status(doc);
            const color = get_status_color(status);

            return `<span class="indicator-pill ${color} ellipsis">${status}</span>`;
        }
    }
};

function get_business_status(doc) {
    if (cint(doc.docstatus) === 2) {
        return "Cancelled";
    }

    if (cint(doc.docstatus) === 0) {
        return "Draft";
    }

    const payment_status = (doc.custom_payment_status || "").trim();

    if (payment_status === "Paid") {
        return "Paid";
    }

    if (payment_status === "Partial Paid") {
        return "Partial Paid";
    }

    if (payment_status === "SI Created") {
        return "SI Created";
    }

    return "Submitted";
}

function get_status_color(status) {
    const color_map = {
        "Draft": "grey",
        "Submitted": "blue",
        "SI Created": "blue",
        "Partial Paid": "orange",
        "Paid": "green",
        "Cancelled": "red"
    };

    return color_map[status] || "grey";
}

function cint(v) {
    return parseInt(v || 0, 10);
}