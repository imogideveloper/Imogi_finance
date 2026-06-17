# ============================================================
# delivery_order_towing.py
# Lokasi: imogi_finance/imogi_finance/overrides/delivery_order_towing.py
# ============================================================

import frappe
import json
from frappe.model.document import Document
from frappe.utils import now_datetime, nowdate
from frappe import _


# ──────────────────────────────────────────────────────────────
# KONFIGURASI — DYNAMIC PER SITE
# ──────────────────────────────────────────────────────────────

def _is_remote() -> bool:
    return bool(frappe.conf.get("finance_imogi_url"))


def _get_imogi_base_url() -> str:
    url = frappe.conf.get("finance_imogi_url", "").rstrip("/")
    if not url:
        frappe.throw(_("finance_imogi_url belum dikonfigurasi di site_config."))
    return url


def _get_imogi_headers() -> dict:
    key    = frappe.conf.get("finance_imogi_api_key", "")
    secret = frappe.conf.get("finance_imogi_api_secret", "")
    if not key or not secret:
        frappe.throw(_("finance_imogi_api_key / api_secret belum dikonfigurasi."))
    return {
        "Content-Type" : "application/json",
        "Authorization": f"token {key}:{secret}",
    }


# ──────────────────────────────────────────────────────────────
# LOCAL MODE
# ──────────────────────────────────────────────────────────────

def _local_create(doctype: str, data: dict) -> dict:
    import frappe.model.document as _doc_module
    _original = _doc_module.Document.round_floats_in

    def _patched(self, doc, fieldnames=None, do_not_round_fields=None):
        return _original(self, doc, fieldnames)

    _doc_module.Document.round_floats_in = _patched

    try:
        doc = frappe.new_doc(doctype)
        doc.update(data)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory   = True
        doc.insert(ignore_permissions=True)

        if doctype == "Sales Invoice":
            frappe.db.commit()
            fresh = frappe.get_doc(doctype, doc.name)
            fresh.flags.ignore_permissions = True
            fresh.submit()

        frappe.db.commit()
        return {"name": doc.name}
    finally:
        _doc_module.Document.round_floats_in = _original


def _local_get(doctype: str, name: str) -> dict:
    return frappe.get_doc(doctype, name).as_dict()


def _local_update(doctype: str, name: str, data: dict) -> dict:
    frappe.db.set_value(doctype, name, data)
    frappe.db.commit()
    return {"name": name}


# ──────────────────────────────────────────────────────────────
# REMOTE MODE
# ──────────────────────────────────────────────────────────────

def _remote_create(doctype: str, data: dict) -> dict:
    import requests
    url  = f"{_get_imogi_base_url()}/api/resource/{doctype}"
    resp = requests.post(url, headers=_get_imogi_headers(), json=data, timeout=30)
    _raise_for_status(resp, f"CREATE {doctype}")
    return resp.json().get("data", {})


def _remote_get(doctype: str, name: str) -> dict:
    import requests
    url  = f"{_get_imogi_base_url()}/api/resource/{doctype}/{name}"
    resp = requests.get(url, headers=_get_imogi_headers(), timeout=15)
    _raise_for_status(resp, f"GET {doctype}/{name}")
    return resp.json().get("data", {})


def _remote_update(doctype: str, name: str, data: dict) -> dict:
    import requests
    url  = f"{_get_imogi_base_url()}/api/resource/{doctype}/{name}"
    resp = requests.put(url, headers=_get_imogi_headers(), json=data, timeout=15)
    _raise_for_status(resp, f"UPDATE {doctype}/{name}")
    return resp.json().get("data", {})


def _raise_for_status(resp, context: str):
    if resp.status_code == 200:
        return
    try:
        msg = resp.json().get("exception") or resp.json().get("message") or resp.text
    except Exception:
        msg = resp.text
    frappe.log_error(
        f"Finance Imogi REST error [{context}]\nStatus: {resp.status_code}\n{resp.text[:1000]}",
        "DO Towing → Finance Imogi Error"
    )
    if resp.status_code == 401:
        frappe.throw(_("Finance Imogi: API Key/Secret salah."))
    elif resp.status_code == 403:
        frappe.throw(_("Finance Imogi: Tidak punya permission untuk {0}.").format(context))
    elif resp.status_code == 404:
        frappe.throw(_("Finance Imogi: Data tidak ditemukan — {0}.").format(context))
    else:
        frappe.throw(_("Finance Imogi error ({0}): {1}").format(resp.status_code, msg))


# ──────────────────────────────────────────────────────────────
# PUBLIC INTERFACE — auto local/remote
# ──────────────────────────────────────────────────────────────

def imogi_create(doctype: str, data: dict) -> dict:
    return _remote_create(doctype, data) if _is_remote() else _local_create(doctype, data)

def imogi_get(doctype: str, name: str) -> dict:
    return _remote_get(doctype, name) if _is_remote() else _local_get(doctype, name)

def imogi_update(doctype: str, name: str, data: dict) -> dict:
    return _remote_update(doctype, name, data) if _is_remote() else _local_update(doctype, name, data)

def _resolve_company() -> str:
    """Resolve company for server-side created docs with robust fallbacks."""
    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or frappe.db.get_value("Company", {"is_group": 0}, "name")
    )
    if not company:
        frappe.throw(
            _("Company belum dikonfigurasi. Set Global Defaults > Default Company atau buat Company aktif.")
        )
    return company


# ──────────────────────────────────────────────────────────────
# DOCTYPE CLASS
# ──────────────────────────────────────────────────────────────

class DeliveryOrderTowing(Document):

    # ── VALIDATE ─────────────────────────────────────────────
    def validate(self):
        self.normalize_status()
        self.validate_driver_required_on_assign()
        self.validate_invoice_fields_on_awaiting_document()
        self.validate_harga_jasa()
        self.set_customer_name()

    def normalize_status(self):
        """Status legacy 'Submitted' tidak dipakai — samakan ke Assigned."""
        if self.status == "Submitted":
            self.status = "Assigned"
        if self.docstatus == 1 and self.status == "Draft":
            self.status = "Assigned"

    def validate_driver_required_on_assign(self):
        if self.status == "Assigned" and not self.driver:
            frappe.throw(_("Driver wajib diisi sebelum status Assigned."))

    def validate_invoice_fields_on_awaiting_document(self):
        if self.status == "Awaiting Dokument" and not self.tanggal_invoice:
            frappe.throw(_("Tanggal Invoice wajib diisi saat status Awaiting Dokument."))

    def validate_harga_jasa(self):
        if self.harga_jasa is not None and self.harga_jasa <= 0:
            frappe.throw(_("Harga Jasa Towing harus lebih dari 0."))

    def set_customer_name(self):
        if self.customer and not self.customer_name:
            self.customer_name = frappe.db.get_value(
                "Customer", self.customer, "customer_name"
            )

    # ── AFTER SAVE ───────────────────────────────────────────
    def after_save(self):
        self._record_status_timestamps()

    def _record_status_timestamps(self):
        now    = now_datetime()
        update = {}
        if self.status == "Assigned"  and not self.waktu_assigned:  update["waktu_assigned"]  = now
        if self.status == "Pick Up"   and not self.waktu_pickup:    update["waktu_pickup"]    = now
        if self.status == "Delivered" and not self.waktu_delivered: update["waktu_delivered"] = now
        if self.status == "Done"      and not self.waktu_done:      update["waktu_done"]      = now
        if update:
            frappe.db.set_value(
                "Delivery Order Towing", self.name, update, update_modified=False
            )

    # ── ON UPDATE AFTER SUBMIT ───────────────────────────────
    def on_update_after_submit(self):
        pass
        # if self.status == "Done" and not self.sales_invoice:
        #     self.create_sales_invoice_via_imogi()

    # ──────────────────────────────────────────────────────────
    # INTEGRASI 1: AUTO-CREATE PURCHASE ORDER UANG JALAN
    # Dipanggil saat DO di-submit (status: Draft → Submitted)
    # ──────────────────────────────────────────────────────────

    def create_po_uang_jalan(self):
        """
        Auto-create Purchase Order uang jalan saat DO di-submit.
        Detail kendaraan diambil dari DO itu sendiri (bukan seluruh SO).
        """
        if self.get("purchase_order_uang_jalan"):
            return

        if not self.driver:
            frappe.throw(
                _("Driver wajib diisi sebelum DO bisa di-submit."),
                title="Driver Belum Diisi"
            )

        supplier = frappe.db.get_value("Driver", self.driver, "custom_supplier")
        if not supplier:
            frappe.throw(
                _("Driver {0} belum punya Supplier (Uang Jalan). "
                "Buka master Driver → isi field <b>Supplier (Uang Jalan)</b> terlebih dahulu.").format(
                    self.driver_nama or self.driver
                ),
                title="Driver Belum Punya Supplier"
            )

        company = _resolve_company()

        # ✅ item_code diambil dari SO Towing Kendaraan yang linked ke DO ini
        item_code = frappe.db.get_value(
            "SO Towing Kendaraan",
            {"delivery_order": self.name},
            "so_item_code"
        ) or "JASA-TOWING-001"

        po_data = {
            "naming_series"        : "PUR-ORD-.YYYY.-",
            "supplier"             : supplier,
            "company"              : company,
            "transaction_date"     : nowdate(),
            "schedule_date"        : nowdate(),
            "custom_delivery_order": self.name,
            "custom_nomor_rangka"  : self.nomor_rangka or "-",
            "currency"             : self.currency or "IDR",
            "buying_price_list"    : "Standard Buying",
            "remarks": (
                f"Uang Jalan DO Towing: {self.name} | "
                f"Nopol: {self.nomor_polisi} | "
                f"No. Rangka: {self.nomor_rangka or '-'}"
            ),
            "items": [
                {
                    "item_code"    : item_code,
                    "item_name"    : f"Uang Jalan - {self.nomor_polisi}",
                    "description"  : (
                        f"Uang jalan towing {self.nomor_polisi} | "
                        f"No. Rangka: {self.nomor_rangka or '-'} | "
                        f"Rute: {self.lokasi_pickup or '-'} → {self.lokasi_tujuan or '-'}"
                    ),
                    "qty"          : 1,
                    "rate"         : 0,
                    "uom"          : "Nos",
                    "schedule_date": nowdate(),
                }
            ],
        }

        result  = imogi_create("Purchase Order", po_data)
        po_name = result.get("name")

        if not po_name:
            frappe.log_error(
                f"PO response tidak ada 'name': {result}",
                "DO Towing: PO uang jalan gagal"
            )
            frappe.throw(_("Purchase Order gagal dibuat. Cek Error Log."))

        frappe.db.set_value(
            "Delivery Order Towing", self.name,
            "purchase_order_uang_jalan", po_name
        )
        frappe.db.commit()

        frappe.msgprint(
            _("✅ Purchase Order {0} berhasil dibuat untuk uang jalan.").format(
                frappe.bold(po_name)
            ),
            title="Purchase Order Dibuat",
            indicator="green"
        )
        return po_name


    def _get_towing_rows(do_name: str) -> list:
        """
        ✅ Ambil data kendaraan dari DO itu sendiri — hanya 1 kendaraan
        yang di-assigned ke DO ini. BUKAN dari Sales Order.
        """
        try:
            do = frappe.get_doc("Delivery Order Towing", do_name)
            item_code = frappe.db.get_value(
                "SO Towing Kendaraan",
                {"delivery_order": do_name},
                "so_item_code"
            )
            return [{
                "so_item_code": item_code or "",
                "nomor_rangka": do.nomor_rangka or "",
                "nomor_polisi": do.nomor_polisi or "",
                "tipe_model"  : do.tipe_kendaraan or "",
                "nomor_mesin" : do.nomor_mesin or "",
            }]
        except Exception as exc:
            frappe.log_error(
                f"[Towing] Gagal ambil data dari DO {do_name}: {exc}",
                "Auto Populate Towing",
            )
            return []

    # ──────────────────────────────────────────────────────────
    # INTEGRASI 2: BUAT SALES INVOICE
    # ──────────────────────────────────────────────────────────

    def create_sales_invoice_via_imogi(self):
        if self.sales_invoice:
            return self.sales_invoice

        if not self.customer or not self.harga_jasa:
            frappe.throw(_("Customer dan Harga Jasa wajib diisi sebelum buat invoice."))

        company = _resolve_company()

        invoice_data = {
            "naming_series"    : "ACC-SINV-.YYYY.-",
            "customer"         : self.customer,
            "company"          : company,
            "posting_date"     : nowdate(),
            "due_date"         : nowdate(),
            "currency"         : self.currency or "IDR",
            "conversion_rate"  : 1,
            "selling_price_list": "Standard Selling",
            "po_no"  : self.name,
            "remarks": (
                f"DO Towing: {self.name} | "
                f"Nopol: {self.nomor_polisi} | "
                f"Rute: {self.lokasi_pickup or '-'} → {self.lokasi_tujuan or '-'}"
            ),
            "items": [
                {
                    "item_code"  : "JASA-TOWING-001",
                    "item_name"  : f"Jasa Towing - {self.nomor_polisi}",
                    "description": (
                        f"Jasa towing {self.merk_kendaraan or ''} "
                        f"{self.tipe_kendaraan or ''} ({self.nomor_polisi}) "
                        f"dari {self.lokasi_pickup or '-'} ke {self.lokasi_tujuan or '-'}"
                    ),
                    "qty" : 1,
                    "rate": self.harga_jasa,
                    "uom" : "Nos",
                }
            ],
        }

        result       = imogi_create("Sales Invoice", invoice_data)
        invoice_name = result.get("name")

        if not invoice_name:
            frappe.log_error(
                f"Response tidak ada 'name':\n{json.dumps(result, default=str, indent=2)}",
                "DO Towing: Invoice name tidak ditemukan"
            )
            frappe.throw(_("Invoice dibuat tapi nama tidak terbaca. Cek Error Log."))

        frappe.db.set_value("Delivery Order Towing", self.name, "sales_invoice", invoice_name)
        frappe.db.commit()

        frappe.msgprint(
            _("✅ Sales Invoice {0} berhasil dibuat.").format(frappe.bold(invoice_name)),
            title="Invoice Dibuat",
            indicator="green",
        )
        return invoice_name

    # ──────────────────────────────────────────────────────────
    # INTEGRASI 3: BUAT EXPENSE CLAIM
    # ──────────────────────────────────────────────────────────

    def create_expense_claim_via_imogi(self, employee: str, amount: float):
        if self.expense_claim:
            frappe.throw(_("Expense Claim sudah ada: {0}").format(self.expense_claim))

        company = _resolve_company()

        ec_data = {
            "naming_series": "HR-EXP-.YYYY.-",
            "employee"     : employee,
            "company"      : company,
            "posting_date" : nowdate(),
            "remark"       : f"Uang jalan DO Towing: {self.name} | Nopol: {self.nomor_polisi}",
            "expenses": [
                {
                    "expense_date"     : nowdate(),
                    "expense_type"     : "Uang Jalan Towing",
                    "description"      : f"Uang jalan DO {self.name} — {self.nomor_polisi}",
                    "amount"           : amount,
                    "sanctioned_amount": amount,
                }
            ],
        }

        result  = imogi_create("Expense Claim", ec_data)
        ec_name = result.get("name")

        if not ec_name:
            frappe.log_error(
                f"EC response:\n{json.dumps(result, default=str, indent=2)}",
                "DO Towing: EC name tidak ditemukan"
            )
            frappe.throw(_("Expense Claim gagal dibuat. Cek Error Log."))

        frappe.db.set_value(
            "Delivery Order Towing", self.name, {
                "expense_claim"    : ec_name,
                "uang_jalan_amount": amount,
                "uang_jalan_status": "Diajukan",
            }
        )
        frappe.db.commit()

        frappe.msgprint(
            _("✅ Expense Claim {0} berhasil dibuat.").format(frappe.bold(ec_name)),
            title="Uang Jalan Dibuat",
            indicator="green",
        )
        return ec_name

    # ──────────────────────────────────────────────────────────
    # INTEGRASI 4: SYNC REMARKS
    # ──────────────────────────────────────────────────────────

    def sync_remarks_to_imogi(self):
        if not self.sales_invoice:
            return
        try:
            imogi_update("Sales Invoice", self.sales_invoice, {
                "remarks": (
                    f"DO Towing: {self.name} | Status: {self.status} | "
                    f"Nopol: {self.nomor_polisi} | Driver: {self.driver_nama or '-'}"
                )
            })
        except Exception:
            frappe.log_error(
                f"Gagal sync remarks DO {self.name} → {self.sales_invoice}",
                "DO Towing Sync Warning"
            )


# ──────────────────────────────────────────────────────────────
# HOOK FUNCTIONS — dipanggil dari hooks.py doc_events
# ──────────────────────────────────────────────────────────────

def after_save(doc, method=None):
    instance = DeliveryOrderTowing(doc.doctype, doc.name)
    instance.after_save()

def on_update_after_submit(doc, method=None):
    instance = DeliveryOrderTowing(doc.doctype, doc.name)
    instance.on_update_after_submit()

def before_submit(doc, method=None):
	"""Simpan status workflow sebelum Frappe reset ke state docstatus=1 pertama."""
	if doc.doctype != "Delivery Order Towing":
		return

	preserve = doc.status
	if preserve in (None, "", "Submitted"):
		preserve = "Assigned"
	if preserve and preserve != "Draft":
		doc.flags.towing_preserve_status = preserve


def validate_towing_workflow_status(doc, method=None):
	"""Pastikan status tidak pernah tertinggal sebagai 'Submitted'."""
	if doc.doctype != "Delivery Order Towing":
		return

	if doc.status == "Submitted":
		doc.status = "Assigned"

	if doc.docstatus == 1 and doc.status == "Draft":
		doc.status = "Assigned"


def restore_towing_status_after_submit(doc, method=None):
	"""Kembalikan status yang sudah di-set apply_workflow sebelum doc.submit()."""
	if doc.doctype != "Delivery Order Towing":
		return

	preserve = getattr(doc.flags, "towing_preserve_status", None)
	if not preserve and doc.status == "Submitted":
		preserve = "Assigned"

	if preserve and doc.status != preserve:
		frappe.db.set_value(
			"Delivery Order Towing",
			doc.name,
			"status",
			preserve,
			update_modified=False,
		)
		doc.status = preserve


def on_submit(doc, method=None):
	"""Hook: submit DO Towing + buat PO uang jalan."""
	restore_towing_status_after_submit(doc, method)
	instance = DeliveryOrderTowing(doc.doctype, doc.name)
	instance.create_po_uang_jalan()
	populate_towing_to_linked_docs(doc)


# ──────────────────────────────────────────────────────────────
# POPULATE DETAIL KENDARAAN TOWING → PO / PI / PE
# ──────────────────────────────────────────────────────────────

def _get_towing_rows(sales_order: str) -> list:
    """Ambil baris SO Towing Kendaraan dari Sales Order."""
    try:
        return frappe.db.sql(
            """
            SELECT so_item_code, nomor_rangka, nomor_polisi, tipe_model, nomor_mesin
            FROM `tabSO Towing Kendaraan`
            WHERE parent = %s AND parenttype = 'Sales Order'
            ORDER BY idx ASC
            """,
            sales_order,
            as_dict=True,
        )
    except Exception as exc:
        frappe.log_error(
            f"[Towing] Gagal ambil baris dari SO {sales_order}: {exc}",
            "Auto Populate Towing",
        )
        return []


def _populate_towing_table(doctype: str, docname: str, towing_rows: list) -> bool:
    """
    Isi custom_towing_kendaraan langsung via SQL — menghindari TimestampMismatchError.
    """
    try:
        docstatus = frappe.db.get_value(doctype, docname, "docstatus")
        if docstatus == 1:
            return False

        # ✅ Cari nama child doctype yang benar dari Custom Field atau DocField
        child_doctype = (
            frappe.db.get_value(
                "Custom Field",
                {"dt": doctype, "fieldname": "custom_towing_kendaraan"},
                "options"
            )
            or frappe.db.get_value(
                "DocField",
                {"parent": doctype, "fieldname": "custom_towing_kendaraan"},
                "options"
            )
        )

        if not child_doctype:
            frappe.log_error(
                f"[Towing] custom_towing_kendaraan tidak ditemukan di {doctype}",
                "Auto Populate Towing"
            )
            return False

        # ✅ Hapus existing rows via SQL langsung ke nama table child yang benar
        frappe.db.sql(
            "DELETE FROM `tab{0}` WHERE parent=%s AND parenttype=%s".format(child_doctype),
            (docname, doctype)
        )

        # ✅ Insert 1 baris via SQL — tidak melalui .save() sama sekali
        from frappe.utils import now_datetime
        now  = now_datetime()
        user = frappe.session.user or "Administrator"

        for idx, row in enumerate(towing_rows, start=1):
            frappe.db.sql(
                """INSERT INTO `tab{0}`
                   (name, parent, parenttype, parentfield, idx,
                    so_item_code, nomor_rangka, nomor_polisi, tipe_model, nomor_mesin,
                    owner, modified_by, creation, modified, docstatus)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """.format(child_doctype),
                (
                    frappe.generate_hash(length=10),
                    docname, doctype, "custom_towing_kendaraan", idx,
                    row.get("so_item_code") or "",
                    row.get("nomor_rangka") or "",
                    row.get("nomor_polisi") or "",
                    row.get("tipe_model")   or "",
                    row.get("nomor_mesin")  or "",
                    user, user, now, now, 0,
                )
            )

        frappe.db.commit()
        return True

    except Exception as exc:
        frappe.log_error(
            f"[Towing] Gagal populate {doctype} {docname}: {exc}",
            "Auto Populate Towing",
        )
        return False


def _field_exists(doctype: str, fieldname: str) -> bool:
    """Cek apakah custom field sudah ada di database sebelum dipakai sebagai filter."""
    return frappe.db.has_column(doctype, fieldname)


def _safe_get_linked_docs(doctype: str, do_field: str, do_name: str) -> list:
    """
    Query dokumen yang linked ke DO ini, dengan pengecekan field terlebih dahulu.
    Menghindari crash jika custom field belum di-migrate.
    """
    if not _field_exists(doctype, do_field):
        frappe.logger().warning(
            f"[Towing] Field '{do_field}' belum ada di {doctype}. "
            f"Jalankan bench migrate terlebih dahulu."
        )
        return []
    return frappe.db.get_all(
        doctype,
        filters={do_field: do_name, "docstatus": 0},
        fields=["name"],
    )


def populate_towing_to_linked_docs(doc, method=None):
    """
    Setelah DO di-submit, otomatis isi Detail Kendaraan Towing
    ke PO, PI, PE yang terhubung — data diambil dari DO itu sendiri.
    """
    # ✅ Tidak lagi butuh sales_order, langsung dari DO
    towing_rows = _get_towing_rows(doc.name)
    if not towing_rows:
        return

    for po in _safe_get_linked_docs("Purchase Order", "custom_delivery_order", doc.name):
        _populate_towing_table("Purchase Order", po.name, towing_rows)

    for pi in _safe_get_linked_docs("Purchase Invoice", "custom_delivery_order", doc.name):
        _populate_towing_table("Purchase Invoice", pi.name, towing_rows)

    for pe in _safe_get_linked_docs("Payment Entry", "delivery_order_towing", doc.name):
        _populate_towing_table("Payment Entry", pe.name, towing_rows)

    # Silent - tidak perlu notifikasi terpisah, cukup notif PO uang jalan


# ──────────────────────────────────────────────────────────────
# AUTO-GENERATE DO DARI SALES ORDER
# ──────────────────────────────────────────────────────────────

def create_do_from_sales_order(doc, method=None):
    """
    Dipanggil dari hooks.py saat Sales Order di-submit.
    Kendaraan diambil dari custom_towing_kendaraan di SO.
    Field so_item_code menentukan rute/harga dari item SO mana.
    """
    kendaraan_list = doc.get("custom_towing_kendaraan", [])
    if not kendaraan_list:
        frappe.msgprint(
            "⚠️ Tidak ada kendaraan di tabel Detail Kendaraan Towing. DO tidak dibuat.",
            indicator="orange"
        )
        return

    created_dos = []
    errors      = []

    for kendaraan in kendaraan_list:
        if kendaraan.get("delivery_order"):
            continue

        try:
            item_code     = kendaraan.get("so_item_code")
            harga_jasa    = 0
            lokasi_pickup = ""
            lokasi_tujuan = ""

            if item_code:
                for so_item in doc.items:
                    if so_item.item_code == item_code:
                        harga_jasa = so_item.rate or 0
                        break
                item_doc = frappe.get_cached_doc("Item", item_code)

                # Prioritas 1: custom field lokasi di Item
                lokasi_pickup = getattr(item_doc, "custom_lokasi_pickup", "") or ""
                lokasi_tujuan = getattr(item_doc, "custom_lokasi_tujuan", "") or ""

                # Prioritas 2: parse dari item_name jika format "Pickup - Tujuan"
                if not lokasi_pickup and not lokasi_tujuan:
                    item_name = item_doc.item_name or item_code
                    if " - " in item_name:
                        parts = item_name.split(" - ", 1)
                        lokasi_pickup = parts[0].strip()
                        lokasi_tujuan = parts[1].strip()

            do = frappe.new_doc("Delivery Order Towing")
            do.sales_order     = doc.name
            do.customer        = doc.customer
            do.customer_name   = doc.customer_name
            do.tanggal_do      = doc.transaction_date
            do.status          = "Draft"
            do.currency        = doc.currency or "IDR"
            do.harga_jasa      = harga_jasa
            do.lokasi_pickup   = lokasi_pickup or ""
            do.lokasi_tujuan   = lokasi_tujuan or ""
            # Jika nomor_polisi kosong, fallback ke nomor_rangka
            # (karena nomor_polisi adalah title_field di DO, harus terisi)
            _nomor_polisi = (kendaraan.get("nomor_polisi") or "").strip()
            _nomor_rangka = (kendaraan.get("nomor_rangka") or "-").strip()
            do.nomor_polisi    = _nomor_polisi if _nomor_polisi else _nomor_rangka
            do.nomor_rangka    = _nomor_rangka
            do.tahun_kendaraan = kendaraan.get("tahun_kendaraan") or 0
            do.tipe_kendaraan  = kendaraan.get("tipe_model") or "-"
            do.nomor_mesin     = kendaraan.get("nomor_mesin") or "-"
            do.merk_kendaraan  = "-"

            do.insert(ignore_permissions=True)

            frappe.db.set_value(
                "SO Towing Kendaraan",
                kendaraan.get("name"),
                "delivery_order",
                do.name
            )

            created_dos.append(do.name)

        except Exception as e:
            errors.append(f"Nopol {kendaraan.get('nomor_polisi', '?')}: {str(e)}")
            frappe.log_error(
                f"Gagal buat DO {kendaraan.get('nomor_polisi')} dari SO {doc.name}: {e}",
                "DO Towing Auto-Create Error"
            )

    frappe.db.commit()

    if created_dos:
        frappe.msgprint(
            _("✅ {0} Delivery Order Towing berhasil dibuat:<br>{1}").format(
                len(created_dos),
                "<br>".join(f"• {do}" for do in created_dos)
            ),
            title="DO Towing Dibuat",
            indicator="green"
        )

    if errors:
        frappe.msgprint(
            _("⚠️ {0} DO gagal:<br>{1}").format(
                len(errors), "<br>".join(errors)
            ),
            title="Sebagian DO Gagal",
            indicator="orange"
        )

def update_do_from_po(doc, method=None):
    """
    Update nominal uang jalan & status di DO berdasarkan state PO Approval.

    Mapping workflow state PO → uang_jalan_status DO:
      Draft            → Belum Diajukan
      Pending Approval → Diajukan
      Approved         → Approved
      Rejected         → Belum Diajukan  (bisa diajukan ulang)
      Cancelled        → Belum Diajukan  (PO cancelled, bisa ajukan ulang)
    """
    do_name = doc.get("custom_delivery_order")
    if not do_name:
        return

    # ✅ FIX Issue #3: kalau PO sudah di-cancel (docstatus=2),
    # paksa status DO jadi "Belum Diajukan" terlepas dari workflow_state
    if doc.docstatus == 2:
        frappe.db.sql("""
            UPDATE `tabDelivery Order Towing`
            SET purchase_order_uang_jalan = NULL,
                uang_jalan_status = 'Belum Diajukan',
                uang_jalan_amount = 0
            WHERE name = %s
        """, (do_name,))
        frappe.db.commit()
        return

    # Map workflow_state PO ke uang_jalan_status DO
    state_map = {
        "Draft":            "Belum Diajukan",
        "Pending Approval": "Diajukan",
        "Approved":         "Approved",
        "Rejected":         "Belum Diajukan",
        "Cancelled":        "Belum Diajukan",
    }

    po_state = doc.get("workflow_state") or doc.get("status") or "Draft"
    uang_jalan_status = state_map.get(po_state, "Diajukan")

    # Ambil total amount dari items PO
    total = sum(item.amount for item in doc.items) if doc.items else 0

    updates = {"uang_jalan_status": uang_jalan_status}
    if total > 0:
        updates["uang_jalan_amount"] = total

    frappe.db.set_value("Delivery Order Towing", do_name, updates)
    frappe.db.commit()

def validate_invoice_do_completion(doc, method=None):
	"""
	Block Sales Invoice jika DO towing terkait belum siap ditagih.
	Untuk invoice towing: hanya validasi DO yang ada di baris item.
	"""
	from imogi_finance.overrides.sales_invoice_towing import (
		extract_delivery_orders_from_doc,
		is_billable_do_status,
		_items_already_towing_expanded,
	)

	if _items_already_towing_expanded(doc):
		for do_name in extract_delivery_orders_from_doc(doc):
			do = frappe.db.get_value(
				"Delivery Order Towing",
				do_name,
				["name", "status", "sales_invoice", "nomor_polisi"],
				as_dict=True,
			)
			if not do:
				frappe.throw(_("Delivery Order Towing {0} tidak ditemukan.").format(do_name))
			if not is_billable_do_status(do.status):
				frappe.throw(
					_("DO Towing {0} ({1}) belum siap ditagih — status: <b>{2}</b>").format(
						do.name, do.nomor_polisi, do.status
					),
					title=_("DO Towing Belum Siap"),
				)
			if do.sales_invoice and do.sales_invoice != doc.name:
				frappe.throw(
					_("DO Towing {0} sudah ditagih di {1}.").format(do.name, do.sales_invoice),
					title=_("DO Sudah Ditagih"),
				)
		return

	so_list = list(
		set(item.sales_order for item in doc.items if item.get("sales_order"))
	)

	if not so_list:
		return

	for so_name in so_list:
		dos = frappe.get_all(
			"Delivery Order Towing",
			filters={
				"sales_order": so_name,
				"docstatus": ["!=", 2],
			},
			fields=["name", "status", "nomor_polisi"],
		)

		if not dos:
			continue

		belum_siap = [d for d in dos if not is_billable_do_status(d.status)]

		if belum_siap:
			detail = "<br>".join(
				f"• {d.name} ({d.nomor_polisi}) — status: <b>{d.status}</b>"
				for d in belum_siap
			)
			frappe.throw(
				_("Sales Invoice tidak bisa dibuat dari SO <b>{0}</b> "
				  "karena ada DO Towing yang belum siap ditagih:<br><br>{1}").format(
					so_name, detail
				),
				title=_("DO Towing Belum Siap"),
			)


def update_do_payment_status(doc, method=None):
    """Update status uang jalan di DO saat Payment Entry di-submit."""
    # Cari PO dari payment entry
    for ref in doc.get("references", []):
        if ref.reference_doctype != "Purchase Order":
            continue
        
        po_name = ref.reference_name
        do_name = frappe.db.get_value(
            "Purchase Order", po_name, "custom_delivery_order"
        )
        
        if not do_name:
            continue
        
        frappe.db.set_value("Delivery Order Towing", do_name, {
            "uang_jalan_status": "Dibayar",
            "uang_jalan_amount": ref.allocated_amount or doc.paid_amount,
        })
        frappe.db.commit()

# ──────────────────────────────────────────────────────────────
# WHITELISTED API ENDPOINTS
# ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def trigger_create_invoice(do_name: str):
    doc = frappe.get_doc("Delivery Order Towing", do_name)
    if doc.status != "Done":
        frappe.throw(_("Invoice hanya bisa dibuat saat status = Done."))
    if doc.sales_invoice:
        return {"status": "already_exists", "invoice": doc.sales_invoice}
    invoice_name = doc.create_sales_invoice_via_imogi()
    return {"status": "created", "invoice": invoice_name}


@frappe.whitelist()
def trigger_create_expense_claim(do_name: str, employee: str, amount: float):
    amount = float(amount)
    if amount <= 0:
        frappe.throw(_("Nominal uang jalan harus lebih dari 0."))
    doc = frappe.get_doc("Delivery Order Towing", do_name)
    if doc.expense_claim:
        return {"status": "already_exists", "expense_claim": doc.expense_claim}
    ec_name = doc.create_expense_claim_via_imogi(employee, amount)
    return {"status": "created", "expense_claim": ec_name}


@frappe.whitelist()
def get_invoice_status_from_imogi(invoice_name: str):
    data = imogi_get("Sales Invoice", invoice_name)
    return {
        "name"              : data.get("name"),
        "status"            : data.get("status"),
        "grand_total"       : data.get("grand_total"),
        "outstanding_amount": data.get("outstanding_amount"),
        "docstatus"         : data.get("docstatus"),
    }


@frappe.whitelist()
def update_driver_status(do_name: str, new_status: str, catatan_driver: str = None):
    allowed        = {"Assigned": "Pick Up", "Pick Up": "Delivered"}
    doc            = frappe.get_doc("Delivery Order Towing", do_name)
    is_koordinator = frappe.has_role("Towing Koordinator")
    driver_user    = frappe.db.get_value("Driver", doc.driver, "user") if doc.driver else None

    if not is_koordinator and driver_user != frappe.session.user:
        frappe.throw(_("Anda tidak berhak mengubah DO ini."), frappe.PermissionError)
    if doc.status not in allowed:
        frappe.throw(_("Status {0} tidak bisa diubah dari portal ini.").format(doc.status))
    if new_status != allowed[doc.status]:
        frappe.throw(_("Status hanya bisa diubah ke: {0}").format(allowed[doc.status]))

    doc.status = new_status
    if catatan_driver:
        doc.catatan_driver = catatan_driver

    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"success": True, "status": doc.status, "do_name": doc.name}

@frappe.whitelist()
def get_towing_kendaraan_from_pi(pi_name: str) -> list:
    """
    Ambil detail kendaraan dari Purchase Invoice.
    Dipakai oleh Payment Entry JS untuk copy data dari PI.
    """
    child_doctype = (
        frappe.db.get_value(
            "Custom Field",
            {"dt": "Purchase Invoice", "fieldname": "custom_towing_kendaraan"},
            "options"
        )
        or frappe.db.get_value(
            "DocField",
            {"parent": "Purchase Invoice", "fieldname": "custom_towing_kendaraan"},
            "options"
        )
    )
    if not child_doctype:
        return []

    return frappe.db.sql(
        f"""SELECT so_item_code, nomor_rangka, nomor_polisi, tipe_model, nomor_mesin
            FROM `tab{child_doctype}`
            WHERE parent=%s AND parenttype='Purchase Invoice'
            ORDER BY idx ASC""",
        pi_name,
        as_dict=True,
    )


@frappe.whitelist()
def get_towing_kendaraan_from_do(do_name: str) -> dict:
    """
    Ambil detail kendaraan dari Delivery Order Towing langsung.
    Dipakai sebagai fallback oleh Payment Entry / PI JS.
    """
    do = frappe.get_doc("Delivery Order Towing", do_name)
    item_code = frappe.db.get_value(
        "SO Towing Kendaraan",
        {"delivery_order": do_name},
        "so_item_code"
    )
    return {
        "so_item_code": item_code or "",
        "nomor_rangka": do.nomor_rangka or "",
        "nomor_polisi": do.nomor_polisi or "",
        "tipe_model"  : do.tipe_kendaraan or "",
        "nomor_mesin" : do.nomor_mesin or "",
    }

# ══════════════════════════════════════════════════════════════════════════
# CANCEL CASCADE: Sales Order ↔ DO Towing ↔ PO Uang Jalan ↔ PI ↔ PE
# ══════════════════════════════════════════════════════════════════════════
#
# Hooks (registered di hooks.py):
#   1. before_cancel SO → cancel_do_from_sales_order()  [defensive layer]
#   2. before_cancel DO → before_cancel_do_towing()
#   3. before_cancel PO → before_cancel_po_uang_jalan() [defensive layer]
#
# Whitelist API (untuk tombol custom JS — skip dialog Frappe):
#   • cancel_so_with_cleanup(so_name)             → tombol "Cancel SO Towing"
#   • cancel_po_uang_jalan_with_cleanup(po_name)  → tombol "Cancel PO Uang Jalan"
#
# Pattern Cancel:
#   Setiap level cuma cascade child Draft langsung di bawah, semua selain itu BLOCK
# ══════════════════════════════════════════════════════════════════════════


# ──────────────────────────────────────────────────────────────────────────
# HOOK 1: SALES ORDER → before_cancel (defensive layer)
# ──────────────────────────────────────────────────────────────────────────

def cancel_do_from_sales_order(doc, method=None):
    """Hook: before_cancel pada Sales Order. Cascade cancel DO Towing ter-link."""
    if doc.flags.get("skip_cancel_check"):
        return

    kendaraan_list = doc.get("custom_towing_kendaraan", [])
    if not kendaraan_list:
        return

    do_names = []
    seen = set()
    for kendaraan in kendaraan_list:
        do_name = kendaraan.get("delivery_order")
        if do_name and do_name not in seen:
            seen.add(do_name)
            do_names.append(do_name)

    if not do_names:
        return

    blocked = []
    cancellable = []

    for do_name in do_names:
        if not frappe.db.exists("Delivery Order Towing", do_name):
            continue

        do_status = frappe.db.get_value("Delivery Order Towing", do_name, "docstatus")
        if do_status == 2:
            continue

        active_links = _get_active_linked_docs_for_do(do_name, include_po_draft=True)

        if active_links:
            blocked.append((do_name, active_links))
        else:
            cancellable.append((do_name, do_status))

    if blocked:
        msg_lines = [
            _("❌ Sales Order tidak bisa di-cancel karena ada Delivery Order Towing "
              "yang masih punya dokumen turunan aktif."),
            "",
            _("Silakan <b>cancel dokumen turunan terlebih dahulu</b>, "
              "lalu cancel SO ini lagi:"),
            "",
        ]
        for do_name, links in blocked:
            do_link = frappe.utils.get_link_to_form("Delivery Order Towing", do_name)
            msg_lines.append(f"<b>📋 DO: {do_link}</b>")
            for link_desc in links:
                msg_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;• {link_desc}")
            msg_lines.append("")

        frappe.throw("<br>".join(msg_lines), title=_("Cancel Diblokir: Ada Turunan Aktif"))

    cancelled_dos = []
    failed_dos = []

    for do_name, do_status in cancellable:
        try:
            _clear_so_link_to_do(do_name)

            if do_status == 0:
                frappe.db.set_value(
                    "Delivery Order Towing", do_name,
                    {"docstatus": 2, "status": "Cancelled"}
                )
            else:
                do_doc = frappe.get_doc("Delivery Order Towing", do_name)
                do_doc.flags.ignore_permissions = True
                do_doc.flags.skip_cancel_check = True
                do_doc.cancel()

            cancelled_dos.append(do_name)

        except Exception as e:
            failed_dos.append((do_name, str(e)))
            frappe.log_error(
                f"Gagal cancel DO Towing {do_name} dari SO {doc.name}: {e}",
                "DO Towing Auto-Cancel Error"
            )

    if cancelled_dos:
        do_links = "<br>".join(
            f"• {frappe.utils.get_link_to_form('Delivery Order Towing', name)}"
            for name in cancelled_dos
        )
        frappe.msgprint(
            _("✅ {0} Delivery Order Towing berhasil di-cancel:<br>{1}").format(
                len(cancelled_dos), do_links
            ),
            title=_("DO Towing Auto-Cancelled"),
            indicator="orange"
        )

    if failed_dos:
        err_lines = [f"• <b>{name}</b>: {err}" for name, err in failed_dos]
        frappe.throw(
            _("⚠️ {0} DO gagal di-cancel:<br>{1}<br><br>"
              "SO cancel di-rollback. Cek Error Log untuk detail.").format(
                len(failed_dos), "<br>".join(err_lines)
            ),
            title=_("DO Cancel Gagal")
        )


# ──────────────────────────────────────────────────────────────────────────
# HOOK 2: DELIVERY ORDER TOWING → before_cancel
# ──────────────────────────────────────────────────────────────────────────

def before_cancel_do_towing(doc, method=None):
    """
    Hook: before_cancel pada Delivery Order Towing.
    Auto-cancel PO (Draft maupun Submitted) asal PO tidak punya PI/PE aktif.
    Jika PO punya PI/PE aktif → BLOCK.
    """
    if doc.flags.get("skip_cancel_check"):
        return

    if not _field_exists("Purchase Order", "custom_delivery_order"):
        _clear_so_link_to_do(doc.name)
        return

    pos = frappe.get_all(
        "Purchase Order",
        filters={"custom_delivery_order": doc.name, "docstatus": ["<", 2]},
        fields=["name", "docstatus", "workflow_state", "status"]
    )

    blocking_lines = []
    cancelled_pos  = []

    for po in pos:
        # Cek apakah PO punya PI atau PE aktif (1 tingkat di atas PO)
        po_blocks = _get_active_linked_docs_for_po(po.name, include_pi_draft=False)
        if po_blocks:
            state = po.get("workflow_state") or po.get("status") or _docstatus_label(po["docstatus"])
            po_link = frappe.utils.get_link_to_form("Purchase Order", po.name)
            blocking_lines.append(
                f"<b>Purchase Order {po_link} [{state}]</b> masih punya dokumen aktif:"
            )
            for desc in po_blocks:
                blocking_lines.append(f"&nbsp;&nbsp;&nbsp;• {desc}")
            continue  # skip auto-cancel untuk PO ini

        # Tidak ada PI/PE aktif → safe to cancel/delete
        try:
            if po["docstatus"] == 0:
                # Draft PO → hapus langsung
                frappe.delete_doc("Purchase Order", po.name, ignore_permissions=True, force=True)
            else:
                # Submitted PO → cancel melalui frappe (trigger hook, update workflow_state)
                po_doc = frappe.get_doc("Purchase Order", po.name)
                po_doc.flags.skip_cancel_check = True
                po_doc.cancel()
            cancelled_pos.append(po.name)
        except Exception as e:
            frappe.log_error(
                f"Gagal cancel/hapus PO {po.name} dari DO {doc.name}: {e}",
                "DO Towing: PO Auto-Cancel Error"
            )
            blocking_lines.append(f"Gagal cancel PO {po.name}: {e}")

    if blocking_lines:
        msg_lines = [
            _("❌ Delivery Order Towing <b>{0}</b> tidak bisa di-cancel "
              "karena PO Uang Jalan masih punya dokumen turunan aktif.").format(doc.name),
            "",
            _("Silakan <b>cancel PI / PE terlebih dahulu</b>, lalu cancel DO ini lagi:"),
            "",
        ] + blocking_lines
        frappe.throw("<br>".join(msg_lines), title=_("Cancel Diblokir: Ada Turunan Aktif di PO"))

    _clear_so_link_to_do(doc.name)

    if cancelled_pos:
        po_links = "<br>".join(
            f"• {frappe.utils.get_link_to_form('Purchase Order', name)}"
            for name in cancelled_pos
        )
        frappe.msgprint(
            _("✅ {0} Purchase Order Uang Jalan ikut di-cancel / dihapus:<br>{1}").format(
                len(cancelled_pos), po_links
            ),
            title=_("PO Uang Jalan Auto-Cancelled"),
            indicator="orange"
        )


# ──────────────────────────────────────────────────────────────────────────
# HOOK 3: PURCHASE ORDER → before_cancel (defensive layer)
# ──────────────────────────────────────────────────────────────────────────

def before_cancel_po_uang_jalan(doc, method=None):
    """
    Hook: before_cancel pada Purchase Order Uang Jalan.

    Alur:
      1. Cek setiap PI yang ter-link ke PO ini.
         - Jika PI punya PE aktif → BLOCK (user harus cancel PE dulu).
         - Jika PI tidak punya PE aktif → auto-cancel PI (Draft maupun Submitted).
      2. Setelah semua PI di-cancel/hapus, bersihkan link di DO, lanjutkan cancel PO.
    """
    if doc.flags.get("skip_cancel_check"):
        return

    do_name = doc.get("custom_delivery_order")
    if not do_name:
        return

    # Cari semua PI yang ter-link ke PO ini (Draft maupun Submitted)
    pi_names = frappe.db.sql_list("""
        SELECT DISTINCT pi.name
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
        WHERE pii.purchase_order = %s
          AND pi.docstatus < 2
    """, (doc.name,))

    blocking_lines = []
    cancelled_pis  = []

    for pi_name in pi_names:
        pi_docstatus = frappe.db.get_value("Purchase Invoice", pi_name, "docstatus")

        # Cek PE aktif di PI ini
        pe_count = frappe.db.sql("""
            SELECT COUNT(DISTINCT pe.name)
            FROM `tabPayment Entry` pe
            INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
            WHERE per.reference_doctype = 'Purchase Invoice'
              AND per.reference_name = %s
              AND pe.docstatus < 2
        """, (pi_name,))[0][0]

        if pe_count > 0:
            pi_link = frappe.utils.get_link_to_form("Purchase Invoice", pi_name)
            blocking_lines.append(
                f"<b>Purchase Invoice {pi_link}</b> masih punya {pe_count} Payment Entry aktif"
            )
            continue

        # Tidak ada PE aktif → safe to cancel/delete
        try:
            if pi_docstatus == 0:
                frappe.delete_doc("Purchase Invoice", pi_name, ignore_permissions=True, force=True)
            else:
                pi_doc = frappe.get_doc("Purchase Invoice", pi_name)
                pi_doc.flags.skip_cancel_check = True
                pi_doc.flags.ignore_permissions = True
                pi_doc.cancel()
            cancelled_pis.append(pi_name)
        except Exception as e:
            frappe.log_error(
                f"Gagal cancel/hapus PI {pi_name} dari PO {doc.name}: {e}",
                "PO Towing: PI Auto-Cancel Error"
            )
            blocking_lines.append(f"Gagal cancel PI {pi_name}: {e}")

    if blocking_lines:
        msg_lines = [
            _("❌ Purchase Order <b>{0}</b> tidak bisa di-cancel "
              "karena PI masih punya Payment Entry aktif.").format(doc.name),
            "",
            _("Silakan <b>cancel Payment Entry terlebih dahulu</b>, lalu cancel PO ini lagi:"),
            "",
        ] + blocking_lines
        frappe.throw("<br>".join(msg_lines), title=_("Cancel Diblokir: Ada PE Aktif di PI"))

    _clear_do_link_to_po(do_name, doc.name)

    if cancelled_pis:
        pi_links = "<br>".join(
            f"• {frappe.utils.get_link_to_form('Purchase Invoice', name)}"
            for name in cancelled_pis
        )
        frappe.msgprint(
            _("✅ {0} Purchase Invoice ikut di-cancel / dihapus:<br>{1}").format(
                len(cancelled_pis), pi_links
            ),
            title=_("Purchase Invoice Auto-Cancelled"),
            indicator="orange"
        )


# ──────────────────────────────────────────────────────────────────────────
# WHITELIST API: Tombol "Cancel SO Towing" di JS
# ──────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def cancel_so_with_cleanup(so_name: str):
    """
    Cancel Sales Order dengan cleanup link DO duluan, supaya Frappe tidak
    munculin dialog "Cancel All Documents". Dipanggil dari tombol custom JS.

    Flow:
      1. Validasi SO ada & docstatus=1 (submitted)
      2. Cek tiap DO ter-link → kalau punya turunan apapun (PO/PI/PE/dll), THROW
      3. Untuk DO yang aman:
         - Clear link delivery_order di SO Towing Kendaraan
         - Cancel DO (Draft → set docstatus=2; Submitted → cancel())
      4. Cancel SO sendiri
    """
    if not frappe.db.exists("Sales Order", so_name):
        frappe.throw(_("Sales Order {0} tidak ditemukan.").format(so_name))

    so_doc = frappe.get_doc("Sales Order", so_name)

    if so_doc.docstatus == 2:
        frappe.throw(_("Sales Order {0} sudah Cancelled.").format(so_name))

    if so_doc.docstatus == 0:
        frappe.throw(_("Sales Order {0} masih Draft, hapus saja langsung.").format(so_name))

    # Kumpulkan semua DO unik yang ter-link
    kendaraan_list = so_doc.get("custom_towing_kendaraan", [])
    do_names = []
    seen = set()
    for kendaraan in kendaraan_list:
        do_name = kendaraan.get("delivery_order")
        if do_name and do_name not in seen:
            seen.add(do_name)
            do_names.append(do_name)

    blocked = []
    cancellable = []

    for do_name in do_names:
        if not frappe.db.exists("Delivery Order Towing", do_name):
            continue

        do_status = frappe.db.get_value("Delivery Order Towing", do_name, "docstatus")
        if do_status == 2:
            continue

        # Cancel SO mau block kalau DO punya turunan APAPUN (termasuk PO Draft)
        active_links = _get_active_linked_docs_for_do(do_name, include_po_draft=True)

        if active_links:
            blocked.append((do_name, active_links))
        else:
            cancellable.append((do_name, do_status))

    # ───────────────────────────────────────────────────────────────
    # KALAU ADA YANG BLOCKED → THROW (block cancel SO)
    # ───────────────────────────────────────────────────────────────
    if blocked:
        msg_lines = [
            _("❌ Sales Order <b>{0}</b> tidak bisa di-cancel karena ada "
              "Delivery Order Towing yang masih punya dokumen turunan aktif.").format(so_name),
            "",
            _("Silakan <b>cancel dokumen turunan terlebih dahulu</b>, "
              "lalu cancel SO ini lagi:"),
            "",
        ]
        for do_name, links in blocked:
            do_link = frappe.utils.get_link_to_form("Delivery Order Towing", do_name)
            msg_lines.append(f"<b>📋 DO: {do_link}</b>")
            for link_desc in links:
                msg_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;• {link_desc}")
            msg_lines.append("")

        frappe.throw("<br>".join(msg_lines), title=_("Cancel Diblokir: Ada Turunan Aktif"))

    # ───────────────────────────────────────────────────────────────
    # CANCEL SEMUA DO YANG AMAN
    # ───────────────────────────────────────────────────────────────
    cancelled_dos = []
    failed_dos = []

    for do_name, do_status in cancellable:
        try:
            _clear_so_link_to_do(do_name)

            if do_status == 0:
                frappe.db.set_value(
                    "Delivery Order Towing", do_name,
                    {"docstatus": 2, "status": "Cancelled"}
                )
            else:
                do_doc = frappe.get_doc("Delivery Order Towing", do_name)
                do_doc.flags.ignore_permissions = True
                do_doc.flags.skip_cancel_check = True
                do_doc.cancel()

            cancelled_dos.append(do_name)

        except Exception as e:
            failed_dos.append((do_name, str(e)))
            frappe.log_error(
                f"Gagal cancel DO Towing {do_name} dari SO {so_name}: {e}",
                "DO Towing Auto-Cancel Error"
            )

    if failed_dos:
        err_lines = [f"• <b>{name}</b>: {err}" for name, err in failed_dos]
        frappe.throw(
            _("⚠️ {0} DO gagal di-cancel:<br>{1}<br><br>"
              "SO cancel dibatalkan. Cek Error Log untuk detail.").format(
                len(failed_dos), "<br>".join(err_lines)
            ),
            title=_("DO Cancel Gagal")
        )

    # ───────────────────────────────────────────────────────────────
    # CANCEL SO SENDIRI
    # ───────────────────────────────────────────────────────────────
    try:
        # Skip re-check di before_cancel hook karena sudah handled di atas
        so_doc.flags.ignore_permissions = True
        so_doc.flags.skip_cancel_check = True
        so_doc.cancel()
    except Exception as e:
        frappe.log_error(
            f"Gagal cancel SO {so_name}: {e}",
            "SO Cancel Error"
        )
        frappe.throw(_("Gagal cancel Sales Order {0}: {1}").format(so_name, str(e)))

    return {
        "success": True,
        "so_name": so_name,
        "cancelled_dos": cancelled_dos,
    }


# ──────────────────────────────────────────────────────────────────────────
# WHITELIST API: Tombol "Cancel PO Uang Jalan" di JS
# ──────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def cancel_po_uang_jalan_with_cleanup(po_name: str):
    """
    Cancel PO Uang Jalan dengan cleanup link DO duluan.
    Dipanggil dari tombol custom JS di form PO.
    """
    if not frappe.db.exists("Purchase Order", po_name):
        frappe.throw(_("Purchase Order {0} tidak ditemukan.").format(po_name))

    po_doc = frappe.get_doc("Purchase Order", po_name)

    if po_doc.docstatus == 2:
        frappe.throw(_("Purchase Order {0} sudah Cancelled.").format(po_name))

    if po_doc.docstatus == 0:
        frappe.throw(_("Purchase Order {0} masih Draft, hapus saja langsung.").format(po_name))

    do_name = po_doc.get("custom_delivery_order")
    if not do_name:
        frappe.throw(_("Purchase Order {0} bukan PO Uang Jalan towing. "
                      "Pakai tombol Cancel default.").format(po_name))

    blocking_links = _get_active_linked_docs_for_po(po_name, include_pi_draft=False)
    if blocking_links:
        msg_lines = [
            _("❌ Purchase Order <b>{0}</b> tidak bisa di-cancel "
              "karena masih punya dokumen turunan aktif.").format(po_name),
            "",
            _("Silakan <b>cancel dokumen turunan terlebih dahulu</b>:"),
            "",
        ]
        for link_desc in blocking_links:
            msg_lines.append(f"&nbsp;&nbsp;&nbsp;&nbsp;• {link_desc}")

        frappe.throw("<br>".join(msg_lines), title=_("Cancel Diblokir: Ada Turunan Aktif"))

    cancelled_pis = _cancel_pi_draft_for_po(po_name)
    _clear_do_link_to_po(do_name, po_name)

    try:
        po_doc.flags.ignore_permissions = True
        po_doc.flags.skip_cancel_check = True
        po_doc.cancel()
    except Exception as e:
        frappe.log_error(
            f"Gagal cancel PO Uang Jalan {po_name}: {e}",
            "PO Uang Jalan Cancel Error"
        )
        frappe.throw(_("Gagal cancel Purchase Order {0}: {1}").format(po_name, str(e)))

    return {
        "success": True,
        "po_name": po_name,
        "cancelled_pis": cancelled_pis,
        "do_name": do_name,
    }


# ══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — CANCEL CASCADE
# ══════════════════════════════════════════════════════════════════════════

def _cancel_po_draft_for_do(do_name: str) -> list:
    """Cancel semua PO Uang Jalan yang masih Draft (docstatus=0) ter-link ke DO."""
    cancelled = []

    if not _field_exists("Purchase Order", "custom_delivery_order"):
        return cancelled

    pos = frappe.get_all(
        "Purchase Order",
        filters={"custom_delivery_order": do_name, "docstatus": 0},
        fields=["name"]
    )

    for po in pos:
        try:
            # ✅ FIX Issue #2: set workflow_state juga, bukan cuma status
            # Karena yang ditampilkan di UI sebagai "Approved/Draft" itu workflow_state
            update_data = {"docstatus": 2, "status": "Cancelled"}

            # Cek apakah PO punya field workflow_state (untuk apps yang pakai workflow)
            if frappe.db.has_column("Purchase Order", "workflow_state"):
                update_data["workflow_state"] = "Cancelled"

            frappe.db.set_value("Purchase Order", po.name, update_data)
            cancelled.append(po.name)
        except Exception as e:
            frappe.log_error(
                f"Gagal cancel PO Draft {po.name} dari DO {do_name}: {e}",
                "PO Uang Jalan Auto-Cancel Error"
            )

    return cancelled


def _cancel_pi_draft_for_po(po_name: str) -> list:
    """Cancel semua PI Draft yang ter-link ke PO via PI Item.purchase_order."""
    cancelled = []

    pi_names = frappe.db.sql_list("""
        SELECT DISTINCT pi.name
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
        WHERE pii.purchase_order = %s
          AND pi.docstatus = 0
    """, (po_name,))

    for pi_name in pi_names:
        try:
            update_data = {"docstatus": 2, "status": "Cancelled"}
            if frappe.db.has_column("Purchase Invoice", "workflow_state"):
                update_data["workflow_state"] = "Cancelled"

            frappe.db.set_value("Purchase Invoice", pi_name, update_data)
            cancelled.append(pi_name)
        except Exception as e:
            frappe.log_error(
                f"Gagal cancel PI Draft {pi_name} dari PO {po_name}: {e}",
                "PI Auto-Cancel Error"
            )

    return cancelled


def _clear_so_link_to_do(do_name: str):
    """Clear field `delivery_order` di SO Towing Kendaraan yang nunjuk ke DO ini."""
    frappe.db.sql("""
        UPDATE `tabSO Towing Kendaraan`
        SET delivery_order = NULL
        WHERE delivery_order = %s
    """, (do_name,))
    frappe.db.commit()


def _clear_do_link_to_po(do_name: str, po_name: str):
    """Clear field purchase_order_uang_jalan di DO + reset status uang jalan."""
    if not frappe.db.exists("Delivery Order Towing", do_name):
        return

    current_po = frappe.db.get_value(
        "Delivery Order Towing", do_name, "purchase_order_uang_jalan"
    )

    if current_po == po_name:
        frappe.db.sql("""
            UPDATE `tabDelivery Order Towing`
            SET purchase_order_uang_jalan = NULL,
                uang_jalan_status = 'Belum Diajukan',
                uang_jalan_amount = 0
            WHERE name = %s
        """, (do_name,))
        frappe.db.commit()


def _get_active_linked_docs_for_do(do_name: str, include_po_draft: bool = True) -> list:
    """Cek dokumen turunan dari DO yang masih aktif."""
    active_links = []

    # 1. Purchase Order
    if _field_exists("Purchase Order", "custom_delivery_order"):
        po_filters = {"custom_delivery_order": do_name, "docstatus": ["<", 2]}
        if not include_po_draft:
            po_filters["docstatus"] = 1

        pos = frappe.get_all(
            "Purchase Order",
            filters=po_filters,
            fields=["name", "docstatus", "workflow_state", "status"]
        )
        for po in pos:
            state = po.get("workflow_state") or po.get("status") or _docstatus_label(po["docstatus"])
            link = frappe.utils.get_link_to_form("Purchase Order", po["name"])
            active_links.append(f"Purchase Order (Uang Jalan): {link} [{state}]")

    # 2. Purchase Invoice
    if _field_exists("Purchase Invoice", "custom_delivery_order"):
        pis = frappe.get_all(
            "Purchase Invoice",
            filters={"custom_delivery_order": do_name, "docstatus": ["<", 2]},
            fields=["name", "docstatus", "status"]
        )
        for pi in pis:
            state = pi.get("status") or _docstatus_label(pi["docstatus"])
            link = frappe.utils.get_link_to_form("Purchase Invoice", pi["name"])
            active_links.append(f"Purchase Invoice: {link} [{state}]")

    # 3. Payment Entry
    if _field_exists("Payment Entry", "delivery_order_towing"):
        pes = frappe.get_all(
            "Payment Entry",
            filters={"delivery_order_towing": do_name, "docstatus": ["<", 2]},
            fields=["name", "docstatus", "status"]
        )
        for pe in pes:
            state = pe.get("status") or _docstatus_label(pe["docstatus"])
            link = frappe.utils.get_link_to_form("Payment Entry", pe["name"])
            active_links.append(f"Payment Entry: {link} [{state}]")

    # 4. Sales Invoice
    if _field_exists("Sales Invoice", "custom_delivery_order"):
        sis = frappe.get_all(
            "Sales Invoice",
            filters={"custom_delivery_order": do_name, "docstatus": ["<", 2]},
            fields=["name", "docstatus", "status"]
        )
        for si in sis:
            state = si.get("status") or _docstatus_label(si["docstatus"])
            link = frappe.utils.get_link_to_form("Sales Invoice", si["name"])
            active_links.append(f"Sales Invoice: {link} [{state}]")

    # 5. Expense Claim
    if _field_exists("Expense Claim", "custom_delivery_order"):
        ecs = frappe.get_all(
            "Expense Claim",
            filters={"custom_delivery_order": do_name, "docstatus": ["<", 2]},
            fields=["name", "docstatus", "status"]
        )
        for ec in ecs:
            state = ec.get("status") or _docstatus_label(ec["docstatus"])
            link = frappe.utils.get_link_to_form("Expense Claim", ec["name"])
            active_links.append(f"Expense Claim: {link} [{state}]")

    # 6. Driver Commission
    try:
        dc_parents = frappe.get_all(
            "Driver Commission Item",
            filters={"delivery_order_towing": do_name},
            fields=["parent"]
        )
        seen_dc = set()
        for row in dc_parents:
            parent = row.get("parent")
            if not parent or parent in seen_dc:
                continue
            seen_dc.add(parent)

            dc_status = frappe.db.get_value(
                "Driver Commission", parent, ["docstatus", "status"], as_dict=True
            )
            if dc_status and dc_status.get("docstatus", 2) < 2:
                state = dc_status.get("status") or _docstatus_label(dc_status["docstatus"])
                link = frappe.utils.get_link_to_form("Driver Commission", parent)
                active_links.append(f"Driver Commission: {link} [{state}]")
    except Exception:
        pass

    return active_links


def _get_active_linked_docs_for_po(po_name: str, include_pi_draft: bool = True) -> list:
    """Cek dokumen turunan dari PO yang masih aktif."""
    active_links = []

    pi_filter_docstatus = "pi.docstatus < 2" if include_pi_draft else "pi.docstatus = 1"
    pis = frappe.db.sql(f"""
        SELECT DISTINCT pi.name, pi.docstatus, pi.status
        FROM `tabPurchase Invoice` pi
        INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
        WHERE pii.purchase_order = %s
          AND {pi_filter_docstatus}
    """, (po_name,), as_dict=True)

    for pi in pis:
        state = pi.get("status") or _docstatus_label(pi["docstatus"])
        link = frappe.utils.get_link_to_form("Purchase Invoice", pi["name"])
        active_links.append(f"Purchase Invoice: {link} [{state}]")

    pes = frappe.db.sql("""
        SELECT DISTINCT pe.name, pe.docstatus, pe.status
        FROM `tabPayment Entry` pe
        INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
        WHERE per.reference_doctype = 'Purchase Order'
          AND per.reference_name = %s
          AND pe.docstatus < 2
    """, (po_name,), as_dict=True)

    for pe in pes:
        state = pe.get("status") or _docstatus_label(pe["docstatus"])
        link = frappe.utils.get_link_to_form("Payment Entry", pe["name"])
        active_links.append(f"Payment Entry: {link} [{state}]")

    return active_links


def _docstatus_label(docstatus: int) -> str:
    return {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(docstatus, "Unknown")


# ──────────────────────────────────────────────────────────────────────────
# HOOK: on_trash — putus link sebelum hapus (hindari circular-link error)
# ──────────────────────────────────────────────────────────────────────────

def on_trash_do_towing(doc, method=None):
    """
    Dipanggil sebelum Delivery Order Towing dihapus.
    Putus link:
      - custom_delivery_order di semua PO yang menunjuk ke DO ini
      - delivery_order di SO Towing Kendaraan
    Sehingga PO yang sudah di-cancel bisa dihapus tanpa "still linked" error.
    """
    do_name = doc.name

    # Putus link PO → DO
    if _field_exists("Purchase Order", "custom_delivery_order"):
        frappe.db.sql("""
            UPDATE `tabPurchase Order`
            SET custom_delivery_order = NULL
            WHERE custom_delivery_order = %s
        """, (do_name,))

    # Putus link SO Towing Kendaraan → DO
    frappe.db.sql("""
        UPDATE `tabSO Towing Kendaraan`
        SET delivery_order = NULL
        WHERE delivery_order = %s
    """, (do_name,))

    frappe.db.commit()


def on_trash_po_uang_jalan(doc, method=None):
    """
    Dipanggil sebelum Purchase Order dihapus.
    Hanya berlaku untuk PO Uang Jalan (yang punya custom_delivery_order).
    Putus link purchase_order_uang_jalan di DO sehingga DO tidak terblokir.
    """
    do_name = doc.get("custom_delivery_order")
    if not do_name:
        return  # bukan PO Uang Jalan, skip

    if frappe.db.exists("Delivery Order Towing", do_name):
        frappe.db.sql("""
            UPDATE `tabDelivery Order Towing`
            SET purchase_order_uang_jalan = NULL,
                uang_jalan_status = 'Belum Diajukan',
                uang_jalan_amount = 0
            WHERE name = %s
              AND purchase_order_uang_jalan = %s
        """, (do_name, doc.name))
        frappe.db.commit()


# ══════════════════════════════════════════════════════════════════════════
# CANCEL CASCADE: Purchase Invoice → Payment Entry (auto cancel)
# ══════════════════════════════════════════════════════════════════════════
#
# Hook: before_cancel pada Purchase Invoice (registered di hooks.py)
#
# Saat user cancel PI:
#   • Cari semua Payment Entry yang reference ke PI ini (docstatus < 2)
#   • Auto-cancel PE — tidak unallocate, langsung set docstatus=2
#   • PI cancel lanjut normal
#
# Catatan: hook ini terpisah dari before_cancel di events/purchase_invoice.py
# yang sudah ada (untuk budget control). Frappe akan jalankan keduanya secara
# berurutan sesuai urutan di hooks.py.
# ══════════════════════════════════════════════════════════════════════════

def before_cancel_pi_auto_cancel_pe(doc, method=None):
    """
    Hook: before_cancel pada Purchase Invoice.
    Auto-cancel semua Payment Entry yang ter-link ke PI ini.
    """
    if doc.flags.get("skip_cancel_check"):
        return

    # Cari PE yang reference ke PI ini (docstatus < 2 = Draft atau Submitted)
    pe_names = frappe.db.sql_list("""
        SELECT DISTINCT pe.name
        FROM `tabPayment Entry` pe
        INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
        WHERE per.reference_doctype = 'Purchase Invoice'
          AND per.reference_name = %s
          AND pe.docstatus < 2
    """, (doc.name,))

    if not pe_names:
        return

    cancelled_pes = []
    failed_pes = []

    for pe_name in pe_names:
        try:
            pe_status = frappe.db.get_value("Payment Entry", pe_name, "docstatus")

            if pe_status == 0:
                # Draft → set docstatus=2 langsung
                update_data = {"docstatus": 2, "status": "Cancelled"}
                if frappe.db.has_column("Payment Entry", "workflow_state"):
                    update_data["workflow_state"] = "Cancelled"
                frappe.db.set_value("Payment Entry", pe_name, update_data)
            else:
                # Submitted → cancel via doc.cancel() supaya GL Entry & PLE auto-handled
                pe_doc = frappe.get_doc("Payment Entry", pe_name)
                pe_doc.flags.ignore_permissions = True
                pe_doc.flags.ignore_links = True
                pe_doc.flags.skip_cancel_check = True
                pe_doc.cancel()

            cancelled_pes.append(pe_name)

        except Exception as e:
            failed_pes.append((pe_name, str(e)))
            frappe.log_error(
                f"Gagal auto-cancel PE {pe_name} dari PI {doc.name}: {e}",
                "PE Auto-Cancel from PI Error"
            )

    if cancelled_pes:
        pe_links = "<br>".join(
            f"• {frappe.utils.get_link_to_form('Payment Entry', name)}"
            for name in cancelled_pes
        )
        frappe.msgprint(
            _("✅ {0} Payment Entry ikut di-cancel:<br>{1}").format(
                len(cancelled_pes), pe_links
            ),
            title=_("Payment Entry Auto-Cancelled"),
            indicator="orange"
        )

    if failed_pes:
        err_lines = [f"• <b>{name}</b>: {err}" for name, err in failed_pes]
        frappe.throw(
            _("⚠️ {0} Payment Entry gagal di-cancel:<br>{1}<br><br>"
              "PI cancel di-rollback. Cek Error Log untuk detail.").format(
                len(failed_pes), "<br>".join(err_lines)
            ),
            title=_("PE Cancel Gagal")
        )