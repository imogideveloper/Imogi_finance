"""
Patch for frappe.desk.reportview.get_count

Handles TableMissingError (DocType belum ter-migrate) agar:
  - Tidak muncul sebagai Server Error / popup merah ke user
  - Tidak muncul di browser console (tidak return HTTP 500)
  - Tetap tercatat di Error Log Frappe
"""
from __future__ import annotations

import frappe
from frappe import _


@frappe.whitelist()
def get_count(doctype, filters=None, distinct=False, fields=None):
    """
    Override frappe.desk.reportview.get_count.

    Delegasi ke fungsi asli Frappe. Jika DocType-nya belum ter-migrate
    (tabel belum ada di DB), kembalikan 0 secara diam-diam dan catat ke Error Log.
    """
    try:
        from frappe.desk.reportview import get_count as _original_get_count

        return _original_get_count(
            doctype=doctype,
            filters=filters,
            distinct=distinct,
            fields=fields,
        )

    except Exception as e:
        if _is_table_missing_error(e):
            frappe.log_error(
                title=_("DocType tabel belum ada: {0}").format(doctype),
                message=str(e),
            )
            return 0
        raise


def _is_table_missing_error(exc: Exception) -> bool:
    """Return True jika exception adalah TableMissingError (belum migrate)."""
    # Frappe raises database.TableMissingError yang inherit dari
    # pymysql.err.ProgrammingError dengan args[0] == 'DocType'
    try:
        import pymysql.err

        if isinstance(exc, pymysql.err.ProgrammingError):
            if exc.args and exc.args[0] == "DocType":
                return True
    except ImportError:
        pass

    # Fallback: cek nama class
    if "TableMissing" in type(exc).__name__:
        return True

    return False
