"""Accounting helpers for IMOGI Finance."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_months, cint, flt

from imogi_finance.branching import apply_branch, resolve_branch
from imogi_finance.tax_invoice_ocr import get_settings, sync_tax_invoice_upload
from imogi_finance.settings.utils import get_gl_account
from imogi_finance.settings.gl_purposes import PPN_VARIANCE

PURCHASE_INVOICE_REQUEST_TYPES = {"Expense"}
PURCHASE_INVOICE_ALLOWED_STATUSES = frozenset({"Approved"})


def _raise_verification_error(message: str):
    marker = getattr(frappe, "ThrowMarker", None)
    throw_fn = getattr(frappe, "throw", None)

    if callable(throw_fn):
        try:
            throw_fn(message, title=_("Verification Required"))
            return
        except Exception as exc:
            if marker and not isinstance(exc, marker) and exc.__class__.__name__ != "ThrowCalled":
                raise marker(message)
            raise

    if marker:
        raise marker(message)
    raise Exception(message)


def _get_item_value(item: object, field: str):
    if isinstance(item, dict):
        return item.get(field)
    return getattr(item, field, None)


def summarize_request_items(
    items: list[frappe.model.document.Document] | None,
    *,
    skip_invalid_items: bool = False,
) -> tuple[float, tuple[str, ...]]:
    if not items:
        if skip_invalid_items:
            return 0.0, ()
        frappe.throw(_("Please add at least one item."))

    total = 0.0
    accounts = set()

    for item in items:
        # Use net_amount if available (amount after discount), otherwise use amount
        net_amount = _get_item_value(item, "net_amount")
        amount = net_amount if net_amount is not None else _get_item_value(item, "amount")

        if amount is None or amount <= 0:
            if skip_invalid_items:
                continue
            frappe.throw(_("Each item must have an Amount greater than zero."))

        account = _get_item_value(item, "expense_account")
        if not account:
            if skip_invalid_items:
                continue
            frappe.throw(_("Each item must have an Expense Account."))

        accounts.add(account)
        total += float(amount)

    return total, tuple(sorted(accounts))


def _sync_request_amounts(
    request: frappe.model.document.Document, total: float, expense_accounts: tuple[str, ...]
) -> None:
    updates = {}
    primary_account = expense_accounts[0] if len(expense_accounts) == 1 else None

    if getattr(request, "amount", None) != total:
        updates["amount"] = total

    if getattr(request, "expense_account", None) != primary_account:
        updates["expense_account"] = primary_account

    if updates and hasattr(request, "db_set"):
        request.db_set(updates)

    for field, value in updates.items():
        setattr(request, field, value)
    # Convert tuple to newline-separated string for Small Text field
    setattr(request, "expense_accounts", "\n".join(expense_accounts) if expense_accounts else "")


def _get_pph_base_amount(request: frappe.model.document.Document) -> float:
    items = getattr(request, "items", []) or []
    item_bases = [
        getattr(item, "pph_base_amount", None)
        for item in items
        if getattr(item, "is_pph_applicable", 0) and getattr(item, "pph_base_amount", None)
    ]

    if item_bases:
        return float(sum(item_bases))

    if getattr(request, "is_pph_applicable", 0) and getattr(request, "pph_base_amount", None):
        return request.pph_base_amount
    return request.amount


def _validate_request_ready_for_link(request: frappe.model.document.Document) -> None:
    status = None
    if hasattr(request, "get"):
        status = request.get("status") or request.get("workflow_state")
    if request.docstatus != 1 or status not in PURCHASE_INVOICE_ALLOWED_STATUSES:
        frappe.throw(
            _("Expense Request must be submitted and have status {0} before creating accounting entries.").format(
                ", ".join(sorted(PURCHASE_INVOICE_ALLOWED_STATUSES))
            )
        )


def _validate_request_type(
    request: frappe.model.document.Document, allowed_types: set[str], action: str
) -> None:
    if request.request_type not in allowed_types:
        frappe.throw(
            _("{0} can only be created for request type(s): {1}").format(
                action, ", ".join(sorted(allowed_types))
            )
        )


def _validate_no_existing_purchase_invoice(request: frappe.model.document.Document) -> None:
    # Query untuk cek apakah sudah ada PI yang submitted untuk ER ini
    existing_pi = frappe.db.get_value(
        "Purchase Invoice",
        {
            "imogi_expense_request": request.name,
            "docstatus": ["!=", 2]  # Not cancelled
        },
        "name"
    )

    if existing_pi:
        frappe.throw(
            _("Expense Request is already linked to Purchase Invoice {0}.").format(
                existing_pi
            )
        )


def _update_request_purchase_invoice_links(
    request: frappe.model.document.Document,
    purchase_invoice: frappe.model.document.Document,
    mark_pending: bool = True,
) -> None:
    """Legacy function - kept for backward compatibility.

    With native connections, PI link is established via imogi_expense_request field
    on Purchase Invoice. Status is determined by querying submitted documents.

    This function now only clears pending_purchase_invoice field.
    """
    # Clear pending field only - actual link is via PI.imogi_expense_request
    if hasattr(request, "db_set"):
        request.db_set("pending_purchase_invoice", None)
    else:
        setattr(request, "pending_purchase_invoice", None)


@frappe.whitelist()
def create_purchase_invoice_from_request(expense_request_name: str) -> str:
    """Create a Purchase Invoice from an Expense Request or Advanced Expense Request."""
    # Auto-detect which doctype holds this document
    source_doctype = None
    for _dt in ("Expense Request", "Advanced Expense Request"):
        if frappe.db.exists(_dt, expense_request_name):
            source_doctype = _dt
            break
    if not source_doctype:
        frappe.throw(_("Expense Request {0} not found.").format(expense_request_name))

    request = frappe.get_doc(source_doctype, expense_request_name)
    _validate_request_ready_for_link(request)
    _validate_request_type(request, PURCHASE_INVOICE_REQUEST_TYPES, _("Purchase Invoice"))
    _validate_no_existing_purchase_invoice(request)

    # Resolve a single cost center for company/branch lookup.
    # Advanced Expense Request has per-item cost_centers; use approval_cost_center or first item.
    request_cost_center = (
        getattr(request, "cost_center", None)
        or getattr(request, "approval_cost_center", None)
        or next(
            (getattr(it, "cost_center", None) for it in (getattr(request, "items", []) or [])),
            None,
        )
    )

    company = frappe.db.get_value("Cost Center", request_cost_center, "company")
    if not company:
        frappe.throw(_("Unable to resolve company from the selected Cost Center."))

    branch = resolve_branch(
        company=company, cost_center=request_cost_center, explicit_branch=getattr(request, "branch", None)
    )

    request_items = getattr(request, "items", []) or []

    if not request_items:
        frappe.throw(_("Expense Request must have at least one item to create a Purchase Invoice."))

    total_amount, expense_accounts = summarize_request_items(request_items, skip_invalid_items=True)
    _sync_request_amounts(request, total_amount, expense_accounts)

    settings = get_settings()
    sync_tax_invoice_upload(request, source_doctype, save=False)

    enforce_mode = (settings.get("enforce_mode") or "").lower()
    if settings.get("enable_budget_lock") and enforce_mode in {"approval only", "both"}:
        lock_status = getattr(request, "budget_lock_status", None)
        if lock_status not in {"Locked", "Overrun Allowed"}:
            frappe.throw(
                _("Expense Request must be budget locked before creating a Purchase Invoice. Current status: {0}").format(
                    lock_status or _("Not Locked")
                )
            )

        if getattr(request, "allocation_mode", "Direct") == "Allocated via Internal Charge":
            ic_name = getattr(request, "internal_charge_request", None)
            if not ic_name:
                frappe.throw(_("Internal Charge Request is required before creating a Purchase Invoice."))

            ic_status = frappe.db.get_value("Internal Charge Request", ic_name, "status")
            if ic_status != "Approved":
                frappe.throw(_("Internal Charge Request {0} must be Approved.").format(ic_name))

    pph_items = [item for item in request_items if getattr(item, "is_pph_applicable", 0)]
    has_item_level_pph = bool(pph_items)

    # Count items with Apply WHT to detect MIXED scenario
    items_with_pph = len(pph_items)
    total_items = len(request_items)
    has_mixed_pph = 0 < items_with_pph < total_items  # Some but not all items have Apply WHT

    is_ppn_applicable = bool(getattr(request, "is_ppn_applicable", 0))
    # apply_pph is first determined by item-level flags; header-level fallback below
    apply_ppn = is_ppn_applicable
    apply_pph = items_with_pph > 0  # Apply PPh if ANY item has Apply WHT checked

    # Header checkbox - also used as fallback when no items have item-level WHT
    header_apply_wht = bool(getattr(request, "is_pph_applicable", 0))

    # FALLBACK: If header PPh enabled but no items have item-level WHT checked,
    # treat all non-variance items as subject to WHT (header-level PPh mode).
    # This matches how the ER/Advanced ER controller calculates total_pph.
    is_header_level_pph = header_apply_wht and not has_item_level_pph
    if is_header_level_pph:
        apply_pph = True

    # Log tax configuration for debugging
    frappe.logger().info(
        f"[TAX CONFIG] ER {request.name}: "
        f"is_ppn_applicable={is_ppn_applicable}, apply_ppn={apply_ppn}, "
        f"ppn_template={getattr(request, 'ppn_template', None)}, "
        f"apply_pph={apply_pph}, items_with_pph={items_with_pph}"
    )

    # ============================================================================
    # VALIDATION: If items have Apply WHT, Header must provide PPh category
    # ============================================================================
    # RULE: If any item has Apply WHT checked, Header must have PPh Type specified
    if apply_pph:  # apply_pph = True if any item has Apply WHT
        pph_type = getattr(request, "pph_type", None)
        if not pph_type:
            frappe.throw(
                _("Found {0} item(s) with 'Apply WHT' checked but PPh Type is NOT specified in Tab Tax. "
                  "Please select PPh Type in Tab Tax.").format(items_with_pph)
            )

    # CRITICAL: If mixed Apply WHT (some items have, some don't)
    # Then don't use supplier's category at all (it would apply to all items)
    # No need to log this - it's a valid configuration
    has_mixed_pph = has_mixed_pph  # Keep variable for later use

    # Validate PPN template exists when PPN applicable
    if apply_ppn:
        ppn_template = getattr(request, "ppn_template", None)
        if not ppn_template:
            frappe.throw(
                _("PPN Template is required in Expense Request {0} before creating Purchase Invoice").format(request.name)
            )

        # Validate template exists in system (Purchase Invoice uses Purchase Taxes and Charges Template)
        # Try exact match first, then try with stripped whitespace
        _PURCHASE_TAX_DOCTYPE = "Purchase Taxes and Charges Template"
        template_exists = frappe.db.exists(_PURCHASE_TAX_DOCTYPE, ppn_template)

        if not template_exists:
            # Try with stripped whitespace in case there's spacing issue
            ppn_template_stripped = ppn_template.strip()
            template_exists = frappe.db.exists(_PURCHASE_TAX_DOCTYPE, ppn_template_stripped)

            if template_exists:
                # Update the value to use stripped version
                ppn_template = ppn_template_stripped
            else:
                # Still doesn't exist - throw error with helpful message
                available = frappe.db.get_list(_PURCHASE_TAX_DOCTYPE, pluck="name")
                frappe.logger().error(
                    f"[PPN ERROR] ER {request.name}: Template '{ppn_template}' not found. "
                    f"Available: {available}"
                )
                frappe.throw(
                    _(
                        "PPN Template '{0}' tidak ditemukan di sistem.\n"
                        "Pastikan template Purchase Taxes and Charges yang sesuai sudah dibuat "
                        "dan dipilih di field PPN Template pada Expense Request."
                    ).format(ppn_template)
                )

    # Validate PPh category exists in system when PPh applicable
    if apply_pph:
        pph_type = getattr(request, "pph_type", None)
        # Validate category exists in system
        category_exists = frappe.db.exists("Tax Withholding Category", pph_type)
        if not category_exists:
            frappe.throw(
                _("Tax Withholding Category '{0}' does not exist in system").format(pph_type)
            )

    pi = frappe.new_doc("Purchase Invoice")
    pi.company = company

    # IMPORTANT: Set apply_tds = 0 BEFORE assigning supplier
    # This prevents Frappe's TDS controller from auto-calculating supplier's WHT
    # We will set it to 1 later if ER's Apply WHT is checked
    pi.apply_tds = 0

    pi.supplier = request.supplier
    # NOTE: After setting supplier, Frappe auto-populates tax_withholding_category
    # BUT since apply_tds=0, Frappe's TDS won't calculate it yet
    # We will override this with ON/OFF logic below
    pi.posting_date = request.request_date
    pi.bill_date = request.supplier_invoice_date
    pi.bill_no = request.supplier_invoice_no
    pi.currency = request.currency
    if hasattr(pi, "tax_category"):
        pi.tax_category = getattr(request, "tax_category", None)
    pi.imogi_expense_request = request.name
    pi.internal_charge_request = getattr(request, "internal_charge_request", None)
    pi.imogi_request_type = request.request_type

    # ============================================================================
    # ON/OFF LOGIC FOR PPh (Withholding Tax)
    # CRITICAL: Control which PPh source to use (ER vs Supplier)
    # ============================================================================
    # RULE:
    # - Jika SEMUA items Apply WHT ✅ CENTANG → AKTIFKAN ER's pph_type
    # - Jika ADA items dengan Apply WHT PARTIAL (mixed) → NO supplier category (items control)
    # - Jika TIDAK ADA items Apply WHT ❌ → GUNAKAN supplier's category (jika enabled)
    # - TIDAK BOLEH supplier category dipakai saat ada item-level Apply WHT
    # ============================================================================

    if apply_pph:
        # ✅ Some items have Apply WHT checked → Enable PPh calculation
        # Use ER's pph_type from Tab Tax
        # CRITICAL: Check if supplier has conflicting category
        supplier_category = pi.tax_withholding_category  # Auto-populated by Frappe after setting supplier

        if supplier_category and supplier_category != request.pph_type:
            # ⚠️ CONFLICT: Supplier's category berbeda dengan ER's PPh Type
            frappe.msgprint(
                msg=_(
                    "<b>Supplier WHT Category Conflict Detected</b><br><br>"
                    "Supplier <b>{0}</b> has Tax Withholding Category: <b>{1}</b><br>"
                    "But Expense Request specifies PPh Type: <b>{2}</b><br><br>"
                    "The system will use <b>{2}</b> (from Expense Request) and override supplier's category.<br>"
                    "If you want to use supplier's category instead, please update PPh Type in Expense Request Tab Tax."
                ).format(request.supplier, supplier_category, request.pph_type),
                title=_("WHT Category Conflict"),
                indicator="orange"
            )

        # Override supplier's category with ER's pph_type
        pi.tax_withholding_category = request.pph_type
        pi.imogi_pph_type = request.pph_type
        pi.apply_tds = 1  # Enable TDS for items with Apply WHT
    else:
        # ❌ ER does NOT have Apply WHT set (no items with Apply WHT)
        # Action: MATIKAN ER's pph_type, GUNAKAN supplier's category (jika ada & enabled)

        settings = get_settings() if callable(get_settings) else {}
        use_supplier_wht = cint(settings.get("use_supplier_wht_if_no_er_pph", 0))

        if use_supplier_wht:
            # Setting enabled: Auto-copy supplier's tax withholding category
            supplier_wht = frappe.db.get_value("Supplier", request.supplier, "tax_withholding_category")
            if supplier_wht:
                pi.tax_withholding_category = supplier_wht
                pi.imogi_pph_type = supplier_wht
                pi.apply_tds = 1
            else:
                pi.tax_withholding_category = None
                pi.imogi_pph_type = None
                pi.apply_tds = 0
        else:
            # Setting disabled: Don't use supplier's category
            pi.tax_withholding_category = None
            pi.imogi_pph_type = None
            pi.apply_tds = 0
    # withholding_tax_base_amount will be set after all items are added

    # Collect per-item PPh details during item creation
    temp_pph_items = []

    for idx, item in enumerate(request_items, start=1):
        expense_account = getattr(item, "expense_account", None)
        is_deferred = bool(getattr(item, "is_deferred_expense", 0))
        prepaid_account = getattr(item, "prepaid_account", None)
        deferred_start_date = getattr(item, "deferred_start_date", None)
        deferred_periods = getattr(item, "deferred_periods", None)

        qty = getattr(item, "qty", 1) or 1

        # CRITICAL: Use net_amount (after discount), not amount (before discount)
        # ER has: amount (before discount), discount_amount, net_amount (after discount)
        item_net_amount = flt(getattr(item, "net_amount", 0) or getattr(item, "amount", 0))
        item_discount = flt(getattr(item, "discount_amount", 0) or 0)

        # Determine which account to use for PI item
        pi_expense_account = prepaid_account if (is_deferred and prepaid_account) else expense_account

        pi_item = {
            "item_name": getattr(item, "asset_name", None)
            or getattr(item, "description", None)
            or getattr(item, "expense_account", None),
            "description": getattr(item, "asset_description", None)
            or getattr(item, "description", None),
            "expense_account": pi_expense_account,
            "cost_center": getattr(item, "cost_center", None) or request_cost_center,
            "project": getattr(item, "project", None) or request.project,
            "qty": qty,
            "uom": "Nos",  # Default UOM for expense items
            "rate": item_net_amount / qty if qty > 0 else item_net_amount,
            "amount": item_net_amount,  # Use net amount (after discount)
        }

        # Copy discount_amount if PI supports it
        if item_discount > 0 and hasattr(pi, "items"):
            # Check if PI item supports discount_amount field
            pi_item["discount_amount"] = item_discount

        if is_deferred and prepaid_account:
            service_end = add_months(deferred_start_date, deferred_periods or 0)
            pi_item["enable_deferred_expense"] = 1
            pi_item["service_start_date"] = deferred_start_date
            pi_item["service_end_date"] = service_end
            pi_item["service_stop_date"] = service_end  # CRITICAL: Required for schedule generation
            pi_item["deferred_expense_account"] = expense_account

        elif is_deferred and not prepaid_account:
            # Deferred is enabled but prepaid account missing; fall back to expense account
            pass

        pi_item_doc = pi.append("items", pi_item)

        # Mark variance item for later tax exemption
        is_variance = bool(getattr(item, "is_variance_item", 0))
        if is_variance:
            # Set persistent custom field if exists (CRITICAL: do this FIRST)
            if hasattr(pi_item_doc, "is_ppn_variance_row"):
                pi_item_doc.is_ppn_variance_row = 1
            # Also set standard variance flag
            if hasattr(pi_item_doc, "is_variance_item"):
                pi_item_doc.is_variance_item = 1
            frappe.logger().info(
                f"[VARIANCE ITEM] PI item {idx}: Flagged variance item for tax exemption"
            )

        # Set item_tax_rate to exempt variance items from all taxes
        # This will be updated with specific PPN account later
        # CRITICAL: Set this BEFORE any tax calculations
        if is_variance:
            pi_item_doc.item_tax_rate = "{}"
            frappe.logger().info(
                f"[VARIANCE ITEM] PI item {idx}: Set item_tax_rate to empty (will exempt from all taxes)"
            )

        # Set item-level apply_tds flag if PPh applies
        if apply_pph and hasattr(pi_item_doc, "apply_tds"):
            # CRITICAL: Explicitly set apply_tds for EACH item
            # Only items with is_pph_applicable = 1 get apply_tds = 1 (taxed)
            # Items without Apply WHT must get apply_tds = 0 (NOT taxed)
            if getattr(item, "is_pph_applicable", 0):
                pi_item_doc.apply_tds = 1
                frappe.logger().info(
                    f"[PPh ITEM] PI item {idx} ({expense_account}): Set apply_tds=1 (is_pph_applicable=1)"
                )
            elif is_header_level_pph and not getattr(item, "is_variance_item", 0):
                # Header-level PPh mode: all non-variance items are subject to WHT.
                # Mirrors how ER controller computes total_pph when no item has Apply WHT.
                pi_item_doc.apply_tds = 1
                frappe.logger().info(
                    f"[PPh ITEM] PI item {idx} ({expense_account}): Set apply_tds=1 (header-level PPh)"
                )
            else:
                # EXPLICITLY set to 0 for items WITHOUT Apply WHT
                # Without this, Frappe defaults to PI-level apply_tds (which is 1)
                # and ALL items would be taxed (WRONG!)
                pi_item_doc.apply_tds = 0
                frappe.logger().info(
                    f"[PPh ITEM] PI item {idx} ({expense_account}): Set apply_tds=0 (is_pph_applicable=0)"
                )

        # Track which items have PPh for later index mapping
        if apply_pph and getattr(item, "is_pph_applicable", 0):
            base_amount = getattr(item, "pph_base_amount", None)
            if base_amount is not None:
                temp_pph_items.append({
                    "er_index": idx,
                    "base_amount": float(base_amount)
                })

    # ============================================================================
    # PPN VARIANCE HANDLING
    # ============================================================================
    # PPN Variance appears in TWO places:
    # 1. As line item in Items table (for transparency, set as tax-exempt above)
    # 2. Added to tax amount in Purchase Taxes table (for correct PPN total)
    # This ensures variance is visible AND included in tax calculation
    ppn_variance = flt(getattr(request, "ti_ppn_variance", 0) or 0)

    if ppn_variance != 0:
        frappe.logger().info(
            f"[PPN VARIANCE] ER {request.name}: Will adjust PPN tax amount by {ppn_variance}"
        )

    # Build item_wise_tax_detail with correct indices AFTER all items are added
    # This ensures index mapping is accurate regardless of variance items
    item_wise_pph_detail = {}
    if temp_pph_items:
        for pph_item in temp_pph_items:
            # Use ER index directly since items are added in order
            pi_idx = pph_item["er_index"]
            item_wise_pph_detail[str(pi_idx)] = pph_item["base_amount"]

    # Calculate withholding tax base amount
    # IMPORTANT: Exclude variance item from PPh calculation
    if apply_pph:
        if item_wise_pph_detail:
            # If per-item PPh, sum from item_wise_pph_detail
            pi.withholding_tax_base_amount = sum(float(v) for v in item_wise_pph_detail.values())
        else:
            # Header-level PPh: prefer explicit pph_base_amount from the request header,
            # fall back to sum of all non-variance item amounts.
            header_pph_base = flt(getattr(request, "pph_base_amount", 0) or 0)
            if is_header_level_pph and header_pph_base:
                pi.withholding_tax_base_amount = header_pph_base
            else:
                # Variance item is always last if it exists
                items_count = len(request_items)  # Original items without variance
                pi.withholding_tax_base_amount = sum(
                    flt(pi.items[i].get("amount", 0)) for i in range(items_count)
                )

    # Set PPh details after all items are added
    if item_wise_pph_detail:
        pi.item_wise_tax_detail = item_wise_pph_detail

    # =========================================================================
    # PPh TAX ROW — Add directly BEFORE insert
    # =========================================================================
    # Frappe's set_tax_withholding() is designed for the submit lifecycle and
    # relies on cumulative party-ledger checks that don't work reliably on a
    # newly-created draft PI. We calculate the amount directly from the WHT
    # category configuration instead, so the row is present when Frappe runs
    # calculate_taxes_and_totals() during insert().
    # We then set apply_tds=0 so Frappe's controller does NOT overwrite our row.
    # =========================================================================
    # Track for post-save rate restore (ERPNext resets rate=0 on "Actual" rows)
    _pph_actual_rate_to_display = 0.0
    _pph_actual_account_head = None

    if apply_pph:
        _pph_row_added = False
        try:
            wht_category = frappe.get_doc("Tax Withholding Category", request.pph_type)

            # Resolve WHT account for this company
            wht_account = None
            for _acc in wht_category.accounts or []:
                if _acc.company == pi.company:
                    wht_account = _acc.account
                    break

            if not wht_account:
                frappe.logger().error(
                    f"[PPh] No account configured for company '{pi.company}' "
                    f"in Tax Withholding Category '{request.pph_type}'"
                )
            else:
                # Determine base amount (consistent with withholding_tax_base_amount above)
                if item_wise_pph_detail:
                    _pph_base = sum(float(v) for v in item_wise_pph_detail.values())
                elif is_header_level_pph:
                    _pph_base = flt(getattr(request, "pph_base_amount", 0) or 0) or sum(
                        flt(getattr(_it, "net_amount", None) or getattr(_it, "amount", 0))
                        for _it in request_items
                        if not getattr(_it, "is_variance_item", 0)
                    )
                else:
                    _pph_base = sum(
                        flt(getattr(_it, "pph_base_amount", None)
                            or getattr(_it, "net_amount", None)
                            or getattr(_it, "amount", 0))
                        for _it in request_items
                        if getattr(_it, "is_pph_applicable", 0)
                        and not getattr(_it, "is_variance_item", 0)
                    )

                # Resolve rate by date range
                _rate = 0.0
                _posting_date = pi.posting_date
                for _rr in wht_category.rates or []:
                    _from = getattr(_rr, "from_date", None)
                    _to = getattr(_rr, "to_date", None)
                    if _from and _to:
                        if _from <= _posting_date <= _to:
                            _rate = flt(_rr.tax_withholding_rate)
                            break
                    elif hasattr(_rr, "tax_withholding_rate"):
                        _rate = flt(_rr.tax_withholding_rate)
                        break

                if _rate > 0 and _pph_base > 0:
                    _cost_center = (
                        request_cost_center
                        or frappe.get_cached_value("Company", pi.company, "cost_center")
                    )

                    # Determine whether pph_base covers the entire net total of the PI.
                    # Sum item amounts directly from pi.items (pi.net_total not yet computed
                    # at this point since insert() hasn't run).
                    _pi_net_total = sum(flt(getattr(_i, "amount", 0)) for _i in (pi.items or []))

                    # Use "On Net Total" when PPh applies to the whole invoice.
                    # ERPNext resets rate=0 for "Actual" charge type during validate(),
                    # so "On Net Total" is the only way to show the rate in the Tax Rate column.
                    # Use "Actual" only when PPh base is a subset of net total (partial items),
                    # and embed the rate in the description as a fallback.
                    _partial_base = _pi_net_total > 0 and abs(_pi_net_total - _pph_base) > 1

                    if not _partial_base:
                        # All items taxable → "On Net Total"; Frappe computes rate% × net_total
                        pi.append("taxes", {
                            "charge_type": "On Net Total",
                            "account_head": wht_account,
                            "description": f"Tax Withheld - {request.pph_type}",
                            "rate": _rate,
                            "add_deduct_tax": "Deduct",
                            "category": "Total",
                            "cost_center": _cost_center,
                        })
                    else:
                        # Partial base (only some items taxable) → "Actual" with fixed amount
                        _raw = _pph_base * _rate / 100
                        _pph_amount = round(_raw) if getattr(wht_category, "round_off_tax_amount", 0) else _raw
                        pi.append("taxes", {
                            "charge_type": "Actual",
                            "account_head": wht_account,
                            "description": f"Tax Withheld - {request.pph_type} ({_rate}% x {_pph_base:,.0f})",
                            "rate": _rate,
                            "tax_amount": _pph_amount,
                            "base_tax_amount": _pph_amount,
                            "add_deduct_tax": "Deduct",
                            "category": "Total",
                            "cost_center": _cost_center,
                        })
                        # Track so we can restore rate after ERPNext resets it during save()
                        _pph_actual_rate_to_display = _rate
                        _pph_actual_account_head = wht_account
                    _pph_row_added = True
                    frappe.logger().info(
                        f"[PPh] Row added before insert: account={wht_account}, "
                        f"base={_pph_base}, rate={_rate}%, partial={_partial_base}"
                    )
                else:
                    frappe.logger().warning(
                        f"[PPh] rate={_rate} or base={_pph_base} is 0 — PPh row skipped"
                    )
        except Exception as _e:
            frappe.logger().error(f"[PPh] Failed to build PPh row before insert: {_e}")

        # Disable Frappe's WHT controller so it does NOT overwrite our row
        # during validate() / calculate_taxes_and_totals() triggered by insert().
        pi.apply_tds = 0

    # map tax invoice metadata
    pi.ti_tax_invoice_pdf = getattr(request, "ti_tax_invoice_pdf", None)
    pi.ti_tax_invoice_upload = getattr(request, "ti_tax_invoice_upload", None)
    pi.ti_fp_no = getattr(request, "ti_fp_no", None)
    pi.ti_fp_date = getattr(request, "ti_fp_date", None)
    pi.ti_fp_npwp = getattr(request, "ti_fp_npwp", None)
    pi.ti_fp_dpp = getattr(request, "ti_fp_dpp", None)
    pi.ti_fp_ppn = getattr(request, "ti_fp_ppn", None)
    pi.ti_fp_ppn_type = getattr(request, "ti_fp_ppn_type", None)
    pi.ti_verification_status = getattr(request, "ti_verification_status", None)
    pi.ti_verification_notes = getattr(request, "ti_verification_notes", None)
    pi.ti_duplicate_flag = getattr(request, "ti_duplicate_flag", None)
    pi.ti_npwp_match = getattr(request, "ti_npwp_match", None)
    # Copy variance field for reference and audit trail
    pi.ti_ppn_variance = getattr(request, "ti_ppn_variance", None)
    apply_branch(pi, branch)

    pi.insert(ignore_permissions=True)

    # IMPORTANT: Manually add PPN tax rows from template (don't use taxes_and_charges field)
    # Using field causes rows to replace/override PPh rows
    # Manual append ensures PPh + PPN coexist
    if apply_ppn and request.ppn_template:
        try:
            frappe.logger().info(
                f"[PPN] PI {pi.name}: Adding PPN rows from template '{request.ppn_template}'"
            )

            # Get template document - MUST use Purchase template for PI (not Sales)
            ppn_template_doc = frappe.get_doc("Purchase Taxes and Charges Template", request.ppn_template)

            if ppn_template_doc and ppn_template_doc.taxes:
                # Store first PPN tax row info for variance adjustment later
                first_ppn_account = None

                # Add each tax row from template
                for tax_row in ppn_template_doc.taxes:
                    tax_dict = {
                        "charge_type": tax_row.charge_type,
                        "account_head": tax_row.account_head,
                        "description": tax_row.description,
                        "rate": tax_row.rate,
                    }

                    # Track first PPN tax row for variance adjustment
                    if tax_row.charge_type == "On Net Total" and not first_ppn_account:
                        first_ppn_account = tax_row.account_head

                    pi.append("taxes", tax_dict)

                frappe.logger().info(
                    f"[PPN] PI {pi.name}: Added {len(ppn_template_doc.taxes)} PPN tax row(s)"
                )

            # CRITICAL: Exempt variance items from PPN BEFORE first save/calculation
            # Set item_tax_rate with specific PPN account to zero out tax on variance
            if first_ppn_account:
                exempt_count = 0
                for item_row in pi.items:
                    # Check PERSISTENT fields, not runtime flags
                    is_var = (
                        getattr(item_row, "is_variance_item", 0) or
                        getattr(item_row, "is_ppn_variance_row", 0)
                    )
                    if is_var:
                        # Set item_tax_rate to exempt this item from PPN
                        # Format: {"Account Head": 0}
                        import json
                        item_row.item_tax_rate = json.dumps({first_ppn_account: 0})
                        exempt_count += 1
                        frappe.logger().info(
                            f"[VARIANCE ITEM] PI {pi.name} item {item_row.idx}: "
                            f"Set item_tax_rate = {item_row.item_tax_rate} to exempt from PPN {first_ppn_account}"
                        )

                if exempt_count > 0:
                    frappe.logger().info(
                        f"[PPN] PI {pi.name}: Exempted {exempt_count} variance item(s) from PPN"
                    )

            # Save and recalculate with variance items exempted
            pi.save(ignore_permissions=True)
            pi.reload()

            # CRITICAL: Force recalculation to ensure exemptions are applied
            if hasattr(pi, "calculate_taxes_and_totals"):
                pi.calculate_taxes_and_totals()
                # Save again to persist the calculated taxes
                pi.save(ignore_permissions=True)
                pi.reload()

            frappe.logger().info(
                f"[PPN] PI {pi.name}: PPN calculated - Added={flt(pi.taxes_and_charges_added):,.2f}"
            )

        except Exception as e:
            frappe.logger().error(
                f"[PPN ERROR] PI {pi.name}: {str(e)}"
            )
            # Still save document even if PPN fails
            pi.save(ignore_permissions=True)
    else:
        frappe.logger().info(
            f"[PPN] PI {pi.name}: apply_ppn={apply_ppn} - PPN not applicable"
        )

    # Recalculate taxes and totals after insert to ensure PPN and PPh are properly calculated
    # This is critical because:
    # 1. Withholding tax (PPh) is calculated by Frappe's TDS controller after save
    # 2. PPN needs to be recalculated from the final item total (including variance)
    # 3. ERPNext's tax calculation requires the document to exist in DB first
    pi.reload()  # Refresh from DB to get any auto-calculated fields

    # Now recalculate with all items and settings in place
    if hasattr(pi, "calculate_taxes_and_totals"):
        try:
            pi.calculate_taxes_and_totals()
            for fieldname in (
                "taxes_and_charges_added",
                "taxes_and_charges_deducted",
                "total_taxes_and_charges",
            ):
                if getattr(pi, fieldname, None) is None:
                    setattr(pi, fieldname, 0)
            pi.save(ignore_permissions=True)
        except Exception as e:
            frappe.logger().error(f"Tax calculation failed for PI {pi.name}: {str(e)}")
            frappe.msgprint(
                _("Tax calculation encountered an error. Please review the Purchase Invoice {0} manually.").format(pi.name),
                indicator="red",
                alert=True
            )

    # Reload again to get final calculated values
    pi.reload()

    # Apply PPN variance to tax amount AFTER all calculations are complete
    # CRITICAL: Must be done after final calculate_taxes_and_totals() to prevent overwriting
    if apply_ppn and ppn_variance != 0:
        variance_applied = False
        first_ppn_account = None

        # Find first PPN tax row
        for tax_row in pi.taxes:
            if tax_row.charge_type == "On Net Total":
                first_ppn_account = tax_row.account_head
                break

        if first_ppn_account:
            for tax_row in pi.taxes:
                # Find the PPN tax row by matching account_head
                if tax_row.account_head == first_ppn_account:
                    # Add variance to calculated tax_amount
                    original_amount = flt(tax_row.tax_amount)
                    new_amount = original_amount + ppn_variance
                    # ROUND to integer for IDR currency (no decimals)
                    new_amount = round(new_amount)
                    tax_row.tax_amount = new_amount

                    # Update description to show variance adjustment
                    variance_note = _("(incl. OCR variance: {0})").format(
                        frappe.format_value(ppn_variance, {"fieldtype": "Currency"})
                    )
                    if tax_row.description:
                        tax_row.description = f"{tax_row.description} {variance_note}"
                    else:
                        tax_row.description = variance_note

                    frappe.logger().info(
                        f"[PPN VARIANCE] PI {pi.name}: Adjusted PPN from {original_amount:,.2f} "
                        f"to {new_amount:,.2f} (variance={ppn_variance:,.2f})"
                    )
                    variance_applied = True
                    break

            if variance_applied:
                # Update parent totals to reflect variance
                # CRITICAL: Use db_set to bypass calculate_taxes_and_totals()
                # which would recalculate tax from rate and remove variance
                # ROUND all totals to integer for IDR currency
                new_taxes_added = round(flt(pi.taxes_and_charges_added) + ppn_variance)
                new_total_taxes = round(flt(pi.total_taxes_and_charges) + ppn_variance)
                new_grand_total = round(flt(pi.grand_total) + ppn_variance)
                new_rounded_total = round(flt(pi.rounded_total) + ppn_variance)

                # Find and update the tax row in database directly
                updated_tax_amount = 0
                for tax_row in pi.taxes:
                    if tax_row.account_head == first_ppn_account:
                        updated_tax_amount = tax_row.tax_amount
                        # Update child table row directly via db_update (bypass hooks)
                        frappe.db.set_value(
                            "Purchase Taxes and Charges",
                            tax_row.name,
                            {
                                "tax_amount": tax_row.tax_amount,
                                "description": tax_row.description,
                            },
                            update_modified=False
                        )
                        break

                # Update parent fields directly in DB
                frappe.db.set_value(
                    "Purchase Invoice",
                    pi.name,
                    {
                        "taxes_and_charges_added": new_taxes_added,
                        "total_taxes_and_charges": new_total_taxes,
                        "grand_total": new_grand_total,
                        "rounded_total": new_rounded_total,
                    },
                    update_modified=False
                )

                # Reload to get updated values
                pi.reload()

                frappe.logger().info(
                    f"[PPN VARIANCE] PI {pi.name}: Applied variance to totals - "
                    f"Grand Total: {new_grand_total:,.2f}, PPN: {updated_tax_amount:,.2f}"
                )
            else:
                frappe.logger().warning(
                    f"[PPN VARIANCE] PI {pi.name}: Could not find PPN tax row to apply variance"
                )

    # Validate taxes were actually calculated
    # NOTE: Skip validation for MIXED mode since taxes are calculated per-item, not at PI level
    if apply_ppn and flt(pi.taxes_and_charges_added) == 0:
        frappe.msgprint(
            _("Warning: PPN was not calculated. Please check PPN Template '{0}' configuration.").format(
                getattr(request, "ppn_template", "")
            ),
            indicator="orange",
            alert=True
        )

    # CRITICAL: Don't warn if MIXED Apply WHT mode (taxes calculated per-item)
    if apply_pph and not has_mixed_pph:
        # Check actual tax rows — pi.taxes_and_charges_deducted may be stale in memory
        # after set_tax_withholding() + save() without an explicit reload.
        pph_deducted_rows = [
            t for t in (pi.taxes or [])
            if flt(t.get("tax_amount") if isinstance(t, dict) else getattr(t, "tax_amount", 0)) < 0
            or getattr(t, "add_deduct_tax", "") == "Deduct"
        ]
        if not pph_deducted_rows and flt(frappe.db.get_value("Purchase Invoice", pi.name, "taxes_and_charges_deducted") or 0) == 0:
            frappe.msgprint(
                _("Warning: PPH was not calculated. Please check Tax Withholding Category '{0}' configuration.").format(
                    getattr(request, "pph_type", "")
                ),
                indicator="orange",
                alert=True
            )

    # =========================================================================
    # RESTORE PPh RATE — ERPNext resets rate=0 for "Actual" charge_type on every
    # validate() / calculate_taxes_and_totals() call.  Force-write it back now
    # that all saves are complete so the Tax Rate column is readable on the form.
    # =========================================================================
    if apply_pph and _pph_actual_rate_to_display and _pph_actual_account_head:
        try:
            pi.reload()
            for _tax_row in (pi.taxes or []):
                if (
                    getattr(_tax_row, "account_head", "") == _pph_actual_account_head
                    and getattr(_tax_row, "charge_type", "") == "Actual"
                ):
                    frappe.db.set_value(
                        "Purchase Taxes and Charges",
                        _tax_row.name,
                        "rate",
                        _pph_actual_rate_to_display,
                        update_modified=False,
                    )
                    frappe.logger().info(
                        f"[PPh] Restored rate={_pph_actual_rate_to_display}% on Actual PPh row "
                        f"{_tax_row.name} (bypasses ERPNext reset)"
                    )
                    break
        except Exception as _re:
            frappe.logger().warning(f"[PPh] Could not restore Actual PPh rate: {_re}")

    _update_request_purchase_invoice_links(request, pi)

    if getattr(pi, "docstatus", 0) == 0:
        notifier = getattr(frappe, "msgprint", None)
        if notifier:
            notifier(
                _(
                    "Purchase Invoice {0} was created in Draft. Please submit it before continuing to Payment Entry."
                ).format(pi.name),
                alert=True,
            )

    return pi.name
