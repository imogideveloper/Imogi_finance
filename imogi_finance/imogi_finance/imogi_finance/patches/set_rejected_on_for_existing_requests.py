import frappe


def execute():
    """Backfill rejected_on for existing Expense Request.

    For historical documents that already have status Rejected but no rejected_on
    value yet, we approximate the rejection time using the last modified
    timestamp. This at least records *when* the document ended up in Rejected
    state for audit purposes.
    """

    for doctype in ("Expense Request",):
        if not frappe.db.table_exists(doctype):
            continue

        # Only touch records that are Rejected and currently have no rejected_on
        docs = frappe.get_all(
            doctype,
            filters={"status": "Rejected", "rejected_on": ("is", "not set")},
            fields=["name", "modified"],
            limit=None,
        )

        for doc in docs:
            # Use modified as best-effort approximation of rejection time
            frappe.db.set_value(doctype, doc.name, "rejected_on", doc.modified, update_modified=False)
