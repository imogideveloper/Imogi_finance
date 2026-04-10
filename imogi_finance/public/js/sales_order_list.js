console.log("SALES ORDER LIST JS LOADED");

frappe.listview_settings["Sales Order"] = {
    add_fields: ["custom_payment_status", "docstatus", "transaction_date"],

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
    },

    onload: function(listview) {
        listview.page.add_inner_button(__('📅 Filter Tanggal'), function() {
            show_date_filter_dialog(listview);
        });
    }
};

function get_business_status(doc) {
    if (cint(doc.docstatus) === 2) return "Cancelled";
    if (cint(doc.docstatus) === 0) return "Draft";
    const payment_status = (doc.custom_payment_status || "").trim();
    if (payment_status === "Paid") return "Paid";
    if (payment_status === "Partial Paid") return "Partial Paid";
    if (payment_status === "SI Created") return "SI Created";
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

function show_date_filter_dialog(listview) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Sales Order',
            fields: ['transaction_date'],
            limit: 0,
            order_by: 'transaction_date asc'
        },
        callback: function(r) {
            if (!r.message) return;
            let years = [...new Set(
                r.message.map(d => frappe.datetime.str_to_obj(d.transaction_date).getFullYear())
            )].sort();
            show_year_picker(listview, years, r.message);
        }
    });
}

function show_year_picker(listview, years, all_data) {
    const month_names = ['Januari','Februari','Maret','April','Mei','Juni','Juli','Agustus','September','Oktober','November','Desember'];
    let year_buttons = years.map(year => {
        let count = all_data.filter(d => frappe.datetime.str_to_obj(d.transaction_date).getFullYear() === year).length;
        return `<div class="date-filter-item" data-year="${year}" style="padding:10px 20px;margin:5px;border:1px solid #d1d8dd;border-radius:6px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;transition:background 0.2s;"><span style="font-weight:600;font-size:15px;">📅 ${year}</span><span style="background:#e8f4f8;color:#2490ef;padding:2px 10px;border-radius:12px;font-size:12px;">${count} order</span></div>`;
    }).join('');

    let d = new frappe.ui.Dialog({
        title: '🗓️ Pilih Tahun',
        fields: [{
            fieldtype: 'HTML', fieldname: 'year_picker',
            options: `<div style="padding:10px;"><p style="color:#8d99a6;margin-bottom:10px;font-size:13px;">Pilih tahun untuk memfilter Sales Order</p>${year_buttons}<div style="margin-top:15px;padding-top:10px;border-top:1px solid #eee;"><button class="btn btn-sm btn-default" id="clear-date-filter" style="width:100%;">❌ Hapus Filter Tanggal</button></div></div>`
        }]
    });
    d.show();

    d.$wrapper.find('.date-filter-item').on('mouseenter', function() { $(this).css('background','#f0f7ff'); }).on('mouseleave', function() { $(this).css('background',''); });
    d.$wrapper.find('.date-filter-item').on('click', function() {
        let year = parseInt($(this).data('year'));
        d.hide();
        show_month_picker(listview, year, all_data, month_names);
    });
    d.$wrapper.find('#clear-date-filter').on('click', function() {
        try { listview.filter_area.remove('transaction_date'); } catch(e) {}
        listview.refresh(); d.hide();
        frappe.show_alert({ message: 'Filter tanggal dihapus', indicator: 'blue' }, 3);
    });
}

function show_month_picker(listview, year, all_data, month_names) {
    let months_data = all_data.filter(d => frappe.datetime.str_to_obj(d.transaction_date).getFullYear() === year);
    let months = [...new Set(months_data.map(d => frappe.datetime.str_to_obj(d.transaction_date).getMonth()))].sort((a,b)=>a-b);
    let month_buttons = months.map(month => {
        let count = months_data.filter(d => frappe.datetime.str_to_obj(d.transaction_date).getMonth() === month).length;
        return `<div class="month-filter-item" data-month="${month+1}" style="padding:10px 20px;margin:5px;border:1px solid #d1d8dd;border-radius:6px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;transition:background 0.2s;"><span style="font-weight:500;font-size:14px;">📆 ${month_names[month]}</span><span style="background:#e8f4f8;color:#2490ef;padding:2px 10px;border-radius:12px;font-size:12px;">${count} order</span></div>`;
    }).join('');

    let d = new frappe.ui.Dialog({
        title: `🗓️ ${year} — Pilih Bulan`,
        fields: [{
            fieldtype: 'HTML', fieldname: 'month_picker',
            options: `<div style="padding:10px;"><p style="color:#8d99a6;margin-bottom:10px;font-size:13px;">Pilih bulan atau tampilkan semua order di ${year}</p><button class="btn btn-sm btn-primary" id="filter-whole-year" style="width:100%;margin-bottom:10px;">📅 Semua order ${year}</button>${month_buttons}<div style="margin-top:10px;padding-top:10px;border-top:1px solid #eee;display:flex;gap:8px;"><button class="btn btn-sm btn-default" id="back-to-year" style="flex:1;">← Kembali</button><button class="btn btn-sm btn-default" id="clear-filter-month" style="flex:1;">❌ Hapus Filter</button></div></div>`
        }]
    });
    d.show();

    d.$wrapper.find('.month-filter-item').on('mouseenter', function() { $(this).css('background','#f0f7ff'); }).on('mouseleave', function() { $(this).css('background',''); });
    d.$wrapper.find('#filter-whole-year').on('click', function() {
        apply_date_filter(listview, `${year}-01-01`, `${year}-12-31`, `Tahun ${year}`); d.hide();
    });
    d.$wrapper.find('.month-filter-item').on('click', function() {
        let month = parseInt($(this).data('month'));
        let from = frappe.datetime.obj_to_str(new Date(year, month-1, 1));
        let last_day = new Date(year, month, 0).getDate();
        let to = frappe.datetime.obj_to_str(new Date(year, month-1, last_day));
        apply_date_filter(listview, from, to, `${month_names[month-1]} ${year}`); d.hide();
    });
    d.$wrapper.find('#back-to-year').on('click', function() {
        d.hide();
        let years = [...new Set(all_data.map(d => frappe.datetime.str_to_obj(d.transaction_date).getFullYear()))].sort();
        show_year_picker(listview, years, all_data);
    });
    d.$wrapper.find('#clear-filter-month').on('click', function() {
        try { listview.filter_area.remove('transaction_date'); } catch(e) {}
        listview.refresh(); d.hide();
        frappe.show_alert({ message: 'Filter tanggal dihapus', indicator: 'blue' }, 3);
    });
}

function apply_date_filter(listview, from_date, to_date, label) {
    try { listview.filter_area.remove('transaction_date'); } catch(e) {}
    listview.filter_area.add([
        ['Sales Order', 'transaction_date', '>=', from_date],
        ['Sales Order', 'transaction_date', '<=', to_date]
    ]);
    listview.refresh();
    frappe.show_alert({ message: `Filter: ${label}`, indicator: 'green' }, 4);
}
