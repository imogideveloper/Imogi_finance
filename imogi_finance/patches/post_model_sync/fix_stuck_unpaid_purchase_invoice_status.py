"""Perbaiki Purchase Invoice yang statusnya nyangkut padahal utangnya sudah lunas.

events/payment_entry.py::_revert_pi_status_for_bank_payment sengaja menurunkan
status PI dari "Paid" kembali ke "Unpaid" ketika pembayarannya keluar lewat bank,
dengan janji status itu naik lagi begitu sisi banknya direkonsiliasi. Janji itu
tidak pernah ditepati: events/bank_transaction.py sama sekali tidak menyentuh
status PI, dan Bank Clearance - jalur yang dipakai sehari-hari - menulis
clearance_date lewat frappe.db.set_value mentah sehingga tidak memicu doc event
apa pun. Akibatnya invoice yang sudah dibayar lunas tetap terbaca "Unpaid",
yaitu terbaca sebagai uang yang masih terutang.

Patch ini membereskan data lamanya. Pencegahan kekambuhannya ada di
events/bank_transaction.py::sync_reconciled_purchase_invoice_status yang berjalan
terjadwal.

set_status() milik ERPNext yang dipakai menentukan hasil akhirnya, bukan menulis
"Paid" begitu saja - supaya debit note, retur dan pembayaran sebagian tetap
mendarat di status yang memang seharusnya.
"""

from __future__ import annotations

import frappe

# Status yang berarti "masih ada uang terutang". Kalau outstanding sudah <= 0,
# status di daftar ini pasti basi. "Debit Note Issued" dan "Return" sengaja
# tidak diikutkan: keduanya memang wajar punya outstanding 0.
STALE_STATUSES = (
	"Unpaid",
	"Unpaid and Discounted",
	"Overdue",
	"Overdue and Discounted",
	"Partly Paid",
	"Partly Paid and Discounted",
)


def execute():
	stuck = frappe.db.get_all(
		"Purchase Invoice",
		filters={
			"docstatus": 1,
			"is_return": 0,
			"outstanding_amount": ("<=", 0),
			"status": ("in", STALE_STATUSES),
		},
		pluck="name",
	)

	fixed = 0
	for name in stuck:
		# Satu invoice bermasalah tidak boleh menggagalkan seluruh migrate -
		# patch ini berjalan saat deploy ke produksi.
		try:
			invoice = frappe.get_doc("Purchase Invoice", name)
			before = invoice.status
			# update_modified=False: ini perbaikan data, bukan peristiwa bisnis.
			# Membiarkannya True akan mendorong ke-22 invoice lama melompat ke
			# puncak urutan "Last Updated On" seolah-olah baru saja disentuh orang.
			invoice.set_status(update=True, update_modified=False)
			if invoice.status != before:
				fixed += 1
				frappe.logger().info(
					f"[fix_stuck_unpaid_purchase_invoice_status] {name}: {before} -> {invoice.status}"
				)
		except Exception:
			frappe.log_error(
				title="fix_stuck_unpaid_purchase_invoice_status",
				message=f"Purchase Invoice: {name}\n\n{frappe.get_traceback()}",
			)

	# Flag "menunggu rekonsiliasi bank" pada Payment Entry yang banknya nyatanya
	# sudah cleared. Dibiarkan menyala, flag ini membuat sweeper terjadwal
	# memeriksa ulang baris yang sama selamanya.
	if frappe.db.has_column("Payment Entry", "awaiting_bank_reconciliation"):
		frappe.db.sql(
			"""
			update `tabPayment Entry`
			set awaiting_bank_reconciliation = 0
			where docstatus = 1
			  and awaiting_bank_reconciliation = 1
			  and clearance_date is not null
			"""
		)

	frappe.db.commit()

	frappe.logger().info(
		f"[fix_stuck_unpaid_purchase_invoice_status] {fixed} dari {len(stuck)} invoice diperbaiki"
	)
