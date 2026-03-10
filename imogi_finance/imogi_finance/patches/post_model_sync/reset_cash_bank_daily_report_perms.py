"""
Reset Cash Bank Daily Report permissions.

Custom DocPerm entries (set via Role Permission Manager UI) override the
DocType JSON permissions entirely.  This patch clears any such overrides so
the built-in permissions from the DocType definition (which now include
Finance Controller) are active again.
"""

import frappe


def execute():
    doctype = "Cash Bank Daily Report"

    if not frappe.db.exists("DocType", doctype):
        return

    # Remove all Custom DocPerm overrides for this DocType
    frappe.db.delete("Custom DocPerm", {"parent": doctype})

    # Reset built-in DocPerm table from DocType JSON definition
    try:
        frappe.permissions.reset_perms(doctype)
    except Exception as e:
        frappe.logger().warning(
            f"[patch] reset_perms({doctype}) failed — permissions may need manual reset: {e}"
        )

    frappe.db.commit()
    frappe.logger().info(f"[patch] Permissions reset for {doctype}")
