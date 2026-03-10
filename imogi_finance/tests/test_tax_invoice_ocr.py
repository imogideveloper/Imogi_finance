import importlib
import json
import sys
import types

import pytest


def _load_tax_invoice_ocr_module(monkeypatch):
    """Load tax_invoice_ocr with lightweight frappe stubs for unit testing."""
    frappe_stub = types.ModuleType("frappe")
    frappe_stub._ = lambda x: x
    frappe_stub._dict = dict
    frappe_stub.db = None
    frappe_stub.local = types.SimpleNamespace(site="test-site")
    frappe_stub.flags = types.SimpleNamespace(in_test=True)
    frappe_stub.session = types.SimpleNamespace(user="test@example.com")
    frappe_stub.logger = lambda *a, **k: types.SimpleNamespace(
        info=lambda *x, **y: None,
        warning=lambda *x, **y: None,
        error=lambda *x, **y: None,
        debug=lambda *x, **y: None,
    )
    frappe_stub.throw = lambda *a, **k: (_ for _ in ()).throw(Exception(a[0] if a else "error"))
    frappe_stub.log_error = lambda *a, **k: None
    frappe_stub.get_traceback = lambda: ""
    frappe_stub.get_doc = lambda *a, **k: None
    frappe_stub.get_all = lambda *a, **k: []
    frappe_stub.whitelist = lambda *a, **k: (lambda f: f)
    frappe_stub.utils = types.SimpleNamespace(background_jobs=None)

    def _strict_getattr(name):
        raise AttributeError(f"Unexpected frappe attribute access in parser tests: {name}")

    frappe_stub.__getattr__ = _strict_getattr

    frappe_utils_stub = types.ModuleType("frappe.utils")
    frappe_utils_stub.cint = int
    frappe_utils_stub.flt = float
    frappe_utils_stub.get_site_path = lambda *a: ""

    frappe_formatters_stub = types.ModuleType("frappe.utils.formatters")
    frappe_formatters_stub.format_value = lambda value, *a, **k: str(value)

    frappe_exceptions_stub = types.ModuleType("frappe.exceptions")

    class ValidationError(Exception):
        pass

    frappe_exceptions_stub.ValidationError = ValidationError

    monkeypatch.setitem(sys.modules, "frappe", frappe_stub)
    monkeypatch.setitem(sys.modules, "frappe.utils", frappe_utils_stub)
    monkeypatch.setitem(sys.modules, "frappe.utils.formatters", frappe_formatters_stub)
    monkeypatch.setitem(sys.modules, "frappe.exceptions", frappe_exceptions_stub)

    sys.modules.pop("imogi_finance.tax_invoice_ocr", None)
    return importlib.import_module("imogi_finance.tax_invoice_ocr")


@pytest.fixture()
def ocr_module(monkeypatch):
    return _load_tax_invoice_ocr_module(monkeypatch)


def test_parse_faktur_pajak_text_extracts_amounts_and_buyer_npwp(ocr_module):
    text = """
    Faktur Pajak
    Kode dan Nomor Seri Faktur Pajak: 04002500432967499
    Pengusaha Kena Pajak:
    Nama : METROPOLITAN LAND TBK
    Alamat : M GOLD TOWER OFFICE WING LT 12 SUITE ABCGH & SUITE A-H LT 15 JL LETKOL
    #0016573131054000000000
    NPWP: 0016573131054000
    Pembeli Barang Kena Pajak/Penerima Jasa Kena Pajak:
    Nama CAKRA ADHIPERKASA OPTIMA
    Alamat: GEDUNG AD PREMIER OFFICE PARK LT 9 JL TB SIMATUPANG NO.05, RT 005, RW 007, RAGUNAN,
    NPWP0953808789017000
    Harga Jual / Penggantian / Uang Muka / Termin
    Dikurangi Potongan Harga
    Dikurangi Uang Muka yang telah diterima
    Dasar Pengenaan Pajak
    Jumlah PPN (Pajak Pertambahan Nilai)
    Jumlah PPnBM (Pajak Penjualan atas Barang Mewah)
    Harga Jual / Penggantian /
    Uang Muka / Termin
    (Rp)
    953.976,00
    953.976,00
    0,00
    874.478,00
    104.937,00
    0,00
    """

    parsed, confidence = ocr_module.parse_faktur_pajak_text(text)

    assert parsed["fp_no"] == "04002500432967499"
    assert parsed["npwp"] == "0016573131054000"
    assert parsed["dpp"] > 0
    assert parsed["ppn"] > 0
    assert confidence > 0

    summary = json.loads(parsed["notes"])
    buyer = summary["faktur_pajak"]["pembeli"]
    assert buyer["nama"] == "CAKRA ADHIPERKASA OPTIMA"
    assert buyer["npwp"] == "0953808789017000"


def test_google_vision_ocr_uses_full_text_when_filtered_blocks_miss_details(monkeypatch, ocr_module):
    def make_block(text: str, y_min: float, y_max: float, conf: float = 0.95) -> dict:
        words = [{"symbols": [{"text": char} for char in word]} for word in text.split()]
        return {
            "boundingBox": {"normalizedVertices": [{"y": y_min}, {"y": y_max}, {"y": y_max}, {"y": y_min}]},
            "confidence": conf,
            "paragraphs": [{"words": words}],
        }

    header_block = make_block("Header Only", 0.05, 0.12)
    body_block = make_block(
        "Pembeli Barang Kena Pajak Nama CAKRA ADHIPERKASA OPTIMA NPWP 0953808789017000 Dasar Pengenaan Pajak 874.478,00 "
        "Jumlah PPN 104.937,00",
        0.5,
        0.55,
    )

    full_text = (
        "Faktur Pajak\n"
        "Kode dan Nomor Seri Faktur Pajak: 04002500432967499\n"
        "Pengusaha Kena Pajak: METROPOLITAN LAND TBK NPWP: 0016573131054000\n"
        "Pembeli Barang Kena Pajak/Penerima Jasa Kena Pajak:\n"
        "Nama CAKRA ADHIPERKASA OPTIMA NPWP 0953808789017000\n"
        "Dasar Pengenaan Pajak 874.478,00\n"
        "Jumlah PPN 104.937,00\n"
    )

    responses = [
        {
            "fullTextAnnotation": {"text": full_text, "pages": [{"blocks": [header_block, body_block], "confidence": 0.88}]}
        }
    ]

    class DummyResponse:
        def __init__(self, payload):
            self.payload = payload
            self.status_code = 200
            self.text = "ok"

        def json(self):
            return {"responses": self.payload}

    fake_requests = types.SimpleNamespace(post=lambda *args, **kwargs: DummyResponse(responses))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setattr(ocr_module, "_load_pdf_content_base64", lambda file_url: ("dummy.pdf", ""))
    monkeypatch.setattr(ocr_module, "_get_google_vision_headers", lambda settings: {})
    monkeypatch.setattr(ocr_module, "_build_google_vision_url", lambda settings: "https://vision.googleapis.com/v1/files:annotate")

    settings = dict(ocr_module.DEFAULT_SETTINGS)
    settings["google_vision_endpoint"] = "https://vision.googleapis.com/files:annotate"
    text, raw_json, confidence = ocr_module._google_vision_ocr("dummy.pdf", settings)

    assert "Pembeli Barang Kena Pajak/Penerima Jasa Kena Pajak" in text
    assert "874.478,00" in text
    assert "104.937,00" in text
    assert raw_json["responses"] == responses
    assert confidence > 0

    parsed, _ = ocr_module.parse_faktur_pajak_text(text)
    assert parsed["dpp"] > 0
    assert parsed["ppn"] > 0


def test_parse_faktur_pajak_text_reads_amounts_on_following_line(ocr_module):
    text = """
    Dasar Pengenaan Pajak
    17.148,00
    Jumlah PPN (Pajak Pertambahan Nilai)
    15,00
    """

    parsed, _ = ocr_module.parse_faktur_pajak_text(text)

    assert parsed["dpp"] == pytest.approx(17148.0, rel=0, abs=0.01)
    assert parsed["ppn"] == pytest.approx(15.0, rel=0, abs=0.01)


def test_parse_faktur_pajak_text_prefers_largest_currency_amounts_when_partial(ocr_module):
    text = """
    Pengusaha Kena Pajak:
    Nama : PT PARTIAL OCR
    NPWP: 012345678901234
    Pembeli Barang Kena Pajak:
    Nama CUSTOMER
    NPWP: 001122334455667
    Jalan Sudirman No. 15 RT 05 RW 09
    953.976,00
    104.937,00
    """

    parsed, _ = ocr_module.parse_faktur_pajak_text(text)

    assert parsed["dpp"] == pytest.approx(953976.0, rel=0, abs=0.01)
    assert parsed["ppn"] == pytest.approx(104937.0, rel=0, abs=0.01)


def test_parse_faktur_pajak_text_dpp_nilai_lain_uses_correct_ratio_for_harga_jual(ocr_module):
    text = """
    Faktur Pajak
    DPP Nilai Lain 11/12
    Dasar Pengenaan Pajak
    863.335,00
    Jumlah PPN (Pajak Pertambahan Nilai)
    103.600,00
    """

    parsed, _ = ocr_module.parse_faktur_pajak_text(text)

    assert parsed["dpp"] == pytest.approx(863335.0, rel=0, abs=0.01)
    assert parsed["ppn"] == pytest.approx(103600.0, rel=0, abs=0.01)
    assert parsed["harga_jual"] == pytest.approx(941820.0, rel=0, abs=0.01)


def test_parse_faktur_pajak_text_dpp_nilai_lain_never_uses_legacy_092_fallback(ocr_module):
    text = """
    Faktur Pajak
    DPP Nilai Lain 11/12
    Dasar Pengenaan Pajak
    863.335,00
    Jumlah PPN (Pajak Pertambahan Nilai)
    103.600,00
    """

    parsed, _ = ocr_module.parse_faktur_pajak_text(text)

    assert parsed["harga_jual"] != pytest.approx(938407.61, rel=0, abs=0.01)


def test_parse_faktur_pajak_text_dpp_nilai_lain_prefers_extracted_harga_jual_and_flags_mismatch(ocr_module):
    text = """
    Faktur Pajak
    DPP Nilai Lain 11/12
    Harga Jual / Penggantian / Uang Muka / Termin
    980.000,00
    Dasar Pengenaan Pajak
    863.335,00
    Jumlah PPN (Pajak Pertambahan Nilai)
    103.600,00
    """

    parsed, confidence = ocr_module.parse_faktur_pajak_text(text)

    assert parsed["harga_jual"] == pytest.approx(980000.0, rel=0, abs=0.01)

    notes = json.loads(parsed["notes"])
    validation_notes = notes.get("validation_notes", [])
    assert any("DPP Nilai Lain guardrail" in note for note in validation_notes)
    assert confidence <= 0.7


def test_dpp_nilai_lain_without_explicit_fraction_infers_factor_from_dpp_ppn(ocr_module):
    text = """
    Faktur Pajak
    Penyerahan yang menggunakan DPP Nilai Lain - Faktur Pajak Normal
    Dasar Pengenaan Pajak
    863335,00
    Jumlah PPN (Pajak Pertambahan Nilai)
    103600,00
    """

    parsed, confidence = ocr_module.parse_faktur_pajak_text(text)
    notes = json.loads(parsed["notes"])

    assert parsed["harga_jual"] == pytest.approx(941820.0, rel=0, abs=0.01)
    assert any("factor inferred from DPP/PPN" in note for note in notes.get("validation_notes", []))
    assert any("default 11/12 policy" in note or "matched by ppn≈12% of dpp" in note for note in notes.get("validation_notes", []))
    assert confidence <= 0.6


@pytest.mark.parametrize(
    "dpp_raw,ppn_raw",
    [
        ("863.335,00", "103.600,00"),
        ("863335,00", "103600,00"),
        ("863 335,00", "103 600,00"),
    ],
)
def test_dpp_nilai_lain_number_formats_are_handled(ocr_module, dpp_raw, ppn_raw):
    text = f"""
    Faktur Pajak
    DPP Nilai Lain 11/12
    Dasar Pengenaan Pajak
    {dpp_raw}
    Jumlah PPN (Pajak Pertambahan Nilai)
    {ppn_raw}
    """

    parsed, _ = ocr_module.parse_faktur_pajak_text(text)
    assert parsed["harga_jual"] == pytest.approx(941820.0, rel=0, abs=0.01)


def test_dpp_nilai_lain_ppn_mismatch_lowers_confidence_and_sets_notes(ocr_module):
    text = """
    Faktur Pajak
    DPP Nilai Lain 11/12
    Dasar Pengenaan Pajak
    863.335,00
    Jumlah PPN (Pajak Pertambahan Nilai)
    200.000,00
    """

    parsed, confidence = ocr_module.parse_faktur_pajak_text(text)
    notes = json.loads(parsed["notes"])

    assert parsed["harga_jual"] == pytest.approx(941820.0, rel=0, abs=0.01)
    assert confidence <= 0.75
    assert isinstance(notes.get("validation_notes"), list)


def test_infer_nilai_lain_factor_reason_labels(ocr_module):
    factor, reason = ocr_module._infer_nilai_lain_factor_from_amounts(863335, 103600)
    assert factor == pytest.approx(11 / 12, rel=0, abs=1e-9)
    assert reason in {"matched_by_ppn_ratio", "default_policy"}


# =============================================================================
# Tests for _extract_summary_from_last_section and multi-item sanity check
# =============================================================================


class TestExtractSummaryFromLastSection:
    """Tests for the bottom-section summary extraction."""

    def test_finds_summary_values_after_last_marker(self, ocr_module):
        """Given text with column header AND summary marker, returns the LAST marker's values."""
        text = (
            # Column header (FIRST occurrence of "Harga Jual /")
            "No. Barang\n"
            "Harga Jual / Penggantian / Uang Muka / Termin (Rp)\n"
            "80.000,00\n"
            "80.000,00\n"
            "9.600,00\n"
            "0,00\n"
            # ... more item rows ...\n
            "360.500,00\n"
            "228.000,00\n"
            # Summary section (LAST occurrence)
            "Harga Jual / Penggantian / Uang Muka / Termin\n"
            "1.102.500,00\n"
            "Dikurangi Potongan Harga\n"
            "0,00\n"
            "Dasar Pengenaan Pajak\n"
            "1.010.625,00\n"
            "Jumlah PPN (Pajak Pertambahan Nilai)\n"
            "121.275,00\n"
            "Jumlah PPnBM (Pajak Penjualan atas Barang Mewah)\n"
            "0,00\n"
        )
        result = ocr_module._extract_summary_from_last_section(text)

        assert result.get("harga_jual") == pytest.approx(1_102_500.0, abs=1)
        assert result.get("dpp") == pytest.approx(1_010_625.0, abs=1)
        assert result.get("ppn") == pytest.approx(121_275.0, abs=1)

    def test_empty_text_returns_empty(self, ocr_module):
        assert ocr_module._extract_summary_from_last_section("") == {}
        assert ocr_module._extract_summary_from_last_section(None) == {}

    def test_no_marker_returns_empty(self, ocr_module):
        text = "Some random OCR text\n123.456,00\n"
        assert ocr_module._extract_summary_from_last_section(text) == {}

    def test_single_marker_works(self, ocr_module):
        """Single occurrence = always the summary."""
        text = (
            "Harga Jual / Penggantian / Uang Muka / Termin\n"
            "500.000,00\n"
            "Dasar Pengenaan Pajak\n"
            "458.333,00\n"
            "Jumlah PPN (Pajak Pertambahan Nilai)\n"
            "55.000,00\n"
        )
        result = ocr_module._extract_summary_from_last_section(text)
        assert result["harga_jual"] == pytest.approx(500_000.0, abs=1)
        assert result["dpp"] == pytest.approx(458_333.0, abs=1)
        assert result["ppn"] == pytest.approx(55_000.0, abs=1)


class TestMultiItemSanityCheck:
    """End-to-end: parse_faktur_pajak_text detects and corrects item-level values."""

    def test_multi_item_invoice_dpp_corrected(self, ocr_module):
        """
        Simulates Bug #1: DPP picks up last item's price (80,000) instead
        of summary total (1,010,625).  The sanity check should re-extract
        from the bottom section to get the correct values.
        """
        text = (
            "Kode dan Nomor Seri Faktur Pajak: 040.025-00.43645166\n"
            "Pengusaha Kena Pajak:\n"
            "Nama : ASTRA INTERNATIONAL TBK\n"
            "NPWP: 0013025846092000\n"
            # Column header area — causes label misdetection
            "No. Nama Barang/Jasa\n"
            "Harga Jual / Penggantian / Uang Muka / Termin (Rp)\n"
            "Dasar Pengenaan Pajak\n"
            "80.000,00\n"
            "PPN\n"
            "9.600,00\n"
            # Item amounts (many to trigger len(amounts)>=8)
            "360.500,00\n"
            "380.000,00\n"
            "54.000,00\n"
            "228.000,00\n"
            "80.000,00\n"
            "43.260,00\n"
            "45.600,00\n"
            "25.080,00\n"
            # Summary section (LAST occurrence of markers)
            "Harga Jual / Penggantian / Uang Muka / Termin\n"
            "1.102.500,00\n"
            "Dikurangi Potongan Harga\n"
            "0,00\n"
            "Dasar Pengenaan Pajak\n"
            "1.010.625,00\n"
            "Jumlah PPN (Pajak Pertambahan Nilai)\n"
            "121.275,00\n"
            "Jumlah PPnBM (Pajak Penjualan atas Barang Mewah)\n"
            "0,00\n"
            "ditandatangani secara elektronik\n"
            "JOHN DOE\n"
            "1.102.500,00\n"
            "1.102.500,00\n"
            "0,00\n"
            "1.010.625,00\n"
            "121.275,00\n"
            "0,00\n"
        )
        parsed, confidence = ocr_module.parse_faktur_pajak_text(text)

        # After sanity check, the values should be the summary totals
        assert parsed["dpp"] == pytest.approx(1_010_625.0, rel=0.01)
        assert parsed["ppn"] == pytest.approx(121_275.0, rel=0.01)
        assert parsed["harga_jual"] == pytest.approx(1_102_500.0, rel=0.01)

    def test_single_item_invoice_not_affected(self, ocr_module):
        """Single-item invoices should NOT trigger the sanity check."""
        text = (
            "Kode dan Nomor Seri Faktur Pajak: 010.025-00.12345678\n"
            "NPWP: 0013025846092000\n"
            "Harga Jual / Penggantian / Uang Muka / Termin\n"
            "80.000,00\n"
            "Dasar Pengenaan Pajak\n"
            "73.333,00\n"
            "Jumlah PPN (Pajak Pertambahan Nilai)\n"
            "8.800,00\n"
            "ditandatangani secara elektronik\n"
            "JOHN DOE\n"
            "80.000,00\n"
            "80.000,00\n"
            "0,00\n"
            "73.333,00\n"
            "8.800,00\n"
            "0,00\n"
        )
        parsed, _ = ocr_module.parse_faktur_pajak_text(text)

        # Single-item: DPP = 73,333 should stay as-is
        assert parsed["dpp"] == pytest.approx(73_333.0, rel=0.01)
