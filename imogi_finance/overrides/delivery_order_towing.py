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
        self.validate_driver_required_on_assign()
        self.validate_invoice_fields_on_awaiting_document()
        self.validate_harga_jasa()
        self.set_customer_name()

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
        ✅ Ambil data kendaraan dari DO itu sendiri (bukan dari SO).
        Hanya 1 kendaraan yang di-assigned ke DO ini.
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

def on_submit(doc, method=None):
    """Hook: dipanggil saat DO di-submit (Draft → Submitted)."""
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
    Isi custom_towing_kendaraan langsung via SQL — menghindari TimestampMismatchError
    saat dokumen baru saja dibuat dan belum di-reload.
    """
    try:
        # Cek docstatus tanpa load full doc
        docstatus = frappe.db.get_value(doctype, docname, "docstatus")
        if docstatus == 1:
            return False

        # Hapus existing rows langsung via DB
        frappe.db.delete(
            f"tab{doctype} Detail Kendaraan",
            {"parent": docname, "parenttype": doctype}
        )

        # Cari nama child table yang benar
        child_doctype = frappe.db.get_value(
            "DocField",
            {"parent": doctype, "fieldname": "custom_towing_kendaraan"},
            "options"
        )
        if not child_doctype:
            # Fallback: load doc jika child doctype tidak ditemukan
            linked_doc = frappe.get_doc(doctype, docname)
            linked_doc.set("custom_towing_kendaraan", [])
            for row in towing_rows:
                linked_doc.append("custom_towing_kendaraan", {
                    "so_item_code": row.get("so_item_code"),
                    "nomor_rangka": row.get("nomor_rangka"),
                    "nomor_polisi": row.get("nomor_polisi"),
                    "tipe_model"  : row.get("tipe_model"),
                    "nomor_mesin" : row.get("nomor_mesin"),
                })
            linked_doc.flags.ignore_version = True
            linked_doc.flags.ignore_timestamp = True
            linked_doc.save(ignore_permissions=True)
            return True

        # Insert rows langsung via frappe.db.insert
        from frappe.utils import now_datetime
        now = now_datetime()
        user = frappe.session.user or "Administrator"

        for idx, row in enumerate(towing_rows, start=1):
            frappe.db.insert({
                "doctype"     : child_doctype,
                "name"        : frappe.generate_hash(length=10),
                "parent"      : docname,
                "parenttype"  : doctype,
                "parentfield" : "custom_towing_kendaraan",
                "idx"         : idx,
                "so_item_code": row.get("so_item_code") or "",
                "nomor_rangka": row.get("nomor_rangka") or "",
                "nomor_polisi": row.get("nomor_polisi") or "",
                "tipe_model"  : row.get("tipe_model") or "",
                "nomor_mesin" : row.get("nomor_mesin") or "",
                "owner"       : user,
                "modified_by" : user,
                "creation"    : now,
                "modified"    : now,
                "docstatus"   : 0,
            })

        # Update modified timestamp dokumen parent
        frappe.db.set_value(doctype, docname, "modified", now, update_modified=False)
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
    """
    do_name = doc.get("custom_delivery_order")
    if not do_name:
        return

    # Map workflow_state PO ke uang_jalan_status DO
    state_map = {
        "Draft":            "Belum Diajukan",
        "Pending Approval": "Diajukan",
        "Approved":         "Approved",
        "Rejected":         "Belum Diajukan",
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
    Block Sales Invoice jika dibuat dari SO yang punya DO belum Done.
    """
    # Ambil SO dari invoice items
    so_list = list(set(
        item.sales_order 
        for item in doc.items 
        if item.get("sales_order")
    ))

    if not so_list:
        return

    for so_name in so_list:
        dos = frappe.get_all(
            "Delivery Order Towing",
            filters={
                "sales_order": so_name,
                "docstatus": ["!=", 2]
            },
            fields=["name", "status", "nomor_polisi"]
        )

        if not dos:
            continue

        belum_done = [d for d in dos if d.status != "Done"]

        if belum_done:
            detail = "<br>".join(
                f"• {d.name} ({d.nomor_polisi}) — status: <b>{d.status}</b>"
                for d in belum_done
            )
            frappe.throw(
                _("Sales Invoice tidak bisa dibuat dari SO <b>{0}</b> "
                  "karena ada DO Towing yang belum selesai:<br><br>{1}").format(
                    so_name, detail
                ),
                title="DO Towing Belum Selesai"
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