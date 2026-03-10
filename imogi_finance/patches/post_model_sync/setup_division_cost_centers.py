from __future__ import annotations

import frappe


def _ensure_cost_center(name: str, company: str, parent_cost_center: str | None) -> None:
    if frappe.db.exists("Cost Center", name):
        frappe.db.set_value("Cost Center", name, "disabled", 0, update_modified=False)
        return

    doc = frappe.new_doc("Cost Center")
    doc.cost_center_name = name.replace(f" - {company_abbr(company)}", "").strip()
    doc.company = company
    doc.parent_cost_center = parent_cost_center
    doc.is_group = 0
    doc.disabled = 0
    doc.insert(ignore_permissions=True)


def company_abbr(company: str) -> str:
    abbr = frappe.db.get_value("Company", company, "abbr")
    return abbr or ""


def _update_cost_center_references(old_name: str, new_name: str) -> None:
    targets = [
        ("Expense Request", "cost_center", 0),
        ("Expense Request Item", "target_cost_center", None),
        ("Purchase Invoice", "cost_center", 0),
        ("Purchase Invoice Item", "cost_center", None),
        ("Budget", "cost_center", ["in", [0, 1]]),
    ]

    for doctype, fieldname, docstatus_filter in targets:
        if not frappe.db.has_column(doctype, fieldname):
            continue

        filters = {fieldname: old_name}
        if docstatus_filter is not None and frappe.db.has_column(doctype, "docstatus"):
            filters["docstatus"] = docstatus_filter

        records = frappe.get_all(doctype, filters=filters, pluck="name")
        for name in records or []:
            frappe.db.set_value(doctype, name, fieldname, new_name, update_modified=False)


def execute():
    company = "Inovasi Terbaik Bangsa"
    if not frappe.db.exists("Company", company):
        return

    parent = frappe.db.get_value(
        "Cost Center",
        {"company": company, "is_group": 1},
        "name",
    )

    for cost_center in [
        "Finance - ITB",
        "Marketing - ITB",
        "HR - ITB",
        "Services - ITB",
        "IT - ITB",
    ]:
        _ensure_cost_center(cost_center, company, parent)

    legacy_name = "HR Management - ITB"
    if frappe.db.exists("Cost Center", legacy_name):
        _update_cost_center_references(legacy_name, "HR - ITB")
        frappe.db.set_value("Cost Center", legacy_name, "disabled", 1, update_modified=False)
