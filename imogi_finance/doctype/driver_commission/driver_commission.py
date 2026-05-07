import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate

from imogi_finance.doctype.towing_commission_rate.towing_commission_rate import (
    calc_komisi_amount,
    lookup_towing_commission_rate,
)


ELIGIBLE_DO_STATUS = ("Delivered",)


class DriverCommission(Document):
    def validate(self):
        self._validate_period()
        self._validate_no_duplicate_do()
        self._recompute_totals()

    def before_submit(self):
        if not self.commissions:
            frappe.throw(_("Tidak ada baris komisi. Klik Generate dulu."))
        if flt(self.total_komisi) <= 0:
            frappe.throw(_("Total Komisi harus lebih dari 0."))
        self.status = "Approved"

    def on_submit(self):
        pass

    def on_update_after_submit(self):
        if self.status == "Cancelled":
            self.flags.ignore_permissions = True

    def on_cancel(self):
        self.status = "Cancelled"
        if self.payment_entry:
            pe_status = frappe.db.get_value("Payment Entry", self.payment_entry, "docstatus")
            if pe_status == 1:
                frappe.throw(
                    _("Payment Entry {0} masih aktif. Cancel Payment Entry dulu sebelum cancel Driver Commission.").format(
                        self.payment_entry
                    )
                )

    def _validate_period(self):
        if getdate(self.to_date) < getdate(self.from_date):
            frappe.throw(_("Sampai Tanggal tidak boleh lebih awal dari Dari Tanggal."))

    def _validate_no_duplicate_do(self):
        seen = set()
        for row in self.commissions:
            if not row.delivery_order_towing:
                continue
            if row.delivery_order_towing in seen:
                frappe.throw(_("DO Towing {0} duplikat di tabel komisi.").format(row.delivery_order_towing))
            seen.add(row.delivery_order_towing)

    def _recompute_totals(self):
        self.do_count = len(self.commissions or [])
        self.total_komisi = sum(flt(r.komisi_amount) for r in (self.commissions or []))


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _used_do_names(exclude_name: str | None = None):
    """DO Towing yang sudah dipakai di Driver Commission lain (status != Cancelled)."""
    rows = frappe.db.sql(
        """
        SELECT DISTINCT dci.delivery_order_towing
        FROM `tabDriver Commission Item` dci
        INNER JOIN `tabDriver Commission` dc ON dci.parent = dc.name
        WHERE COALESCE(dc.status, '') != 'Cancelled'
          AND dc.docstatus != 2
          AND IFNULL(dci.delivery_order_towing, '') != ''
          AND dc.name != %s
        """,
        (exclude_name or "",),
    )
    return {r[0] for r in rows}


def _get_route_item_for_do(do_name: str):
    """Ambil so_item_code dari SO Towing Kendaraan yang link ke DO ini."""
    return frappe.db.get_value(
        "SO Towing Kendaraan", {"delivery_order": do_name}, "so_item_code"
    )


def _resolve_lokasi_from_item(item_code: str):
    if not item_code:
        return None, None
    pickup = frappe.db.get_value("Item", item_code, "custom_lokasi_pickup")
    tujuan = frappe.db.get_value("Item", item_code, "custom_lokasi_tujuan")
    return pickup, tujuan


# ──────────────────────────────────────────────────────────────
# Whitelisted endpoints
# ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def fetch_eligible_dos(driver: str, from_date: str, to_date: str, exclude_name: str | None = None):
    """Return list dict of eligible DOs with computed commission preview."""
    if not (driver and from_date and to_date):
        frappe.throw(_("Driver, From Date, dan To Date wajib diisi."))

    used = _used_do_names(exclude_name=exclude_name)

    dos = frappe.get_all(
        "Delivery Order Towing",
        filters={
            "driver": driver,
            "status": ("in", ELIGIBLE_DO_STATUS),
            "tanggal_do": ("between", [from_date, to_date]),
            "docstatus": ("!=", 2),
        },
        fields=[
            "name",
            "tanggal_do",
            "nomor_polisi",
            "nomor_rangka",
            "kendaraan_towing",
            "harga_jasa",
            "lokasi_pickup",
            "lokasi_tujuan",
        ],
        order_by="tanggal_do asc, name asc",
    )

    rows = []
    for do in dos:
        if do.name in used:
            continue

        item_code = _get_route_item_for_do(do.name)
        pickup, tujuan = _resolve_lokasi_from_item(item_code)
        rate = lookup_towing_commission_rate(item_code, do.tanggal_do) if item_code else None

        komisi = 0.0
        notes = ""
        rate_source = rate_type = None
        rate_value = 0.0
        if not item_code:
            notes = "Item rute tidak ditemukan di SO Towing Kendaraan"
        elif not rate:
            notes = "Rate tidak ditemukan / tidak aktif untuk tanggal ini"
        else:
            rate_source = rate["name"]
            rate_type = rate["rate_type"]
            rate_value = flt(rate["rate_value"])
            komisi = flt(calc_komisi_amount(rate_type, rate_value, do.harga_jasa))

        rows.append(
            {
                "delivery_order_towing": do.name,
                "tanggal_do": do.tanggal_do,
                "nomor_polisi": do.nomor_polisi,
                "nomor_rangka": do.nomor_rangka,
                "kendaraan_towing": do.kendaraan_towing,
                "so_item_code": item_code,
                "lokasi_pickup": pickup or do.lokasi_pickup,
                "lokasi_tujuan": tujuan or do.lokasi_tujuan,
                "harga_jasa": flt(do.harga_jasa),
                "rate_source": rate_source,
                "rate_type": rate_type,
                "rate_value": rate_value,
                "komisi_amount": komisi,
                "notes": notes,
            }
        )

    return rows


@frappe.whitelist()
def make_payment_entry(name: str, mode_of_payment: str | None = None, paid_from: str | None = None):
    """Buat Payment Entry (Pay) ke Supplier driver. Tidak men-submit otomatis."""
    dc = frappe.get_doc("Driver Commission", name)

    if dc.docstatus != 1:
        frappe.throw(_("Driver Commission harus di-Submit (Approved) terlebih dahulu."))
    if dc.status not in ("Approved",):
        frappe.throw(_("Driver Commission status harus Approved untuk membuat Payment Entry."))
    if dc.payment_entry:
        frappe.throw(_("Payment Entry sudah dibuat: {0}").format(dc.payment_entry))
    if not dc.supplier:
        frappe.throw(_("Driver belum punya Supplier (Uang Jalan)."))
    if flt(dc.total_komisi) <= 0:
        frappe.throw(_("Total Komisi harus lebih dari 0."))

    company = dc.company or frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )
    if not company:
        frappe.throw(_("Company belum diset."))

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Pay"
    pe.company = company
    pe.posting_date = nowdate()
    pe.party_type = "Supplier"
    pe.party = dc.supplier
    pe.paid_amount = flt(dc.total_komisi)
    pe.received_amount = flt(dc.total_komisi)
    pe.source_exchange_rate = 1.0
    pe.target_exchange_rate = 1.0
    pe.reference_no = dc.name
    pe.reference_date = nowdate()
    pe.remarks = (
        f"Komisi Driver {dc.driver_nama or dc.driver} | "
        f"Periode: {dc.from_date} s/d {dc.to_date} | "
        f"Ref: {dc.name}"
    )

    if mode_of_payment:
        pe.mode_of_payment = mode_of_payment
    if paid_from:
        pe.paid_from = paid_from

    if hasattr(pe, "imogi_driver_commission"):
        pe.imogi_driver_commission = dc.name

    pe.flags.ignore_permissions = True
    pe.insert(ignore_permissions=True)

    frappe.db.set_value("Driver Commission", dc.name, "payment_entry", pe.name)
    frappe.db.commit()

    return {"name": pe.name}


def mark_paid_on_payment_submit(payment_entry_doc, method=None):
    """Hook Payment Entry on_submit: jika PE terhubung ke Driver Commission, set status Paid."""
    if not payment_entry_doc:
        return

    dc_name = getattr(payment_entry_doc, "imogi_driver_commission", None)
    if not dc_name:
        dc_name = frappe.db.get_value(
            "Driver Commission", {"payment_entry": payment_entry_doc.name, "docstatus": 1}, "name"
        )
    if not dc_name:
        return

    frappe.db.set_value(
        "Driver Commission",
        dc_name,
        {"status": "Paid", "payment_entry": payment_entry_doc.name},
    )


def revert_paid_on_payment_cancel(payment_entry_doc, method=None):
    """Hook Payment Entry on_cancel: kembalikan Driver Commission ke Approved."""
    if not payment_entry_doc:
        return

    dc_name = getattr(payment_entry_doc, "imogi_driver_commission", None) or frappe.db.get_value(
        "Driver Commission", {"payment_entry": payment_entry_doc.name}, "name"
    )
    if not dc_name:
        return

    dc_status = frappe.db.get_value("Driver Commission", dc_name, "status")
    if dc_status == "Paid":
        frappe.db.set_value("Driver Commission", dc_name, "status", "Approved")
