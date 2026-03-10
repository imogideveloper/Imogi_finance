from __future__ import annotations

from typing import Dict, List, Tuple

import frappe
from frappe import _


def execute(filters: Dict | None = None) -> Tuple[List[Dict], List[Dict]]:
    filters = filters or {}
    columns = _get_columns()
    data = _get_data(filters)
    # Enrich data with reference outstanding and payment status
    data = _enrich_with_reference_data(data)
    # Apply payment_status filter if provided (post-processing filter)
    if filters.get("payment_status"):
        data = [row for row in data if row.get("payment_status") == filters.get("payment_status")]
    return columns, data


def _get_columns() -> List[Dict]:
    return [
        {"fieldname": "receipt_no", "label": _("Receipt No"), "fieldtype": "Link", "options": "Customer Receipt", "width": 160},
        {"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 200},
        {"fieldname": "payment_status", "label": _("Payment Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "receipt_purpose", "label": _("Purpose"), "fieldtype": "Data", "width": 130},
        {"fieldname": "customer_reference_no", "label": _("Customer Ref"), "fieldtype": "Data", "width": 160},
        {"fieldname": "sales_order_no", "label": _("Sales Order"), "fieldtype": "Data", "width": 180},
        {"fieldname": "sales_invoice_no", "label": _("Sales Invoice"), "fieldtype": "Data", "width": 180},
        {"fieldname": "ref_grand_total", "label": _("Ref Grand Total"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "total_amount", "label": _("CR Amount"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "paid_amount", "label": _("CR Paid"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "outstanding_amount", "label": _("CR Outstanding"), "fieldtype": "Currency", "width": 130},
        {"fieldname": "ref_outstanding", "label": _("Ref Outstanding"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "stamp_mode", "label": _("Stamp Mode"), "fieldtype": "Data", "width": 100},
        {"fieldname": "digital_stamp_status", "label": _("Stamp Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "payment_entries", "label": _("Payment Entry"), "fieldtype": "Data", "width": 200},
    ]


def _enrich_with_reference_data(data: List[Dict]) -> List[Dict]:
    """
    Enrich report data with reference document data.
    - ref_grand_total: Total amount from Sales Order/Invoice
    - ref_outstanding: Remaining outstanding in Sales Order/Invoice
    - payment_status: Calculated status based on actual payment state
    """
    for row in data:
        ref_outstanding = 0
        ref_grand_total = 0
        payment_status = ""

        # Get Sales Order data
        if row.get("sales_order_no"):
            so_names = [s.strip() for s in row["sales_order_no"].split(",") if s.strip()]
            for so_name in so_names:
                so_data = frappe.db.get_value(
                    "Sales Order", so_name,
                    ["grand_total", "advance_paid", "rounded_total"],
                    as_dict=True
                )
                if so_data:
                    grand = so_data.get("rounded_total") or so_data.get("grand_total") or 0
                    paid = so_data.get("advance_paid") or 0
                    ref_grand_total += grand
                    ref_outstanding += (grand - paid)

        # Get Sales Invoice data
        if row.get("sales_invoice_no"):
            si_names = [s.strip() for s in row["sales_invoice_no"].split(",") if s.strip()]
            for si_name in si_names:
                si_data = frappe.db.get_value(
                    "Sales Invoice", si_name,
                    ["grand_total", "outstanding_amount", "rounded_total"],
                    as_dict=True
                )
                if si_data:
                    grand = si_data.get("rounded_total") or si_data.get("grand_total") or 0
                    ref_grand_total += grand
                    ref_outstanding += (si_data.get("outstanding_amount") or 0)

        row["ref_outstanding"] = ref_outstanding
        row["ref_grand_total"] = ref_grand_total

        # Determine payment status based on CR status AND reference outstanding
        original_status = row.get("status", "")

        if original_status == "Cancelled":
            payment_status = "Cancelled"
        elif original_status == "Draft":
            payment_status = "Draft"
        elif original_status == "Issued":
            payment_status = "Pending"
        elif original_status == "Partially Paid":
            payment_status = "In Progress"
        elif original_status == "Paid":
            # CR is paid, check if SO/SI is fully paid or still has outstanding
            if ref_outstanding > 0:
                payment_status = "DP/Partial"
            else:
                payment_status = "Full Payment"
        else:
            payment_status = original_status

        row["payment_status"] = payment_status

    return data


def _get_conditions(filters: Dict) -> Tuple[str, Dict]:
    conditions = []
    params: Dict[str, str] = {}

    mapping = {
        "date_from": ("cr.posting_date", ">="),
        "date_to": ("cr.posting_date", "<="),
        "receipt_no": ("cr.name", "="),
        # payment_status is calculated field - filtered post-processing in execute()
        "customer": ("cr.customer", "="),
        "customer_reference_no": ("cr.customer_reference_no", "="),
        "sales_order_no": ("cri.sales_order", "="),
        "billing_no": ("cri.sales_invoice", "="),
        "receipt_purpose": ("cr.receipt_purpose", "="),
        "stamp_mode": ("cr.stamp_mode", "="),
        "digital_stamp_status": ("cr.digital_stamp_status", "="),
    }

    for key, (field, operator) in mapping.items():
        if filters.get(key):
            conditions.append(f"{field} {operator} %({key})s")
            params[key] = filters[key]

    if filters.get("sales_invoice_no"):
        conditions.append("cri.sales_invoice = %(sales_invoice_no)s")
        params["sales_invoice_no"] = filters["sales_invoice_no"]

    where = " and ".join(conditions) if conditions else "1=1"
    return where, params


def _get_data(filters: Dict) -> List[Dict]:
    where, params = _get_conditions(filters)
    query = f"""
        select
            cr.name as receipt_no,
            cr.posting_date,
            cr.customer,
            cr.status,
            cr.receipt_purpose,
            cr.customer_reference_no,
            group_concat(distinct cri.sales_order separator ', ') as sales_order_no,
            group_concat(distinct cri.sales_invoice separator ', ') as sales_invoice_no,
            cr.total_amount,
            cr.paid_amount,
            cr.outstanding_amount,
            cr.stamp_mode,
            cr.digital_stamp_status,
            group_concat(distinct crp.payment_entry separator ', ') as payment_entries
        from `tabCustomer Receipt` cr
        left join `tabCustomer Receipt Item` cri on cri.parent = cr.name
        left join `tabCustomer Receipt Payment` crp on crp.parent = cr.name
        where {where}
        group by cr.name
        order by cr.posting_date desc, cr.name desc
    """
    return frappe.db.sql(query, params, as_dict=True)
