# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance.imogi_finance.parsers.normalization import normalize_identifier_digits
from imogi_finance.tax_invoice_ocr import (
    detect_nilai_lain_factor,
    get_ppn_template_from_type,
)


def _is_valid_fp_length(value: str, expected_fp_no: str | None = None) -> bool:
    if expected_fp_no:
        return len(value) == len(normalize_identifier_digits(expected_fp_no) or "")
    return len(value) in (16, 17)


def _extract_fp_number_from_ocr(ocr_text: str, expected_fp_no: str | None = None) -> str | None:
    """Extract tax invoice number from OCR text with context-aware filtering.

    Prevents false positives where 16-digit NPWP is detected as FP number.
    """
    if not ocr_text:
        return None

    expected_normalized = normalize_identifier_digits(expected_fp_no) or ""

    # Highest confidence: number explicitly labeled as Faktur/NSFP.
    labeled_patterns = [
        r"(?:Kode\s+dan\s+Nomor\s+Seri\s+Faktur\s+Pajak|Nomor\s+Seri\s+Faktur\s+Pajak|Nomor\s+Faktur\s+Pajak|NSFP|Faktur\s+Pajak|Nomor|No\.?)[:\s]*([0-9.\s-]{16,24})",
    ]
    for pattern in labeled_patterns:
        matches = re.findall(pattern, ocr_text, re.IGNORECASE)
        for match in matches:
            normalized = normalize_identifier_digits(match) or ""
            if _is_valid_fp_length(normalized, expected_fp_no=expected_fp_no):
                return normalized

    # Fallback: generic 16-digit candidate with local context scoring.
    candidate_pattern = re.compile(r"\b(\d{3}[.\s-]?\d{3}[.\s-]?\d{2}[.\s-]?\d{8,9})\b")
    candidates: list[tuple[int, str]] = []
    for m in candidate_pattern.finditer(ocr_text):
        candidate = m.group(1)
        normalized = normalize_identifier_digits(candidate) or ""
        if not _is_valid_fp_length(normalized, expected_fp_no=expected_fp_no):
            continue

        start, end = m.span(1)
        context = ocr_text[max(0, start - 80): min(len(ocr_text), end + 80)].lower()

        score = 0
        if any(k in context for k in ("faktur", "nomor seri", "nomor faktur", "nsfp", "tax invoice")):
            score += 5
        if "npwp" in context:
            score -= 6

        if expected_normalized:
            if normalized == expected_normalized:
                score += 20
            elif normalized[:3] == expected_normalized[:3]:
                score += 2

        candidates.append((score, normalized))

    if not candidates:
        return None

    best_score, best_value = max(candidates, key=lambda item: item[0])
    return best_value if best_score > 0 else None


def _resolve_tax_invoice_type(fp_no: str | None) -> tuple[str | None, str | None]:
    if not fp_no:
        return None, None

    digits = re.sub(r"\D", "", str(fp_no))
    if len(digits) < 3:
        return None, None

    prefix = digits[:3]
    type_row = frappe.db.get_value(
        "Tax Invoice Type",
        prefix,
        ["name", "transaction_description", "status_description"],
        as_dict=True,
    )
    if not type_row:
        return None, None

    description_parts = [type_row.transaction_description, type_row.status_description]
    description = " - ".join([part for part in description_parts if part])
    return type_row.name, description or type_row.transaction_description


class TaxInvoiceOCRUpload(Document):
    def validate(self):
        # 🔥 CRITICAL FIX: Skip ALL validation if this is OCR background job save
        # This prevents verification_notes from being overwritten with auto-generated
        # verification messages when OCR is saving parsed JSON data to ocr_summary_json
        if self.flags.get("ignore_validate"):
            return

        # 🆕 Normalize ppn_type to simplified format if legacy value detected
        if self.ppn_type:
            self.ppn_type = self._normalize_ppn_type_value(self.ppn_type)

        # Original validation logic continues...
        # Only runs on USER-initiated saves (from UI or API)

        if not self.fp_no:
            frappe.throw(_("Tax Invoice Number is required."))
        if not self.tax_invoice_pdf:
            frappe.throw(_("Faktur Pajak PDF is required."))

        # 🆕 PPN Type is now REQUIRED - user must select before saving.
        # Exception: post_ocr_validate flag means this is called from background OCR job;
        # user has not had a chance to select ppn_type yet → skip throw, add note instead.
        if not self.ppn_type:
            if self.flags.get("post_ocr_validate"):
                # OCR job: inform user via verification_notes, not throw
                frappe.logger().info(
                    f"[VALIDATE] {self.name}: ppn_type kosong setelah OCR — "
                    "user perlu memilih PPN Type secara manual."
                )
            else:
                frappe.throw(_(
                    "PPN Type wajib dipilih. "
                    "Pilih tipe PPN yang sesuai berdasarkan faktur pajak Anda "
                    "(contoh: Standard 11%, Standard 12%, Zero Rated, dll.)."
                ))

        # 🔥 NILAI LAIN DETECTION: Check if DPP calculation indicates Nilai Lain scenario.
        # Returns a note string to be included in verification_notes_parts (not written directly).
        nilai_lain_note = self._detect_and_suggest_nilai_lain()

        tax_invoice_type, type_description = _resolve_tax_invoice_type(self.fp_no)
        self.tax_invoice_type = tax_invoice_type
        self.tax_invoice_type_description = type_description

        # 🆕 Auto-lookup PPN Template from ppn_type + company
        # Uses get_ppn_template_from_type() which scans Purchase Taxes and Charges Template
        # by matching the VAT rate on tax rows against the expected rate for the PPN Type.
        if self.ppn_type:
            company = self.company or frappe.defaults.get_user_default("Company")
            if company:
                try:
                    matched_template = get_ppn_template_from_type(
                        self.ppn_type, company, template_type="Purchase"
                    )
                    self.recommended_ppn_template = matched_template or None
                except Exception:
                    self.recommended_ppn_template = None
            else:
                self.recommended_ppn_template = None
        else:
            self.recommended_ppn_template = None

        # 🆕 Cross-check Tax Invoice Type vs PPN Type
        ppn_type_match = False
        if self.ppn_type:
            if not self.tax_invoice_type:
                # FP prefix not found in Tax Invoice Type master.
                # Cannot cross-check, but don't penalise user — master may not be configured.
                # ppn_amount_match (below) is the real guard for amount accuracy.
                ppn_type_match = True
                frappe.logger().info(
                    f"[VALIDATE] {self.name}: Tax Invoice Type tidak ditemukan dari prefix FP "
                    f"'{(self.fp_no or '')[:3]}' — lewati cross-check, andalkan ppn_amount_match."
                )
            else:
                try:
                    invoice_type_doc = frappe.get_doc("Tax Invoice Type", self.tax_invoice_type)
                    is_valid, warning_message = invoice_type_doc.matches_ppn_type(self.ppn_type)

                    if is_valid:
                        # ✅ PPN Type matches Tax Invoice Type master
                        ppn_type_match = True
                    elif warning_message:
                        # ⚠️ Mismatch — show warning but don't block save
                        frappe.msgprint(
                            msg=warning_message,
                            title=_("PPN Type Verification Warning"),
                            indicator="orange"
                        )
                except frappe.DoesNotExistError:
                    # Tax Invoice Type exists as reference but no master record.
                    # Treat as unconfigured — don't block auto-verify.
                    ppn_type_match = True
                    frappe.logger().warning(
                        f"[VALIDATE] {self.name}: Tax Invoice Type '{self.tax_invoice_type}' "
                        "tidak ada di master — lewati cross-check (master belum dikonfigurasi)."
                    )

        # 🆕 Cross-check FP Number: Compare doctype fp_no (autoname) vs OCR extracted fp_no
        # ⚠️ CRITICAL: fp_no is autoname (document name), cannot be changed after save
        fp_no_match = False
        ocr_fp_no = None

        # Only validate if OCR has run (ocr_text exists)
        if self.ocr_text:
            ocr_fp_no = _extract_fp_number_from_ocr(self.ocr_text, expected_fp_no=self.fp_no)

            # Normalize both for comparison (remove dots, spaces, dashes)
            if ocr_fp_no:
                fp_normalized = normalize_identifier_digits(self.fp_no) or ""
                ocr_normalized = normalize_identifier_digits(ocr_fp_no) or ""

                if fp_normalized == ocr_normalized:
                    fp_no_match = True
            else:
                # Fallback: simple substring check
                fp_normalized = normalize_identifier_digits(self.fp_no) or ""
                ocr_text_normalized = re.sub(r'\D', '', self.ocr_text or "")

                if fp_normalized in ocr_text_normalized:
                    fp_no_match = True
                    ocr_fp_no = self.fp_no  # Assumed match

        # 🆕 Auto-set verification status based on multiple checks
        verification_notes_parts = []

        # ALWAYS show basic info first
        verification_notes_parts.append(f"📄 FP Number: {self.fp_no}")
        if self.fp_date:
            verification_notes_parts.append(f"📅 FP Date: {self.fp_date}")
        if self.npwp:
            verification_notes_parts.append(f"🏢 NPWP: {self.npwp}")

        # ALWAYS show amounts
        verification_notes_parts.append("")
        verification_notes_parts.append(f"Harga Jual: Rp {self.harga_jual:,.2f}" if self.harga_jual else "Harga Jual: Not set")
        verification_notes_parts.append(f"DPP: Rp {self.dpp:,.2f}" if self.dpp else "DPP: Not set")
        verification_notes_parts.append(f"PPN: Rp {self.ppn:,.2f}" if self.ppn is not None else "PPN: Not set")
        if self.ppnbm:
            verification_notes_parts.append(f"PPnBM: Rp {self.ppnbm:,.2f}")

        # Include Nilai Lain note if detected (returned from helper, not self.verification_notes)
        if nilai_lain_note:
            verification_notes_parts.append("")
            verification_notes_parts.append(nilai_lain_note)

        # Show recommended PPN template if found
        if self.recommended_ppn_template:
            verification_notes_parts.append("")
            verification_notes_parts.append(
                f"💡 Recommended PPN Template: {self.recommended_ppn_template}\n"
                f"   → Template ini akan otomatis di-copy ke field PPN Template\n"
                f"     di Expense Request saat Anda Save/Submit ER dengan OCR ini\n"
                f"     (jika field PPN Template masih kosong)."
            )
        elif self.ppn_type:
            verification_notes_parts.append("")
            verification_notes_parts.append(
                f"⚠️ Tidak ada template ditemukan untuk PPN Type '{self.ppn_type}'.\n"
                f"   → Konfigurasi mapping di: Tax Invoice OCR Settings → PPN Template Mappings.\n"
                f"   → Atau pilih template secara manual di Expense Request."
            )

        verification_notes_parts.append("")

        # Validation checks section
        verification_notes_parts.append("🔍 VALIDATION CHECKS:")

        if ppn_type_match:
            verification_notes_parts.append("   ✅ PPN Type matches Tax Invoice Type")
        elif not self.ppn_type:
            # Derive a PPN type suggestion from OCR-detected tax_rate or from amounts
            suggested_type = None
            detected_rate = None

            if self.tax_rate and float(self.tax_rate) > 0:
                detected_rate = float(self.tax_rate)
            elif self.dpp and self.ppn is not None and float(self.dpp) > 0:
                ppn_val = float(self.ppn or 0)
                dpp_val = float(self.dpp)
                if ppn_val == 0:
                    detected_rate = 0.0
                else:
                    detected_rate = round(ppn_val / dpp_val, 4)

            if detected_rate is not None:
                if detected_rate == 0:
                    suggested_type = "Zero Rated"
                elif abs(detected_rate - 0.12) <= 0.02 or abs(detected_rate - 0.11) <= 0.02:
                    # Standard rate covers both 11% and 12%
                    suggested_type = "Standard"
                elif abs(detected_rate - 0.011) <= 0.005:
                    # Digital services - treat as Standard for now
                    suggested_type = "Standard"
                else:
                    # Other rates - suggest Exempt/Not PPN for review
                    suggested_type = "Exempt/Not PPN"

            if suggested_type and detected_rate is not None:
                verification_notes_parts.append(
                    f"   \u26a0\ufe0f PPN Type belum dipilih.\n"
                    f"      \u2192 OCR mendeteksi tarif PPN \u2248 {detected_rate:.2%}.\n"
                    f"      \u2192 Disarankan pilih PPN Type: '{suggested_type}'.\n"
                    f"      \u2192 Periksa faktur pajak fisik sebelum menyimpan."
                )
            else:
                verification_notes_parts.append(
                    "   \u26a0\ufe0f PPN Type belum dipilih.\n"
                    "      \u2192 Lihat nominal PPN di faktur pajak Anda, lalu pilih PPN Type\n"
                    "        yang sesuai di field PPN Type (contoh: Standard 11%, Standard 12%,\n"
                    "        Zero Rated, Tidak Dipungut, Bukan Objek PPN, dll.)."
                )
        else:
            verification_notes_parts.append("   ⚠️ PPN Type validation incomplete")

        if fp_no_match:
            verification_notes_parts.append(f"   ✅ FP Number verified in OCR")
        elif not self.ocr_text:
            verification_notes_parts.append("   ℹ️ OCR not yet run")
        elif ocr_fp_no and ocr_fp_no != self.fp_no:
            # ⚠️ CRITICAL: Mismatch between document name (autoname) and OCR result
            verification_notes_parts.append(
                f"🚨 FP Number MISMATCH (autoname tidak bisa diubah!):\n"
                f"   Document Name: {self.fp_no}\n"
                f"   OCR Detected: {ocr_fp_no}\n"
                f"   ⚠️ Verifikasi apakah PDF yang diupload sudah benar, atau hapus dokumen ini "
                f"dan buat ulang dengan FP Number yang benar."
            )
            # Only show popup on user-initiated save (not background OCR job)
            if not self.flags.get("post_ocr_validate"):
                frappe.msgprint(
                    msg=_(
                        "FP Number mismatch terdeteksi!<br><br>"
                        "<b>Document Name (autoname):</b> {0}<br>"
                        "<b>OCR Detected:</b> {1}<br><br>"
                        "⚠️ Document name tidak bisa diubah. "
                        "Pastikan PDF yang diupload sudah benar, atau hapus dokumen ini "
                        "dan buat ulang dengan FP Number yang benar."
                    ).format(self.fp_no, ocr_fp_no),
                    title=_("FP Number Verification Failed"),
                    indicator="red"
                )
        else:
            verification_notes_parts.append("   ⚠️ FP Number not verified in OCR text")

        if self.dpp and self.ppn is not None:
            verification_notes_parts.append("   ✅ DPP and PPN amounts present")
        else:
            verification_notes_parts.append("   ⚠️ Missing DPP or PPN values")

        # 🆕 Validate PPN amount matches selected PPN Type
        ppn_amount_match = False
        if self.ppn_type and self.dpp and self.ppn is not None:
            dpp_value = float(self.dpp)
            ppn_value = float(self.ppn)

            if dpp_value > 0:
                actual_rate = ppn_value / dpp_value if ppn_value > 0 else 0

                # Check rate based on PPN Type
                if "Standard 11%" in self.ppn_type:
                    expected_rate = 0.11
                    if ppn_value == 0:
                        verification_notes_parts.append(
                            f"⚠️ PPN Type '{self.ppn_type}' tetapi PPN = Rp 0.\n"
                            f"   → Apakah seharusnya 'Zero Rated (Ekspor)', 'PPN Tidak Dipungut (Fasilitas)', atau 'Bukan Objek PPN'?\n"
                            f"   → Jika memang kena PPN 11%, periksa kembali nilai PPN di faktur."
                        )
                    elif abs(actual_rate - expected_rate) <= 0.02:  # 2% tolerance
                        ppn_amount_match = True
                        verification_notes_parts.append(f"✅ PPN amount matches rate: {actual_rate:.2%} ≈ 11%")
                    else:
                        verification_notes_parts.append(
                            f"⚠️ PPN rate mismatch: Expected 11%, actual {actual_rate:.2%}\n"
                            f"   → Periksa apakah DPP dan PPN sudah benar di faktur pajak.\n"
                            f"   → Jika menggunakan Nilai Lain (DPP faktor 11/12), pilih PPN Type yang sesuai."
                        )

                elif "Standard 12%" in self.ppn_type:
                    expected_rate = 0.12
                    if ppn_value == 0:
                        verification_notes_parts.append(
                            f"⚠️ PPN Type '{self.ppn_type}' tetapi PPN = Rp 0.\n"
                            f"   → Apakah seharusnya 'Zero Rated (Ekspor)', 'PPN Tidak Dipungut (Fasilitas)', atau 'Bukan Objek PPN'?\n"
                            f"   → Jika memang kena PPN 12%, periksa kembali nilai PPN di faktur."
                        )
                    elif abs(actual_rate - expected_rate) <= 0.02:  # 2% tolerance
                        ppn_amount_match = True
                        verification_notes_parts.append(f"✅ PPN amount matches rate: {actual_rate:.2%} ≈ 12%")
                    else:
                        verification_notes_parts.append(
                            f"⚠️ PPN rate mismatch: Expected 12%, actual {actual_rate:.2%}\n"
                            f"   → Periksa apakah DPP dan PPN sudah benar di faktur pajak.\n"
                            f"   → Jika menggunakan Nilai Lain (DPP faktor 11/12), pilih PPN Type yang sesuai."
                        )

                elif "Zero Rated" in self.ppn_type or "Ekspor" in self.ppn_type:
                    if ppn_value == 0:
                        ppn_amount_match = True
                        verification_notes_parts.append("✅ PPN amount is 0 (Zero Rated)")
                    else:
                        verification_notes_parts.append(
                            f"⚠️ Zero Rated should have PPN=0, but got Rp {ppn_value:,.0f}"
                        )

                elif "Tidak Dipungut" in self.ppn_type:
                    # PPN Tidak Dipungut: tax is owed/computed but NOT collected by the supplier.
                    # The PPN amount CAN be non-zero on the faktur — it is "terutang tapi tidak dipungut".
                    ppn_amount_match = True
                    if ppn_value == 0:
                        verification_notes_parts.append(f"✅ PPN amount is 0 ({self.ppn_type})")
                    else:
                        verification_notes_parts.append(
                            f"ℹ️ {self.ppn_type}: PPN Rp {ppn_value:,.0f} tertera di faktur "
                            f"(terutang tapi tidak dipungut oleh penjual — ini normal untuk kode 040/070)."
                        )

                elif "Dibebaskan" in self.ppn_type:
                    # PPN Dibebaskan: tax is fully exempted — must be 0.
                    if ppn_value == 0:
                        ppn_amount_match = True
                        verification_notes_parts.append(f"✅ PPN amount is 0 ({self.ppn_type})")
                    else:
                        verification_notes_parts.append(
                            f"⚠️ {self.ppn_type} (PPN Dibebaskan) seharusnya PPN = 0, "
                            f"tapi tercatat Rp {ppn_value:,.0f}. Periksa kembali faktur."
                        )

                elif "Bukan Objek PPN" in self.ppn_type:
                    if ppn_value == 0:
                        ppn_amount_match = True
                        verification_notes_parts.append("✅ PPN amount is 0 (Bukan Objek PPN)")
                    else:
                        verification_notes_parts.append(
                            f"⚠️ Bukan Objek PPN should have PPN=0, but got Rp {ppn_value:,.0f}"
                        )

                elif "Digital 1.1%" in self.ppn_type or "PMSE" in self.ppn_type:
                    expected_rate = 0.011
                    if abs(actual_rate - expected_rate) <= 0.005:  # 0.5% tolerance
                        ppn_amount_match = True
                        verification_notes_parts.append(f"✅ PPN amount matches rate: {actual_rate:.2%} ≈ 1.1%")
                    else:
                        verification_notes_parts.append(
                            f"⚠️ PPN rate mismatch: Expected 1.1%, actual {actual_rate:.2%}"
                        )

                elif "Custom" in self.ppn_type or "Other" in self.ppn_type:
                    # Custom tariff - always pass but show rate
                    ppn_amount_match = True
                    verification_notes_parts.append(
                        f"ℹ️ Custom PPN Type: Actual rate is {actual_rate:.2%}"
                    )

                else:
                    # PPN Type string tidak cocok dengan pola yang dikenali.
                    # Jangan blokir auto-verify hanya karena string PPN Type berbeda.
                    # Tandai sebagai pass, tapi minta verifikasi manual.
                    ppn_amount_match = True
                    verification_notes_parts.append(
                        f"ℹ️ PPN Type '{self.ppn_type}' tidak cocok pola validasi otomatis "
                        f"(rate aktual: {actual_rate:.2%}). "
                        f"Verifikasi nominal PPN secara manual."
                    )

        # Final status summary
        verification_notes_parts.append("")
        verification_notes_parts.append("─" * 50)

        # ppn=0 is valid for Zero Rated / Tidak Dipungut / Bukan Objek PPN
        # ppn=None means OCR could not extract it — don't auto-verify
        ppn_present = self.ppn is not None
        dpp_present = bool(self.dpp and float(self.dpp) > 0)

        if ppn_type_match and fp_no_match and ppn_amount_match and dpp_present and ppn_present:
            self.verification_status = "Verified"
            verification_notes_parts.append("\u2705 STATUS: Verified - All checks passed")
        elif self.verification_status != "Rejected":
            # Keep as "Needs Review" if not explicitly rejected
            self.verification_status = "Needs Review"
            # Build a specific list of what's still pending
            pending = []
            if not self.ppn_type:
                pending.append("PPN Type belum dipilih")
            if not fp_no_match:
                pending.append("FP Number belum ter-verifikasi dari OCR")
            if not ppn_amount_match:
                pending.append("Nominal PPN tidak sesuai PPN Type yang dipilih")
            if not dpp_present:
                pending.append("DPP tidak ada atau 0")
            if not ppn_present:
                pending.append("PPN belum diekstrak oleh OCR")
            pending_str = "; ".join(pending) if pending else "verifikasi manual diperlukan"
            verification_notes_parts.append(f"\u26a0\ufe0f STATUS: Needs Review \u2014 {pending_str}.")

        # Always set verification notes
        self.verification_notes = "\n".join(verification_notes_parts)

    def on_trash(self):
        """Clean up all links pointing to this OCR Upload before deletion.

        Clears link fields in Expense Request, Purchase Invoice, and Sales Invoice that reference this document.
        Also deletes any Tax Invoice OCR Monitoring records.
        """
        from imogi_finance.tax_invoice_fields import UPLOAD_LINK_FIELDS

        # Clear links from all doctypes that may reference this OCR Upload
        for doctype, link_field in UPLOAD_LINK_FIELDS.items():
            if frappe.db.table_exists(doctype.replace(" ", "")):
                linked_docs = frappe.get_all(
                    doctype,
                    filters={link_field: self.name},
                    pluck="name",
                )
                for doc_name in linked_docs:
                    frappe.db.set_value(doctype, doc_name, link_field, None)

        # Delete any OCR Monitoring records for this upload
        if frappe.db.table_exists("Tax Invoice OCR Monitoring"):
            monitoring_records = frappe.get_all(
                "Tax Invoice OCR Monitoring",
                filters={"upload_name": self.name},
                pluck="name",
            )
            for record in monitoring_records:
                frappe.delete_doc("Tax Invoice OCR Monitoring", record, ignore_permissions=True, force=True)

    def after_insert(self):
        """
        Auto-detect scanned PDFs and trigger OCR on new document creation.

        Flow:
        1. Try PyMuPDF to check if PDF has text layer
        2. If no text (scanned PDF) → Auto-queue OCR
        3. OCR completes → on_update triggers auto-parse
        """
        if not self.tax_invoice_pdf:
            return

        # Check if OCR is enabled
        try:
            from imogi_finance.tax_invoice_ocr import get_settings
            settings = get_settings()
            if not settings.get("enable_tax_invoice_ocr"):
                frappe.logger().debug(f"[AFTER_INSERT] OCR disabled, skipping auto-detect")
                return
        except Exception:
            return

        # Try quick text extraction to detect scanned PDF
        try:
            from imogi_finance.imogi_finance.parsers.faktur_pajak_parser import extract_tokens

            # Quick extraction (PyMuPDF only, no vision_json)
            tokens = extract_tokens(file_url_or_path=self.tax_invoice_pdf, vision_json=None)

            has_text_layer = bool(tokens and len(tokens) > 10)  # At least 10 tokens = has text

            frappe.logger().info(
                f"[AFTER_INSERT] {self.name}: PDF text detection - "
                f"tokens={len(tokens) if tokens else 0}, has_text_layer={has_text_layer}"
            )

            if not has_text_layer:
                # Scanned PDF detected - auto-queue OCR
                frappe.logger().info(f"[AFTER_INSERT] {self.name}: Scanned PDF detected, auto-queueing OCR")

                from imogi_finance.api.tax_invoice import run_ocr_for_upload
                run_ocr_for_upload(self.name)

                # Update status to show OCR is queued
                frappe.db.set_value(
                    "Tax Invoice OCR Upload",
                    self.name,
                    {"ocr_status": "Queued"},
                    update_modified=False
                )

        except Exception as e:
            # Don't fail document creation if detection fails
            frappe.logger().warning(
                f"[AFTER_INSERT] {self.name}: Auto-detect failed: {str(e)}"
            )

    def _detect_and_suggest_nilai_lain(self) -> str | None:
        """Detect Nilai Lain scenario and return a note string for verification_notes.

        Returns a non-empty string if Nilai Lain is confirmed, None otherwise.
        Caller (validate) is responsible for inserting the returned note into
        verification_notes_parts so it is not overwritten.
        """
        if not self.ocr_text or not self.harga_jual or not self.dpp:
            return None

        nilai_lain_factor = detect_nilai_lain_factor(self.ocr_text)
        if not nilai_lain_factor:
            return None

        expected_hj = self.dpp / nilai_lain_factor
        hj_rounded = int(round(self.harga_jual))
        expected_rounded = int(round(expected_hj))

        if hj_rounded != expected_rounded:
            return None

        # ✅ Nilai Lain confirmed
        note_lines = [
            f"⚠️ Nilai Lain terdeteksi (faktor DPP: {nilai_lain_factor:.4f})",
            f"   Harga Jual: Rp {self.harga_jual:,.0f}  |  DPP: Rp {self.dpp:,.0f}",
            f"   Pastikan PPN Template yang digunakan sudah mendukung perhitungan Nilai Lain.",
        ]

        # Show popup only on user-initiated save (not background OCR job)
        if not self.flags.get("post_ocr_validate"):
            frappe.msgprint(
                msg=_(
                    "⚠️ <b>Nilai Lain terdeteksi</b> (DPP menggunakan faktor {0:.4f}).<br><br>"
                    "Harga Jual: Rp {1:,.0f}<br>"
                    "DPP: Rp {2:,.0f}<br>"
                    "Expected Harga Jual: Rp {3:,.0f}<br><br>"
                    "Pastikan PPN Template sudah sesuai untuk perhitungan variance."
                ).format(nilai_lain_factor, self.harga_jual, self.dpp, expected_hj),
                title=_("Nilai Lain Detected"),
                indicator="orange"
            )

        # Template suggestion (uses settings mapping — no company required for global rows)
        if self.ppn_type:
            company = self.company or frappe.defaults.get_user_default("Company")
            suggested_template = get_ppn_template_from_type(
                self.ppn_type, company, template_type="Purchase"
            )
            if suggested_template:
                note_lines.append(f"   💡 Template disarankan: {suggested_template}")
                if not self.flags.get("post_ocr_validate"):
                    frappe.msgprint(
                        msg=_(
                            "💡 <b>Template Suggestion:</b><br><br>"
                            "Purchase Taxes and Charges Template yang cocok:<br>"
                            "<b>{0}</b><br><br>"
                            "Pastikan template ini digunakan di Expense Request / Purchase Invoice."
                        ).format(suggested_template),
                        title=_("Template Recommendation"),
                        indicator="blue"
                    )
            else:
                note_lines.append(
                    "   ℹ️ Tidak ada template ditemukan — pilih manual atau konfigurasi "
                    "Tax Invoice OCR Settings → PPN Template Mappings."
                )

        return "\n".join(note_lines)

    def _normalize_ppn_type_value(self, ppn_type: str) -> str:
        """
        Normalize PPN Type from old simplified format to current detailed format.

        Old simplified values (legacy, from before options were expanded):
        - "Standard"         -> "Standard 11% (PPN 2022-2024)"
        - "Zero Rated"       -> "Zero Rated (Ekspor)"
        - "Exempt/Not PPN"   -> "PPN Tidak Dipungut (Fasilitas)"

        Current detailed values are passed through unchanged:
        - "Standard 11% (PPN 2022-2024)"
        - "Standard 12% (PPN 2025+)"
        - "Zero Rated (Ekspor)"
        - "PPN Tidak Dipungut (Fasilitas)"
        - "PPN Dibebaskan (Fasilitas)"
        - "Bukan Objek PPN"
        - "Digital 1.1% (PMSE)"
        - "Custom/Other (Tarif Khusus)"

        Args:
            ppn_type: Original PPN Type value

        Returns:
            Normalized PPN Type matching the current Select field options
        """
        if not ppn_type:
            return ppn_type

        # Map old simplified values to valid detailed options
        LEGACY_MAP = {
            "Standard": "Standard 11% (PPN 2022-2024)",
            "Zero Rated": "Zero Rated (Ekspor)",
            "Exempt/Not PPN": "PPN Tidak Dipungut (Fasilitas)",
        }
        if ppn_type in LEGACY_MAP:
            return LEGACY_MAP[ppn_type]

        # Already a valid detailed value — return unchanged
        return ppn_type

    @frappe.whitelist()
    def refresh_status(self):
        from imogi_finance.api.tax_invoice import monitor_tax_invoice_ocr

        return monitor_tax_invoice_ocr(self.name, "Tax Invoice OCR Upload")

    def on_update(self):
        """Hook removed - line items auto-parsing no longer needed."""
        pass


# Removed functions: _update_validation_summary, revalidate_items, approve_parse, auto_parse_line_items
