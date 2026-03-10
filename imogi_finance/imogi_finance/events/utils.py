from __future__ import annotations

import frappe
from frappe import _


EXPENSE_REQUEST_LINK_FIELDS = (
    "linked_payment_entry",
    "linked_purchase_invoice",
)
EXPENSE_REQUEST_PENDING_FIELDS = ("pending_purchase_invoice",)

# All expense-request-style doctypes, in lookup priority order
_ER_DOCTYPES = ("Advanced Expense Request", "Expense Request")


def get_er_doctype(request_name: str) -> str | None:
    """Auto-detect doctype for an expense request name (supports ERMC and legacy ER).

    Checks "Advanced Expense Request" first, then "Expense Request".
    Returns the matching doctype string, or None if not found in either.
    """
    for doctype in _ER_DOCTYPES:
        if frappe.db.exists(doctype, request_name):
            return doctype
    return None


def get_approved_expense_request(
    request_name: str, target_label: str, allowed_statuses: frozenset[str] | set[str] | None = None
):
    source_doctype = get_er_doctype(request_name)
    if not source_doctype:
        frappe.throw(_("Expense Request {0} not found").format(request_name))
    request = frappe.get_doc(source_doctype, request_name)
    allowed_statuses = allowed_statuses or {"Approved", "PI Created"}
    if request.docstatus != 1 or request.status not in allowed_statuses:
        frappe.throw(
            _(
                "Expense Request must have docstatus 1 and status {0} before linking to {1}"
            ).format(", ".join(sorted(allowed_statuses)), target_label)
        )
    return request


def get_expense_request_links(request_name: str, *, include_pending: bool = False):
    """Get linked Purchase Invoice and Payment Entry by querying database.

    Uses native connections to find submitted PI and paid PE linked to this Expense Request.

    Note: 1 ER can have:
    - 1 submitted PI (or 0 if none/cancelled)
    - Multiple submitted PE (1 PI can have multiple payments)

    For status determination, we only need to know if ANY PE exists.
    Returns the latest PE for backward compatibility with existing code.

    Returns dict with:
    - linked_purchase_invoice: Latest submitted PI (or None)
    - linked_payment_entry: Latest submitted PE (or None)
    - has_payment_entries: True if any PE exists (for status check)
    """
    # Query Purchase Invoice yang linked dan submitted (max 1)
    # Also get status field (Paid/Unpaid badge)
    pi_data = frappe.db.get_value(
        "Purchase Invoice",
        {
            "imogi_expense_request": request_name,
            "docstatus": 1  # Only submitted PI
        },
        ["name", "status"],
        as_dict=True,
        order_by="creation desc"
    )

    linked_pi = pi_data.get("name") if pi_data else None
    pi_status = pi_data.get("status") if pi_data else None

    # Query Payment Entry yang linked dan submitted (bisa multiple)
    # Return latest PE untuk backward compatibility
    linked_pe = frappe.db.get_value(
        "Payment Entry",
        {
            "imogi_expense_request": request_name,
            "docstatus": 1  # Only submitted PE
        },
        "name",
        order_by="creation desc"
    )

    result = {
        "linked_purchase_invoice": linked_pi,
        "linked_payment_entry": linked_pe,
        "has_payment_entries": bool(linked_pe),  # True if any PE exists
        "pi_status": pi_status  # PI status badge (Paid/Unpaid/etc)
    }

    # Include pending field if requested (for backward compatibility)
    if include_pending:
        pending = frappe.db.get_value(
            "Expense Request", request_name, "pending_purchase_invoice"
        )
        result["pending_purchase_invoice"] = pending

    return result


def has_active_links(request_links, exclude: frozenset[str] | None = None):
    excluded_links = exclude or frozenset()
    return any(
        request_links.get(field)
        for field in EXPENSE_REQUEST_LINK_FIELDS
        if field not in excluded_links
    )


def get_expense_request_status(request_links: dict, *, check_pi_docstatus: bool = False) -> str:
    """Determine Expense Request status based on linked documents.

    Args:
        request_links: Dict with linked_payment_entry, linked_purchase_invoice, pi_status
        check_pi_docstatus: Deprecated - query now automatically filters submitted docs

    Returns:
        - "Paid" if Purchase Invoice status = "Paid" (auto-updated by ERPNext)
        - "Return" if Purchase Invoice status = "Return" (debit note issued)
        - "PI Created" if Purchase Invoice exists (submitted)
        - "Approved" otherwise
    """
    # Status priority: Paid > Return > PI Created > Approved
    pi_name = request_links.get("linked_purchase_invoice")
    pi_status = request_links.get("pi_status")

    # Check PI status badge (auto-updated by ERPNext based on outstanding_amount and returns)
    if pi_name and pi_status == "Paid":
        return "Paid"

    if pi_name and pi_status == "Return":
        return "Return"

    if pi_name:
        return "PI Created"

    return "Approved"


def get_cancel_updates(request_name: str, cleared_link_field: str, *, include_pending: bool = False):
    request_links = get_expense_request_links(request_name, include_pending=include_pending)
    remaining_links = {field: request_links.get(field) for field in request_links if field != cleared_link_field}
    next_status = get_expense_request_status(remaining_links)
    return {cleared_link_field: None, "status": next_status, "workflow_state": next_status}


def normalize_ppn_type_value(ppn_type: str) -> str:
    """
    Normalize PPN Type from detailed format to simplified format.

    Legacy formats (from Tax Invoice OCR Upload):
    - "Standard 11% (PPN 2022-2024)" -> "Standard"
    - "Standard 12% (PPN 2025+)" -> "Standard"
    - "Zero Rated (Ekspor)" -> "Zero Rated"
    - "PPN Tidak Dipungut (Fasilitas)" -> "Exempt/Not PPN"
    - "PPN Dibebaskan (Fasilitas)" -> "Exempt/Not PPN"
    - "Bukan Objek PPN" -> "Exempt/Not PPN"
    - "Digital 1.1% (PMSE)" -> "Standard"
    - "Custom/Other (Tarif Khusus)" -> "Standard"

    Args:
        ppn_type: Original PPN Type value

    Returns:
        Normalized PPN Type ("Standard", "Zero Rated", "Exempt/Not PPN")
    """
    if not ppn_type:
        return ppn_type

    # If already normalized, return original value
    if ppn_type in ["Standard", "Zero Rated", "Exempt/Not PPN"]:
        return ppn_type

    ppn_type_lower = ppn_type.lower()

    # Check for Zero Rated
    if "zero rated" in ppn_type_lower or "ekspor" in ppn_type_lower:
        return "Zero Rated"

    # Check for Exempt/Not PPN
    if any(x in ppn_type_lower for x in ["tidak dipungut", "dibebaskan", "bukan objek", "exempt"]):
        return "Exempt/Not PPN"

    # Everything else (Standard 11%, Standard 12%, Digital, Custom) -> Standard
    return "Standard"


def normalize_tax_invoice_ppn_types(doc, method=None):
    """
    Normalize PPN Type fields on document load.

    Fixes validation errors when loading documents with legacy PPN Type values
    like "Standard 11% (PPN 2022-2024)" which are not in the current Select options.

    This is called via onload hook for Purchase Invoice, Sales Invoice, etc.
    """
    # Normalize ti_fp_ppn_type (Tax Invoice Masukan)
    if hasattr(doc, "ti_fp_ppn_type") and doc.ti_fp_ppn_type:
        doc.ti_fp_ppn_type = normalize_ppn_type_value(doc.ti_fp_ppn_type)

    # Normalize out_fp_ppn_type (Tax Invoice Keluaran)
    if hasattr(doc, "out_fp_ppn_type") and doc.out_fp_ppn_type:
        doc.out_fp_ppn_type = normalize_ppn_type_value(doc.out_fp_ppn_type)

