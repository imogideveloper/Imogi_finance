import importlib
import sys
import types

import pytest


def _load_upload_module(monkeypatch):
    frappe_stub = types.ModuleType("frappe")
    frappe_stub._ = lambda x: x
    frappe_stub.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
    frappe_stub.get_doc = lambda *a, **k: None
    frappe_stub.msgprint = lambda *a, **k: None
    frappe_stub.whitelist = lambda *a, **k: (lambda f: f)

    class DoesNotExistError(Exception):
        pass

    frappe_stub.DoesNotExistError = DoesNotExistError

    normalization_stub = types.ModuleType("imogi_finance.imogi_finance.parsers.normalization")
    normalization_stub.normalize_identifier_digits = lambda value: "".join(ch for ch in (value or "") if ch.isdigit()) or None

    frappe_model_document_stub = types.ModuleType("frappe.model.document")

    class Document:
        pass

    frappe_model_document_stub.Document = Document

    monkeypatch.setitem(sys.modules, "frappe", frappe_stub)
    monkeypatch.setitem(sys.modules, "frappe.model.document", frappe_model_document_stub)
    monkeypatch.setitem(sys.modules, "imogi_finance.imogi_finance.parsers.normalization", normalization_stub)

    sys.modules.pop("imogi_finance.imogi_finance.doctype.tax_invoice_ocr_upload.tax_invoice_ocr_upload", None)
    return importlib.import_module(
        "imogi_finance.imogi_finance.doctype.tax_invoice_ocr_upload.tax_invoice_ocr_upload"
    )


@pytest.fixture()
def upload_module(monkeypatch):
    return _load_upload_module(monkeypatch)


def test_extract_fp_number_prioritizes_labeled_faktur_over_npwp(upload_module):
    text = """
    NPWP: 0013025846092000
    Kode dan Nomor Seri Faktur Pajak: 04002500436451666
    """

    extracted = upload_module._extract_fp_number_from_ocr(text, expected_fp_no="04002500436451666")

    assert extracted == "04002500436451666"


def test_extract_fp_number_ignores_npwp_context_without_faktur_label(upload_module):
    text = """
    Nama PKP: Contoh Supplier
    NPWP: 0013025846092000
    """

    extracted = upload_module._extract_fp_number_from_ocr(text)

    assert extracted is None
