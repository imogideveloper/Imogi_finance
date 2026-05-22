# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
from __future__ import annotations
import frappe
from frappe import _


@frappe.whitelist()
def get_taxes_for_item(
    item_code: str,
    company: str,
    transaction_type: str = "Sales",
    customer: str | None = None,
) -> list[dict]:
    """Resolve mapping pajak untuk item.

    Prioritas:
      1. item_code + customer_group
      2. item_code
      3. item_group + customer_group
      4. item_group
      5. default (no item/group) + customer_group
      6. default (no item/group)
    """
    if not item_code or not company:
        return []

    item_group = frappe.db.get_value("Item", item_code, "item_group")
    customer_group = None
    if customer:
        customer_group = frappe.db.get_value("Customer", customer, "customer_group")

    all_mappings = frappe.get_all(
        "Item Tax Mapping",
        filters={
            "company": company,
            "enabled": 1,
            "transaction_type": ["in", [transaction_type, "Both"]],
        },
        fields=["name", "item_code", "item_group", "customer_group", "priority"],
        order_by="priority asc",
    )

    if not all_mappings:
        return []

    best = _find_best_mapping(all_mappings, item_code, item_group, customer_group)
    if not best:
        return []

    tax_rows = frappe.get_all(
        "Item Tax Mapping Detail",
        filters={"parent": best},
        fields=["account_head", "tax_rate", "charge_type", "add_deduct_tax", "description"],
        order_by="idx asc",
    )

    for row in tax_rows:
        if not row.get("description"):
            row["description"] = row["account_head"]

    return tax_rows


def _find_best_mapping(mappings, item_code, item_group, customer_group):
    tiers = {i: [] for i in range(1, 7)}

    for m in mappings:
        has_item  = bool(m.get("item_code"))
        has_group = bool(m.get("item_group"))
        has_cg    = bool(m.get("customer_group"))

        item_match  = has_item  and m["item_code"]   == item_code
        group_match = has_group and m["item_group"]  == item_group
        cg_match    = has_cg   and m["customer_group"] == customer_group
        is_default  = not has_item and not has_group

        if   item_match  and cg_match:              tiers[1].append(m)
        elif item_match  and not has_cg:            tiers[2].append(m)
        elif group_match and cg_match:              tiers[3].append(m)
        elif group_match and not has_cg:            tiers[4].append(m)
        elif is_default  and cg_match:              tiers[5].append(m)
        elif is_default  and not has_cg:            tiers[6].append(m)

    for tier in range(1, 7):
        if tiers[tier]:
            tiers[tier].sort(key=lambda x: x.get("priority") or 99)
            return tiers[tier][0]["name"]

    return None


@frappe.whitelist()
def get_mapping_preview(name: str) -> dict:
    doc = frappe.get_doc("Item Tax Mapping", name)
    return {
        "name": doc.name,
        "company": doc.company,
        "item_code": doc.item_code,
        "item_group": doc.item_group,
        "customer_group": doc.customer_group,
        "transaction_type": doc.transaction_type,
        "priority": doc.priority,
        "taxes": [
            {"account_head": r.account_head, "tax_rate": r.tax_rate,
             "charge_type": r.charge_type, "add_deduct_tax": r.add_deduct_tax}
            for r in doc.taxes
        ],
    }