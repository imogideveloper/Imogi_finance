"""
Patch untuk kompatibilitas ERPNext taxes_and_totals.py
yang memanggil round_floats_in(do_not_round_fields=...) 
tapi Frappe 15 belum support parameter tersebut.
"""

import frappe
import frappe.model.document


def execute():
    """Dipanggil saat bench migrate."""
    _apply_patch()


def _apply_patch():
    original = frappe.model.document.Document.round_floats_in

    def patched(self, doc, fieldnames=None, do_not_round_fields=None):
        return original(self, doc, fieldnames)

    frappe.model.document.Document.round_floats_in = patched


# Auto-apply saat module di-import
_apply_patch()
