"""Workflow helpers for Expense Request budget lock, internal charge, and consumption."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from typing import Iterable

import frappe
from frappe import _
from frappe.utils import get_first_day, get_last_day

from imogi_finance import accounting, roles
from imogi_finance.budget_control import ledger, service, utils

BUDGET_WORKFLOW_STATES = (
    "Draft",
    "Submitted",
    "Under Review",
    "Approved",
    "Rejected",
    "Completed",
)


def _get_session_user() -> str | None:
    return getattr(getattr(frappe, "session", None), "user", None)


def _safe_now():
    try:
        return frappe.utils.now_datetime()
    except Exception:
        try:
            return datetime.now()
        except Exception:
            return None


def _add_budget_state_comment(expense_request, from_state: str, to_state: str, *, reason: str | None = None):
    add_comment = getattr(expense_request, "add_comment", None)
    if not callable(add_comment):
        return

    timestamp = _safe_now()
    details = []
    session_user = _get_session_user()
    if session_user:
        details.append(_("User: {0}").format(session_user))
    if timestamp:
        details.append(_("At: {0}").format(timestamp))
    if reason:
        details.append(_("Reason: {0}").format(reason))

    detail_text = " ".join(details) if details else ""
    message = _("Budget workflow state changed from {0} to {1}.").format(from_state, to_state)
    if detail_text:
        message = "{0} {1}".format(message, detail_text)

    try:
        add_comment("Comment", message)
    except Exception:
        pass


def _notify_budget_state_change(expense_request, to_state: str):
    notifier = getattr(frappe, "publish_realtime", None)
    if not notifier or not getattr(expense_request, "name", None):
        return

    try:
        notifier(
            event="budget_workflow_update",
            message={
                "expense_request": getattr(expense_request, "name", None),
                "state": to_state,
                "user": _get_session_user(),
            },
        )
    except Exception:
        pass


def _get_budget_workflow_state(expense_request) -> str:
    state = getattr(expense_request, "budget_workflow_state", None)
    return state or "Draft"


def _set_budget_workflow_state(expense_request, state: str, *, reason: str | None = None):
    if state not in BUDGET_WORKFLOW_STATES:
        return

    current_state = _get_budget_workflow_state(expense_request)
    if current_state == state:
        return

    if hasattr(expense_request, "db_set"):
        try:
            expense_request.db_set("budget_workflow_state", state)
        except Exception:
            pass
    expense_request.budget_workflow_state = state

    _add_budget_state_comment(expense_request, current_state, state, reason=reason)
    _notify_budget_state_change(expense_request, state)


def _require_budget_controller_role(settings):
    if not settings.get("require_budget_controller_review"):
        return None

    required_role = settings.get("budget_controller_role") or roles.BUDGET_CONTROLLER
    roles_for_session = set()
    get_roles = getattr(frappe, "get_roles", None)
    if callable(get_roles):
        try:
            roles_for_session = set(get_roles())
        except Exception:
            roles_for_session = set()

    if not roles_for_session:
        return required_role

    if required_role in roles_for_session or roles.SYSTEM_MANAGER in roles_for_session:
        return required_role

    frappe.throw(_("Budget Controller role ({0}) is required to review and approve budget operations.").format(required_role))


def _record_budget_workflow_event(expense_request, action: str | None, next_state: str | None, target_state: str):
    current_state = _get_budget_workflow_state(expense_request)
    if action == "Submit" and current_state in {"Draft", "Rejected"}:
        _set_budget_workflow_state(expense_request, "Submitted", reason=_("Submitted for budget controller review"))
        return

    if action == "Reject":
        _set_budget_workflow_state(expense_request, "Rejected", reason=_("Workflow action rejected"))
        return

    if action == "Reopen":
        _set_budget_workflow_state(expense_request, "Draft", reason=_("Reopened for corrections"))
        return

    if action == "Approve" and next_state == target_state and current_state == "Submitted":
        _set_budget_workflow_state(expense_request, "Under Review", reason=_("Budget controller review started"))


def _get_account_totals(items: Iterable) -> tuple[float, dict[str, float]]:
    total = 0.0
    per_account: dict[str, float] = defaultdict(float)

    for item in items or []:
        # Skip variance items from budget check
        # Variance items are system-generated adjustments (e.g., PPN rounding differences)
        # and should not be subject to budget control
        is_variance = accounting._get_item_value(item, "is_variance_item")
        if is_variance:
            frappe.logger().info(
                f"_get_account_totals: Skipping variance item from budget check: {accounting._get_item_value(item, 'description')}"
            )
            continue

        account = accounting._get_item_value(item, "expense_account")
        amount = accounting._get_item_value(item, "amount")

        if not account or amount is None:
            continue

        per_account[account] += float(amount)
        total += float(amount)

    return total, per_account


def _load_internal_charge_request(ic_name: str | None):
    if not ic_name:
        return None

    try:
        return frappe.get_doc("Internal Charge Request", ic_name)
    except Exception:
        return None


def _parse_route_snapshot(raw_snapshot):
    if not raw_snapshot:
        return {}

    if isinstance(raw_snapshot, dict):
        return raw_snapshot

    try:
        return json.loads(raw_snapshot)
    except Exception:
        return {}


def _get_budget_window(expense_request, settings) -> tuple[date | None, date | None]:
    basis = (settings.get("budget_check_basis") or "Fiscal Year").lower()
    if basis.startswith("fiscal period"):
        posting_date = (
            getattr(expense_request, "posting_date", None)
            or getattr(expense_request, "request_date", None)
        )
        if posting_date:
            return get_first_day(posting_date), get_last_day(posting_date)
    return None, None


def _iter_internal_charge_lines(ic_doc) -> Iterable:
    for line in getattr(ic_doc, "internal_charge_lines", []) or []:
        yield line


def _require_internal_charge_ready(expense_request, settings):
    required = settings.get("internal_charge_required_before_er_approval")
    if not required:
        return None

    ic_name = getattr(expense_request, "internal_charge_request", None)
    if not ic_name:
        frappe.throw(_("Internal Charge Request is required before approval for allocated requests."))

    ic_doc = _load_internal_charge_request(ic_name)
    if not ic_doc or getattr(ic_doc, "status", None) != "Approved":
        frappe.throw(_("Internal Charge Request {0} must be Approved.").format(ic_name))

    total_amount, account_totals = _get_account_totals(getattr(expense_request, "items", []) or [])
    ic_total = sum(float(getattr(line, "amount", 0) or 0) for line in _iter_internal_charge_lines(ic_doc))

    if total_amount and abs(ic_total - total_amount) > 0.0001:
        frappe.throw(_("Internal Charge Request total ({0}) must equal Expense Request total ({1}).").format(ic_total, total_amount))

    if not account_totals:
        frappe.throw(_("Expense Request must have at least one expense account before allocating."))

    return ic_doc


def _build_allocation_slices(expense_request, *, settings=None, ic_doc=None):
    settings = settings or utils.get_settings()
    # Support both Expense Request (header cost_center) and Advanced Expense Request (approval_cost_center)
    header_cc = getattr(expense_request, "cost_center", None) or getattr(expense_request, "approval_cost_center", None)
    company = utils.resolve_company_from_cost_center(header_cc)
    # FIX: Expense Request doesn't have fiscal_year field, need to resolve it
    fiscal_year = utils.resolve_fiscal_year(getattr(expense_request, "fiscal_year", None), company=company)

    # Validate fiscal year is found
    if not fiscal_year:
        frappe.throw(
            _("Fiscal Year could not be determined for Expense Request {0}. Please set a default Fiscal Year for Company {1} or in User Defaults.").format(
                getattr(expense_request, "name", "Unknown"),
                company or "(unknown)"
            ),
            title=_("Fiscal Year Required")
        )

    items = getattr(expense_request, "items", []) or []
    total_amount, account_totals = _get_account_totals(items)

    if not account_totals:
        # Log detailed info for debugging
        item_details = []
        for idx, item in enumerate(items):
            acc = accounting._get_item_value(item, "expense_account")
            amt = accounting._get_item_value(item, "amount")
            item_details.append(f"Item {idx+1}: account={acc}, amount={amt}")

        frappe.logger().warning(
            f"_build_allocation_slices: No account totals for {getattr(expense_request, 'name', 'Unknown')}. "
            f"Items: {item_details}"
        )
        return []

    frappe.logger().info(f"_build_allocation_slices for {getattr(expense_request, 'name', 'Unknown')}: total={total_amount}, accounts={list(account_totals.keys())}")

    slices = []

    if getattr(expense_request, "allocation_mode", "Direct") != "Allocated via Internal Charge":
        # Check if line items carry their own cost_center (e.g. Advanced Expense Request)
        items_have_per_item_cc = any(
            getattr(item, "cost_center", None)
            for item in items
            if not getattr(item, "is_variance_item", 0)
        )
        if items_have_per_item_cc:
            # Per-item cost center mode: aggregate by (cost_center, account) pair
            from collections import defaultdict
            cc_account_totals: dict = defaultdict(float)
            for item in items:
                if getattr(item, "is_variance_item", 0):
                    continue
                account = accounting._get_item_value(item, "expense_account")
                amount = float(accounting._get_item_value(item, "amount") or 0)
                item_cc = getattr(item, "cost_center", None)
                if not account or not amount or not item_cc:
                    continue
                cc_account_totals[(item_cc, account)] += amount
            for (item_cc, account), amount in cc_account_totals.items():
                dims = service.resolve_dims(
                    company=company,
                    fiscal_year=fiscal_year,
                    cost_center=item_cc,
                    account=account,
                    project=getattr(expense_request, "project", None),
                    branch=getattr(expense_request, "branch", None),
                )
                slices.append((dims, amount))
        else:
            header_cc_for_slice = getattr(expense_request, "cost_center", None) or getattr(expense_request, "approval_cost_center", None)
            for account, amount in account_totals.items():
                dims = service.resolve_dims(
                    company=company,
                    fiscal_year=fiscal_year,
                    cost_center=header_cc_for_slice,
                    account=account,
                    project=getattr(expense_request, "project", None),
                    branch=getattr(expense_request, "branch", None),
                )
                slices.append((dims, float(amount)))

        frappe.logger().info(f"_build_allocation_slices: Created {len(slices)} slices for direct allocation")
        return slices

    ic_doc = ic_doc or _load_internal_charge_request(getattr(expense_request, "internal_charge_request", None))
    if not ic_doc:
        return []

    if not total_amount:
        return []

    # New logic: Use direct line amounts (no proportion calculation)
    # Each line specifies exact account and amount
    for line in _iter_internal_charge_lines(ic_doc):
        account = getattr(line, "expense_account", None)
        amount = float(getattr(line, "amount", 0) or 0)

        if not account or not amount:
            continue

        dims = service.resolve_dims(
            company=company,
            fiscal_year=fiscal_year,
            cost_center=getattr(line, "target_cost_center", None),
            account=account,
            project=getattr(expense_request, "project", None),
            branch=getattr(expense_request, "branch", None),
        )
        slices.append((dims, amount))

    return slices


def _get_entries_for_ref(ref_doctype: str, ref_name: str, entry_type: str | None = None):
    filters = {"ref_doctype": ref_doctype, "ref_name": ref_name, "docstatus": 1}
    if entry_type:
        filters["entry_type"] = entry_type

    try:
        return frappe.get_all(
            "Budget Control Entry",
            filters=filters,
            fields=[
                "name",
                "entry_type",
                "company",
                "fiscal_year",
                "cost_center",
                "account",
                "project",
                "branch",
                "amount",
                "direction",
            ],
        )
    except Exception:
        return []


def _reverse_reservations(expense_request):
    """Reverse existing RESERVATION entries by creating RESERVATION IN entries.

    Used when re-submitting an Expense Request that already has reservations.
    Uses RESERVATION IN to offset RESERVATION OUT (simplified flow, replaces RELEASE).
    """
    _er_ref_doctype = getattr(expense_request, "doctype", "Expense Request")
    reservations = _get_entries_for_ref(_er_ref_doctype, getattr(expense_request, "name", None), "RESERVATION")
    # Only reverse OUT reservations (not IN releases)
    reservations_out = [r for r in reservations if r.get("direction") == "OUT"]
    if not reservations_out:
        return

    for row in reservations_out:
        dims = utils.Dimensions(
            company=row.get("company"),
            fiscal_year=row.get("fiscal_year"),
            cost_center=row.get("cost_center"),
            account=row.get("account"),
            project=row.get("project"),
            branch=row.get("branch"),
        )
        # Use RESERVATION IN to offset RESERVATION OUT (replaces RELEASE)
        ledger.post_entry(
            "RESERVATION",
            dims,
            float(row.get("amount") or 0),
            "IN",
            ref_doctype=_er_ref_doctype,
            ref_name=getattr(expense_request, "name", None),
            remarks=_("Releasing prior reservation before re-locking"),
        )


def _cancel_existing_reservations(reservations: list[dict]) -> None:
    for row in reservations or []:
        entry_name = row.get("name")
        if not entry_name:
            continue
        try:
            entry = frappe.get_doc("Budget Control Entry", entry_name)
        except Exception:
            continue
        entry.flags.ignore_permissions = True
        entry.flags.from_parent_cancel = True
        try:
            entry.cancel()
        except Exception:
            frappe.log_error(
                title=_("Budget Reservation Recalculation Failed"),
                message=_("Failed to cancel Budget Control Entry {0} during recalculation.").format(entry_name),
            )


def reserve_budget_for_request(expense_request, *, trigger_action: str | None = None, next_state: str | None = None):
    """Reserve budget for an expense request.

    Args:
        expense_request: Can be either:
            - An Expense Request doc object
            - A string name of an Expense Request document
        trigger_action: Optional action that triggered this (for logging)
        next_state: Optional next state (for logging)
    """
    # If string name provided, load the document
    if isinstance(expense_request, str):
        frappe.logger().info(f"reserve_budget_for_request: Loading doc {expense_request}")
        try:
            expense_request = frappe.get_doc("Expense Request", expense_request)
        except Exception as e:
            frappe.logger().error(f"reserve_budget_for_request: Failed to load {expense_request}: {str(e)}")
            frappe.throw(_("Failed to load Expense Request {0}: {1}").format(expense_request, str(e)))

    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        frappe.logger().info(f"reserve_budget_for_request: Budget lock disabled for {getattr(expense_request, 'name', 'Unknown')}")
        frappe.msgprint(_("Budget lock is disabled in Budget Control Settings"), indicator="orange")
        return
    from_date, to_date = _get_budget_window(expense_request, settings)

    # Check if already reserved (avoid duplicate)
    _er_ref_doctype = getattr(expense_request, "doctype", "Expense Request")
    existing = _get_entries_for_ref(_er_ref_doctype, getattr(expense_request, "name", None), "RESERVATION")
    if existing:
        if trigger_action == "Submit":
            frappe.logger().info(
                f"reserve_budget_for_request: Recalculating reservations for {getattr(expense_request, 'name', 'Unknown')}"
            )
            _cancel_existing_reservations(existing)
        else:
            frappe.logger().info(f"reserve_budget_for_request: Budget already reserved for {getattr(expense_request, 'name', 'Unknown')}")
            frappe.msgprint(
                _("Budget already reserved for this request."),
                indicator="blue",
                alert=True
            )
            return

    # Budget check dilakukan saat submit (docstatus=1), tidak perlu tunggu approved
    docstatus = getattr(expense_request, "docstatus", 0)
    status = getattr(expense_request, "status", None)
    workflow_state = getattr(expense_request, "workflow_state", None)

    frappe.logger().info(
        f"reserve_budget_for_request: {getattr(expense_request, 'name', 'Unknown')} "
        f"- docstatus={docstatus}, status={status}, workflow={workflow_state}"
    )

    # Allow reservation saat submitted (docstatus=1), tidak perlu tunggu state tertentu
    if docstatus != 1:
        frappe.logger().info(f"reserve_budget_for_request: Document not submitted yet (docstatus={docstatus})")
        frappe.msgprint(
            _("Budget reservation requires document to be submitted."),
            indicator="yellow"
        )
        return

    ic_doc = None
    allocation_mode = getattr(expense_request, "allocation_mode", "Direct")
    if allocation_mode == "Allocated via Internal Charge":
        # Check if ICR exists - if not, skip IC validation during Submit
        # ICR is generated AFTER submit, so we can't require it at submit time
        ic_name = getattr(expense_request, "internal_charge_request", None)
        if ic_name:
            # ICR exists, validate it's ready (must be Approved before ER can be fully processed)
            try:
                ic_doc = _require_internal_charge_ready(expense_request, settings)
            except Exception as e:
                frappe.logger().error(f"reserve_budget_for_request: Internal Charge validation failed for {getattr(expense_request, 'name', 'Unknown')}: {str(e)}")
                frappe.throw(
                    _("Internal Charge validation failed. {0}").format(str(e)),
                    title=_("Internal Charge Required")
                )
        else:
            # ICR not yet created - this is expected at Submit time
            # Skip budget reservation for now, will be done when ICR is approved and ER is approved
            frappe.logger().info(
                f"reserve_budget_for_request: {getattr(expense_request, 'name', 'Unknown')} uses Internal Charge "
                f"but ICR not yet created. Skipping budget reservation until ICR is generated and approved."
            )
            frappe.msgprint(
                _("Internal Charge allocation mode detected. Please generate Internal Charge Request after submit, "
                  "then approve ICR before approving this Expense Request."),
                indicator="blue",
                alert=True
            )
            return

    try:
        slices = _build_allocation_slices(expense_request, settings=settings, ic_doc=ic_doc)
    except Exception as e:
        frappe.logger().error(f"reserve_budget_for_request: Failed to build allocation slices for {getattr(expense_request, 'name', 'Unknown')}: {str(e)}")
        frappe.throw(
            _("Failed to build budget allocation slices. Please check expense items, accounts, and cost centers. Error: {0}").format(str(e)),
            title=_("Budget Allocation Failed")
        )

    if not slices:
        # Build detailed error message
        items = getattr(expense_request, "items", []) or []
        allocation_mode = getattr(expense_request, "allocation_mode", "Direct")
        cost_center = getattr(expense_request, "cost_center", None) or getattr(expense_request, "approval_cost_center", None)

        missing_info = []
        if not cost_center:
            missing_info.append(_("Cost Center is not set on Expense Request"))

        items_without_account = []
        items_without_amount = []
        for idx, item in enumerate(items):
            acc = accounting._get_item_value(item, "expense_account")
            amt = accounting._get_item_value(item, "amount")
            if not acc:
                items_without_account.append(str(idx + 1))
            if not amt or float(amt or 0) <= 0:
                items_without_amount.append(str(idx + 1))

        if items_without_account:
            missing_info.append(_("Items without Expense Account: Row {0}").format(", ".join(items_without_account)))
        if items_without_amount:
            missing_info.append(_("Items without valid Amount: Row {0}").format(", ".join(items_without_amount)))
        if not items:
            missing_info.append(_("No expense items found"))

        error_detail = "<br>".join(missing_info) if missing_info else _("Unknown reason - please check expense items")

        frappe.logger().warning(
            f"reserve_budget_for_request: No allocation slices for {getattr(expense_request, 'name', 'Unknown')}. "
            f"Mode={allocation_mode}, CC={cost_center}, Items={len(items)}, Details={missing_info}"
        )
        frappe.throw(
            _("No budget allocation slices could be created.<br><br><b>Issues found:</b><br>{0}").format(error_detail),
            title=_("Budget Allocation Failed")
        )

    frappe.logger().info(f"reserve_budget_for_request: Processing {len(slices)} slices for {getattr(expense_request, 'name', 'Unknown')}")

    controller_role = _require_budget_controller_role(settings)
    reviewer = _get_session_user() or controller_role
    _set_budget_workflow_state(
        expense_request,
        "Under Review",
        reason=_("Budget validation initiated by {0}.").format(reviewer or _("system")),
    )

    allow_role = settings.get("allow_budget_overrun_role")
    allow_overrun = bool(allow_role and allow_role in frappe.get_roles())

    # Note: Tidak perlu _reverse_reservations lagi karena CONSUMPTION akan mengurangi reserved
    # Reservation entry tetap ada, hanya di-offset oleh CONSUMPTION saat PI submit

    any_overrun = False
    for dims, amount in slices:
        try:
            result = service.check_budget_available(dims, float(amount or 0), from_date=from_date, to_date=to_date)
        except Exception as e:
            frappe.logger().error(f"reserve_budget_for_request: Failed to check budget availability: {str(e)}")
            frappe.throw(
                _("Failed to check budget availability. Please contact administrator. Error: {0}").format(str(e)),
                title=_("Budget Check Failed")
            )

        frappe.logger().info(
            f"reserve_budget_for_request: Budget check for {dims.cost_center}/{dims.account}: "
            f"amount={amount}, available={result.available}, ok={result.ok}"
        )

        if not result.ok and not allow_overrun:
            # Enhanced error message with details
            frappe.logger().warning(
                f"reserve_budget_for_request: Budget insufficient for {dims.cost_center}/{dims.account} - "
                f"Requested: {amount}, Available: {result.available}"
            )
            frappe.throw(
                _("Budget Insufficient: {0}<br><br>Cost Center: {1}<br>Account: {2}<br>Requested: {3}<br>Available: {4}").format(
                    result.message,
                    dims.cost_center or "(not set)",
                    dims.account or "(not set)",
                    frappe.format_value(amount, {"fieldtype": "Currency"}),
                    frappe.format_value(result.available, {"fieldtype": "Currency"}) if result.available is not None else "N/A"
                ),
                title=_("Budget Exceeded")
            )

        if not result.ok:
            any_overrun = True
            frappe.logger().warning(
                f"reserve_budget_for_request: Overrun allowed for {dims.cost_center}/{dims.account} by user with special role"
            )

    entries_created = []
    for dims, amount in slices:
        try:
            entry_name = ledger.post_entry(
                "RESERVATION",
                dims,
                float(amount or 0),
                "OUT",
                ref_doctype=_er_ref_doctype,
                ref_name=getattr(expense_request, "name", None),
                remarks=_("Budget reservation for Expense Request"),
            )
            if entry_name:
                entries_created.append(entry_name)
                frappe.logger().info(f"reserve_budget_for_request: ✅ Created reservation {entry_name}")
            else:
                frappe.logger().warning(f"reserve_budget_for_request: ⚠️ No entry created for {dims.cost_center}/{dims.account}")
        except Exception as e:
            frappe.logger().error(f"reserve_budget_for_request: ❌ Failed to create reservation: {str(e)}")
            frappe.log_error(
                title=f"Budget Reservation Failed for {getattr(expense_request, 'name', None)}",
                message=f"Error creating reservation entry: {str(e)}\n\n{frappe.get_traceback()}"
            )
            raise

    lock_status = "Overrun Allowed" if any_overrun else "Locked"
    if getattr(expense_request, "budget_lock_status", None) != lock_status:
        if hasattr(expense_request, "db_set"):
            expense_request.db_set("budget_lock_status", lock_status)
        expense_request.budget_lock_status = lock_status
        _set_budget_workflow_state(
            expense_request,
            "Approved",
            reason=_("Budget {0} during reservation.").format("overrun allowed" if any_overrun else "locked"),
        )

    frappe.logger().info(
        f"reserve_budget_for_request: ✅ Completed for {getattr(expense_request, 'name', None)} "
        f"with status {lock_status}. Created {len(entries_created)} entries: {', '.join(entries_created)}"
    )

    # Show success message to user
    if entries_created:
        frappe.msgprint(
            _("Budget Control Entries created successfully: {0}").format(", ".join(entries_created)),
            indicator="green",
            alert=True
        )

    return entries_created


def release_budget_for_request(expense_request, *, reason: str | None = None):
    """Release budget reservation for an expense request.

    Uses RESERVATION with direction IN to offset the original RESERVATION OUT.
    This is the simplified flow that replaces the deprecated RELEASE entry type.

    Reserved = RESERVATION(OUT) - RESERVATION(IN) - CONSUMPTION(IN) + REVERSAL(OUT)
    """
    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        return

    # Get existing RESERVATION OUT entries (only count OUT, ignore any existing IN)
    _er_ref_doctype = getattr(expense_request, "doctype", "Expense Request")
    reservations = _get_entries_for_ref(_er_ref_doctype, getattr(expense_request, "name", None), "RESERVATION")
    # Filter to only OUT direction entries
    reservations_out = [r for r in reservations if r.get("direction") == "OUT"]

    if not reservations_out:
        frappe.logger().info(
            f"release_budget_for_request: No RESERVATION OUT entries found for {getattr(expense_request, 'name', None)}"
        )
        return

    entries_created = []
    for row in reservations_out:
        dims = utils.Dimensions(
            company=row.get("company"),
            fiscal_year=row.get("fiscal_year"),
            cost_center=row.get("cost_center"),
            account=row.get("account"),
            project=row.get("project"),
            branch=row.get("branch"),
        )
        # Use RESERVATION IN to offset RESERVATION OUT (simplified flow, replaces RELEASE)
        entry_name = ledger.post_entry(
            "RESERVATION",
            dims,
            float(row.get("amount") or 0),
            "IN",  # IN direction to release/offset the OUT reservation
            ref_doctype=_er_ref_doctype,
            ref_name=getattr(expense_request, "name", None),
            remarks=_("Release reservation on {0}").format(reason or "rejection/cancel"),
        )
        if entry_name:
            entries_created.append(entry_name)
            frappe.logger().info(f"release_budget_for_request: Created RESERVATION IN {entry_name}")

    frappe.logger().info(
        f"release_budget_for_request: Released {len(entries_created)} reservations for {getattr(expense_request, 'name', None)}"
    )

    if hasattr(expense_request, "db_set"):
        expense_request.db_set("budget_lock_status", "Released")
    expense_request.budget_lock_status = "Released"
    next_budget_state = None
    if reason == "Reopen":
        next_budget_state = "Draft"
    elif reason in {"Reject", "Cancel"}:
        next_budget_state = "Rejected"
    elif reason:
        next_budget_state = "Rejected"

    if next_budget_state:
        _set_budget_workflow_state(
            expense_request,
            next_budget_state,
            reason=_("Budget release triggered by {0}.").format(reason),
        )


def handle_expense_request_workflow(expense_request, action: str | None, next_state: str | None):
    """Handle budget workflow state changes for Expense Request.

    Simplified flow (RELEASE deprecated, use RESERVATION IN):
    - Submit: Create RESERVATION OUT (lock budget)
    - Reject/Cancel: Create RESERVATION IN (release lock) via release_budget_for_request()
    - Reopen: Create RESERVATION IN (release lock) for re-submission

    Formula: Reserved = RESERVATION(OUT) - RESERVATION(IN) - CONSUMPTION(IN) + REVERSAL(OUT)

    RESERVATION entries remain in database and are offset by:
    - RESERVATION IN when ER is rejected/cancelled
    - CONSUMPTION IN when PI is submitted
    - REVERSAL OUT when PI is cancelled
    """
    settings = utils.get_settings()
    if not settings.get("enable_budget_lock"):
        return

    target_state = settings.get("lock_on_workflow_state") or "Approved"
    _record_budget_workflow_event(expense_request, action, next_state, target_state)

    # No need to release on rejection/reopen - RESERVATION stays
    # Reserved budget calculation will still show correctly:
    # Reserved = RESERVATION - CONSUMPTION + REVERSAL
    if action in {"Reject", "Reopen"}:
        # Just update status, keep RESERVATION entries
        if hasattr(expense_request, "db_set"):
            expense_request.db_set("budget_lock_status", "Draft" if action == "Reopen" else "Rejected")
        _set_budget_workflow_state(
            expense_request,
            "Draft" if action == "Reopen" else "Rejected",
            reason=_("Workflow action: {0}").format(action),
        )
        return

    # Reserve budget saat Submit (bukan saat Approve)
    # Budget check akan gagal di submit jika tidak tersedia
    if action == "Submit":
        reserve_budget_for_request(expense_request, trigger_action=action, next_state=next_state)
        return

    # Skip reserve saat Approve jika sudah ada reservation dari Submit
    # Hanya update state ke Approved
    status = getattr(expense_request, "status", None)
    workflow_state = getattr(expense_request, "workflow_state", None)

    if next_state == target_state or workflow_state == target_state or status == target_state:
        # For Internal Charge allocation mode, validate ICR is approved before ER approval
        allocation_mode = getattr(expense_request, "allocation_mode", "Direct")
        if allocation_mode == "Allocated via Internal Charge":
            ic_name = getattr(expense_request, "internal_charge_request", None)
            if not ic_name:
                frappe.throw(
                    _("Please generate Internal Charge Request first before approving this Expense Request. "
                      "Use the 'Generate Internal Charge' button."),
                    title=_("Internal Charge Required")
                )
            try:
                _require_internal_charge_ready(expense_request, settings)
            except Exception as e:
                frappe.throw(
                    _("Internal Charge Request must be approved before approving Expense Request. {0}").format(str(e)),
                    title=_("Internal Charge Not Ready")
                )

        # Check if already reserved
        existing = _get_entries_for_ref(getattr(expense_request, "doctype", "Expense Request"), getattr(expense_request, "name", None), "RESERVATION")
        if existing:
            # Already reserved, just update status
            frappe.logger().info(f"handle_expense_request_workflow: Budget already reserved for {getattr(expense_request, 'name', None)}, updating to Approved")
            if hasattr(expense_request, "db_set"):
                expense_request.db_set("budget_lock_status", "Locked")
            expense_request.budget_lock_status = "Locked"
            _set_budget_workflow_state(expense_request, "Approved", reason=_("Budget already reserved on submit."))
        else:
            # No reservation yet, reserve now (fallback for old workflow)
            frappe.logger().warning(f"handle_expense_request_workflow: No reservation found for {getattr(expense_request, 'name', None)}, attempting reserve as fallback")
            try:
                reserve_budget_for_request(expense_request, trigger_action=action, next_state=next_state)
            except Exception as e:
                frappe.logger().error(f"handle_expense_request_workflow: Failed to reserve budget during approve: {str(e)}")
                frappe.throw(
                    _("Failed to reserve budget during approval. Please ensure budget is available. Error: {0}").format(str(e)),
                    title=_("Budget Reservation Failed")
                )


def consume_budget_for_purchase_invoice(purchase_invoice, expense_request=None):
    settings = utils.get_settings()
    enforce_mode = (settings.get("enforce_mode") or "Both").lower()
    if not settings.get("enable_budget_lock"):
        frappe.logger().info(f"consume_budget_for_purchase_invoice: Budget lock disabled")
        return

    if enforce_mode not in {"both", "pi submit only"}:
        frappe.logger().info(f"consume_budget_for_purchase_invoice: Enforce mode {enforce_mode} not applicable")
        return

    request = expense_request
    if request is None:
        er_name = getattr(purchase_invoice, "imogi_expense_request", None) or getattr(purchase_invoice, "expense_request", None)
        if not er_name:
            frappe.logger().warning(f"consume_budget_for_purchase_invoice: No expense request linked to PI {getattr(purchase_invoice, 'name', 'Unknown')}")
            return

        try:
            er_doctype = "Advanced Expense Request" if str(er_name).startswith("ERMC-") else "Expense Request"
            request = frappe.get_doc(er_doctype, er_name)
        except Exception as e:
            frappe.logger().error(f"consume_budget_for_purchase_invoice: Failed to load ER {er_name}: {str(e)}")
            request = None

    if not request:
        return

    existing = _get_entries_for_ref("Purchase Invoice", getattr(purchase_invoice, "name", None), "CONSUMPTION")
    if existing:
        frappe.logger().info(f"consume_budget_for_purchase_invoice: Consumption entries already exist for PI {getattr(purchase_invoice, 'name', None)}")
        return

    slices = _build_allocation_slices(request, settings=settings)
    if not slices:
        frappe.logger().warning(f"consume_budget_for_purchase_invoice: No allocation slices for ER {getattr(request, 'name', 'Unknown')}")
        # BUG FIX: Don't update status if no entries created!
        return

    frappe.logger().info(f"consume_budget_for_purchase_invoice: Creating {len(slices)} consumption entries for PI {getattr(purchase_invoice, 'name', None)}")

    # Create consumption entries
    # Note: CONSUMPTION akan mengurangi Reserved (dari RESERVATION yang sudah ada)
    # Tidak perlu RELEASE lagi - CONSUMPTION langsung "consume" dari RESERVATION
    for dims, amount in slices:
        try:
            entry_name = ledger.post_entry(
                "CONSUMPTION",
                dims,
                float(amount or 0),
                "IN",
                ref_doctype="Purchase Invoice",
                ref_name=getattr(purchase_invoice, "name", None),
                remarks=_("Budget consumption on Purchase Invoice submit"),
            )
            frappe.logger().info(f"consume_budget_for_purchase_invoice: Created entry {entry_name} for {dims.cost_center}/{dims.account} amount={amount}")
        except Exception as e:
            frappe.logger().error(f"consume_budget_for_purchase_invoice: Failed to create entry: {str(e)}")
            frappe.log_error(
                title=f"Budget Consumption Failed for PI {getattr(purchase_invoice, 'name', None)}",
                message=f"Error creating consumption entry: {str(e)}\\n\\n{frappe.get_traceback()}"
            )
            # Re-raise to prevent status update
            raise

    if hasattr(request, "db_set"):
        request.db_set("budget_lock_status", "Consumed")
    request.budget_lock_status = "Consumed"
    _set_budget_workflow_state(
        request,
        "Completed",
        reason=_("Budget consumed by Purchase Invoice {0}.").format(getattr(purchase_invoice, "name", None)),
    )
    frappe.logger().info(f"consume_budget_for_purchase_invoice: Updated ER {getattr(request, 'name', None)} status to Consumed/Completed")


def reverse_consumption_for_purchase_invoice(purchase_invoice, expense_request=None):
    settings = utils.get_settings()
    enforce_mode = (settings.get("enforce_mode") or "Both").lower()
    if not settings.get("enable_budget_lock"):
        return

    if enforce_mode not in {"both", "pi submit only"}:
        return

    request = expense_request
    if request is None:
        er_name = getattr(purchase_invoice, "imogi_expense_request", None) or getattr(purchase_invoice, "expense_request", None)
        if er_name:
            try:
                request = frappe.get_doc("Expense Request", er_name)
            except Exception:
                request = None

    # Reverse consumption entries
    # Note: REVERSAL akan menambah Reserved kembali (restore RESERVATION yang sudah di-consume)
    # Tidak perlu re-create RESERVATION - RESERVATION asli masih ada di database
    entries = _get_entries_for_ref("Purchase Invoice", getattr(purchase_invoice, "name", None), "CONSUMPTION")
    if not entries:
        return

    for row in entries:
        dims = utils.Dimensions(
            company=row.get("company"),
            fiscal_year=row.get("fiscal_year"),
            cost_center=row.get("cost_center"),
            account=row.get("account"),
            project=row.get("project"),
            branch=row.get("branch"),
        )
        ledger.post_entry(
            "REVERSAL",
            dims,
            float(row.get("amount") or 0),
            "OUT",
            ref_doctype="Purchase Invoice",
            ref_name=getattr(purchase_invoice, "name", None),
            remarks=_("Reverse consumption on Purchase Invoice cancel"),
        )

    # Update status back to Locked (from Consumed)
    if request:
        if hasattr(request, "db_set"):
            request.db_set("budget_lock_status", "Locked")
        request.budget_lock_status = "Locked"
        _set_budget_workflow_state(
            request,
            "Approved",
            reason=_("Budget consumption reversed from Purchase Invoice {0}.").format(getattr(purchase_invoice, "name", None)),
        )


def maybe_post_internal_charge_je(purchase_invoice, expense_request=None):
    settings = utils.get_settings()
    if settings.get("internal_charge_posting_mode") != "Auto JE on PI Submit":
        return

    request = expense_request
    if request is None:
        er_name = getattr(purchase_invoice, "imogi_expense_request", None) or getattr(purchase_invoice, "expense_request", None)
        if not er_name:
            return

        try:
            request = frappe.get_doc("Expense Request", er_name)
        except Exception:
            return

    if getattr(request, "allocation_mode", "Direct") != "Allocated via Internal Charge":
        return

    ic_doc = _load_internal_charge_request(getattr(request, "internal_charge_request", None))
    if not ic_doc or getattr(ic_doc, "status", None) != "Approved":
        return

    slices = _build_allocation_slices(request, settings=settings, ic_doc=ic_doc)
    if not slices:
        return

    total_amount, account_totals = _get_account_totals(getattr(request, "items", []) or [])
    if not total_amount:
        return

    per_cc_account: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for dims, amount in slices:
        per_cc_account[dims.cost_center][dims.account] += float(amount or 0)

    try:
        je = frappe.new_doc("Journal Entry")
    except Exception:
        return

    je.company = getattr(purchase_invoice, "company", None)
    je.posting_date = getattr(purchase_invoice, "posting_date", None)
    je.user_remark = _(
        "Auto internal charge reclassification for Expense Request {0} via Purchase Invoice {1}."
    ).format(getattr(request, "name", None), getattr(purchase_invoice, "name", None))

    source_cc = getattr(request, "cost_center", None)

    for account, amount in account_totals.items():
        je.append(
            "accounts",
            {
                "account": account,
                "cost_center": source_cc,
                "credit_in_account_currency": float(amount or 0),
                "reference_type": "Purchase Invoice",
                "reference_name": getattr(purchase_invoice, "name", None),
            },
        )

    for cc, accounts in per_cc_account.items():
        if cc == source_cc:
            continue
        for account, amount in accounts.items():
            je.append(
                "accounts",
                {
                    "account": account,
                    "cost_center": cc,
                    "debit_in_account_currency": float(amount or 0),
                    "reference_type": "Purchase Invoice",
                    "reference_name": getattr(purchase_invoice, "name", None),
                },
            )

    if not getattr(je, "accounts", None):
        return

    je.flags.ignore_permissions = True
    try:
        je.insert(ignore_permissions=True)
        if hasattr(je, "submit"):
            je.submit()
    except Exception:
        try:
            frappe.log_error(
                title=_("Internal Charge Journal Entry Failed"),
                message={
                    "expense_request": getattr(request, "name", None),
                    "purchase_invoice": getattr(purchase_invoice, "name", None),
                },
            )
        except Exception:
            pass


@frappe.whitelist()
def reserve_budget_for_request_api(expense_request):
    """Whitelisted API wrapper for reserve_budget_for_request.

    This can be called from browser console or client-side JavaScript.
    """
    return reserve_budget_for_request(expense_request)


@frappe.whitelist()
def create_internal_charge_from_expense_request(er_name: str) -> str:
    settings = utils.get_settings()
    if not settings.get("enable_internal_charge"):
        frappe.throw(_("Internal Charge feature is disabled. Please enable it in Budget Control Settings."))

    request = frappe.get_doc("Expense Request", er_name)
    if getattr(request, "allocation_mode", "Direct") != "Allocated via Internal Charge":
        frappe.throw(_("Allocation mode must be 'Allocated via Internal Charge' to create an Internal Charge Request."))

    if getattr(request, "internal_charge_request", None):
        return request.internal_charge_request

    items = getattr(request, "items", []) or []
    total, expense_accounts = accounting.summarize_request_items(items)

    # Resolve company - try from cost center first, then from request, then default
    company = utils.resolve_company_from_cost_center(getattr(request, "cost_center", None))
    if not company:
        company = getattr(request, "company", None) or frappe.defaults.get_user_default("Company")
    if not company:
        frappe.throw(_("Cannot determine Company. Please set company on Expense Request or Cost Center."))

    # Resolve fiscal year
    fiscal_year = utils.resolve_fiscal_year(getattr(request, "fiscal_year", None), company=company)
    if not fiscal_year:
        fiscal_year = frappe.defaults.get_user_default("fiscal_year") or frappe.db.get_value(
            "Fiscal Year", {"disabled": 0}, "name", order_by="year_start_date desc"
        )
    if not fiscal_year:
        frappe.throw(_("Cannot determine Fiscal Year. Please set fiscal_year on Expense Request."))

    ic = frappe.new_doc("Internal Charge Request")
    ic.expense_request = request.name
    ic.company = company
    ic.fiscal_year = fiscal_year
    ic.posting_date = getattr(request, "request_date", None) or frappe.utils.nowdate()
    ic.source_cost_center = getattr(request, "cost_center", None)
    ic.total_amount = total
    ic.allocation_mode = "Allocated via Internal Charge"

    # Populate internal_charge_lines from ER items
    # Use target_cost_center from item if specified, otherwise default to source
    source_cc = getattr(request, "cost_center", None)

    for idx, item in enumerate(items):
        expense_account = getattr(item, "expense_account", None)
        amount = float(getattr(item, "amount", 0) or 0)

        # Get explicit target (not default)
        explicit_target = getattr(item, "target_cost_center", None)
        target_cc = explicit_target or source_cc

        # Validate: only throw error if user EXPLICITLY set target = source
        # If target is empty (None), it will default to source without error
        if explicit_target and source_cc and explicit_target == source_cc:
            frappe.throw(
                _("Row {0}: Target Cost Center ({1}) cannot be the same as Source Cost Center ({2}). "
                  "Internal Charge is meant to allocate expenses to different cost centers.").format(
                    idx + 1, explicit_target, source_cc
                ),
                title=_("Unable to Generate Internal Charge")
            )

        if expense_account and amount > 0:
            ic.append("internal_charge_lines", {
                "target_cost_center": target_cc,
                "expense_account": expense_account,
                "description": getattr(item, "description", None),
                "amount": amount,
            })

    ic.insert(ignore_permissions=True)

    if hasattr(request, "db_set"):
        request.db_set("internal_charge_request", ic.name)
    request.internal_charge_request = ic.name

    return ic.name
