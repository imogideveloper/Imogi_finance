import frappe
from frappe import _
from frappe.utils import flt, nowdate, add_days


@frappe.whitelist()
def set_komisi_override(delivery_order_towing, komisi=None):
    """Simpan nilai komisi manual (override) pada DO Towing.

    Dipakai dari report Rekap Komisi Driver saat user mengubah nilai komisi
    yang tidak selalu sama dengan Towing Commission Rate.
    Kosongkan (None / string kosong) untuk menghapus override dan kembali
    ke nilai rate. Isi 0 tetap dianggap override aktif senilai Rp 0 — beda
    dari "belum di-override".
    """
    if not delivery_order_towing:
        frappe.throw(_("Delivery Order Towing tidak boleh kosong."))

    if not frappe.db.exists("Delivery Order Towing", delivery_order_towing):
        frappe.throw(_("Delivery Order Towing {0} tidak ditemukan.").format(delivery_order_towing))

    is_clearing = komisi is None or str(komisi).strip() == ""
    value = 0.0 if is_clearing else flt(komisi)
    if value < 0:
        frappe.throw(_("Nilai komisi tidak boleh negatif."))

    # Hanya item rute yang ditandai custom_komisi_editable yang boleh diubah manual.
    item_code = frappe.db.get_value(
        "SO Towing Kendaraan", {"delivery_order": delivery_order_towing}, "so_item_code"
    )
    if not item_code or not frappe.db.get_value("Item", item_code, "custom_komisi_editable"):
        frappe.throw(_("Komisi item rute ini tidak bisa diubah manual."))

    # Tolak edit kalau komisi DO ini sudah dibayar (Driver Commission status Paid)
    paid = frappe.db.sql(
        """
        SELECT 1
        FROM `tabDriver Commission Item` dci
        INNER JOIN `tabDriver Commission` dc ON dci.parent = dc.name
        WHERE dci.delivery_order_towing = %(do)s
          AND dc.docstatus != 2
          AND dc.status = 'Paid'
        LIMIT 1
        """,
        {"do": delivery_order_towing},
    )
    if paid:
        frappe.throw(_("Komisi DO ini sudah dibayar (Paid), tidak bisa diubah."))

    frappe.db.set_value(
        "Delivery Order Towing",
        delivery_order_towing,
        {
            "komisi_override": value,
            "komisi_is_override": 0 if is_clearing else 1,
        },
    )
    frappe.db.commit()

    return {"delivery_order_towing": delivery_order_towing, "komisi": value, "is_override": not is_clearing}


@frappe.whitelist()
def create_payment_entry_from_report(do_names, supplier, driver_nama, total_komisi):
    """
    Flow:
    1. Buat Driver Commission (submitted)
    2. Buat Purchase Invoice (submitted) sebagai tagihan komisi
    3. Buat Payment Entry yang references ke PI → status Allocated
    """
    import json

    if isinstance(do_names, str):
        do_names = json.loads(do_names)

    total_komisi = flt(total_komisi)

    if not do_names:
        frappe.throw(_("Tidak ada DO yang dipilih."))
    if not supplier:
        frappe.throw(_("Driver belum memiliki Supplier."))
    if total_komisi <= 0:
        frappe.throw(_("Total komisi harus lebih dari 0."))

    # Resolve company
    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or frappe.db.get_value("Company", {"is_group": 0}, "name")
    )
    if not company:
        frappe.throw(_("Tidak ada Company yang ditemukan."))

    driver    = frappe.db.get_value("Delivery Order Towing", do_names[0], "driver")
    from_date = frappe.db.get_value("Delivery Order Towing", do_names[0], "tanggal_do")
    to_date   = frappe.db.get_value("Delivery Order Towing", do_names[-1], "tanggal_do")

    from imogi_finance.doctype.towing_commission_rate.towing_commission_rate import (
        calc_komisi_amount,
        lookup_towing_commission_rate,
    )

    # ── 1. Buat Driver Commission ────────────────────────────────────────────
    dc = frappe.new_doc("Driver Commission")
    dc.driver       = driver
    dc.driver_nama  = driver_nama
    dc.supplier     = supplier
    dc.company      = company
    dc.posting_date = nowdate()
    dc.from_date    = from_date
    dc.to_date      = to_date
    dc.status       = "Draft"

    computed_total = 0.0
    for do_name in do_names:
        do        = frappe.get_doc("Delivery Order Towing", do_name)
        item_code = frappe.db.get_value(
            "SO Towing Kendaraan", {"delivery_order": do_name}, "so_item_code"
        )
        rate = lookup_towing_commission_rate(item_code, do.tanggal_do) if item_code else None

        komisi_amount = rate_source = rate_type = None
        rate_value    = 0.0
        komisi_amount = 0.0

        if rate:
            rate_source   = rate["name"]
            rate_type     = rate["rate_type"]
            rate_value    = flt(rate["rate_value"])
            komisi_amount = flt(calc_komisi_amount(rate_type, rate_value, do.harga_jasa))

        # Override manual menggantikan nilai dari Towing Commission Rate (jika aktif),
        # termasuk kalau nilainya sengaja 0.
        if do.get("komisi_is_override"):
            komisi_amount = flt(do.get("komisi_override"))

        computed_total += komisi_amount

        dc.append("commissions", {
            "delivery_order_towing": do_name,
            "tanggal_do"           : do.tanggal_do,
            "nomor_polisi"         : do.nomor_polisi,
            "nomor_rangka"         : do.nomor_rangka,
            "so_item_code"         : item_code,
            "lokasi_pickup"        : do.lokasi_pickup,
            "lokasi_tujuan"        : do.lokasi_tujuan,
            "harga_jasa"           : flt(do.harga_jasa),
            "rate_source"          : rate_source,
            "rate_type"            : rate_type,
            "rate_value"           : rate_value,
            "komisi_amount"        : komisi_amount,
        })

    # Pakai total hasil hitung (sudah termasuk override) supaya DC, PI, dan PE konsisten.
    total_komisi    = flt(computed_total) or total_komisi
    dc.total_komisi = total_komisi
    dc.do_count     = len(do_names)
    dc.flags.ignore_permissions = True
    dc.insert(ignore_permissions=True)
    frappe.db.commit()
    # Fetch fresh dari DB sebelum submit
    dc = frappe.get_doc("Driver Commission", dc.name)
    dc.flags.ignore_permissions = True
    dc.submit()
    frappe.db.commit()

    # ── 2. Buat Purchase Invoice sebagai tagihan komisi ──────────────────────
    from imogi_finance.settings.utils import get_driver_commission_expense_account

    expense_account = get_driver_commission_expense_account(company)

    pi = frappe.new_doc("Purchase Invoice")
    pi.supplier         = supplier
    pi.company          = company
    pi.posting_date     = nowdate()
    pi.due_date         = nowdate()
    pi.bill_no          = dc.name
    pi.bill_date        = nowdate()
    pi.remarks          = (
        f"Komisi Driver {driver_nama} | "
        f"Periode: {from_date} s/d {to_date} | "
        f"{len(do_names)} DO | Ref: {dc.name}"
    )
    pi.is_paid          = 0
    pi.append("items", {
        "item_name"       : f"Komisi Driver - {driver_nama}",
        "description"     : (
            f"Komisi towing {driver_nama} periode {from_date} s/d {to_date} "
            f"({len(do_names)} DO)"
        ),
        "qty"             : 1,
        "rate"            : total_komisi,
        "amount"          : total_komisi,
        "expense_account" : expense_account,
        "uom"             : "Nos",
    })
    pi.flags.ignore_permissions = True
    pi.flags.ignore_mandatory   = True
    pi.insert(ignore_permissions=True)
    frappe.db.commit()
    # Fetch fresh dari DB sebelum submit untuk hindari TimestampMismatch
    pi_name = pi.name
    pi = frappe.get_doc("Purchase Invoice", pi_name)
    pi.flags.ignore_permissions = True
    pi.flags.ignore_mandatory   = True
    pi.submit()
    frappe.db.commit()

    # ── 3. Resolve akun untuk Payment Entry ─────────────────────────────────
    default_bank_account = (
        frappe.db.get_value("Company", company, "default_bank_account")
        or frappe.db.get_value("Account", {
            "company": company, "account_type": "Bank", "is_group": 0
        }, "name")
        or frappe.db.get_value("Account", {
            "company": company, "account_type": "Cash", "is_group": 0
        }, "name")
    )

    # Ambil payable account dari PI yang baru dibuat
    payable_account = pi.credit_to

    # ── 4. Buat Payment Entry references ke PI → status Allocated ───────────
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type         = "Pay"
    pe.company              = company
    pe.posting_date         = nowdate()
    pe.party_type           = "Supplier"
    pe.party                = supplier
    pe.paid_amount          = total_komisi
    pe.received_amount      = total_komisi
    pe.source_exchange_rate = 1.0
    pe.target_exchange_rate = 1.0
    pe.reference_no         = dc.name
    pe.reference_date       = nowdate()
    pe.remarks              = (
        f"Komisi Driver {driver_nama} | "
        f"Periode: {from_date} s/d {to_date} | "
        f"{len(do_names)} DO | Ref: {dc.name}"
    )

    if default_bank_account:
        pe.paid_from                  = default_bank_account
        pe.paid_from_account_currency = (
            frappe.db.get_value("Account", default_bank_account, "account_currency") or "IDR"
        )

    if payable_account:
        pe.paid_to                  = payable_account
        pe.paid_to_account_currency = (
            frappe.db.get_value("Account", payable_account, "account_currency") or "IDR"
        )

    # References ke PI → PE jadi Allocated
    pe.append("references", {
        "reference_doctype"  : "Purchase Invoice",
        "reference_name"     : pi.name,
        "bill_no"            : pi.bill_no,
        "due_date"           : pi.due_date,
        "total_amount"       : total_komisi,
        "outstanding_amount" : total_komisi,
        "allocated_amount"   : total_komisi,
    })

    pe.flags.ignore_permissions = True
    pe.insert(ignore_permissions=True)

    # Link PE ke DC
    frappe.db.set_value("Driver Commission", dc.name, "payment_entry", pe.name)
    frappe.db.set_value("Driver Commission", dc.name, "status", "Approved")
    frappe.db.commit()

    return {
        "payment_entry"    : pe.name,
        "purchase_invoice" : pi.name,
        "driver_commission": dc.name,
        "url"              : f"/app/payment-entry/{pe.name}"
    }