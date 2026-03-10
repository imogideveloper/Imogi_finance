"""
Script to check Tax Withholding Category configuration
Run in browser console
"""

import frappe
from frappe.utils import flt


@frappe.whitelist()
def check_pph_category(category_name="PPh 23"):
    """
    Check Tax Withholding Category configuration

    Usage in browser console:
    frappe.call({
        method: 'imogi_finance.scripts.check_pph_config.check_pph_category',
        args: {category_name: 'PPh 23'},
        callback: function(r) {
            console.log(r.message);
            alert(JSON.stringify(r.message, null, 2));
        }
    });
    """
    try:
        if not frappe.db.exists("Tax Withholding Category", category_name):
            return {
                "status": "error",
                "message": f"Tax Withholding Category '{category_name}' not found!",
                "exists": False
            }

        # Get category details
        category = frappe.get_doc("Tax Withholding Category", category_name)

        result = {
            "status": "found",
            "category_name": category_name,
            "data": {
                "category_name": category.category_name,
                "rate": category.rate,
                "account_head": getattr(category, "account_head", None),
                "description": getattr(category, "description", None),
                "disabled": getattr(category, "disabled", 0),
            }
        }

        # Check accounts table
        accounts = []
        for acc in (category.accounts or []):
            accounts.append({
                "company": acc.company,
                "account": acc.account
            })

        result["accounts"] = accounts

        # Check rates table
        rates = []
        for rate in (category.rates or []):
            rates.append({
                "fiscal_year": getattr(rate, "fiscal_year", None),
                "tax_withholding_rate": rate.tax_withholding_rate,
                "from_date": str(getattr(rate, "from_date", "")),
                "to_date": str(getattr(rate, "to_date", "")),
            })

        result["rates"] = rates

        # Diagnosis
        issues = []

        if getattr(category, "disabled", 0):
            issues.append("Category is DISABLED")

        if not accounts:
            issues.append("No accounts configured in Accounts table")

        if not category.rate and not rates:
            issues.append("No rate configured")

        # Check if account exists for company
        if accounts:
            for acc in accounts:
                if not frappe.db.exists("Account", acc["account"]):
                    issues.append(f"Account '{acc['account']}' does not exist")

        result["issues"] = issues
        result["has_issues"] = len(issues) > 0

        if issues:
            result["recommendation"] = "Fix the issues listed above in Tax Withholding Category"
        else:
            result["recommendation"] = "Configuration looks OK. Check supplier configuration."

        return result

    except Exception as e:
        frappe.log_error(
            title=f"Check PPh Category Error - {category_name}",
            message=frappe.get_traceback()
        )
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist()
def check_supplier_pph(supplier_name):
    """
    Check if supplier is configured for withholding tax

    Usage in browser console:
    frappe.call({
        method: 'imogi_finance.scripts.check_pph_config.check_supplier_pph',
        args: {supplier_name: 'PT Ringdua'},
        callback: function(r) {
            console.log(r.message);
            alert(JSON.stringify(r.message, null, 2));
        }
    });
    """
    try:
        if not frappe.db.exists("Supplier", supplier_name):
            return {
                "status": "error",
                "message": f"Supplier '{supplier_name}' not found!"
            }

        supplier = frappe.get_doc("Supplier", supplier_name)

        result = {
            "status": "found",
            "supplier_name": supplier_name,
            "data": {
                "supplier_name": supplier.supplier_name,
                "supplier_type": supplier.supplier_type,
                "tax_withholding_category": getattr(supplier, "tax_withholding_category", None),
                "tax_id": getattr(supplier, "tax_id", None),
                "pan": getattr(supplier, "pan", None),
            }
        }

        # Diagnosis
        issues = []

        if not getattr(supplier, "tax_withholding_category", None):
            issues.append("Supplier does NOT have Tax Withholding Category configured")
            issues.append("This may prevent automatic PPh calculation")

        result["issues"] = issues
        result["has_issues"] = len(issues) > 0

        if issues:
            result["recommendation"] = f"Edit Supplier '{supplier_name}' → Set Tax Withholding Category to 'PPh 23'"
        else:
            result["recommendation"] = "Supplier configuration looks OK"

        return result

    except Exception as e:
        frappe.log_error(
            title=f"Check Supplier Error - {supplier_name}",
            message=frappe.get_traceback()
        )
        return {
            "status": "error",
            "message": str(e)
        }


@frappe.whitelist()
def quick_fix_pi(pi_name):
    """
    Quick fix for PI without PPh - manually add PPh entry

    Usage in browser console:
    frappe.call({
        method: 'imogi_finance.scripts.check_pph_config.quick_fix_pi',
        args: {pi_name: 'ACC-PINV-2026-00025'},
        callback: function(r) {
            console.log(r.message);
            if (r.message.status === 'success') {
                cur_frm.reload_doc();
            }
        }
    });
    """
    try:
        pi = frappe.get_doc("Purchase Invoice", pi_name)

        # Check if already has PPh
        current_pph = flt(getattr(pi, "taxes_and_charges_deducted", 0))
        if current_pph > 0:
            return {
                "status": "skip",
                "message": f"PI already has PPh: Rp {current_pph:,.2f}",
                "pi_name": pi_name
            }

        # Get ER
        er_name = getattr(pi, "imogi_expense_request", None)
        if not er_name:
            return {
                "status": "error",
                "message": "PI not created from Expense Request",
                "pi_name": pi_name
            }

        er = frappe.get_doc("Expense Request", er_name)

        # Get PPh config from ER
        pph_type = getattr(er, "pph_type", None)
        total_pph_er = flt(getattr(er, "total_pph", 0))

        if not pph_type or total_pph_er == 0:
            return {
                "status": "error",
                "message": "ER does not have PPh configuration or PPh amount is 0",
                "pi_name": pi_name,
                "er_name": er_name
            }

        # Check category exists
        if not frappe.db.exists("Tax Withholding Category", pph_type):
            return {
                "status": "error",
                "message": f"Tax Withholding Category '{pph_type}' not found",
                "pi_name": pi_name
            }

        category = frappe.get_doc("Tax Withholding Category", pph_type)

        # Get account for company
        account = None
        for acc in (category.accounts or []):
            if acc.company == pi.company:
                account = acc.account
                break

        if not account:
            return {
                "status": "error",
                "message": f"No account configured for company '{pi.company}' in category '{pph_type}'",
                "pi_name": pi_name
            }

        # Calculate PPh base amount from items
        pph_base = sum(
            flt(item.amount)
            for item in (pi.items or [])
        )

        # Get rate from child table (rates by fiscal year/date range)
        rate = 0
        posting_date = pi.posting_date

        # Try to find rate for posting date
        for rate_row in (category.rates or []):
            from_date = getattr(rate_row, "from_date", None)
            to_date = getattr(rate_row, "to_date", None)

            if from_date and to_date:
                if from_date <= posting_date <= to_date:
                    rate = flt(rate_row.tax_withholding_rate)
                    break
            elif hasattr(rate_row, "tax_withholding_rate"):
                # Fallback: use first rate if no date filter
                rate = flt(rate_row.tax_withholding_rate)
                break

        # Calculate PPh amount
        if rate > 0:
            pph_amount = pph_base * rate / 100
        else:
            # Fallback: use ER's pre-calculated amount
            pph_amount = total_pph_er

        # Set PPh fields on PI
        pi.apply_tds = 1
        pi.tax_withholding_category = pph_type
        if hasattr(pi, "imogi_pph_type"):
            pi.imogi_pph_type = pph_type

        # Add tax row for PPh
        existing_pph_row = None
        for tax in (pi.taxes or []):
            if tax.account_head == account:
                existing_pph_row = tax
                break

        if existing_pph_row:
            # Update existing row
            existing_pph_row.tax_amount = -pph_amount
            existing_pph_row.total = pi.total - pph_amount
            existing_pph_row.base_tax_amount = -pph_amount
            existing_pph_row.base_total = pi.total - pph_amount
        else:
            # Add new tax row
            pi.append("taxes", {
                "charge_type": "Actual",
                "account_head": account,
                "description": f"Tax Withheld - {pph_type}",
                "rate": rate,  # Show tax rate in UI
                "tax_amount": -pph_amount,
                "total": pi.total - pph_amount,
                "base_tax_amount": -pph_amount,
                "base_total": pi.total - pph_amount,
                "add_deduct_tax": "Deduct",
                "category": "Total",
                "cost_center": pi.get("cost_center") or frappe.get_cached_value("Company", pi.company, "cost_center")
            })

        # Calculate totals
        pi.run_method("calculate_taxes_and_totals")

        # Save
        pi.save(ignore_permissions=True)
        frappe.db.commit()

        # Reload to verify
        pi.reload()
        final_pph = flt(getattr(pi, "taxes_and_charges_deducted", 0))

        return {
            "status": "success",
            "message": f"PPh successfully added to PI",
            "pi_name": pi_name,
            "er_name": er_name,
            "pph_type": pph_type,
            "pph_base": pph_base,
            "pph_rate": rate,
            "pph_amount_calculated": pph_amount,
            "pph_amount_final": final_pph,
            "account_used": account
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            title=f"Quick Fix PI Error - {pi_name}",
            message=frappe.get_traceback()
        )
        return {
            "status": "error",
            "message": str(e),
            "pi_name": pi_name
        }
