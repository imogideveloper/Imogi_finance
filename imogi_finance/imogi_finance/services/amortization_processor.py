"""
Manual amortization processor untuk deferred expenses.

Untuk generate Journal Entries dari amortization schedule yang belum di-posting.
Used untuk fix missing amortization di Deferred Expense Tracker.
"""

import frappe
from frappe.utils import add_months, flt, getdate
from frappe import _
from datetime import date


@frappe.whitelist()
def create_amortization_schedule_for_pi(pi_name: str):
    """
    Generate dan create amortization schedule untuk Purchase Invoice.

    Akan create Journal Entry untuk setiap bulan dari deferred items.

    Args:
        pi_name: Purchase Invoice document name

    Returns:
        dict: {
            "pi_name": str,
            "total_schedules": int,
            "journal_entries": list[str],
            "total_amount": float
        }
    """

    # Get PI
    pi = frappe.get_doc("Purchase Invoice", pi_name)

    if pi.docstatus != 1:
        frappe.throw(_("Purchase Invoice must be submitted"))

    # Get deferred items - convert to dict untuk reliable access
    deferred_items = []

    # Get PI as dict
    pi_dict = pi.as_dict()
    items_data = pi_dict.get("items", [])

    for idx, item_dict in enumerate(items_data):
        deferred_acct = item_dict.get("deferred_expense_account")

        if deferred_acct:
            # Find matching item object from pi.items
            for item_obj in pi.items:
                if item_obj.name == item_dict.get("name"):
                    deferred_items.append(item_obj)
                    break
    if not deferred_items:
        frappe.throw(_("No deferred items found in this Purchase Invoice"))

    # Generate schedule per item
    all_schedules = []

    for item in deferred_items:
        # Try different field names untuk amount
        amount = flt(item.get("net_amount") or item.get("amount") or item.get("line_amount") or item.get("base_net_amount") or 0)

        # Get periods - use default 12 if not set
        periods_raw = item.get("deferred_expense_periods")
        if periods_raw and periods_raw != "undefined":
            periods = int(periods_raw)
        else:
            periods = 12

        start_date = getdate(item.service_start_date)
        prepaid_account = item.deferred_expense_account
        expense_account = prepaid_account

		# Tambahkan:
        # Generate monthly schedule untuk item ini
        item_schedules = _generate_monthly_schedule(
            amount=amount,
            periods=periods,
            start_date=start_date,
            prepaid_account=prepaid_account,
            expense_account=expense_account,
            pi_name=pi_name,
            item_code=item.item_code
        )

        all_schedules.extend(item_schedules)

    # Create Journal Entries
    je_names = []
    total_amount = 0
    je_errors = []

    for schedule_entry in all_schedules:
        try:
            je_name = _create_deferred_expense_je(schedule_entry, pi_name)
            je_names.append(je_name)
            total_amount += schedule_entry["amount"]
        except Exception as e:
            error_msg = f"Error creating JE for {schedule_entry['posting_date']}: {str(e)}"
            je_errors.append(error_msg)

    return {
        "pi_name": pi_name,
        "total_schedules": len(all_schedules),
        "total_amount": total_amount,
        "journal_entries": je_names,
        "errors": je_errors,
        "status": "success" if je_names else "failed"
    }


def _generate_monthly_schedule(
    amount: float,
    periods: int,
    start_date: date,
    prepaid_account: str,
    expense_account: str,
    pi_name: str,
    item_code: str
) -> list:
    """
    Generate monthly breakdown dari total amount.

    Divides total amount by periods, handles rounding di period terakhir.
    """

    schedule = []
    monthly_amount = amount / periods
    remaining = amount

    for month_idx in range(periods):
        # Last month gets remainder (untuk handle rounding errors)
        if month_idx == periods - 1:
            period_amount = remaining
        else:
            period_amount = flt(monthly_amount)

        posting_date = add_months(start_date, month_idx)

        schedule.append({
            "period": month_idx + 1,
            "posting_date": posting_date,
            "amount": period_amount,
            "prepaid_account": prepaid_account,
            "expense_account": expense_account,
            "pi_name": pi_name,
            "item_code": item_code,
            "description": f"Deferred Expense Amortization - {item_code} (Month {month_idx + 1} of {periods})"
        })

        remaining -= period_amount

    return schedule


def _create_deferred_expense_je(schedule_entry: dict, pi_name: str) -> str:
    """
    Create individual Journal Entry untuk satu bulan amortization.

    Prepaid Account (Debit) → Expense Account (Credit)
    """

    # Create new Journal Entry langsung (tanpa duplicate check yang kompleks)
    je_doc = frappe.new_doc("Journal Entry")
    je_doc.posting_date = schedule_entry["posting_date"]
    je_doc.reference_type = "Purchase Invoice"
    je_doc.reference_name = pi_name
    je_doc.description = schedule_entry["description"]
    je_doc.remark = f"Auto-generated deferred expense amortization for {schedule_entry['item_code']}"

    # Get project if any
    project = frappe.db.get_value("Purchase Invoice", pi_name, "project")

    # Account 1: Prepaid/Deferred Account (Debit)
    je_doc.append("accounts", {
        "account": schedule_entry["prepaid_account"],
        "debit": schedule_entry["amount"],
        "debit_in_account_currency": schedule_entry["amount"],
        "project": project,
        "party_type": None,
        "party": None,
        "cost_center": None
    })

    # Account 2: Expense Account (Credit)
    je_doc.append("accounts", {
        "account": schedule_entry["expense_account"],
        "credit": schedule_entry["amount"],
        "credit_in_account_currency": schedule_entry["amount"],
        "project": project,
        "party_type": None,
        "party": None,
        "cost_center": None
    })

    # Insert dan submit
    je_doc.insert(ignore_permissions=True)
    je_doc.submit()

    frappe.db.commit()

    return je_doc.name


@frappe.whitelist()
def get_amortization_schedule(pi_name: str) -> dict:
    """
    Get breakdown schedule untuk satu Purchase Invoice.

    Returns:
        dict: {
            "pi": str,
            "total_deferred": float,
            "schedule": list[dict]
        }
    """

    pi = frappe.get_doc("Purchase Invoice", pi_name)
    deferred_items = [i for i in pi.items if i.get("enable_deferred_expense")]

    if not deferred_items:
        frappe.throw(f"No deferred items found in PI {pi_name}")

    schedule = []
    total_deferred = 0

    for item in deferred_items:
        amount = flt(item.amount)
        periods = int(item.get("deferred_expense_periods") or 12)
        start_date = getdate(item.service_start_date)

        monthly = amount / periods
        remaining = amount

        for month_idx in range(periods):
            if month_idx == periods - 1:
                period_amount = remaining
            else:
                period_amount = flt(monthly)

            posting_date = add_months(start_date, month_idx)

            schedule.append({
                "period": month_idx + 1,
                "posting_date": str(posting_date),
                "amount": period_amount,
                "item_code": item.item_code,
                "description": item.description,
                "bulan": posting_date.strftime("%B %Y")
            })

            total_deferred += period_amount
            remaining -= period_amount

    # Sort by date
    schedule.sort(key=lambda x: x["posting_date"])

    return {
        "pi": pi_name,
        "total_deferred": total_deferred,
        "total_periods": len(schedule),
        "schedule": schedule
    }


@frappe.whitelist()
def create_all_missing_amortization() -> dict:
    """
    Create amortization untuk SEMUA PI yang punya deferred items.

    Used untuk batch processing missing amortization.
    """

    # Get semua PI dengan deferred items dan status submitted
    pi_list = frappe.db.get_list(
        "Purchase Invoice",
        filters={
            "docstatus": 1  # submitted only
        },
        fields=["name"]
    )

    results = {
        "total_pi": 0,
        "success": 0,
        "failed": 0,
        "journal_entries_created": 0,
        "errors": [],
        "details": []
    }

    for pi_record in pi_list:
        try:
            pi_doc = frappe.get_doc("Purchase Invoice", pi_record["name"])

            # Check jika ada deferred items
            deferred_items = [i for i in pi_doc.items if i.get("enable_deferred_expense")]

            if not deferred_items:
                continue

            results["total_pi"] += 1

            # Create amortization untuk PI ini
            result = create_amortization_schedule_for_pi(pi_record["name"])

            results["success"] += 1
            results["journal_entries_created"] += len(result["journal_entries"])

            results["details"].append({
                "pi_name": pi_record["name"],
                "schedules": result["total_schedules"],
                "amount": result["total_amount"],
                "jes": result["journal_entries"]
            })

        except Exception as e:
            results["failed"] += 1
            results["errors"].append({
                "pi_name": pi_record["name"],
                "error": str(e)
            })

    return results


if __name__ == "__main__":
    # Test execution
    # python -c "from imogi_finance.services.amortization_processor import create_amortization_schedule_for_pi; print(create_amortization_schedule_for_pi('ACC-PI-2026-00001'))"
    pass
