import json
from pathlib import Path

from imogi_finance import tax_invoice_fields


def test_field_maps_follow_shared_json_definition():
    json_path = Path(tax_invoice_fields.__file__).resolve().parent / "public" / "json" / "tax_invoice_field_maps.json"
    shared_payload = json.loads(json_path.read_text())

    python_maps = tax_invoice_fields.get_field_maps()
    assert python_maps["Purchase Invoice"]["fp_no"] == shared_payload["field_maps"]["Purchase Invoice"]["fp_no"]
    assert "Tax Invoice OCR Upload" in python_maps
    assert set(tax_invoice_fields.iter_copy_keys()) == set(shared_payload["copy_keys"])
