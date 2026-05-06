# ============================================================
# delivery_order_towing.py
# Lokasi: imogi_finance/imogi_finance/overrides/delivery_order_towing.py
#
# AUTO-DETECT environment:
#   - Sama site/bench → langsung frappe.get_doc() / frappe.new_doc()
#   - Beda server     → Frappe REST API + API key
#
# CARA KERJA:
#   Kalau "finance_imogi_url" TIDAK ada di site_config → pakai local (direct)
#   Kalau "finance_imogi_url" ADA di site_config       → pakai REST API
#
# Untuk LOCAL: tidak perlu config apapun, langsung jalan.
#
# Untuk PRODUCTION (deploy ke server lain):
#   bench --site [site] set-config finance_imogi_url        "https://imogi-dev.j.frappe.cloud"
#   bench --site [site] set-config finance_imogi_api_key    "xxx"
#   bench --site [site] set-config finance_imogi_api_secret "yyy"
# ============================================================

import frappe
import json
from frappe.model.document import Document
from frappe.utils import now_datetime, nowdate
from frappe import _


# ──────────────────────────────────────────────────────────────
# DETEKSI MODE: LOCAL atau REMOTE
# ──────────────────────────────────────────────────────────────

def _is_remote() -> bool:
    """
    Return True  → Finance Imogi ada di server lain, pakai REST API.
    Return False → Finance Imogi sama site/bench, pakai direct frappe call.

    Cukup cek apakah finance_imogi_url sudah di-set di site_config.
    Kalau belum di-set = local mode.
    """
    return bool(frappe.conf.get("finance_imogi_url"))


# ──────────────────────────────────────────────────────────────
# MODE LOCAL — direct frappe call (sama site/bench)
# ──────────────────────────────────────────────────────────────

# Di delivery_order_towing.py — ganti _local_create dengan ini

def _local_create(doctype: str, data: dict) -> dict:
    doc = frappe.new_doc(doctype)
    doc.update(data)
    doc.flags.ignore_permissions = True
    doc.flags.ignore_mandatory   = True
    doc.insert(ignore_permissions=True)
    
    # Langsung submit setelah insert
    if doctype == "Sales Invoice":
        frappe.db.commit()  # commit insert dulu
        fresh = frappe.get_doc(doctype, doc.name)
        fresh.flags.ignore_permissions = True
        fresh.submit()
    
    frappe.db.commit()
    return {"name": doc.name}


def _local_get(doctype: str, name: str) -> dict:
    """Ambil dokumen langsung via frappe.get_doc()."""
    doc = frappe.get_doc(doctype, name)
    return doc.as_dict()


def _local_update(doctype: str, name: str, data: dict) -> dict:
    """Update dokumen langsung via frappe.db.set_value()."""
    frappe.db.set_value(doctype, name, data)
    frappe.db.commit()
    return {"name": name}


# ──────────────────────────────────────────────────────────────
# MODE REMOTE — Frappe REST API (beda server/production)
# ──────────────────────────────────────────────────────────────

def _get_remote_base_url() -> str:
    url = frappe.conf.get("finance_imogi_url", "").rstrip("/")
    if not url:
        frappe.throw(_("finance_imogi_url belum dikonfigurasi di site_config."))
    return url


def _get_remote_headers() -> dict:
    key    = frappe.conf.get("finance_imogi_api_key", "")
    secret = frappe.conf.get("finance_imogi_api_secret", "")
    if not key or not secret:
        frappe.throw(
            _("finance_imogi_api_key / finance_imogi_api_secret belum dikonfigurasi.<br>"
              "<code>bench --site [site] set-config finance_imogi_api_key \"xxx\"</code>"),
            title="API Key Tidak Ditemukan"
        )
    return {
        "Content-Type" : "application/json",
        "Authorization": f"token {key}:{secret}",
    }


def _remote_create(doctype: str, data: dict) -> dict:
    import requests
    url  = f"{_get_remote_base_url()}/api/resource/{doctype}"
    resp = requests.post(url, headers=_get_remote_headers(), json=data, timeout=30)
    _raise_for_status(resp, f"CREATE {doctype}")
    return resp.json().get("data", {})


def _remote_get(doctype: str, name: str) -> dict:
    import requests
    url  = f"{_get_remote_base_url()}/api/resource/{doctype}/{name}"
    resp = requests.get(url, headers=_get_remote_headers(), timeout=15)
    _raise_for_status(resp, f"GET {doctype}/{name}")
    return resp.json().get("data", {})


def _remote_update(doctype: str, name: str, data: dict) -> dict:
    import requests
    url  = f"{_get_remote_base_url()}/api/resource/{doctype}/{name}"
    resp = requests.put(url, headers=_get_remote_headers(), json=data, timeout=15)
    _raise_for_status(resp, f"UPDATE {doctype}/{name}")
    return resp.json().get("data", {})


def _raise_for_status(resp, context: str):
    """Error handler untuk REST API response."""
    if resp.status_code == 200:
        return
    try:
        msg = resp.json().get("exception") or resp.json().get("message") or resp.text
    except Exception:
        msg = resp.text

    frappe.log_error(
        f"Finance Imogi REST error [{context}]\n"
        f"Status: {resp.status_code}\nResponse: {resp.text[:1000]}",
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
# PUBLIC INTERFACE — otomatis pilih local atau remote
# ──────────────────────────────────────────────────────────────

def imogi_create(doctype: str, data: dict) -> dict:
    """Buat dokumen di Finance Imogi — auto local/remote."""
    if _is_remote():
        return _remote_create(doctype, data)
    return _local_create(doctype, data)


def imogi_get(doctype: str, name: str) -> dict:
    """Ambil dokumen dari Finance Imogi — auto local/remote."""
    if _is_remote():
        return _remote_get(doctype, name)
    return _local_get(doctype, name)


def imogi_update(doctype: str, name: str, data: dict) -> dict:
    """Update dokumen di Finance Imogi — auto local/remote."""
    if _is_remote():
        return _remote_update(doctype, name, data)
    return _local_update(doctype, name, data)


# ──────────────────────────────────────────────────────────────
# DOCTYPE CLASS
# ──────────────────────────────────────────────────────────────

class DeliveryOrderTowing(Document):

    # ── VALIDATE ─────────────────────────────────────────────
    def validate(self):
        self.validate_driver_required_on_assign()
        self.validate_harga_jasa()
        self.set_customer_name()

    def validate_driver_required_on_assign(self):
        if self.status == "Assigned" and not self.driver:
            frappe.throw(_("Driver wajib diisi sebelum status Assigned."))

    def validate_harga_jasa(self):
        if self.harga_jasa is not None and self.harga_jasa <= 0:
            frappe.throw(_("Harga Jasa Towing harus lebih dari 0."))

    def set_customer_name(self):
        if self.customer and not self.customer_name:
            self.customer_name = frappe.db.get_value(
                "Customer", self.customer, "customer_name"
            )

    def _get_sales_order_item_code(self) -> str:
        """Resolve towing item from linked Sales Order (required for PO/SI consistency)."""
        if not self.sales_order:
            frappe.throw(
                _(
                    "Sales Order belum terisi pada Delivery Order Towing. "
                    "Item harus mengikuti item yang di-order."
                ),
                title="Sales Order Wajib Diisi",
            )

        so_item = frappe.db.get_value(
            "Sales Order Item",
            {"parent": self.sales_order},
            "item_code",
        )
        if not so_item:
            frappe.throw(
                _(
                    "Item Sales Order untuk {0} tidak ditemukan. "
                    "Pastikan Sales Order memiliki item sebelum melanjutkan."
                ).format(self.sales_order),
                title="Item Sales Order Tidak Ditemukan",
            )
        return so_item

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
        """Auto-buat invoice ke Finance Imogi saat status pertama kali Done."""
        if self.status == "Done" and not self.sales_invoice:
            self.create_sales_invoice_via_imogi()

    # ──────────────────────────────────────────────────────────
    # INTEGRASI 1: BUAT SALES INVOICE
    # ──────────────────────────────────────────────────────────

    def create_sales_invoice_via_imogi(self):
        """
        Buat Sales Invoice di Finance Imogi.
        Local  → frappe.new_doc() langsung
        Remote → POST /api/resource/Sales Invoice
        """
        if self.sales_invoice:
            return self.sales_invoice

        if not self.customer or not self.harga_jasa:
            frappe.throw(_("Customer dan Harga Jasa wajib diisi sebelum buat invoice."))

        company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )

        item_code = self._get_sales_order_item_code()

        invoice_data = {
            "naming_series"    : "ACC-SINV-.YYYY.-",
            "customer"         : self.customer,
            "company"          : company,
            "posting_date"     : nowdate(),
            "due_date"         : nowdate(),
            "currency"         : self.currency or "IDR",
            "conversion_rate"  : 1,
            "selling_price_list": "Standard Selling",
            "po_no"  : self.name,   # referensi DO Towing
            "remarks": (
                f"DO Towing: {self.name} | "
                f"Nopol: {self.nomor_polisi} | "
                f"Rute: {self.lokasi_pickup or '-'} → {self.lokasi_tujuan or '-'}"
            ),
            "items": [
                {
                    "item_code"  : item_code,
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
            _("✅ Sales Invoice {0} berhasil dibuat di Finance Imogi.").format(
                frappe.bold(invoice_name)
            ),
            title="Invoice Dibuat",
            indicator="green",
        )
        return invoice_name

    # ──────────────────────────────────────────────────────────
    # INTEGRASI: AUTO-CREATE PURCHASE ORDER UANG JALAN
    # ──────────────────────────────────────────────────────────
    def create_po_uang_jalan(self):
        """
        Auto-create Purchase Order uang jalan saat DO di-submit.
        Supplier diambil dari Driver.custom_supplier (logic lama).
        """
        if not self.driver:
            frappe.throw(
                _("Driver wajib diisi sebelum DO bisa di-submit."),
                title="Driver Belum Diisi",
            )

        supplier = frappe.db.get_value("Driver", self.driver, "custom_supplier")
        if not supplier:
            frappe.throw(
                _(
                    "Driver {0} belum punya Supplier (Uang Jalan). "
                    "Buka master Driver dan isi field Supplier terlebih dahulu."
                ).format(self.driver_nama or self.driver),
                title="Driver Belum Punya Supplier",
            )

        company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )

        item_code = self._get_sales_order_item_code()

        # Guard duplikasi: cek PO aktif dengan supplier + nomor rangka yang sama.
        po_filters = {"supplier": supplier, "docstatus": ["!=", 2]}
        if frappe.db.has_column("Purchase Order", "custom_nomor_rangka"):
            po_filters["custom_nomor_rangka"] = self.nomor_rangka or "-"
        existing_po = frappe.db.get_value("Purchase Order", po_filters, "name")
        if existing_po:
            return existing_po

        po_data = {
            "naming_series": "PUR-ORD-.YYYY.-",
            "supplier": supplier,
            "company": company,
            "transaction_date": nowdate(),
            "schedule_date": nowdate(),
            "currency": self.currency or "IDR",
            "ignore_pricing_rule": 1,
            "buying_price_list": "Standard Buying",
            "remarks": (
                f"Uang Jalan DO Towing: {self.name} | "
                f"Nopol: {self.nomor_polisi or '-'} | "
                f"No. Rangka: {self.nomor_rangka or '-'}"
            ),
            "items": [
                {
                    "item_code": item_code,
                    "item_name": f"Uang Jalan - {self.nomor_polisi or '-'}",
                    "description": (
                        f"Uang jalan towing {self.nomor_polisi or '-'} | "
                        f"No. Rangka: {self.nomor_rangka or '-'} | "
                        f"Rute: {self.lokasi_pickup or '-'} -> {self.lokasi_tujuan or '-'}"
                    ),
                    "qty": 1,
                    "rate": 0,
                    "price_list_rate": 0,
                    "uom": "Nos",
                    "schedule_date": nowdate(),
                }
            ],
        }
        if frappe.db.has_column("Purchase Order", "custom_delivery_order"):
            po_data["custom_delivery_order"] = self.name
        if frappe.db.has_column("Purchase Order", "custom_nomor_rangka"):
            po_data["custom_nomor_rangka"] = self.nomor_rangka or "-"

        result = imogi_create("Purchase Order", po_data)
        po_name = result.get("name")
        if not po_name:
            frappe.log_error(
                f"PO response tidak ada name: {json.dumps(result, default=str, indent=2)}",
                "DO Towing: PO uang jalan gagal",
            )
            frappe.throw(_("Purchase Order gagal dibuat. Cek Error Log."))

        if frappe.db.has_column("Delivery Order Towing", "purchase_order_uang_jalan"):
            frappe.db.set_value(
                "Delivery Order Towing",
                self.name,
                "purchase_order_uang_jalan",
                po_name,
                update_modified=False,
            )
        frappe.db.set_value(
            "Delivery Order Towing",
            self.name,
            "uang_jalan_status",
            "Diajukan",
            update_modified=False,
        )
        frappe.db.commit()
        return po_name

    # ──────────────────────────────────────────────────────────
    # INTEGRASI 2: BUAT EXPENSE CLAIM UANG JALAN
    # ──────────────────────────────────────────────────────────

    def create_expense_claim_via_imogi(self, employee: str, amount: float):
        """
        Buat Expense Claim di Finance Imogi.
        Local  → frappe.new_doc() langsung
        Remote → POST /api/resource/Expense Claim

        Args:
            employee : ID employee, contoh "HR-EMP-00001"
            amount   : nominal uang jalan (IDR)
        """
        if self.expense_claim:
            frappe.throw(_("Expense Claim sudah ada: {0}").format(self.expense_claim))

        company = (
            frappe.defaults.get_user_default("Company")
            or frappe.db.get_single_value("Global Defaults", "default_company")
        )

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
                f"Expense Claim response:\n{json.dumps(result, default=str, indent=2)}",
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
            _("✅ Expense Claim {0} berhasil dibuat di Finance Imogi.").format(
                frappe.bold(ec_name)
            ),
            title="Uang Jalan Dibuat",
            indicator="green",
        )
        return ec_name

    # ──────────────────────────────────────────────────────────
    # INTEGRASI 3: SYNC REMARKS KE INVOICE (opsional)
    # ──────────────────────────────────────────────────────────

    def sync_remarks_to_imogi(self):
        """Update remarks di Sales Invoice saat status DO berubah. Non-blocking."""
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
                f"Gagal sync remarks DO {self.name} → invoice {self.sales_invoice}",
                "DO Towing Sync Warning"
            )


# ──────────────────────────────────────────────────────────────
# WHITELISTED ENDPOINTS — dipanggil dari client-side JS
# ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def trigger_create_invoice(do_name: str):
    """Tombol 'Buat Invoice' di form DO Towing."""
    doc = frappe.get_doc("Delivery Order Towing", do_name)
    if doc.status != "Done":
        frappe.throw(_("Invoice hanya bisa dibuat saat status = Done."))
    if doc.sales_invoice:
        return {"status": "already_exists", "invoice": doc.sales_invoice}
    invoice_name = doc.create_sales_invoice_via_imogi()
    return {"status": "created", "invoice": invoice_name}


@frappe.whitelist()
def trigger_create_expense_claim(do_name: str, employee: str, amount: float):
    """Tombol 'Buat Uang Jalan' di form DO Towing."""
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
    """Refresh status invoice dari Finance Imogi — ditampilkan live di form DO."""
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
    """Update status DO dari mobile portal driver."""
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

# ── HOOK FUNCTIONS — dipanggil dari hooks.py ─────────────────

def after_save(doc, method=None):
    instance = DeliveryOrderTowing(doc.doctype, doc.name)
    instance.after_save()

def on_update_after_submit(doc, method=None):
    instance = DeliveryOrderTowing(doc.doctype, doc.name)
    instance.on_update_after_submit()


def _legacy_hook_noop(hook_name: str, doc=None):
    """Keep backward compatibility for legacy hooks still referenced in hooks.py."""
    target = f"{getattr(doc, 'doctype', '-')}/{getattr(doc, 'name', '-')}"
    frappe.logger("imogi_finance").warning(
        "Legacy towing hook '%s' executed as no-op on %s", hook_name, target
    )


def create_do_from_sales_order(doc, method=None):
    """
    Auto-create Delivery Order Towing rows from Sales Order child table `custom_towing_kendaraan`.
    Keeps backward compatibility with existing hook wiring in hooks.py.
    """
    rows = getattr(doc, "custom_towing_kendaraan", None) or []
    if not rows:
        return

    items_by_code = {d.item_code: d for d in (getattr(doc, "items", None) or []) if d.item_code}
    fallback_item = (getattr(doc, "items", None) or [None])[0]

    def _split_route(route_value):
        route = (route_value or "").strip()
        if " - " in route:
            pickup, tujuan = route.split(" - ", 1)
            return pickup.strip(), tujuan.strip()
        return route, route

    created = 0

    for row in rows:
        # Idempotency: if already linked, skip.
        if getattr(row, "delivery_order", None):
            continue

        route_item = getattr(row, "so_item_code", None)
        item_row = items_by_code.get(route_item) or fallback_item
        pickup, tujuan = _split_route(route_item or "")

        # Best-effort duplicate guard by Sales Order + key vehicle identifiers.
        existing_name = frappe.db.get_value(
            "Delivery Order Towing",
            {
                "sales_order": doc.name,
                "nomor_rangka": getattr(row, "nomor_rangka", None) or "",
                "nomor_polisi": getattr(row, "nomor_polisi", None) or "",
            },
            "name",
        )

        if existing_name:
            frappe.db.set_value(
                row.doctype,
                row.name,
                "delivery_order",
                existing_name,
                update_modified=False,
            )
            continue

        harga_jasa = 0
        try:
            harga_jasa = float(getattr(item_row, "rate", 0) or 0)
        except Exception:
            harga_jasa = 0

        if harga_jasa <= 0:
            harga_jasa = 1

        do_doc = frappe.new_doc("Delivery Order Towing")
        do_doc.update(
            {
                "naming_series": "DO-TOW-.YYYY.-.####",
                "status": "Draft",
                "customer": doc.customer,
                "customer_name": doc.customer_name,
                "tanggal_do": doc.transaction_date or nowdate(),
                "sales_order": doc.name,
                "nomor_polisi": getattr(row, "nomor_polisi", None) or route_item or "-",
                "nomor_rangka": getattr(row, "nomor_rangka", None),
                "merk_kendaraan": getattr(item_row, "item_name", None)
                or getattr(item_row, "item_code", None)
                or route_item
                or "-",
                "tipe_kendaraan": getattr(row, "tipe_model", None)
                or getattr(item_row, "description", None)
                or "-",
                "lokasi_pickup": pickup or "-",
                "lokasi_tujuan": tujuan or "-",
                "harga_jasa": harga_jasa,
                "currency": getattr(doc, "currency", None) or "IDR",
            }
        )
        do_doc.insert(ignore_permissions=True)

        frappe.db.set_value(
            row.doctype,
            row.name,
            "delivery_order",
            do_doc.name,
            update_modified=False,
        )
        created += 1

    if created:
        frappe.msgprint(
            _("Berhasil membuat {0} Delivery Order Towing dari Sales Order ini.").format(created),
            alert=True,
        )


def validate_invoice_do_completion(doc, method=None):
    _legacy_hook_noop("validate_invoice_do_completion", doc)


def update_do_payment_status(doc, method=None):
    _legacy_hook_noop("update_do_payment_status", doc)


def on_submit(doc, method=None):
    instance = DeliveryOrderTowing(doc.doctype, doc.name)
    instance.create_po_uang_jalan()


def update_do_from_po(doc, method=None):
    """Sync nominal/status uang jalan DO dari Purchase Order terkait."""
    do_name = None

    if frappe.db.has_column("Purchase Order", "custom_delivery_order"):
        do_name = getattr(doc, "custom_delivery_order", None)

    if not do_name and frappe.db.has_column("Delivery Order Towing", "purchase_order_uang_jalan"):
        do_name = frappe.db.get_value(
            "Delivery Order Towing",
            {"purchase_order_uang_jalan": doc.name},
            "name",
        )

    if not do_name:
        return

    # Nominal mengikuti nilai yang diisi user di PO (rate x qty per row).
    total = sum(
        float(getattr(item, "rate", 0) or 0) * float(getattr(item, "qty", 0) or 0)
        for item in (doc.get("items") or [])
    )

    if doc.docstatus == 1:
        status = "Dibayar"
    elif doc.docstatus == 2:
        status = "Belum Diajukan"
    else:
        status = "Diajukan"

    frappe.db.set_value(
        "Delivery Order Towing",
        do_name,
        {
            "uang_jalan_amount": total,
            "uang_jalan_status": status,
        },
    )