__version__ = "0.1.0"


# Patch kompatibilitas ERPNext round_floats_in
def _patch_round_floats():
    try:
        import frappe.model.document as _doc_module
        _original = _doc_module.Document.round_floats_in

        def _patched(self, doc, fieldnames=None, do_not_round_fields=None):
            return _original(self, doc, fieldnames)

        _doc_module.Document.round_floats_in = _patched
    except Exception:
        pass


_patch_round_floats()
