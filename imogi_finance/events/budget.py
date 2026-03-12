# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _


def before_delete(doc, method=None):
    """Prevent deletion of Budget if linked transactions exist."""

    budget_name = doc.name
    company = doc.company
    fiscal_year = doc.fiscal_year
    cost_center = doc.get("cost_center")

    linked = []

    # 1. Cek Budget Control Entry (dari Expense Request)
    bce_filters = {"company": company, "fiscal_year": fiscal_year, "docstatus": 1}
    if cost_center:
        bce_filters["cost_center"] = cost_center

    bce_list = frappe.get_all(
        "Budget Control Entry",
        filters=bce_filters,
        fields=["name", "ref_doctype", "ref_name"],
        limit=5,
    )
    for bce in bce_list:
        ref = "{} {}".format(bce.get("ref_doctype"), bce.get("ref_name")) if bce.get("ref_name") else bce.get("name")
        linked.append("Budget Control Entry: {}".format(ref))

    # 2. Cek Purchase Invoice aktif
    if cost_center:
        pi_list = frappe.db.sql(
            """
            SELECT DISTINCT pi.name
            FROM `tabPurchase Invoice` pi
            INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
            INNER JOIN `tabFiscal Year` fy ON fy.name = %(fiscal_year)s
            WHERE pi.company = %(company)s
              AND pi.docstatus = 1
              AND pii.cost_center = %(cost_center)s
              AND pi.posting_date BETWEEN fy.year_start_date AND fy.year_end_date
            LIMIT 5
            """,
            {"company": company, "cost_center": cost_center, "fiscal_year": fiscal_year},
            as_dict=True,
        )
        for pi in pi_list:
            linked.append("Purchase Invoice: {}".format(pi.get("name")))

    # 3. Cek Payment Entry aktif
    if cost_center:
        pe_list = frappe.db.sql(
            """
            SELECT DISTINCT pe.name
            FROM `tabPayment Entry` pe
            INNER JOIN `tabPayment Entry Reference` per ON per.parent = pe.name
            INNER JOIN `tabPurchase Invoice` pi ON pi.name = per.reference_name
            INNER JOIN `tabPurchase Invoice Item` pii ON pii.parent = pi.name
            INNER JOIN `tabFiscal Year` fy ON fy.name = %(fiscal_year)s
            WHERE pe.company = %(company)s
              AND pe.docstatus = 1
              AND pii.cost_center = %(cost_center)s
              AND pe.posting_date BETWEEN fy.year_start_date AND fy.year_end_date
            LIMIT 5
            """,
            {"company": company, "cost_center": cost_center, "fiscal_year": fiscal_year},
            as_dict=True,
        )
        for pe in pe_list:
            linked.append("Payment Entry: {}".format(pe.get("name")))

    # 4. Cek Expense Request aktif (pakai cost_center saja, tidak ada company/fiscal_year)
    if cost_center:
        er_list = frappe.get_all(
            "Expense Request",
            filters={
                "cost_center": cost_center,
                "docstatus": 1,
            },
            fields=["name"],
            limit=5,
        )
        for er in er_list:
            linked.append("Expense Request: {}".format(er.get("name")))

    if not linked:
        return

    sample = linked[:5]
    more = len(linked) - 5 if len(linked) > 5 else 0
    detail = "<br>".join(["• {}".format(item) for item in sample])
    if more:
        detail += "<br>• ... dan {} transaksi lainnya".format(more)

    frappe.throw(
        _(
            "Budget <b>{budget}</b> tidak dapat dihapus karena masih memiliki transaksi aktif:"
            "<br><br>{detail}<br><br>"
            "Batalkan semua transaksi terkait terlebih dahulu sebelum menghapus Budget ini."
        ).format(budget=budget_name, detail=detail),
        title=_("Budget Masih Digunakan"),
    )
