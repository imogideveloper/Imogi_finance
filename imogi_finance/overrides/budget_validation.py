# Override for erpnext budget validation
from __future__ import annotations
import frappe
from frappe import _
from frappe.utils import flt, get_last_day
from erpnext.accounts.doctype.budget.budget import (
    BudgetError, compare_expense_with_budget,
    get_accumulated_monthly_budget, get_actions,
)

def validate_budget_records(args, budget_records, expense_amount):
    for budget in budget_records:
        yearly_action, monthly_action = get_actions(args, budget)
        args["for_material_request"] = budget.for_material_request
        args["for_purchase_order"] = budget.for_purchase_order
        if yearly_action in ("Stop", "Warn"):
            if flt(budget.budget_amount):
                compare_expense_with_budget(args, flt(budget.budget_amount), _("Annual"), yearly_action, budget.budget_against, expense_amount)
            else:
                frappe.throw(_("Budget Amount is not set for Account {0}. Please configure the budget amount.").format(frappe.bold(args.account)), BudgetError, title=_("Budget Not Configured"))
        if monthly_action in ["Stop", "Warn"]:
            if flt(budget.budget_amount):
                budget_amount = get_accumulated_monthly_budget(budget.monthly_distribution, args.posting_date, args.fiscal_year, budget.budget_amount)
                args["month_end_date"] = get_last_day(args.posting_date)
                compare_expense_with_budget(args, budget_amount, _("Accumulated Monthly"), monthly_action, budget.budget_against, expense_amount)
            else:
                frappe.throw(_("Budget Amount is not set for Account {0}. Please configure the budget amount.").format(frappe.bold(args.account)), BudgetError, title=_("Budget Not Configured"))
