import frappe
from frappe import _
from frappe.utils import cint, flt

from imogi_finance.branching import get_branch_settings, validate_branch_alignment
from imogi_finance.accounting import PURCHASE_INVOICE_ALLOWED_STATUSES, PURCHASE_INVOICE_REQUEST_TYPES
from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_cancel_updates,
    get_er_doctype,
    get_expense_request_links,
    get_expense_request_status,
)
from imogi_finance.tax_invoice_ocr import (
    get_settings,
    normalize_npwp,
    sync_tax_invoice_upload,
    validate_tax_invoice_upload_link,
)
from imogi_finance.budget_control.workflow import (
    consume_budget_for_purchase_invoice,
    reverse_consumption_for_purchase_invoice,
    maybe_post_internal_charge_je,
)
from imogi_finance.budget_control import utils as budget_utils
from imogi_finance.budget_control import service as budget_service


def sync_expense_request_status_from_pi(doc, method=None):
    """Sync Expense Request status when Purchase Invoice status changes (e.g., Paid).

    Triggered on PI on_update_after_submit to detect when PI status badge
    changes from Unpaid to Paid (after Payment Entry is applied).
    """
    expense_request = doc.get("imogi_expense_request")

    # Handle Expense Request
    if expense_request:
        _er_doctype = get_er_doctype(expense_request)
        if _er_doctype:
            # Get current ER status based on PI status
            request_links = get_expense_request_links(expense_request)
            new_status = get_expense_request_status(request_links)

            # Get current status
            current_status = frappe.db.get_value(_er_doctype, expense_request, "status")

            # Update ER status if changed
            if current_status != new_status:
                frappe.db.set_value(
                    _er_doctype,
                    expense_request,
                    {"workflow_state": new_status, "status": new_status},
                    update_modified=False
                )
                frappe.logger().info(
                    f"[PI status sync] PI {doc.name} status changed to {doc.status}. "
                    f"Updated ER {expense_request} status: {current_status} → {new_status}"
                )



def prevent_double_wht_validate(doc, method=None):
    """Prevent double WHT on validate hook - called before other validations.

    When a Purchase Invoice is created from an Expense Request with Apply WHT,
    we need to clear the supplier's tax withholding category early to prevent
    Frappe from auto-populating it and causing double calculations.
    """
    _prevent_double_wht(doc)


def manage_ppn_variance_validate(doc, method=None):
    """Manage PPN variance for PI from ER - creates variance item and adjusts tax.

    Only runs for PI WITH Expense Request link.
    Creates/updates/deletes variance item in items table based on OCR vs calculated PPN.
    """
    # Only run for PI WITH Expense Request link
    if not getattr(doc, "imogi_expense_request", None):
        return

    # Skip if no tax invoice upload or no OCR PPN
    if not getattr(doc, "ti_tax_invoice_upload", None):
        return

    ocr_ppn = flt(getattr(doc, "ti_fp_ppn", 0) or 0)
    if ocr_ppn <= 0:
        return

    # Get PPN tax rows from taxes table
    if not hasattr(doc, "taxes") or not doc.taxes:
        return

    # Find PPN tax row(s) - look for "On Net Total" charge type
    # CRITICAL: Exclude PPh/WHT rows (add_deduct_tax="Deduct") — PPh is also "On Net Total"
    # Without this filter, PPh row (rate=2%) is mistakenly used instead of PPN (rate=11%)
    ppn_tax_rows = [
        tax for tax in doc.taxes
        if getattr(tax, "charge_type", None) == "On Net Total"
        and getattr(tax, "add_deduct_tax", "Add") == "Add"
    ]

    if not ppn_tax_rows:
        return

    # Get variance account from settings
    try:
        from imogi_finance.settings.utils import get_vat_input_accounts
        company = getattr(doc, "company", None)
        vat_accounts = get_vat_input_accounts(company)
        if not vat_accounts:
            frappe.throw("VAT Input Account di Tax Profile belum dikonfigurasi. Harap hubungi administrator.")

        # Use first VAT account as variance account
        variance_account = vat_accounts[0]
    except Exception as e:
        frappe.throw(f"Error getting VAT account: {str(e)}")

    # CRITICAL FIX: Calculate expected PPN from items EXCLUDING variance items
    # This prevents double-counting variance (once as item, once as tax adjustment)
    first_ppn_row = ppn_tax_rows[0]
    ppn_rate = flt(getattr(first_ppn_row, "rate", 0) or 0) / 100.0  # Convert percentage to decimal

    if ppn_rate <= 0:
        # Fallback to tax_amount if rate not available
        calculated_ppn = flt(getattr(first_ppn_row, "tax_amount", 0) or 0)
    else:
        # Calculate DPP excluding variance items
        dpp = 0.0
        for item in doc.get("items") or []:
            # Skip variance items from DPP calculation
            if getattr(item, "is_variance_item", 0) or getattr(item, "is_ppn_variance_row", 0):
                continue
            dpp += flt(getattr(item, "amount", 0) or 0)

        # Calculate expected PPN from DPP (excluding variance)
        calculated_ppn = dpp * ppn_rate

        frappe.logger().info(
            f"[PPN VARIANCE] PI {doc.name}: DPP (excl variance) = {dpp:,.2f}, "
            f"Rate = {ppn_rate*100:.2f}%, Expected PPN = {calculated_ppn:,.2f}"
        )

    # Calculate variance with decimal precision (don't round to integer)
    # This allows tracking sub-rupiah variances like Rp 0.11
    variance = round(ocr_ppn - calculated_ppn, 2)  # Round to 2 decimal places

    # Get existing variance items - query by item_name instead of field flag
    # (is_variance_item field may not exist in Purchase Invoice Item DocType)
    ppn_var_rows = [
        item for item in doc.get("items") or []
        if (getattr(item, "item_name", None) == "PPN Variance" or
            getattr(item, "is_variance_item", 0) or
            getattr(item, "is_ppn_variance_row", 0))
    ]

    # Tolerance check: if variance is negligible, DELETE existing variance items
    if abs(variance) < 0.01:
        if ppn_var_rows:
            for var_row in ppn_var_rows:
                doc.remove(var_row)
            frappe.logger().info(
                f"[PPN VARIANCE] PI {doc.name}: Variance {variance:.2f} is negligible, "
                f"deleted {len(ppn_var_rows)} variance row(s)"
            )
        return  # Skip creating variance item

    elif len(ppn_var_rows) == 0:
        # CREATE: No variance row exists, create new one
        new_item = doc.append("items", {
            "item_name": "PPN Variance",
            "description": "PPN Variance (OCR adjustment)",
            "expense_account": variance_account,
            "cost_center": getattr(doc, "cost_center", None),
            "qty": 1,
            "uom": "Nos",
            "rate": variance,
            "amount": variance,
            "is_variance_item": 1,
        })

        # CRITICAL: Set item_tax_rate to exempt from PPN
        # Get PPN account from first tax row
        import json
        first_ppn_account = ppn_tax_rows[0].account_head if ppn_tax_rows else None
        if first_ppn_account:
            new_item.item_tax_rate = json.dumps({first_ppn_account: 0})
            frappe.logger().info(
                f"[PPN VARIANCE] PI {doc.name}: Set item_tax_rate for variance item to exempt from {first_ppn_account}"
            )

        # Set custom field if exists
        if hasattr(new_item, "is_ppn_variance_row"):
            new_item.is_ppn_variance_row = 1

        frappe.logger().info(f"[PPN VARIANCE] PI {doc.name}: Created variance row = {variance:,.2f}")

    elif len(ppn_var_rows) == 1:
        # UPDATE: Exactly 1 row exists, update it
        row = ppn_var_rows[0]
        row.amount = variance
        row.rate = variance
        row.description = "PPN Variance (OCR adjustment)"
        frappe.logger().info(f"[PPN VARIANCE] PI {doc.name}: Updated variance row = {variance:,.2f}")

    else:
        # MERGE: Multiple rows exist, merge to 1
        first_row = ppn_var_rows[0]
        first_row.amount = variance
        first_row.rate = variance
        first_row.description = "PPN Variance (OCR adjustment)"

        for duplicate in ppn_var_rows[1:]:
            doc.remove(duplicate)

        frappe.logger().info(f"[PPN VARIANCE] PI {doc.name}: Merged {len(ppn_var_rows)} rows to 1, variance = {variance:,.2f}")

    # Recalculate totals after variance item changes
    if hasattr(doc, "calculate_taxes_and_totals"):
        doc.calculate_taxes_and_totals()


def manage_direct_pi_ppn_variance(doc, method=None):
    """Manage PPN variance for direct PI (without ER) - strict zero tolerance + idempotent.

    Only runs for PI WITHOUT Expense Request link.
    Creates/updates/deletes variance item in items table.
    """
    # Skip if linked to ER (variance already managed by ER)
    if getattr(doc, "imogi_expense_request", None):
        return

    # Skip if no OCR or no PPN
    if not getattr(doc, "ti_tax_invoice_upload", None):
        return

    ocr_ppn = flt(getattr(doc, "ti_fp_ppn", 0) or 0)
    if ocr_ppn <= 0:
        return

    # Must have taxes_and_charges template
    if not getattr(doc, "taxes_and_charges", None):
        frappe.throw("Purchase Taxes and Charges Template wajib dipilih untuk PI dengan OCR. Pilih template VAT yang sesuai.")

    # Get expected PPN from taxes table
    if not hasattr(doc, "taxes") or not doc.taxes:
        frappe.throw("Purchase Taxes and Charges Template wajib dipilih untuk PI dengan OCR. Pilih template VAT yang sesuai.")

    # CRITICAL: Exclude PPh/WHT rows (add_deduct_tax="Deduct") — PPh is also "On Net Total"
    # Without this filter, PPh row (rate=2%) is mistakenly used instead of PPN (rate=11%)
    ppn_tax_rows = [
        tax for tax in doc.taxes
        if getattr(tax, "charge_type", None) == "On Net Total"
        and getattr(tax, "add_deduct_tax", "Add") == "Add"
    ]
    if not ppn_tax_rows:
        frappe.throw("Template tidak memiliki baris VAT (On Net Total). Periksa template & Tax Profile.")

    # STRICT: Throw if no VAT account configured in Tax Profile
    try:
        from imogi_finance.settings.utils import get_vat_input_accounts
        company = getattr(doc, "company", None)
        vat_accounts = get_vat_input_accounts(company)
    except frappe.ValidationError as e:
        frappe.throw(str(e))

    # CRITICAL FIX: Calculate expected PPN from items EXCLUDING variance items
    # This prevents double-counting variance (once as item, once as tax adjustment)
    first_ppn_row = ppn_tax_rows[0]
    ppn_rate = flt(getattr(first_ppn_row, "rate", 0) or 0) / 100.0  # Convert percentage to decimal

    if ppn_rate <= 0:
        # Fallback to tax_amount if rate not available
        expected_ppn = flt(getattr(first_ppn_row, "tax_amount", 0) or 0)
    else:
        # Calculate DPP excluding variance items
        dpp = 0.0
        for item in doc.get("items") or []:
            # Skip variance items from DPP calculation
            if getattr(item, "is_variance_item", 0) or getattr(item, "is_ppn_variance_row", 0):
                continue
            dpp += flt(getattr(item, "amount", 0) or 0)

        # Calculate expected PPN from DPP (excluding variance)
        expected_ppn = dpp * ppn_rate

        frappe.logger().info(
            f"[DIRECT PI VARIANCE] PI {doc.name}: DPP (excl variance) = {dpp:,.2f}, "
            f"Rate = {ppn_rate*100:.2f}%, Expected PPN = {expected_ppn:,.2f}"
        )

    # Calculate variance with decimal precision (don't round to integer)
    # This allows tracking sub-rupiah variances like Rp 0.11
    variance = round(ocr_ppn - expected_ppn, 2)  # Round to 2 decimal places

    # Get PPN Variance account
    try:
        from imogi_finance.settings.utils import get_gl_account
        from imogi_finance.settings.gl_purposes import PPN_VARIANCE
        company = getattr(doc, "company", None)
        variance_account = get_gl_account(PPN_VARIANCE, company=company, required=True)
    except frappe.DoesNotExistError:
        frappe.throw("GL Account Mapping untuk purpose 'PPN_VARIANCE' belum ada. Tambahkan di GL Purposes/Mapping.")
    except Exception as e:
        frappe.throw(str(e))

    # IDEMPOTENT: Query existing variance rows - by item_name instead of field flag
    # (is_variance_item field may not exist in Purchase Invoice Item DocType)
    items = doc.get("items") or []
    ppn_var_rows = [
        r for r in items
        if (getattr(r, "item_name", None) == "PPN Variance" or
            (getattr(r, "is_variance_item", 0) and getattr(r, "expense_account", None) == variance_account))
    ]

    # Skip only if variance is truly negligible (< 1 sen)
    if abs(variance) < 0.01:
        # Delete all variance rows if exists
        if ppn_var_rows:
            for row in ppn_var_rows:
                doc.remove(row)
            frappe.logger().info(
                f"[DIRECT PI VARIANCE] PI {doc.name}: Variance {variance:.2f} is negligible, "
                f"deleted {len(ppn_var_rows)} variance row(s)"
            )
        return  # Skip creating variance item

    elif len(ppn_var_rows) == 0:
        # CREATE: No variance row exists, create new one
        new_item = doc.append("items", {
            "item_name": "PPN Variance",
            "description": "PPN Variance (OCR adjustment)",
            "expense_account": variance_account,
            "cost_center": getattr(doc, "cost_center", None),
            "qty": 1,
            "uom": "Nos",
            "rate": variance,
            "amount": variance,
            "is_variance_item": 1,
        })

        # CRITICAL: Set item_tax_rate to exempt from PPN
        # Get PPN account from first tax row
        import json
        first_ppn_account = ppn_tax_rows[0].account_head if ppn_tax_rows else None
        if first_ppn_account:
            new_item.item_tax_rate = json.dumps({first_ppn_account: 0})
            frappe.logger().info(
                f"[DIRECT PI VARIANCE] PI {doc.name}: Set item_tax_rate for variance item to exempt from {first_ppn_account}"
            )

        # Set custom field if exists
        if hasattr(new_item, "is_ppn_variance_row"):
            new_item.is_ppn_variance_row = 1

        frappe.logger().info(f"[DIRECT PI VARIANCE] PI {doc.name}: Created variance row = {variance}")

    elif len(ppn_var_rows) == 1:
        # UPDATE: Exactly 1 row exists, update it
        row = ppn_var_rows[0]
        row.amount = variance
        row.rate = variance
        row.description = "PPN Variance (OCR adjustment)"
        frappe.logger().info(f"[DIRECT PI VARIANCE] PI {doc.name}: Updated variance row = {variance}")

    else:
        # MERGE: Multiple rows exist, merge to 1
        first_row = ppn_var_rows[0]
        first_row.amount = variance
        first_row.rate = variance
        first_row.description = "PPN Variance (OCR adjustment)"

        for duplicate in ppn_var_rows[1:]:
            doc.remove(duplicate)

        frappe.logger().info(f"[DIRECT PI VARIANCE] PI {doc.name}: Merged {len(ppn_var_rows)} rows to 1, variance = {variance}")

    # Recalculate totals after variance item changes
    if hasattr(doc, "calculate_taxes_and_totals"):
        doc.calculate_taxes_and_totals()


def validate_before_submit(doc, method=None):
    # Prevent double WHT: clear supplier's tax category if Apply WHT already set from ER
    _prevent_double_wht(doc)

    # Sync OCR fields but don't save - document will be saved automatically after this hook
    sync_tax_invoice_upload(doc, "Purchase Invoice", save=False)
    validate_tax_invoice_upload_link(doc, "Purchase Invoice")

    # Validate NPWP match between OCR and Supplier
    _validate_npwp_match(doc)

    # Validate 1 ER = 1 PI (only submitted PI, cancelled are ignored)
    _validate_one_pi_per_request(doc)

    # Option A: Budget check for direct PI (without ER)
    _validate_budget_for_direct_pi(doc)


def _validate_one_pi_per_request(doc):
    """Validate 1 Expense Request = 1 Purchase Invoice (submitted only).

    Cancelled PI are ignored - allow creating new PI if old one is cancelled.
    """
    expense_request = getattr(doc, "imogi_expense_request", None)

    if expense_request:
        existing_pi = frappe.db.get_value(
            "Purchase Invoice",
            {
                "imogi_expense_request": expense_request,
                "docstatus": 1,  # Only submitted
                "name": ["!=", doc.name]
            },
            "name"
        )

        if existing_pi:
            frappe.throw(
                _("Expense Request {0} is already linked to submitted Purchase Invoice {1}. Please cancel that PI first.").format(
                    expense_request, existing_pi
                ),
                title=_("Duplicate Purchase Invoice")
            )


def _validate_npwp_match(doc):
    """Validate NPWP from OCR matches supplier's NPWP.

    Skip validation if Purchase Invoice is created from Expense Request
    because validation has already been done at the request level.
    """
    # Skip if linked to Expense Request
    if getattr(doc, "imogi_expense_request", None):
        return

    has_tax_invoice_upload = bool(getattr(doc, "ti_tax_invoice_upload", None))
    if not has_tax_invoice_upload:
        return

    supplier_npwp = getattr(doc, "supplier_tax_id", None)
    ocr_npwp = getattr(doc, "ti_fp_npwp", None)

    if not supplier_npwp or not ocr_npwp:
        return

    supplier_npwp_normalized = normalize_npwp(supplier_npwp)
    ocr_npwp_normalized = normalize_npwp(ocr_npwp)

    if supplier_npwp_normalized and ocr_npwp_normalized and supplier_npwp_normalized != ocr_npwp_normalized:
        frappe.throw(
            _("NPWP dari OCR ({0}) tidak sesuai dengan NPWP Supplier ({1})").format(
                ocr_npwp, supplier_npwp
            ),
            title=_("NPWP Mismatch")
        )


def _validate_budget_for_direct_pi(doc):
    """Validate budget availability for Purchase Invoice created directly (without Expense Request).

    Option A: Hard block - PI without ER must have sufficient budget available.

    This check is controlled by the 'enable_budget_check_direct_pi' setting.
    When enabled, PI without ER will be blocked if budget is insufficient.

    Note: PI from ER already has budget reserved via RESERVATION entries,
    so this check only applies to direct PI creation.
    """
    # Skip if linked to Expense Request
    expense_request = getattr(doc, "imogi_expense_request", None)
    if expense_request:
        return

    # Get budget control settings
    settings = budget_utils.get_settings()

    # Skip if budget lock or direct PI check is disabled
    if not settings.get("enable_budget_lock"):
        return
    if not settings.get("enable_budget_check_direct_pi"):
        frappe.logger().info(
            f"_validate_budget_for_direct_pi: Direct PI budget check disabled for PI {getattr(doc, 'name', 'Unknown')}"
        )
        return

    # Get company and fiscal year
    company = getattr(doc, "company", None)
    fiscal_year = budget_utils.resolve_fiscal_year(
        getattr(doc, "fiscal_year", None),
        company=company
    )

    if not fiscal_year:
        frappe.logger().warning(
            f"_validate_budget_for_direct_pi: Could not resolve fiscal year for PI {getattr(doc, 'name', 'Unknown')}"
        )
        return

    # Check budget role for overrun
    allow_role = settings.get("allow_budget_overrun_role")
    allow_overrun = bool(allow_role and allow_role in frappe.get_roles())

    # Build dimensions from PI items and check budget
    items = getattr(doc, "items", []) or []

    # Group amounts by cost_center + expense_account
    allocation_map = {}
    for item in items:
        cost_center = getattr(item, "cost_center", None) or getattr(doc, "cost_center", None)
        expense_account = getattr(item, "expense_account", None)
        amount = float(getattr(item, "amount", 0) or 0)

        if not cost_center or not expense_account:
            continue

        key = (cost_center, expense_account)
        allocation_map[key] = allocation_map.get(key, 0) + amount

    if not allocation_map:
        frappe.logger().warning(
            f"_validate_budget_for_direct_pi: No valid items found for PI {getattr(doc, 'name', 'Unknown')}"
        )
        return

    # Check budget availability for each dimension
    for (cost_center, expense_account), amount in allocation_map.items():
        if amount <= 0:
            continue

        dims = budget_utils.Dimensions(
            company=company,
            fiscal_year=fiscal_year,
            cost_center=cost_center,
            account=expense_account,
            project=getattr(doc, "project", None),
            branch=getattr(doc, "branch", None),
        )

        result = budget_service.check_budget_available(dims, amount)

        frappe.logger().info(
            f"_validate_budget_for_direct_pi: Budget check for {cost_center}/{expense_account}: "
            f"amount={amount}, available={result.get('available')}, ok={result.get('ok')}"
        )

        if not result.get("ok") and not allow_overrun:
            frappe.throw(
                _("Budget Insufficient for direct Purchase Invoice.<br><br>"
                  "Cost Center: {0}<br>"
                  "Account: {1}<br>"
                  "Requested: {2}<br>"
                  "Available: {3}<br><br>"
                  "Please create an Expense Request first or contact Budget Controller.").format(
                    cost_center or "(not set)",
                    expense_account or "(not set)",
                    frappe.format_value(amount, {"fieldtype": "Currency"}),
                    frappe.format_value(result.get("available"), {"fieldtype": "Currency"})
                        if result.get("available") is not None else "N/A"
                ),
                title=_("Budget Exceeded")
            )
        elif not result.get("ok") and allow_overrun:
            frappe.logger().warning(
                f"_validate_budget_for_direct_pi: Budget overrun allowed by role for PI {getattr(doc, 'name', 'Unknown')}"
            )
            frappe.msgprint(
                _("Budget overrun allowed for {0}/{1}. Proceeding with special permission.").format(
                    cost_center, expense_account
                ),
                indicator="orange",
                alert=True
            )


def _generate_deferred_expense_schedule(doc):
    """Generate deferred expense schedule for Purchase Invoice items.

    This function triggers ERPNext's built-in deferred expense schedule generation
    for items that have Enable Deferred Expense checked.

    ERPNext requires:
    - enable_deferred_expense = 1
    - service_start_date is set
    - service_stop_date is set (CRITICAL!)
    - deferred_expense_account is set

    Without this trigger, schedule won't be auto-generated and amortization won't work.
    """
    has_deferred_items = any(
        cint(item.get("enable_deferred_expense"))
        for item in doc.get("items", [])
    )

    if not has_deferred_items:
        return

    try:
        # Call ERPNext's built-in method to calculate deferred schedule
        if hasattr(doc, "calculate_deferred_expense_schedule"):
            doc.calculate_deferred_expense_schedule()
        else:
            return
    except Exception as e:
        # Don't throw error - let PI submit succeed even if deferred schedule fails
        # User can manually regenerate schedule later
        return


def _prevent_double_wht(doc):
    """Prevent double WHT calculation with ON/OFF logic for PPh.

    ============================================================================
    ON/OFF LOGIC:
    ============================================================================

    RULE 1: Jika SEMUA items Apply WHT ✅ CENTANG
    → AKTIFKAN ER's pph_type
    → MATIKAN supplier's Tax Withholding Category (clear to NULL)
    → Result: Single PPh dari ER only (tidak double)

    RULE 2: Jika ADA MIXED Apply WHT (some items yes, some no)
    → MATIKAN supplier's category DAN PI-level PPh
    → Items akan calculate PPh individually
    → Result: Only items with Apply WHT get taxed

    RULE 3: Jika TIDAK ADA Apply WHT ❌ SAMA SEKALI
    → MATIKAN ER's pph_type
    → AKTIFKAN supplier's Tax Withholding Category (auto-copy via accounting.py)
    → Result: Single PPh dari supplier only (jika ada & enabled)

    TIDAK BOLEH supplier's category dipakai saat ada item-level Apply WHT!

    ============================================================================
    Implementation Details:
    ============================================================================

    Function ini dipanggil di 2 event hooks:
    1. validate() - Early prevention (paling awal)
    2. before_submit() - Double-check sebelum submit

    CRITICAL TIMING ISSUE:
    - Frappe auto-populates supplier's tax_withholding_category AFTER supplier is assigned
    - Even if supplier's category is NULL at validate() time, Frappe's TDS controller
      might still calculate it independently based on supplier master
    - SOLUTION: When ER's Apply WHT is set, explicitly set tax_withholding_category = None
      AND set apply_tds = 0 to prevent Frappe's TDS controller from using supplier's category
    """
    expense_request = getattr(doc, "imogi_expense_request", None)
    apply_tds = cint(getattr(doc, "apply_tds", 0))  # Dari ER's Apply WHT checkbox (at PI level)
    pph_type = getattr(doc, "imogi_pph_type", None)        # Dari ER's Tab Tax
    supplier_tax_category = getattr(doc, "tax_withholding_category", None)  # Auto-populated oleh Frappe

    # Check if this is a mixed Apply WHT scenario
    # MIXED mode: apply_tds=1 at PI level, pph_type is set, supplier_tax_category exists
    # Event hook must clear supplier category to prevent it being used (causing double tax)
    is_mixed_mode = (
        expense_request and
        apply_tds and
        pph_type and
        supplier_tax_category and
        pph_type == supplier_tax_category  # Both same = came from same source
    )

    # LOGIC: Ensure supplier's category doesn't interfere with item-level Apply WHT
    if expense_request and (apply_tds or is_mixed_mode):
        # ✅ CONSISTENT MODE (apply_tds=1, pph_type set): ER's Apply WHT for all items
        # ✅ MIXED MODE (apply_tds=1 but is_mixed_mode=True): Items control individually

        if is_mixed_mode:
            # MIXED mode: Clear supplier's category to prevent applying to all items
            # Items will use per-item apply_tds flags with ER's pph_type
            if supplier_tax_category:
                frappe.logger().info(
                    f"[PPh MIXED] PI {doc.name}: "
                    f"MIXED mode - clearing supplier's category '{supplier_tax_category}' to prevent override. "
                    f"Items control individual PPh via apply_tds flags. Using template: '{pph_type}'"
                )
                doc.tax_withholding_category = None  # Clear supplier category
                doc.apply_tds = 1  # Keep enabled so items can control via their flags
        elif apply_tds and supplier_tax_category and supplier_tax_category != pph_type:
            # CONSISTENT mode + supplier has DIFFERENT category
            frappe.logger().info(
                f"[PPh PROTECT] PI {doc.name}: "
                f"CONSISTENT mode - found supplier's category '{supplier_tax_category}' conflicting with ER Apply WHT '{pph_type}'. "
                f"Clearing it to prevent double calculation."
            )
            doc.tax_withholding_category = None  # Clear conflicting category
            doc.apply_tds = 1  # Use ER's pph_type only
    else:
        # ❌ RULE 3: ER does NOT have Apply WHT
        # Supplier's category is OK (auto-copied by accounting.py)
        if expense_request and not apply_tds and not pph_type:
            frappe.logger().info(
                f"[PPh SUPPLIER MODE] PI {doc.name}: "
                f"No Apply WHT in ER. Supplier's category allowed: '{supplier_tax_category}'"
            )
        # ❌ RULE 2: ER's Apply WHT TIDAK CENTANG atau tidak ada ER
        # Di sini kita TIDAK clear supplier's category
        # Biarkan logic di accounting.py yang mengurus auto-copy ke supplier's category
        if expense_request and not pph_type:
            frappe.logger().info(
                f"[PPh ON/OFF] PI {doc.name}: "
                f"Apply WHT di ER TIDAK CENTANG (apply_tds=0, pph_type=None). "
                f"Supplier's category will be used if enabled in settings (auto-copy feature)."
            )


def on_submit(doc, method=None):
    # CRITICAL: Generate deferred expense schedule for items with deferred expense enabled
    _generate_deferred_expense_schedule(doc)

    # Check for Expense Request
    expense_request = doc.get("imogi_expense_request")

    if expense_request:
        _handle_expense_request_submit(doc, expense_request)


def _handle_expense_request_submit(doc, request_name):
    """Handle Purchase Invoice submit for Expense Request."""
    request = get_approved_expense_request(
        request_name, _("Purchase Invoice"), allowed_statuses=PURCHASE_INVOICE_ALLOWED_STATUSES | {"PI Created"}
    )

    # Validate tidak ada PI lain yang sudah linked (query dari DB)
    existing_pi = frappe.db.get_value(
        "Purchase Invoice",
        {
            "imogi_expense_request": request.name,
            "docstatus": 1,
            "name": ["!=", doc.name]
        },
        "name"
    )

    if existing_pi:
        frappe.throw(
            _("Expense Request is already linked to a different Purchase Invoice {0}.").format(
                existing_pi
            )
        )

    if request.request_type not in PURCHASE_INVOICE_REQUEST_TYPES:
        frappe.throw(
            _("Purchase Invoice can only be linked for request type(s): {0}").format(
                ", ".join(sorted(PURCHASE_INVOICE_REQUEST_TYPES))
            )
        )

    branch_settings = get_branch_settings()
    if branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
        validate_branch_alignment(
            getattr(doc, "branch", None),
            getattr(request, "branch", None),
            label=_("Purchase Invoice"),
        )

    # Update workflow state to PI Created
    # Status akan auto-update via query karena PI.imogi_expense_request sudah set
    frappe.db.set_value(
        request.doctype,
        request.name,
        {"workflow_state": "PI Created", "status": "PI Created", "pending_purchase_invoice": None},
    )

    # Budget consumption MUST succeed or PI submit fails
    try:
        consume_budget_for_purchase_invoice(doc, expense_request=request)
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(
            title=f"Budget Consumption Failed for PI {doc.name}",
            message=f"Error: {str(e)}\n\n{frappe.get_traceback()}"
        )
        frappe.throw(
            _("Budget consumption failed. Purchase Invoice cannot be submitted. Error: {0}").format(str(e)),
            title=_("Budget Control Error")
        )

    maybe_post_internal_charge_je(doc, expense_request=request)


def before_cancel(doc, method=None):
    if doc.get("imogi_expense_request"):
        doc.flags.ignore_links = True

    # Mark that we're cancelling this PI - BCE should allow its cancellation
    # Store in frappe.local so BCE.before_cancel can check it
    if not hasattr(frappe.local, "cancelling_purchase_invoices"):
        frappe.local.cancelling_purchase_invoices = set()
    frappe.local.cancelling_purchase_invoices.add(doc.name)


def before_delete(doc, method=None):
    """Set flag to ignore link validation before deletion.

    This prevents LinkExistsError when deleting draft PI that is linked to ER.
    The actual link cleanup happens in on_trash.
    """
    if doc.get("imogi_expense_request"):
        doc.flags.ignore_links = True


def on_cancel(doc, method=None):
    """Handle Purchase Invoice cancellation.

    When PI is cancelled:
    1. Check for active Payment Entry (must be cancelled first)
    2. Reverse budget consumption
    3. Update workflow state (status auto-updated via query)
    """
    expense_request_name = doc.get("imogi_expense_request")

    # Check for active Payment Entry via query
    if expense_request_name:
        pe = frappe.db.get_value(
            "Payment Entry",
            {"imogi_expense_request": expense_request_name, "docstatus": 1},
            "name"
        )
        if pe:
            frappe.throw(
                _("Cannot cancel Purchase Invoice. Payment Entry {0} must be cancelled first.").format(pe),
                title=_("Active Payment Exists")
            )

    # Reverse budget consumption - MUST succeed or cancel fails
    try:
        reverse_consumption_for_purchase_invoice(doc)
    except Exception as e:
        frappe.log_error(
            title=f"Budget Reversal Failed for PI {doc.name}",
            message=f"Error: {str(e)}\n\n{frappe.get_traceback()}"
        )
        frappe.throw(
            _("Failed to reverse budget consumption. Purchase Invoice cannot be cancelled. Error: {0}").format(str(e)),
            title=_("Budget Reversal Error")
        )

    # Update Expense Request workflow state and status
    # Update Expense Request workflow state and status
    # After PI cancel, status should revert to Approved (no PI submitted anymore)
    if expense_request_name:
        _er_doctype = get_er_doctype(expense_request_name) or "Expense Request"
        request_links = get_expense_request_links(expense_request_name)
        next_status = get_expense_request_status(request_links)
        frappe.db.set_value(
            _er_doctype,
            expense_request_name,
            {"workflow_state": next_status, "status": next_status, "pending_purchase_invoice": None},
            update_modified=False
        )
        frappe.logger().info(
            f"[PI cancel] PI {doc.name} cancelled. Updated ER {expense_request_name} status to {next_status}"
        )


def on_trash(doc, method=None):
    """Clear links from Expense Request before deleting PI to avoid LinkExistsError."""
    expense_request = doc.get("imogi_expense_request")

    # Handle Expense Request
    if expense_request:
        _er_doctype = get_er_doctype(expense_request)
        if _er_doctype:
            # Clear BOTH linked and pending fields to break the link
            request_links = get_expense_request_links(expense_request, include_pending=True)
            updates = {}

            # Clear pending_purchase_invoice if it matches
            if request_links.get("pending_purchase_invoice") == doc.name:
                updates["pending_purchase_invoice"] = None

            # Clear linked_purchase_invoice if it matches (THIS IS THE FIX)
            # This field is what causes LinkExistsError
            current_linked = frappe.db.get_value(_er_doctype, expense_request, "linked_purchase_invoice")
            if current_linked == doc.name:
                updates["linked_purchase_invoice"] = None

            if updates or True:  # Always update workflow state and status
                # Re-query untuk get status terbaru (after clearing links)
                current_links = get_expense_request_links(expense_request)
                next_status = get_expense_request_status(current_links)
                updates["workflow_state"] = next_status
                updates["status"] = next_status  # Update status field juga

                frappe.db.set_value(_er_doctype, expense_request, updates)
                frappe.db.commit()  # Commit immediately to ensure link is cleared
                frappe.logger().info(
                    f"[PI trash] PI {doc.name} deleted. Updated ER {expense_request} status to {next_status}"
                )
