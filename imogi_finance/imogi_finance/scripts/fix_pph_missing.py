"""
Quick Fix Script: Add PPh to Purchase Invoice
==============================================

This script adds missing PPh (Withholding Tax) to Purchase Invoice
that was created from Expense Request but PPh was not calculated.

Usage:
------
1. Via Browser Console (Frappe Cloud):
   frappe.call({
       method: 'imogi_finance.scripts.fix_pph_missing.diagnose_pph',
       args: {pi_name: 'ACC-PINV-2026-00025'},
       callback: function(r) { console.log(r.message); }
   });

2. Via Server Console:
   bench --site [site-name] console

   Then run:
   from imogi_finance.scripts.fix_pph_missing import fix_pph_for_pi
   fix_pph_for_pi("ACC-PINV-2026-00024")

   Or for batch fix:
   fix_multiple_pis(["ACC-PINV-2026-00024", "ACC-PINV-2026-00025"])
"""

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def diagnose_pph(pi_name):
    """
    Diagnose why PPh is not calculated for a Purchase Invoice.
    Can be called from browser console.

    Args:
        pi_name: Purchase Invoice name

    Returns:
        dict with diagnosis information
    """
    try:
        # Get PI document
        pi = frappe.get_doc("Purchase Invoice", pi_name)

        result = {
            "pi_name": pi_name,
            "pi_data": {
                "supplier": pi.supplier,
                "total": pi.total,
                "grand_total": pi.grand_total,
                "apply_tds": getattr(pi, "apply_tds", 0),
                "tax_withholding_category": getattr(pi, "tax_withholding_category", None),
                "imogi_pph_type": getattr(pi, "imogi_pph_type", None),
                "taxes_deducted": getattr(pi, "taxes_and_charges_deducted", 0),
            }
        }

        # Check if from ER
        er_name = getattr(pi, "imogi_expense_request", None)
        result["er_name"] = er_name

        if not er_name:
            result["status"] = "not_from_er"
            result["message"] = "PI was not created from Expense Request"
            return result

        # Get ER
        er = frappe.get_doc("Expense Request", er_name)

        result["er_data"] = {
            "total": er.total,
            "is_pph_applicable": getattr(er, "is_pph_applicable", 0),
            "pph_type": getattr(er, "pph_type", None),
            "total_pph": getattr(er, "total_pph", 0),
        }

        # Check ER items
        er_items_with_pph = []
        for item in (er.items or []):
            if getattr(item, "is_pph_applicable", 0):
                er_items_with_pph.append({
                    "expense_account": item.expense_account,
                    "amount": item.amount,
                    "pph_base_amount": getattr(item, "pph_base_amount", 0),
                    "pph_amount": getattr(item, "pph_amount", 0),
                })

        result["er_items_with_pph"] = er_items_with_pph

        # Check PI items
        pi_items_with_tds = []
        for item in (pi.items or []):
            if getattr(item, "apply_tds", 0):
                pi_items_with_tds.append({
                    "expense_account": item.expense_account,
                    "amount": item.amount,
                })

        result["pi_items_with_tds"] = pi_items_with_tds

        # Diagnosis
        issues = []

        if not getattr(er, "is_pph_applicable", 0):
            issues.append("ER Header 'Apply WHT' is NOT checked")

        if not getattr(er, "pph_type", None):
            issues.append("ER 'PPh Type' is NOT set")

        if not er_items_with_pph:
            issues.append("NO items in ER have 'Apply WHT' checked")

        if not getattr(pi, "apply_tds", 0):
            issues.append("PI 'Apply TDS' is NOT set")

        if not getattr(pi, "tax_withholding_category", None):
            issues.append("PI 'Tax Withholding Category' is NOT set")

        if not pi_items_with_tds:
            issues.append("NO items in PI have 'Apply TDS' set")

        result["issues"] = issues
        result["status"] = "has_issues" if issues else "ok"

        # Recommendation
        if issues:
            if not getattr(er, "is_pph_applicable", 0) or not getattr(er, "pph_type", None) or not er_items_with_pph:
                result["recommendation"] = f"Fix ER {er_name}: Check 'Apply WHT', select PPh Type, and check 'Apply WHT' on items. Then recreate PI."
            else:
                result["recommendation"] = f"Run fix script or manually set PPh configuration on PI {pi_name}"
        else:
            result["recommendation"] = "Configuration looks correct. Issue may be in Tax Withholding Category or Supplier setup."

        return result

    except Exception as e:
        frappe.log_error(
            title=f"PPh Diagnosis Error - {pi_name}",
            message=frappe.get_traceback()
        )
        return {
            "status": "error",
            "pi_name": pi_name,
            "error": str(e)
        }


@frappe.whitelist()
def apply_pph_fix(pi_name):
    """
    Apply PPh fix to Purchase Invoice.
    Can be called from browser console.

    Args:
        pi_name: Purchase Invoice name

    Returns:
        dict with fix result
    """
    result = fix_pph_for_pi(pi_name, dry_run=False)
    frappe.db.commit()
    return result


def fix_pph_for_pi(pi_name, dry_run=False):
    """
    Add PPh calculation to Purchase Invoice that's missing it.

    Args:
        pi_name: Purchase Invoice name (e.g., "ACC-PINV-2026-00024")
        dry_run: If True, only show what would be done (no save)

    Returns:
        dict with status and details
    """
    try:
        # Get PI document
        pi = frappe.get_doc("Purchase Invoice", pi_name)

        print(f"\n{'='*60}")
        print(f"Checking Purchase Invoice: {pi_name}")
        print(f"{'='*60}")

        # Check if PI was created from Expense Request
        er_name = getattr(pi, "imogi_expense_request", None)
        if not er_name:
            print(f"⚠️  PI {pi_name} was NOT created from Expense Request")
            print(f"   Cannot auto-fix. Manual review required.")
            return {
                "status": "skipped",
                "reason": "Not created from ER",
                "pi_name": pi_name
            }

        print(f"✓ Created from Expense Request: {er_name}")

        # Get ER document
        er = frappe.get_doc("Expense Request", er_name)

        # Check if ER has PPh
        er_total_pph = flt(getattr(er, "total_pph", 0))
        if er_total_pph == 0:
            print(f"✓ ER has no PPh (total_pph = 0)")
            print(f"   No fix needed.")
            return {
                "status": "no_action_needed",
                "reason": "ER has no PPh",
                "pi_name": pi_name,
                "er_name": er_name
            }

        print(f"✓ ER Total PPh: Rp {er_total_pph:,.2f}")

        # Check current PI PPh status
        current_pph = flt(getattr(pi, "taxes_and_charges_deducted", 0))
        print(f"  Current PI PPh: Rp {current_pph:,.2f}")

        if current_pph > 0:
            print(f"✓ PI already has PPh calculated")
            print(f"   No fix needed.")
            return {
                "status": "already_ok",
                "reason": "PPh already calculated",
                "pi_name": pi_name,
                "current_pph": current_pph
            }

        # Check if ER has Apply WHT enabled
        header_apply_wht = bool(getattr(er, "is_pph_applicable", 0))
        pph_type = getattr(er, "pph_type", None)

        if not header_apply_wht or not pph_type:
            print(f"⚠️  ER does not have proper PPh configuration:")
            print(f"   - Header Apply WHT: {header_apply_wht}")
            print(f"   - PPh Type: {pph_type}")
            print(f"   ")
            print(f"   ACTION REQUIRED:")
            print(f"   1. Edit ER {er_name}")
            print(f"   2. Tab Tax → Check 'Apply WHT'")
            print(f"   3. Select PPh Type")
            print(f"   4. Save ER")
            print(f"   5. Re-run this script")
            return {
                "status": "er_config_error",
                "reason": "ER missing PPh configuration",
                "pi_name": pi_name,
                "er_name": er_name
            }

        print(f"✓ ER PPh Configuration:")
        print(f"  - Apply WHT: {header_apply_wht}")
        print(f"  - PPh Type: {pph_type}")

        # Check which items have Apply WHT
        items_with_pph = [
            item for item in (getattr(er, "items", []) or [])
            if getattr(item, "is_pph_applicable", 0)
        ]

        if not items_with_pph:
            print(f"⚠️  No items in ER have 'Apply WHT' checked")
            print(f"   ")
            print(f"   ACTION REQUIRED:")
            print(f"   1. Edit ER {er_name}")
            print(f"   2. Tab Items → Check 'Apply WHT' on relevant items")
            print(f"   3. Save ER")
            print(f"   4. Re-run this script")
            return {
                "status": "er_items_error",
                "reason": "No items with Apply WHT",
                "pi_name": pi_name,
                "er_name": er_name
            }

        print(f"✓ Items with Apply WHT: {len(items_with_pph)}")
        for item in items_with_pph:
            print(f"  - {item.expense_account}")

        # Calculate total PPh base amount
        pph_base_amount = sum(
            flt(getattr(item, "pph_base_amount", 0) or getattr(item, "net_amount", 0))
            for item in items_with_pph
        )

        print(f"✓ PPh Base Amount: Rp {pph_base_amount:,.2f}")

        # Verify tax withholding category exists
        if not frappe.db.exists("Tax Withholding Category", pph_type):
            print(f"❌ Tax Withholding Category '{pph_type}' does not exist")
            return {
                "status": "category_not_found",
                "reason": f"Category '{pph_type}' not in system",
                "pi_name": pi_name
            }

        print(f"✓ Tax Withholding Category '{pph_type}' exists")

        # Check category rate
        category_rate = frappe.db.get_value(
            "Tax Withholding Category",
            pph_type,
            "rate"
        )
        print(f"✓ WHT Rate: {category_rate}%")

        # Expected PPh amount
        expected_pph = pph_base_amount * flt(category_rate) / 100
        print(f"✓ Expected PPh: Rp {expected_pph:,.2f}")

        print(f"\n{'='*60}")
        print(f"FIX SUMMARY")
        print(f"{'='*60}")
        print(f"Purchase Invoice: {pi_name}")
        print(f"Expense Request: {er_name}")
        print(f"")
        print(f"Current Status:")
        print(f"  PI PPh Amount: Rp {current_pph:,.2f}")
        print(f"  ER PPh Amount: Rp {er_total_pph:,.2f}")
        print(f"")
        print(f"Will Apply:")
        print(f"  tax_withholding_category: {pph_type}")
        print(f"  withholding_tax_base_amount: Rp {pph_base_amount:,.2f}")
        print(f"  apply_tds: 1")
        print(f"  Expected PPh: Rp {expected_pph:,.2f}")
        print(f"")

        if dry_run:
            print(f"🔍 DRY RUN MODE - No changes will be saved")
            print(f"   Remove dry_run=True to apply fix")
            return {
                "status": "dry_run",
                "pi_name": pi_name,
                "expected_pph": expected_pph
            }

        # Apply the fix
        print(f"Applying fix...")

        # Set PPh fields
        pi.apply_tds = 1
        pi.tax_withholding_category = pph_type
        pi.imogi_pph_type = pph_type
        pi.withholding_tax_base_amount = pph_base_amount

        # Set item-level apply_tds
        for pi_item in pi.items:
            # Find matching ER item by expense_account
            er_item = next(
                (item for item in items_with_pph
                 if getattr(item, "expense_account", None) == pi_item.expense_account),
                None
            )

            if er_item and hasattr(pi_item, "apply_tds"):
                pi_item.apply_tds = 1
                print(f"  ✓ Set apply_tds=1 for item: {pi_item.expense_account}")
            elif hasattr(pi_item, "apply_tds"):
                pi_item.apply_tds = 0
                print(f"  ✓ Set apply_tds=0 for item: {pi_item.expense_account}")

        # Call set_tax_withholding to generate tax rows
        if hasattr(pi, "set_tax_withholding") and callable(pi.set_tax_withholding):
            print(f"  Calling set_tax_withholding()...")
            pi.set_tax_withholding()
        else:
            print(f"  ⚠️  set_tax_withholding method not available")

        # Save
        print(f"  Saving Purchase Invoice...")
        pi.save(ignore_permissions=True)

        # Reload and verify
        pi.reload()
        final_pph = flt(getattr(pi, "taxes_and_charges_deducted", 0))

        print(f"\n{'='*60}")
        print(f"✅ FIX COMPLETED")
        print(f"{'='*60}")
        print(f"Purchase Invoice: {pi_name}")
        print(f"Final PPh Amount: Rp {final_pph:,.2f}")
        print(f"Expected: Rp {expected_pph:,.2f}")

        if abs(final_pph - expected_pph) < 1:  # Allow 1 IDR rounding difference
            print(f"✅ PPh calculated correctly!")
        else:
            print(f"⚠️  PPh amount mismatch:")
            print(f"   Expected: Rp {expected_pph:,.2f}")
            print(f"   Got: Rp {final_pph:,.2f}")
            print(f"   Difference: Rp {abs(final_pph - expected_pph):,.2f}")

        return {
            "status": "success",
            "pi_name": pi_name,
            "er_name": er_name,
            "expected_pph": expected_pph,
            "actual_pph": final_pph,
            "difference": abs(final_pph - expected_pph)
        }

    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ ERROR")
        print(f"{'='*60}")
        print(f"Purchase Invoice: {pi_name}")
        print(f"Error: {str(e)}")
        frappe.log_error(
            title=f"PPh Fix Error - {pi_name}",
            message=frappe.get_traceback()
        )
        return {
            "status": "error",
            "pi_name": pi_name,
            "error": str(e)
        }


def fix_multiple_pis(pi_names, dry_run=False):
    """
    Fix multiple Purchase Invoices in batch.

    Args:
        pi_names: List of PI names
        dry_run: If True, only show what would be done

    Returns:
        Summary of results
    """
    results = []

    print(f"\n{'#'*60}")
    print(f"BATCH PPh FIX - {len(pi_names)} Purchase Invoices")
    print(f"{'#'*60}\n")

    for pi_name in pi_names:
        result = fix_pph_for_pi(pi_name, dry_run=dry_run)
        results.append(result)

    # Print summary
    print(f"\n{'#'*60}")
    print(f"BATCH SUMMARY")
    print(f"{'#'*60}")

    success_count = sum(1 for r in results if r["status"] == "success")
    skipped_count = sum(1 for r in results if r["status"] in ["skipped", "no_action_needed", "already_ok"])
    error_count = sum(1 for r in results if r["status"] == "error")

    print(f"Total: {len(results)}")
    print(f"✅ Success: {success_count}")
    print(f"⏭️  Skipped: {skipped_count}")
    print(f"❌ Errors: {error_count}")

    if dry_run:
        print(f"\n🔍 DRY RUN MODE - No changes were saved")

    return results


# Example usage in console:
"""
from imogi_finance.scripts.fix_pph_missing import fix_pph_for_pi, fix_multiple_pis

# Single PI - dry run first
fix_pph_for_pi("ACC-PINV-2026-00024", dry_run=True)

# If looks good, apply fix
fix_pph_for_pi("ACC-PINV-2026-00024")

# Batch fix
fix_multiple_pis([
    "ACC-PINV-2026-00024",
    "ACC-PINV-2026-00025",
    "ACC-PINV-2026-00026"
])
"""
