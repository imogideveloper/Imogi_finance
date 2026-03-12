import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": _("ID"),
            "fieldname": "budget_name",
            "fieldtype": "Link",
            "options": "Budget",
            "width": 180,
        },
        {
            "label": _("Cost Center"),
            "fieldname": "cost_center",
            "fieldtype": "Link",
            "options": "Cost Center",
            "width": 180,
        },
        {
            "label": _("Fiscal Year"),
            "fieldname": "fiscal_year",
            "fieldtype": "Link",
            "options": "Fiscal Year",
            "width": 120,
        },
        {
            "label": _("Akun"),
            "fieldname": "account",
            "fieldtype": "Link",
            "options": "Account",
            "width": 220,
        },
        {
            "label": _("Budget Amount"),
            "fieldname": "budget_amount",
            "fieldtype": "Currency",
            "width": 160,
        },
    ]


def get_data(filters):
    conditions = []
    values = {}

    if filters.get("company"):
        conditions.append("b.company = %(company)s")
        values["company"] = filters.get("company")

    if filters.get("fiscal_year"):
        conditions.append("b.fiscal_year = %(fiscal_year)s")
        values["fiscal_year"] = filters.get("fiscal_year")

    if filters.get("cost_center"):
        conditions.append("b.cost_center = %(cost_center)s")
        values["cost_center"] = filters.get("cost_center")

    if filters.get("account"):
        conditions.append("ba.account = %(account)s")
        values["account"] = filters.get("account")

    if filters.get("budget_against"):
        conditions.append("b.budget_against = %(budget_against)s")
        values["budget_against"] = filters.get("budget_against")

    conditions.append("b.docstatus < 2")

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    data = frappe.db.sql(
        f"""
        SELECT
            b.name AS budget_name,
            b.cost_center AS cost_center,
            b.fiscal_year AS fiscal_year,
            ba.account AS account,
            ba.budget_amount AS budget_amount
        FROM `tabBudget` b
        LEFT JOIN `tabBudget Account` ba
            ON ba.parent = b.name
        {where_clause}
        ORDER BY b.name ASC, ba.idx ASC
        """,
        values,
        as_dict=True,
    )

    return data