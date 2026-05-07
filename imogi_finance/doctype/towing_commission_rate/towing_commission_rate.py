import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate


class TowingCommissionRate(Document):
    def validate(self):
        self._auto_fill_lokasi()
        self._validate_dates()
        self._validate_rate_value()
        self._validate_no_active_overlap()

    def _auto_fill_lokasi(self):
        """Auto-fill lokasi dari item_name jika format 'Pickup - Tujuan'."""
        if not self.item:
            return

        item_name = frappe.db.get_value("Item", self.item, "item_name") or self.item
        if " - " not in item_name:
            return

        parts = item_name.split(" - ", 1)
        pickup = parts[0].strip()
        tujuan = parts[1].strip()

        # Isi jika kosong ATAU berisi nilai placeholder '-'
        if not self.lokasi_pickup or self.lokasi_pickup.strip() in ('', '-'):
            self.lokasi_pickup = pickup
        if not self.lokasi_tujuan or self.lokasi_tujuan.strip() in ('', '-'):
            self.lokasi_tujuan = tujuan

    def _validate_dates(self):
        if self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
            frappe.throw(_("Berlaku Sampai tidak boleh lebih awal dari Berlaku Dari."))

    def _validate_rate_value(self):
        if flt(self.rate_value) <= 0:
            frappe.throw(_("Nilai komisi harus lebih dari 0."))
        if self.rate_type == "Percent" and flt(self.rate_value) > 100:
            frappe.throw(_("Nilai Percent tidak boleh lebih dari 100."))

    def _validate_no_active_overlap(self):
        if not self.is_active:
            return

        params = {
            "item": self.item,
            "name": self.name or "",
            "eff_from": self.effective_from,
            "eff_to": self.effective_to or "9999-12-31",
        }
        rows = frappe.db.sql(
            """
            SELECT name, effective_from, effective_to
            FROM `tabTowing Commission Rate`
            WHERE item = %(item)s
              AND is_active = 1
              AND name != %(name)s
              AND effective_from <= %(eff_to)s
              AND (effective_to IS NULL OR effective_to = '' OR effective_to >= %(eff_from)s)
            LIMIT 1
            """,
            params,
            as_dict=True,
        )
        if rows:
            frappe.throw(
                _("Sudah ada Towing Commission Rate aktif untuk Item {0} pada periode tersebut: {1}").format(
                    frappe.bold(self.item), rows[0].name
                )
            )


def lookup_towing_commission_rate(item_code: str, posting_date: str | None = None):
    """
    Cari Towing Commission Rate aktif untuk Item & tanggal tertentu.
    Mengembalikan dict (name, rate_type, rate_value, currency) atau None.
    """
    if not item_code:
        return None

    today = posting_date or nowdate()
    rows = frappe.db.sql(
        """
        SELECT name, rate_type, rate_value, currency, item, lokasi_pickup, lokasi_tujuan
        FROM `tabTowing Commission Rate`
        WHERE item = %s
          AND is_active = 1
          AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to = '' OR effective_to >= %s)
        ORDER BY effective_from DESC, modified DESC
        LIMIT 1
        """,
        (item_code, today, today),
        as_dict=True,
    )
    return rows[0] if rows else None


def calc_komisi_amount(rate_type: str, rate_value: float, harga_jasa: float) -> float:
    """Hitung komisi sesuai tipe."""
    rate_value = flt(rate_value)
    if rate_type == "Flat":
        return rate_value
    if rate_type == "Percent":
        return flt(harga_jasa) * rate_value / 100.0
    return 0.0


@frappe.whitelist()
def get_rate_for_item(item_code: str, posting_date: str | None = None):
    """Whitelisted: buat client script preview."""
    return lookup_towing_commission_rate(item_code, posting_date)