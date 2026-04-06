import frappe


def set_tax_invoice_display_fields(doc, method=None):
    # isi tanggal faktur pajak
    if not getattr(doc, "custom_tanggal_faktur_pajak", None):
        for fieldname in ["ti_fp_date", "tax_invoice_date", "invoice_date"]:
            value = getattr(doc, fieldname, None)
            if value:
                doc.custom_tanggal_faktur_pajak = value
                break

    # isi supplier
    if not getattr(doc, "custom_display_supplier_text", None):
        for fieldname in ["supplier", "supplier_name", "vendor", "party_name"]:
            value = getattr(doc, fieldname, None)
            if value:
                doc.custom_display_supplier_text = value
                break

    # isi status default
    if not getattr(doc, "custom_fp_status", None):
        doc.custom_fp_status = "Available"


def sync_tax_invoice_from_expense(doc, method=None):
    tax_invoice_name = doc.get("custom_tax_invoice_ocr_upload") or doc.get("ti_tax_invoice_upload")
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    frappe.db.set_value(
        "Tax Invoice OCR Upload",
        tax_invoice_name,
        {
            "custom_display_supplier_text": doc.get("supplier"),
            "custom_tanggal_faktur_pajak": doc.get("ti_fp_date") or doc.get("request_date"),
            "custom_used_in": doc.name,
            "custom_fp_status": "Used",
        },
        update_modified=False,
    )


def release_tax_invoice_on_cancel(doc, method=None):
    tax_invoice_name = doc.get("custom_tax_invoice_ocr_upload") or doc.get("ti_tax_invoice_upload")
    if not tax_invoice_name:
        return

    if not frappe.db.exists("Tax Invoice OCR Upload", tax_invoice_name):
        return

    frappe.db.set_value(
        "Tax Invoice OCR Upload",
        tax_invoice_name,
        {
            "custom_used_in": None,
            "custom_fp_status": "Available",
        },
        update_modified=False,
    )

def auto_link_to_sales_invoice(doc, method=None):
    """
    Dipanggil saat Tax Invoice OCR Upload di-save (after_save).
    Jika OCR sudah Done dan status masih Available, cari Sales Invoice
    yang cocok lalu link otomatis.

    Matching priority:
    1. Nomor Faktur Pajak (fp_no) cocok dengan out_fp_no di Sales Invoice
    2. Fallback: NPWP + DPP + PPN + posting_date dalam bulan yang sama
    """
    # Guard: hanya jalan jika OCR selesai dan belum dipakai
    if doc.ocr_status != "Done":
        return
    if doc.custom_fp_status not in ("Available", None, ""):
        return
    if not doc.fp_no:
        return

    sinv_name = None

    # --- Matching 1: berdasarkan nomor faktur pajak ---
    match_by_fp_no = frappe.db.get_value(
        "Sales Invoice",
        {
            "out_fp_no": doc.fp_no,
            "out_fp_tax_invoice_upload": ("is", "not set"),
            "docstatus": 1,
        },
        "name",
    )
    if match_by_fp_no:
        sinv_name = match_by_fp_no

    # --- Matching 2: fallback NPWP + DPP + PPN ---
    # Tanggal tidak difilter ketat karena faktur pajak bisa diupload
    # berhari-hari setelah invoice dibuat.
    # Jika ada lebih dari 1 kandidat, ambil yang posting_date paling dekat fp_date.
    if not sinv_name and doc.npwp and doc.dpp:
        import datetime

        candidates = frappe.db.get_all(
            "Sales Invoice",
            filters={
                "tax_id": doc.npwp,
                "out_fp_dpp": doc.dpp,
                "out_fp_ppn": doc.ppn,
                "out_fp_tax_invoice_upload": ("is", "not set"),
                "docstatus": 1,
            },
            fields=["name", "posting_date"],
            order_by="posting_date desc",
        )

        if len(candidates) == 1:
            sinv_name = candidates[0]["name"]
        elif len(candidates) > 1:
            fp_date = doc.custom_tanggal_faktur_pajak or doc.fp_date
            if fp_date:
                if isinstance(fp_date, str):
                    fp_date = datetime.date.fromisoformat(str(fp_date))
                best = min(
                    candidates,
                    key=lambda x: abs((x["posting_date"] - fp_date).days)
                )
                sinv_name = best["name"]
            else:
                sinv_name = candidates[0]["name"]

    if not sinv_name:
        return

    # Update Sales Invoice — isi semua field Output Tax Invoice
    fp_date = doc.custom_tanggal_faktur_pajak or doc.fp_date
    frappe.db.set_value(
        "Sales Invoice",
        sinv_name,
        {
            "out_fp_tax_invoice_upload": doc.name,
            "out_fp_no":               doc.fp_no,
            "out_fp_date":             fp_date,
            "out_fp_dpp":              doc.dpp,
            "out_fp_ppn":              doc.ppn,
            "out_fp_customer_npwp":    doc.npwp,
            "out_fp_npwp_match":       1,
            "out_fp_status":           "Verified",
            "out_fp_tax_invoice_pdf":  doc.tax_invoice_pdf,
            "synch_status":            "Synced",
        },
        update_modified=False,
    )

    # Update status OCR Upload → Used
    frappe.db.set_value(
        "Tax Invoice OCR Upload",
        doc.name,
        {
            "custom_fp_status": "Used",
            "custom_used_in":   sinv_name,
        },
        update_modified=False,
    )

    frappe.msgprint(
        f"✅ Faktur Pajak <b>{doc.fp_no}</b> otomatis ter-link ke Sales Invoice <b>{sinv_name}</b>",
        alert=True,
    )
