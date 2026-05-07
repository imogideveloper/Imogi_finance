import frappe
from frappe import _
from frappe.utils import flt, nowdate


@frappe.whitelist()
def create_payment_entry_from_report(do_names, supplier, driver_nama, total_komisi):
    """
    Buat Driver Commission + Payment Entry (draft) dari Rekap Komisi Driver report.
    """
    import json

    if isinstance(do_names, str):
        do_names = json.loads(do_names)

    total_komisi = flt(total_komisi)

    if not do_names:
        frappe.throw(_("Tidak ada DO yang dipilih."))
    if not supplier:
        frappe.throw(_("Driver belum memiliki Supplier. Isi field Supplier di master Driver."))
    if total_komisi <= 0:
        frappe.throw(_("Total komisi harus lebih dari 0."))

    # Resolve company
    company = (
        frappe.defaults.get_user_default("Company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or frappe.db.get_value("Company", {"is_group": 0}, "name")
    )
    if not company:
        frappe.throw(_("Tidak ada Company yang ditemukan. Buat Company terlebih dahulu."))

    # Ambil driver dari DO pertama
    driver = frappe.db.get_value("Delivery Order Towing", do_names[0], "driver")
    from_date = frappe.db.get_value("Delivery Order Towing", do_names[0], "tanggal_do")
    to_date = frappe.db.get_value("Delivery Order Towing", do_names[-1], "tanggal_do")

    # Import helpers
    from imogi_finance.doctype.towing_commission_rate.towing_commission_rate import (
        calc_komisi_amount,
        lookup_towing_commission_rate,
    )

    # Buat Driver Commission
    dc = frappe.new_doc("Driver Commission")
    dc.driver = driver
    dc.driver_nama = driver_nama
    dc.supplier = supplier
    dc.company = company
    dc.posting_date = nowdate()
    dc.from_date = from_date
    dc.to_date = to_date
    dc.status = "Draft"

    for do_name in do_names:
        do = frappe.get_doc("Delivery Order Towing", do_name)
        item_code = frappe.db.get_value(
            "SO Towing Kendaraan", {"delivery_order": do_name}, "so_item_code"
        )
        rate = lookup_towing_commission_rate(item_code, do.tanggal_do) if item_code else None

        komisi_amount = 0.0
        rate_source = rate_type = None
        rate_value = 0.0

        if rate:
            rate_source = rate["name"]
            rate_type = rate["rate_type"]
            rate_value = flt(rate["rate_value"])
            komisi_amount = flt(calc_komisi_amount(rate_type, rate_value, do.harga_jasa))

        dc.append("commissions", {
            "delivery_order_towing": do_name,
            "tanggal_do": do.tanggal_do,
            "nomor_polisi": do.nomor_polisi,
            "nomor_rangka": do.nomor_rangka,
            "so_item_code": item_code,
            "lokasi_pickup": do.lokasi_pickup,
            "lokasi_tujuan": do.lokasi_tujuan,
            "harga_jasa": flt(do.harga_jasa),
            "rate_source": rate_source,
            "rate_type": rate_type,
            "rate_value": rate_value,
            "komisi_amount": komisi_amount,
        })

    dc.total_komisi = total_komisi
    dc.do_count = len(do_names)
    dc.flags.ignore_permissions = True
    dc.insert(ignore_permissions=True)

    # Submit DC
    dc.reload()
    dc.submit()

    # Ambil akun default dari Company
    default_bank_account = (
        frappe.db.get_value("Company", company, "default_bank_account")
        or frappe.db.get_value("Account", {
            "company": company,
            "account_type": "Bank",
            "is_group": 0
        }, "name")
        or frappe.db.get_value("Account", {
            "company": company,
            "account_type": "Cash",
            "is_group": 0
        }, "name")
    )

    payable_account = (
        frappe.db.get_value("Company", company, "default_payable_account")
        or frappe.db.get_value("Account", {
            "company": company,
            "account_type": "Payable",
            "is_group": 0
        }, "name")
    )

    # Buat Payment Entry (draft — user perlu set akun lalu submit)
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Pay"
    pe.company = company
    pe.posting_date = nowdate()
    pe.party_type = "Supplier"
    pe.party = supplier
    pe.paid_amount = total_komisi
    pe.received_amount = total_komisi
    pe.source_exchange_rate = 1.0
    pe.target_exchange_rate = 1.0
    pe.reference_no = dc.name
    pe.reference_date = nowdate()
    pe.remarks = (
        f"Komisi Driver {driver_nama} | "
        f"Periode: {from_date} s/d {to_date} | "
        f"{len(do_names)} DO | Ref: {dc.name}"
    )

    if default_bank_account:
        pe.paid_from = default_bank_account
        pe.paid_from_account_currency = frappe.db.get_value(
            "Account", default_bank_account, "account_currency"
        ) or "IDR"

    if payable_account:
        pe.paid_to = payable_account
        pe.paid_to_account_currency = frappe.db.get_value(
            "Account", payable_account, "account_currency"
        ) or "IDR"

    pe.flags.ignore_permissions = True
    pe.insert(ignore_permissions=True)

    # Link PE ke DC
    frappe.db.set_value("Driver Commission", dc.name, "payment_entry", pe.name)
    frappe.db.commit()

    return {
        "payment_entry": pe.name,
        "driver_commission": dc.name,
        "url": f"/app/payment-entry/{pe.name}"
    }