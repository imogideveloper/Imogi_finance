# ============================================================
# towing_admin.py
# API khusus Administrator untuk operasi maintenance Towing Imogi
# ============================================================

import frappe
from frappe import _

# Urutan hapus: anak dulu (PE), induk terakhir (SO)
PURGE_DELETE_ORDER = [
	"Payment Entry",
	"Sales Invoice",
	"Purchase Invoice",
	"Expense Claim",
	"Driver Commission",
	"Purchase Order",
	"Delivery Order Towing",
	"Sales Order",
]

# Tabel Version/Comment/Log Frappe
HISTORY_TABLES = [
	("tabVersion", "ref_doctype, docname"),
	("tabComment", "reference_doctype, reference_name"),
	("tabCommunication", "reference_doctype, reference_name"),
	("tabActivity Log", "reference_doctype, reference_name"),
]


def _only_administrator():
	if frappe.session.user != "Administrator":
		frappe.throw(
			_("Akses ditolak. Hanya Administrator yang bisa menjalankan ini."),
			frappe.PermissionError,
		)


def _field_exists(doctype: str, fieldname: str) -> bool:
	return bool(frappe.db.get_value("DocField", {"parent": doctype, "fieldname": fieldname}))


def _table_exists(table_name: str) -> bool:
	return frappe.db.table_exists(table_name)


def _collect_towing_transaction_docs(*, full_site: bool = False) -> dict[str, list[str]]:
	"""Kumpulkan dokumen transaksi towing untuk purge.

	full_site=True  → hapus semua SO/SI/PI/PE/PO/DO di site (reset towing).
	full_site=False → hanya dokumen yang terdeteksi terhubung towing.
	"""
	do_names = frappe.db.sql_list("SELECT name FROM `tabDelivery Order Towing`")

	so_names: set[str] = set()
	if full_site:
		so_names.update(frappe.db.sql_list("SELECT name FROM `tabSales Order`"))
	else:
		so_names.update(_collect_linked_sales_orders(do_names))

	si_names: set[str] = set()
	if full_site:
		si_names.update(frappe.db.sql_list("SELECT name FROM `tabSales Invoice`"))
	else:
		si_names.update(_collect_linked_sales_invoices(do_names, so_names))

	po_names: set[str] = set()
	if full_site:
		po_names.update(frappe.db.sql_list("SELECT name FROM `tabPurchase Order`"))
	else:
		po_names.update(_collect_linked_purchase_orders(do_names))

	pi_names: set[str] = set()
	if full_site:
		pi_names.update(frappe.db.sql_list("SELECT name FROM `tabPurchase Invoice`"))
	else:
		pi_names.update(_collect_linked_purchase_invoices(do_names, po_names))

	pe_names: set[str] = set()
	if full_site:
		pe_names.update(frappe.db.sql_list("SELECT name FROM `tabPayment Entry`"))
	else:
		pe_names.update(_collect_linked_payment_entries(si_names, pi_names))

	ec_names: set[str] = set(_collect_linked_expense_claims(do_names))
	dc_names: set[str] = set(_collect_linked_driver_commissions(do_names))

	return {
		"Payment Entry": sorted(pe_names),
		"Sales Invoice": sorted(si_names),
		"Purchase Invoice": sorted(pi_names),
		"Expense Claim": sorted(ec_names),
		"Driver Commission": sorted(dc_names),
		"Purchase Order": sorted(po_names),
		"Delivery Order Towing": sorted(do_names),
		"Sales Order": sorted(so_names),
	}


def _collect_linked_sales_orders(do_names: list[str]) -> set[str]:
	so_names: set[str] = set()
	if do_names:
		so_names.update(
			frappe.db.sql_list(
				"""
				SELECT DISTINCT sales_order
				FROM `tabDelivery Order Towing`
				WHERE IFNULL(sales_order, '') != ''
				"""
			)
		)
	so_names.update(
		frappe.db.sql_list(
			"""
			SELECT DISTINCT soi.parent
			FROM `tabSales Order Item` soi
			WHERE UPPER(IFNULL(soi.item_code, '')) LIKE '%%TOWING%%'
			   OR UPPER(IFNULL(soi.item_code, '')) LIKE '%%RDC%%'
			   OR UPPER(IFNULL(soi.item_code, '')) LIKE '%%POOL%%'
			"""
		)
	)
	if _table_exists("tabSO Towing Kendaraan"):
		so_names.update(
			frappe.db.sql_list("SELECT DISTINCT parent FROM `tabSO Towing Kendaraan`")
		)
	return so_names


def _collect_linked_sales_invoices(do_names: list[str], so_names: set[str]) -> set[str]:
	si_names: set[str] = set()
	if do_names:
		si_names.update(
			frappe.db.sql_list(
				"""
				SELECT DISTINCT sales_invoice
				FROM `tabDelivery Order Towing`
				WHERE IFNULL(sales_invoice, '') != ''
				"""
			)
		)
	if _field_exists("Sales Invoice", "custom_delivery_order"):
		si_names.update(
			frappe.db.sql_list(
				"""
				SELECT name FROM `tabSales Invoice`
				WHERE IFNULL(custom_delivery_order, '') != ''
				"""
			)
		)

	si_names.update(
		frappe.db.sql_list(
			"""
			SELECT DISTINCT parent
			FROM `tabSales Invoice Item`
			WHERE IFNULL(item_name, '') LIKE 'Jasa Towing%%'
			   OR IFNULL(description, '') LIKE '%%DO-TOW%%'
			   OR IFNULL(item_code, '') = 'JASA-TOWING-001'
			"""
		)
	)
	if so_names:
		placeholders = ", ".join(["%s"] * len(so_names))
		si_names.update(
			frappe.db.sql_list(
				f"""
				SELECT DISTINCT parent
				FROM `tabSales Invoice Item`
				WHERE sales_order IN ({placeholders})
				""",
				tuple(so_names),
			)
		)
	return si_names


def _collect_linked_purchase_orders(do_names: list[str]) -> set[str]:
	po_names: set[str] = set()
	if _field_exists("Purchase Order", "custom_delivery_order"):
		po_names.update(
			frappe.db.sql_list(
				"""
				SELECT name FROM `tabPurchase Order`
				WHERE IFNULL(custom_delivery_order, '') != ''
				"""
			)
		)
	if do_names:
		po_names.update(
			frappe.db.sql_list(
				"""
				SELECT DISTINCT purchase_order_uang_jalan
				FROM `tabDelivery Order Towing`
				WHERE IFNULL(purchase_order_uang_jalan, '') != ''
				"""
			)
		)
	return po_names


def _collect_linked_purchase_invoices(do_names: list[str], po_names: set[str]) -> set[str]:
	pi_names: set[str] = set()
	if po_names:
		placeholders = ", ".join(["%s"] * len(po_names))
		pi_names.update(
			frappe.db.sql_list(
				f"""
				SELECT DISTINCT pi.name
				FROM `tabPurchase Invoice` pi
				INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
				WHERE pii.purchase_order IN ({placeholders})
				""",
				tuple(po_names),
			)
		)
	if _field_exists("Purchase Invoice", "custom_delivery_order"):
		pi_names.update(
			frappe.db.sql_list(
				"""
				SELECT name FROM `tabPurchase Invoice`
				WHERE IFNULL(custom_delivery_order, '') != ''
				"""
			)
		)
	return pi_names


def _collect_linked_payment_entries(si_names: set[str], pi_names: set[str]) -> set[str]:
	pe_names: set[str] = set()
	for si_name in si_names:
		pe_names.update(
			frappe.db.sql_list(
				"""
				SELECT DISTINCT parent
				FROM `tabPayment Entry Reference`
				WHERE reference_doctype = 'Sales Invoice' AND reference_name = %s
				""",
				si_name,
			)
		)
	for pi_name in pi_names:
		pe_names.update(
			frappe.db.sql_list(
				"""
				SELECT DISTINCT parent
				FROM `tabPayment Entry Reference`
				WHERE reference_doctype = 'Purchase Invoice' AND reference_name = %s
				""",
				pi_name,
			)
		)
	return pe_names


def _collect_linked_expense_claims(do_names: list[str]) -> set[str]:
	ec_names: set[str] = set(
		frappe.db.sql_list(
			"""
			SELECT DISTINCT expense_claim
			FROM `tabDelivery Order Towing`
			WHERE IFNULL(expense_claim, '') != ''
			"""
		)
	)
	if _field_exists("Expense Claim", "custom_delivery_order"):
		ec_names.update(
			frappe.db.sql_list(
				"""
				SELECT name FROM `tabExpense Claim`
				WHERE IFNULL(custom_delivery_order, '') != ''
				"""
			)
		)
	return ec_names


def _collect_linked_driver_commissions(do_names: list[str]) -> set[str]:
	if not _table_exists("tabDriver Commission Item"):
		return set()
	return set(
		frappe.db.sql_list(
			"""
			SELECT DISTINCT parent
			FROM `tabDriver Commission Item`
			WHERE IFNULL(delivery_order, '') != ''
			"""
		)
	)


def _count_documents(doc_groups: dict[str, list[str]]) -> dict[str, int]:
	return {doctype: len(names) for doctype, names in doc_groups.items()}


def _unlink_towing_references():
	"""Putus semua link antar dokumen towing agar hapus massal tidak terblokir."""
	frappe.db.sql(
		"""
		UPDATE `tabDelivery Order Towing`
		SET sales_invoice = NULL,
			purchase_order_uang_jalan = NULL,
			expense_claim = NULL,
			uang_jalan_status = 'Belum Diajukan',
			uang_jalan_amount = 0
		"""
	)

	if _field_exists("Purchase Order", "custom_delivery_order"):
		frappe.db.sql(
			"UPDATE `tabPurchase Order` SET custom_delivery_order = NULL WHERE IFNULL(custom_delivery_order, '') != ''"
		)
	if _field_exists("Purchase Invoice", "custom_delivery_order"):
		frappe.db.sql(
			"UPDATE `tabPurchase Invoice` SET custom_delivery_order = NULL WHERE IFNULL(custom_delivery_order, '') != ''"
		)
	if _field_exists("Sales Invoice", "custom_delivery_order"):
		frappe.db.sql(
			"UPDATE `tabSales Invoice` SET custom_delivery_order = NULL WHERE IFNULL(custom_delivery_order, '') != ''"
		)
	if _field_exists("Expense Claim", "custom_delivery_order"):
		frappe.db.sql(
			"UPDATE `tabExpense Claim` SET custom_delivery_order = NULL WHERE IFNULL(custom_delivery_order, '') != ''"
		)
	if _table_exists("tabSO Towing Kendaraan"):
		frappe.db.sql(
			"UPDATE `tabSO Towing Kendaraan` SET delivery_order = NULL WHERE IFNULL(delivery_order, '') != ''"
		)
	if _table_exists("tabDriver Commission Item"):
		frappe.db.sql(
			"UPDATE `tabDriver Commission Item` SET delivery_order = NULL WHERE IFNULL(delivery_order, '') != ''"
		)

	frappe.db.commit()


def _force_delete_document(doctype: str, name: str) -> bool:
	if not frappe.db.exists(doctype, name):
		return False

	frappe.flags.in_towing_purge = True
	try:
		doc = frappe.get_doc(doctype, name)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_links = True
		doc.flags.ignore_validate = True
		doc.flags.skip_cancel_check = True
		doc.flags.in_towing_purge = True

		if doc.docstatus == 1:
			try:
				doc.cancel()
			except Exception:
				frappe.db.set_value(doctype, name, "docstatus", 2, update_modified=False)
				frappe.db.commit()

		frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
		frappe.db.commit()
		return True
	except Exception as exc:
		frappe.db.rollback()
		try:
			frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
			frappe.db.commit()
			return True
		except Exception as exc2:
			frappe.log_error(
				f"Purge gagal hapus {doctype} {name}: {exc} | retry: {exc2}",
				"Towing Transaction Purge",
			)
			return False


def _purge_towing_history_for_groups(doc_groups: dict[str, list[str]]) -> dict[str, int]:
	deleted = {}
	for doctype, names in doc_groups.items():
		if not names:
			deleted[doctype] = 0
			continue

		placeholders = ", ".join(["%s"] * len(names))
		args = [doctype] + names
		count = 0

		count += frappe.db.sql(
			f"SELECT COUNT(*) FROM `tabVersion` WHERE ref_doctype = %s AND docname IN ({placeholders})",
			args,
		)[0][0]
		frappe.db.sql(
			f"DELETE FROM `tabVersion` WHERE ref_doctype = %s AND docname IN ({placeholders})",
			args,
		)

		count += frappe.db.sql(
			f"SELECT COUNT(*) FROM `tabComment` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
			args,
		)[0][0]
		frappe.db.sql(
			f"DELETE FROM `tabComment` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
			args,
		)

		count += frappe.db.sql(
			f"SELECT COUNT(*) FROM `tabCommunication` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
			args,
		)[0][0]
		frappe.db.sql(
			f"DELETE FROM `tabCommunication` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
			args,
		)

		count += frappe.db.sql(
			f"SELECT COUNT(*) FROM `tabActivity Log` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
			args,
		)[0][0]
		frappe.db.sql(
			f"DELETE FROM `tabActivity Log` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
			args,
		)

		deleted[doctype] = count

	frappe.db.commit()
	return deleted


# ─────────────────────────────────────────────────────────────
# PREVIEW: Hitung berapa record riwayat yang akan dihapus
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def preview_towing_history():
	"""Hitung riwayat (Version/Comment/Communication/Activity Log) yang akan dihapus."""
	_only_administrator()

	doc_groups = _collect_towing_transaction_docs()
	result = {}
	for doctype, names in doc_groups.items():
		result[doctype] = _count_history(doctype, names)

	total = sum(v.get("total", 0) for v in result.values())
	return {"summary": result, "total": total}


@frappe.whitelist()
def preview_towing_purge_all():
	"""Preview jumlah dokumen transaksi towing yang akan dihapus permanen."""
	_only_administrator()

	doc_groups = _collect_towing_transaction_docs(full_site=True)
	counts = _count_documents(doc_groups)
	total_docs = sum(counts.values())
	history_preview = preview_towing_history()

	return {
		"documents": counts,
		"total_documents": total_docs,
		"history_total": history_preview.get("total", 0),
	}


def _count_history(doctype, names):
	if not names:
		return {"total": 0, "version": 0, "comment": 0, "communication": 0, "activity_log": 0}

	placeholders = ", ".join(["%s"] * len(names))
	counts = {}

	counts["version"] = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabVersion` WHERE ref_doctype = %s AND docname IN ({placeholders})",
		[doctype] + names,
	)[0][0]

	counts["comment"] = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabComment` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
		[doctype] + names,
	)[0][0]

	counts["communication"] = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabCommunication` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
		[doctype] + names,
	)[0][0]

	counts["activity_log"] = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabActivity Log` WHERE reference_doctype = %s AND reference_name IN ({placeholders})",
		[doctype] + names,
	)[0][0]

	counts["total"] = sum(counts.values())
	return counts


# ─────────────────────────────────────────────────────────────
# EKSEKUSI: Hapus riwayat transaksi towing
# ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def purge_towing_history(confirm="no"):
	"""
	Hapus riwayat (Version, Comment, Communication, Activity Log)
	dari semua dokumen yang terhubung ke Towing Imogi.

	TIDAK menghapus dokumen aslinya, hanya riwayat/log-nya.
	"""
	_only_administrator()

	if confirm != "HAPUS":
		frappe.throw(
			_("Konfirmasi tidak valid. Kirim confirm='HAPUS' untuk melanjutkan."),
			frappe.ValidationError,
		)

	doc_groups = _collect_towing_transaction_docs()
	deleted = _purge_towing_history_for_groups(doc_groups)
	total = sum(deleted.values())

	frappe.log_error(
		f"[Towing Admin] Administrator menghapus {total} riwayat transaksi towing.\nDetail: {deleted}",
		"Towing History Purge",
	)

	return {
		"success": True,
		"total_deleted": total,
		"detail": deleted,
		"message": _("Berhasil menghapus {0} record riwayat dari semua dokumen towing.").format(total),
	}


@frappe.whitelist()
def purge_towing_transactions(confirm="no"):
	"""
	Hapus permanen semua dokumen transaksi towing (PE, SI, PI, EC, DC, PO, DO, SO)
	dan riwayat terkait. Hanya Administrator.
	"""
	_only_administrator()

	if confirm != "HAPUS SEMUA":
		frappe.throw(
			_("Konfirmasi tidak valid. Kirim confirm='HAPUS SEMUA' untuk melanjutkan."),
			frappe.ValidationError,
		)

	frappe.flags.in_towing_purge = True
	doc_groups = _collect_towing_transaction_docs(full_site=True)
	deleted_docs: dict[str, int] = {}
	failed: list[str] = []

	_unlink_towing_references()

	for doctype in PURGE_DELETE_ORDER:
		names = doc_groups.get(doctype, [])
		deleted_count = 0
		for name in names:
			if _force_delete_document(doctype, name):
				deleted_count += 1
			else:
				failed.append(f"{doctype}: {name}")
		deleted_docs[doctype] = deleted_count

	# Bersihkan riwayat sisa (jika ada)
	remaining_groups = _collect_towing_transaction_docs(full_site=True)
	deleted_history = _purge_towing_history_for_groups(remaining_groups)

	total_docs = sum(deleted_docs.values())
	total_history = sum(deleted_history.values())

	frappe.log_error(
		f"[Towing Admin] PURGE SEMUA towing oleh Administrator.\n"
		f"Dokumen: {deleted_docs}\nRiwayat: {deleted_history}\nGagal: {failed}",
		"Towing Transaction Purge",
	)

	return {
		"success": not failed,
		"total_documents_deleted": total_docs,
		"documents": deleted_docs,
		"history_deleted": total_history,
		"failed": failed,
		"message": _(
			"Berhasil menghapus {0} dokumen transaksi towing dan {1} record riwayat."
		).format(total_docs, total_history),
	}
