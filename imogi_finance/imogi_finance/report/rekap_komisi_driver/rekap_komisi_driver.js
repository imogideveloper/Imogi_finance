frappe.query_reports["Rekap Komisi Driver"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_end(),
			reqd: 1,
		},
		{
			fieldname: "driver",
			label: __("Driver"),
			fieldtype: "Link",
			options: "Driver",
			placeholder: __("Semua Driver"),
		},
		{
			fieldname: "status_komisi",
			label: __("Status Komisi"),
			fieldtype: "Select",
			options: "Semua\nUnpaid\nPaid",
			default: "Semua",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		try {
			value = default_formatter(value, row, column, data, default_formatter);

			if (column.fieldname === "status_komisi") {
				let status = data ? data.status_komisi : value;
				if (status === "Unpaid") {
					value = `<span style="color:#e67e22;font-weight:600">● Unpaid</span>`;
				} else if (status === "Paid") {
					value = `<span style="color:#27ae60;font-weight:600">● Paid</span>`;
				}
			}

			if (column.fieldname === "delivery_order_towing") {
				let do_name = data ? data.delivery_order_towing : value;
				if (do_name) {
					value = `<a href="/app/delivery-order-towing/${do_name}" target="_blank">${do_name}</a>`;
				}
			}
		} catch(e) {
			// jangan crash, return value apa adanya
		}
		return value;
	},

	onload: function (report) {
		// Tambah tombol Create Payment Entry
		report.page.add_inner_button(__("Create Payment Entry"), function () {
			let all_data = report.data || [];
			let unpaid = all_data.filter(r => r.status_komisi === "Unpaid");

			if (!unpaid.length) {
				frappe.msgprint(__("Tidak ada DO Unpaid di report ini."));
				return;
			}

			// Group by driver
			let by_driver = {};
			unpaid.forEach(r => {
				let key = r.driver || "unknown";
				if (!by_driver[key]) {
					by_driver[key] = {
						driver: r.driver,
						driver_nama: r.driver_nama,
						supplier: r.supplier,
						rows: []
					};
				}
				by_driver[key].rows.push(r);
			});

			let driver_list = Object.values(by_driver);

			if (driver_list.length === 1) {
				// Langsung proses kalau hanya 1 driver
				_confirm_and_create(report, driver_list[0]);
			} else {
				// Tampilkan dialog pilih driver
				_show_driver_picker(report, driver_list);
			}
		}, __("Tools"));

		// Tambah tombol Export Excel
		report.page.add_inner_button(__("Export Excel"), function () {
			report.export_report("Excel");
		}, __("Tools"));
	},

	get_chart_data: function (columns, result) {
		try {
			if (!result || !result.length) return null;

			// Cari index kolom driver_nama dan komisi
			let driver_idx = columns.findIndex(c => c.fieldname === "driver_nama");
			let komisi_idx = columns.findIndex(c => c.fieldname === "komisi");

			if (driver_idx < 0 || komisi_idx < 0) return null;

			let by_driver = {};
			result.forEach(r => {
				// Support both dict and array format
				let driver_nama = Array.isArray(r) ? r[driver_idx] : r.driver_nama;
				let komisi = Array.isArray(r) ? r[komisi_idx] : r.komisi;
				if (!driver_nama) return;
				if (!by_driver[driver_nama]) by_driver[driver_nama] = 0;
				by_driver[driver_nama] += flt(komisi);
			});

			let labels = Object.keys(by_driver);
			let values = Object.values(by_driver);
			if (!labels.length) return null;

			return {
				data: {
					labels: labels,
					datasets: [{ values: values }],
				},
				type: "bar",
				colors: ["#5e64ff"],
				title: __("Komisi per Driver"),
			};
		} catch(e) {
			console.error("Chart error:", e);
			return null;
		}
	},

	after_datatable_render: function (datatable) {
		// Tambah summary row di bawah
		_render_summary(this);
	},
};


// ── Helpers ──────────────────────────────────────────────────

function _confirm_and_create(report, driver_info) {
	let rows = driver_info.rows;
	let total = rows.reduce((s, r) => s + (flt(r.komisi) || 0), 0);
	let do_list = rows.map(r => r.delivery_order_towing);
	let driver_nama = driver_info.driver_nama || driver_info.driver;
	let supplier = driver_info.supplier;

	if (!supplier) {
		frappe.msgprint({
			title: __("Supplier Belum Diset"),
			message: __(`Driver <b>${driver_nama}</b> belum memiliki Supplier. `+
				`Buka master Driver → isi field <b>Supplier (Uang Jalan)</b> terlebih dahulu.`),
			indicator: "orange"
		});
		return;
	}

	frappe.confirm(
		`Buat Payment Entry untuk <b>${driver_nama}</b>?<br><br>` +
		`Jumlah DO: <b>${do_list.length}</b><br>` +
		`Total Komisi: <b>${format_currency(total)}</b>`,
		function () {
			_create_payment_entry(report, rows, supplier, driver_nama, total, do_list);
		}
	);
}

function _show_driver_picker(report, driver_list) {
	let options_html = driver_list.map(d => {
		let total = d.rows.reduce((s, r) => s + flt(r.komisi), 0);
		return `<div class="driver-pick-item" style="padding:8px;border:1px solid #d1d8dd;
				border-radius:4px;margin-bottom:8px;cursor:pointer;background:#fff;"
				data-driver="${d.driver}">
			<b>${d.driver_nama || d.driver}</b>
			<span style="float:right;color:#6c757d">${d.rows.length} DO · ${format_currency(total)}</span>
		</div>`;
	}).join('');

	let d = new frappe.ui.Dialog({
		title: __("Pilih Driver"),
		fields: [{
			fieldname: "info",
			fieldtype: "HTML",
			options: `<p>Ada <b>${driver_list.length}</b> driver dengan komisi Unpaid. Pilih driver:</p>` +
				`<div id="driver-pick-list">${options_html}</div>`,
		}],
	});

	d.show();

	setTimeout(() => {
		$(d.wrapper).find('.driver-pick-item').on('click', function() {
			let driver_id = $(this).data('driver');
			let selected = driver_list.find(x => x.driver === driver_id);
			d.hide();
			if (selected) _confirm_and_create(report, selected);
		});
	}, 300);
}

function _get_checked_rows(report) {
	let rows = [];
	try {
		let checked_rows = report.datatable.rowmanager.getCheckedRows();
		checked_rows.forEach(idx => {
			let row_data = report.data[idx];
			if (row_data) rows.push(row_data);
		});
	} catch (e) {
		// fallback: ambil semua data yang Unpaid
		rows = (report.data || []).filter(r => r.status_komisi === "Unpaid");
	}
	return rows;
}

function _create_payment_entry(report, checked, supplier, driver_nama, total, do_list) {
	frappe.call({
		method: "imogi_finance.api.commission.create_payment_entry_from_report",
		args: {
			do_names: do_list,
			supplier: supplier,
			driver_nama: driver_nama,
			total_komisi: total,
		},
		freeze: true,
		freeze_message: __("Membuat Payment Entry..."),
		callback: function (r) {
			if (r.message && r.message.payment_entry) {
				let pe_name = r.message.payment_entry;
				let dc_name = r.message.driver_commission;

				frappe.msgprint({
					title: __("Payment Entry Dibuat"),
					message: `
						Driver Commission <b>${dc_name}</b> berhasil dibuat.<br><br>
						Payment Entry <b>${pe_name}</b> sudah disiapkan (Draft).<br>
						<b>Langkah selanjutnya:</b> Buka Payment Entry → set akun → Submit untuk mencatat pembayaran.
						<br><br>
						<a href="/app/payment-entry/${pe_name}" class="btn btn-primary btn-sm">
							Buka Payment Entry →
						</a>
					`,
					indicator: "green",
					wide: true,
				});
				report.refresh();
			}
		},
	});
}

function _render_summary(report) {
	let data = report.data || [];
	if (!data.length) return;

	let total_komisi = data.reduce((s, r) => s + flt(r.komisi), 0);
	let unpaid = data.filter(r => r.status_komisi === "Unpaid").reduce((s, r) => s + flt(r.komisi), 0);
	let paid = data.filter(r => r.status_komisi === "Paid").reduce((s, r) => s + flt(r.komisi), 0);
	let total_do = data.length;

	let summary_html = `
		<div style="padding: 8px 16px; background: #f4f5f6; border-top: 1px solid #d1d8dd;
			display: flex; gap: 24px; font-size: 13px; align-items: center;">
			<span><b>${total_do}</b> DO ditemukan</span>
			<span>Total komisi: <b>${format_currency(total_komisi)}</b></span>
			<span style="color:#e67e22">● Unpaid: <b>${format_currency(unpaid)}</b></span>
			<span style="color:#27ae60">● Paid: <b>${format_currency(paid)}</b></span>
		</div>
	`;

	// Remove existing summary
	$(report.wrapper).find(".commission-summary").remove();
	$(report.wrapper).find(".datatable").after(summary_html.replace('class="', 'class="commission-summary '));
}

function format_currency(val) {
	try {
		// Frappe v15 pakai format_number atau number_format tergantung versi
		if (frappe.utils.format_number) {
			return "Rp " + frappe.utils.format_number(val, null, 0);
		}
		// Fallback manual
		return "Rp " + Math.round(flt(val)).toLocaleString("id-ID");
	} catch(e) {
		return "Rp " + Math.round(flt(val)).toLocaleString("id-ID");
	}
}

function flt(val) {
	return parseFloat(val) || 0;
}