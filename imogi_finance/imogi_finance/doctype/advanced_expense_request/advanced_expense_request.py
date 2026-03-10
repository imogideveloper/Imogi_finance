"""Advanced Expense Request - copy of Expense Request with cost_center per line item.

Approval route is resolved from `approval_cost_center` (header field, same logic as
Expense Request uses `cost_center`).  Budget control operates per line item: each row
is reserved/released against its own `cost_center`.
"""
from __future__ import annotations

import json
from datetime import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from imogi_finance import accounting, roles
from imogi_finance.branching import apply_branch, resolve_branch
from imogi_finance.approval import get_active_setting_meta, approval_setting_required_message
from imogi_finance.budget_control.workflow import handle_expense_request_workflow, release_budget_for_request
from imogi_finance.services.approval_route_service import ApprovalRouteService
from imogi_finance.services.approval_service import ApprovalService
from imogi_finance.services.deferred_expense import generate_amortization_schedule
from imogi_finance.settings.utils import get_gl_account
from ..expense_deferred_settings.expense_deferred_settings import get_deferrable_account_map
from imogi_finance.tax_invoice_ocr import sync_tax_invoice_upload, validate_tax_invoice_upload_link
from imogi_finance.tax_invoice_fields import get_upload_link_field
from imogi_finance.validators.finance_validator import FinanceValidator


def _resolve_pph_rate(pph_type: str | None) -> float:
    if not pph_type:
        return 0

    get_doc = getattr(frappe, "get_doc", None)
    if not callable(get_doc):
        return 0

    try:
        category = get_doc("Tax Withholding Category", pph_type)
    except Exception:
        return 0

    for field in ("tax_withholding_rate", "rate", "withholding_rate"):
        value = getattr(category, field, None)
        if value:
            return flt(value)

    withholding_rows = None
    for field in ("withholding_tax", "tax_withholding_rates", "rates", "tax_withholding_rate"):
        rows = getattr(category, field, None)
        if rows:
            withholding_rows = rows
            break
    if withholding_rows is None:
        withholding_rows = []
    today = now_datetime().date()
    fallback_rate = 0.0

    for row in withholding_rows:
        row_rate = None
        for field in ("tax_withholding_rate", "rate", "withholding_rate", "tax_rate"):
            value = getattr(row, field, None)
            if value:
                row_rate = flt(value)
                break

        if row_rate:
            from_date = getattr(row, "from_date", None)
            to_date = getattr(row, "to_date", None)
            if (from_date or to_date) and (
                (not from_date or from_date <= today) and (not to_date or to_date >= today)
            ):
                return row_rate
            if not fallback_rate:
                fallback_rate = row_rate
                continue

        withholding_name = getattr(row, "withholding_tax", None)
        if withholding_name:
            rate = getattr(frappe.db, "get_value", lambda *_args, **_kwargs: None)(
                "Withholding Tax",
                withholding_name,
                "rate",
            )
            if rate:
                return flt(rate)

    if fallback_rate:
        return fallback_rate

    return 0


@frappe.whitelist()
def get_pph_rate(pph_type: str | None = None) -> dict:
    return {"rate": _resolve_pph_rate(pph_type)}


def get_approval_route(cost_center: str, accounts, amount: float, *, setting_meta=None):
    """Wrapper for ApprovalRouteService.get_route."""
    return ApprovalRouteService.get_route(cost_center, accounts, amount, setting_meta=setting_meta)


class AdvancedExpenseRequest(Document):
    """Advanced Expense Request.

    Identical flow to Expense Request, with the single change that each line
    item carries its own `cost_center` for per-item budget allocation.
    The header field `approval_cost_center` replaces the role previously played
    by `cost_center` in ER for approval route resolution and branch derivation.
    """

    def before_validate(self):
        self.validate_amounts()

    def before_insert(self):
        self._set_requester_to_creator()
        self._reset_status_if_copied()

    def after_insert(self):
        pass

    def validate(self):
        """All business rule validation."""
        self._set_requester_to_creator()
        self._initialize_status()
        self._auto_set_approval_cost_center()
        self.validate_amounts()
        self.validate_items_have_cost_center()
        self.apply_branch_defaults()
        self._sync_tax_invoice_upload()
        self.validate_tax_fields()
        self.validate_deferred_expense()
        validate_tax_invoice_upload_link(self, "Advanced Expense Request")
        self._ensure_final_state_immutability()

    def before_submit(self):
        """Prepare for submission - resolve approval route and initialize state."""
        self.validate_submit_permission()
        self.validate_tax_invoice_ocr_before_submit()

        route, setting_meta, failed = self._resolve_approval_route()
        self._ensure_route_ready(route, failed)
        self.apply_route(route, setting_meta=setting_meta)
        self.record_approval_route_snapshot(route)
        self.validate_route_users_exist(route)
        approval_service = ApprovalService(self.doctype, state_field="workflow_state")
        approval_service.before_submit(self, route=route, skip_approval=not self._has_approver(route))

    def on_submit(self):
        """Post-submit: sync budget (if enabled) and record in activity."""
        try:
            handle_expense_request_workflow(self, "Submit", getattr(self, "workflow_state"))
        except frappe.ValidationError:
            raise
        except frappe.DoesNotExistError as de:
            frappe.throw(
                _("Required document not found during budget control. Please check your setup. Error: {0}").format(str(de)),
                title=_("Document Not Found")
            )
        except Exception as e:
            error_msg = str(e)
            frappe.throw(
                _("Budget control operation failed during submission.<br><br>Error: {0}<br><br>Please contact administrator if the problem persists.").format(error_msg),
                title=_("Budget Control Error")
            )

    def before_workflow_action(self, action, **kwargs):
        """Gate workflow actions using ApprovalService + route validation."""
        if action == "Reopen" and getattr(self, "workflow_state", None) != "Rejected":
            frappe.throw(_("Reopen is only allowed for rejected Expense Requests."))
        approval_service = ApprovalService(self.doctype, state_field="workflow_state")
        route = self._get_route_snapshot()
        approval_service.before_workflow_action(self, action, next_state=kwargs.get("next_state"), route=route)

    def on_workflow_action(self, action, **kwargs):
        """Handle state transitions via ApprovalService."""
        approval_service = ApprovalService(self.doctype, state_field="workflow_state")
        next_state = kwargs.get("next_state")
        approval_service.on_workflow_action(self, action, next_state=next_state)

        if action in ("Approve", "Reject", "Reopen"):
            try:
                handle_expense_request_workflow(self, action, next_state)
            except frappe.ValidationError:
                raise
            except Exception as e:
                frappe.throw(
                    _("Budget control operation failed. Workflow action cannot be completed. Error: {0}").format(str(e)),
                    title=_("Budget Control Error")
                )

    def on_update_after_submit(self):
        """Post-save: guard status changes to prevent bypass."""
        approval_service = ApprovalService(self.doctype, state_field="workflow_state")
        approval_service.guard_status_changes(self)

    def before_cancel(self):
        """Validate permissions and linked documents before cancel."""
        allowed_roles = {roles.SYSTEM_MANAGER, roles.EXPENSE_APPROVER}
        current_roles = set(frappe.get_roles())
        if not (current_roles & allowed_roles):
            frappe.throw(_("Only System Manager or Expense Approver can cancel."), title=_("Not Allowed"))

        linked_pi = frappe.db.get_value(
            "Purchase Invoice",
            {"imogi_expense_request": self.name, "docstatus": 1},
            "name"
        )

        linked_pe = frappe.db.get_value(
            "Payment Entry",
            {"imogi_expense_request": self.name, "docstatus": 1},
            "name"
        )

        if linked_pi or linked_pe:
            docs = []
            if linked_pe:
                docs.append(f"Payment Entry {linked_pe}")
            if linked_pi:
                docs.append(f"Purchase Invoice {linked_pi}")

            frappe.throw(
                _("Cannot cancel Advanced Expense Request - linked documents exist: {0}.<br><br>"
                  "Please either:<br>"
                  "1. Cancel linked documents first in reverse order (PE → PI → ER), or<br>"
                  "2. Use 'Cancel All Linked Documents' from the menu to cancel everything at once."
                ).format(", ".join(docs)),
                title=_("Linked Documents Exist")
            )

        if not hasattr(frappe.local, "cancelling_expense_requests"):
            frappe.local.cancelling_expense_requests = set()
        frappe.local.cancelling_expense_requests.add(self.name)

    def on_cancel(self):
        """Clean up: release budget reservations."""
        try:
            release_budget_for_request(self, reason="Cancel")
        except Exception as e:
            frappe.throw(
                _("Failed to release budget. Cancel operation cannot proceed. Error: {0}").format(str(e)),
                title=_("Budget Release Error")
            )

    def on_trash(self):
        """Clean up OCR links and monitoring records before deletion."""
        upload_field = get_upload_link_field("Advanced Expense Request")
        if upload_field and getattr(self, upload_field, None):
            frappe.db.set_value(self.doctype, self.name, upload_field, None)

        if frappe.db.table_exists("Tax Invoice OCR Monitoring"):
            monitoring_records = frappe.get_all(
                "Tax Invoice OCR Monitoring",
                filters={"target_doctype": self.doctype, "target_name": self.name},
                pluck="name",
            )
            for record in monitoring_records:
                frappe.delete_doc("Tax Invoice OCR Monitoring", record, ignore_permissions=True, force=True)

    # ===================== Business Logic =====================

    def validate_items_have_cost_center(self):
        """Ensure every non-variance line item has a cost_center set."""
        for idx, item in enumerate(self.get("items") or [], start=1):
            if getattr(item, "is_variance_item", 0):
                continue
            if not getattr(item, "cost_center", None):
                frappe.throw(
                    _("Row {0}: Cost Center is required on each line item.").format(idx),
                    title=_("Missing Cost Center")
                )

    def validate_amounts(self):
        """Sum item amounts and set total."""
        total, expense_accounts = FinanceValidator.validate_amounts(self.get("items"))
        self.amount = total
        self.expense_accounts = expense_accounts
        self.expense_account = expense_accounts[0] if len(expense_accounts) == 1 else None
        self._set_totals()

    def _set_totals(self):
        """Calculate and set all total fields + manage PPN variance row idempotently."""
        items = self.get("items") or []
        total_expense = flt(getattr(self, "amount", 0) or 0)

        total_ppn = 0
        ppn_rate = 0
        if getattr(self, "is_ppn_applicable", 0):
            ppn_template = getattr(self, "ppn_template", None)
            if not ppn_template:
                frappe.throw("PPN Template wajib dipilih (Tab Tax) karena Apply PPN aktif.")
            ppn_rate = self._get_ppn_rate()
            total_ppn = total_expense * ppn_rate / 100

        ocr_ppn = flt(getattr(self, "ti_fp_ppn", 0) or 0)
        expected_ppn = total_ppn
        variance_raw = ocr_ppn - expected_ppn
        variance = round(variance_raw, 2)

        variance_account = None
        if variance != 0:
            company = self._get_company()
            if company:
                try:
                    from imogi_finance.settings.utils import get_gl_account
                    from imogi_finance.settings.gl_purposes import PPN_VARIANCE
                    variance_account = get_gl_account(PPN_VARIANCE, company=company, required=True)
                except frappe.DoesNotExistError:
                    frappe.throw("GL Account Mapping untuk purpose 'PPN_VARIANCE' belum ada. Tambahkan di GL Purposes/Mapping.")
                except Exception as e:
                    frappe.throw(str(e))

        ppn_var_rows = [
            r for r in items
            if (getattr(r, "description", None) == "PPN Variance" or
                (getattr(r, "is_variance_item", 0) and getattr(r, "expense_account", None) == variance_account))
        ]

        if abs(variance) < 0.01:
            if ppn_var_rows:
                for row in ppn_var_rows:
                    self.remove(row)
        elif len(ppn_var_rows) == 0:
            if variance_account:
                self.append("items", {
                    "expense_account": variance_account,
                    "description": "PPN Variance",
                    "amount": variance,
                    "is_variance_item": 1,
                    "is_pph_applicable": 0,
                    "is_deferred_expense": 0,
                })
        elif len(ppn_var_rows) == 1:
            row = ppn_var_rows[0]
            row.amount = variance
            row.description = "PPN Variance"
        else:
            first_row = ppn_var_rows[0]
            first_row.amount = variance
            first_row.description = "PPN Variance"
            for duplicate in ppn_var_rows[1:]:
                self.remove(duplicate)

        self.ti_ppn_variance = variance_raw

        variance_total = sum(
            flt(getattr(item, "amount", 0) or 0)
            for item in self.get("items") or []
            if getattr(item, "is_variance_item", 0)
        )

        total_ppnbm = flt(getattr(self, "ti_fp_ppnbm", None) or getattr(self, "ppnbm", None) or 0)
        item_pph_total = sum(
            flt(getattr(item, "pph_base_amount", 0) or 0)
            for item in items
            if getattr(item, "is_pph_applicable", 0) and not getattr(item, "is_variance_item", 0)
        )
        pph_base_total = item_pph_total or (
            flt(getattr(self, "pph_base_amount", 0) or 0) if getattr(self, "is_pph_applicable", 0) else 0
        )
        pph_rate = _resolve_pph_rate(getattr(self, "pph_type", None))
        total_pph = (pph_base_total * pph_rate / 100) if pph_rate else pph_base_total
        total_pph = abs(total_pph)
        total_amount = total_expense + total_ppn + total_ppnbm - total_pph + variance_total

        if getattr(self, "is_pph_applicable", 0) or item_pph_total:
            self.pph_base_amount = pph_base_total
        else:
            self.pph_base_amount = 0

        self.total_expense = total_expense
        self.total_ppn = total_ppn
        self.total_ppnbm = total_ppnbm
        self.total_pph = total_pph
        self.total_amount = total_amount

    def apply_branch_defaults(self):
        """Auto-set branch fields based on approval_cost_center."""
        try:
            branch = resolve_branch(
                company=self._get_company(),
                cost_center=getattr(self, "approval_cost_center", None),
                explicit_branch=getattr(self, "branch", None),
            )
            if branch:
                apply_branch(self, branch)
        except Exception:
            pass

    def _get_ppn_rate(self):
        """Get PPN rate from template or infer from date."""
        ppn_rate = 0
        ppn_template = getattr(self, "ppn_template", None)

        if ppn_template:
            try:
                template = frappe.get_cached_doc("Purchase Taxes and Charges Template", ppn_template)
                for tax in template.get("taxes", []):
                    if tax.rate:
                        ppn_rate = flt(tax.rate)
                        break
            except Exception:
                pass

        if not ppn_rate:
            try:
                from imogi_finance.tax_invoice_ocr import infer_tax_rate
                fp_date = getattr(self, "ti_fp_date", None) or getattr(self, "request_date", None)
                ppn_rate = infer_tax_rate(dpp=flt(self.amount), ppn=None, fp_date=fp_date) * 100
            except Exception:
                pass

        return ppn_rate

    def validate_tax_fields(self):
        """Validate tax configuration."""
        FinanceValidator.validate_tax_fields(self)

    def validate_tax_invoice_ocr_before_submit(self):
        """Validate NPWP before submit."""
        try:
            from imogi_finance.tax_invoice_ocr import get_settings, normalize_npwp
        except ImportError:
            return

        settings = get_settings()
        if not settings.get("enable_tax_invoice_ocr"):
            return

        if not getattr(self, "ti_tax_invoice_upload", None):
            return

        supplier_npwp = getattr(self, "supplier_tax_id", None)
        if supplier_npwp:
            supplier_npwp_normalized = normalize_npwp(supplier_npwp)
            ocr_npwp = normalize_npwp(getattr(self, "ti_fp_npwp", None))

            if ocr_npwp and supplier_npwp_normalized and ocr_npwp != supplier_npwp_normalized:
                frappe.throw(
                    _("NPWP dari OCR ({0}) tidak sesuai dengan NPWP Supplier ({1})").format(
                        getattr(self, "ti_fp_npwp", ""), supplier_npwp
                    ),
                    title=_("NPWP Tidak Cocok")
                )
            elif ocr_npwp and supplier_npwp_normalized:
                self.ti_npwp_match = 1

    def validate_deferred_expense(self):
        """Validate deferred expense configuration."""
        settings, deferrable_accounts = get_deferrable_account_map()
        if not getattr(settings, "enable_deferred_expense", 1):
            if any(getattr(item, "is_deferred_expense", 0) for item in self.get("items", [])):
                frappe.throw(_("Deferred Expense is disabled in settings."))
            return

        for item in self.get("items", []):
            if not getattr(item, "is_deferred_expense", 0):
                continue

            if not getattr(item, "prepaid_account", None):
                frappe.throw(_("Prepaid Account is required for deferred expense items."))

            account = frappe.db.get_value(
                "Account",
                item.prepaid_account,
                ["account_type", "is_group", "company"],
                as_dict=True,
            )
            if not account:
                frappe.throw(_("Prepaid Account {0} does not exist.").format(item.prepaid_account))
            if account.is_group:
                frappe.throw(_("Prepaid Account {0} cannot be a group account.").format(item.prepaid_account))
            if account.account_type != "Current Asset":
                frappe.throw(
                    _("Prepaid Account {0} must have Account Type Current Asset.").format(
                        item.prepaid_account
                    )
                )
            company = self._get_company()
            if company and account.company and account.company != company:
                frappe.throw(
                    _("Prepaid Account {0} must belong to company {1}.").format(
                        item.prepaid_account, company
                    )
                )

            if not getattr(item, "deferred_start_date", None):
                frappe.throw(_("Deferred Start Date required for deferred expense items."))

            periods = getattr(item, "deferred_periods", None)
            if not periods or periods <= 0:
                frappe.throw(_("Deferred Periods must be > 0 for deferred expense items."))

            schedule = generate_amortization_schedule(
                flt(item.amount), periods, item.deferred_start_date
            )
            if not hasattr(item, "flags"):
                item.flags = type("Flags", (), {})()
            item.flags.deferred_amortization_schedule = schedule

    def _sync_tax_invoice_upload(self):
        """Sync tax invoice OCR data if configured."""
        if getattr(self, "ti_tax_invoice_upload", None):
            sync_tax_invoice_upload(self, "Advanced Expense Request", save=False)

    def _ensure_final_state_immutability(self):
        """Prevent key field edits after approval."""
        if getattr(self, "docstatus", 0) != 1:
            return

        if self.status not in ("Approved", "PI Created", "Paid"):
            return

        previous = self._get_previous_doc()
        if not previous:
            return

        key_fields = ("request_type", "supplier", "amount", "approval_cost_center", "branch", "project")
        changed = [f for f in key_fields if self._get_value(previous, f) != getattr(self, f, None)]

        if changed:
            frappe.throw(_("Cannot modify after approval: {0}").format(", ".join(changed)))

    # ===================== Approval Helpers =====================

    def _initialize_status(self):
        """Set initial status from workflow_state or default."""
        if getattr(self, "status", None):
            return
        state = getattr(self, "workflow_state", None)
        self.status = state or "Draft"
        if self.status == "Pending Review":
            self.current_approval_level = getattr(self, "current_approval_level", None) or 1
        else:
            self.current_approval_level = 0

    def _set_requester_to_creator(self):
        """Set requester to current user if not set."""
        if not getattr(self, "requester", None):
            session_user = getattr(frappe, "session", None)
            self.requester = getattr(session_user, "user", None) or "Administrator"

    def _reset_status_if_copied(self):
        """Clear status when copying from submitted doc."""
        if getattr(self, "docstatus", 0) == 0 and getattr(self, "status", None) in ("Rejected", "Approved"):
            self.status = None
            self.workflow_state = None
            self.current_approval_level = 0
            self.approved_on = None
            self.rejected_on = None
            self.approval_route_snapshot = None
            self.level_1_user = None
            self.level_2_user = None
            self.level_3_user = None

    def validate_submit_permission(self):
        """Only creator or Expense Approver/System Manager can submit."""
        allowed_roles = {roles.SYSTEM_MANAGER, roles.EXPENSE_APPROVER}
        current_roles = set(frappe.get_roles())

        if frappe.session.user == self.owner:
            return

        if current_roles & allowed_roles:
            return

        frappe.throw(_("Only the creator or an Expense Approver/System Manager can submit."))

    def _resolve_approval_route(self) -> tuple[dict, dict | None, bool]:
        """Get approval route using approval_cost_center."""
        try:
            # Ensure approval_cost_center is populated before resolving
            if not self.approval_cost_center:
                self._auto_set_approval_cost_center()
            setting = get_active_setting_meta(self.approval_cost_center)
            route = get_approval_route(
                self.approval_cost_center,
                self._get_expense_accounts(),
                self.amount,
                setting_meta=setting,
            )
            return route or {}, setting, False
        except Exception:
            return {}, None, True

    def _auto_set_approval_cost_center(self) -> None:
        """Auto-populate approval_cost_center from the default Expense Approval Setting.

        Looks for an active EAS with is_default_for_multi_cc=1. If found, sets
        self.approval_cost_center to its cost_center value.
        """
        if self.approval_cost_center:
            return
        result = frappe.db.get_value(
            "Expense Approval Setting",
            {"is_default_for_multi_cc": 1, "is_active": 1},
            "cost_center",
        )
        if result:
            self.approval_cost_center = result

    def _ensure_route_ready(self, route: dict, failed: bool = False) -> None:
        """Validate route is ready; require at least one configured approver."""
        if failed or not self._has_approver(route):
            message = approval_setting_required_message(getattr(self, "approval_cost_center", None))
            frappe.throw(message, title=_("Approval Route Not Found"))

    def apply_route(self, route: dict, *, setting_meta: dict | None = None) -> None:
        """Store approval route on document."""
        self.level_1_user = route.get("level_1", {}).get("user")
        self.level_2_user = route.get("level_2", {}).get("user")
        self.level_3_user = route.get("level_3", {}).get("user")
        ApprovalRouteService.record_setting_meta(self, setting_meta)

    def record_approval_route_snapshot(self, route: dict | None = None) -> None:
        """Save route for audit."""
        route = route or self._get_route_snapshot()
        try:
            self.approval_route_snapshot = json.dumps(route) if isinstance(route, dict) else route
        except Exception:
            pass

    def validate_route_users_exist(self, route: dict | None = None) -> None:
        """Ensure all route users exist and are enabled."""
        from imogi_finance.approval import validate_route_users

        route = route or self._get_route_snapshot()
        if not route:
            return

        validation = validate_route_users(route)
        if validation.get("valid"):
            return

        error_parts: list[str] = []

        invalid_users = validation.get("invalid_users") or []
        if invalid_users:
            user_list = ", ".join(
                _("Level {level}: {user}").format(level=u.get("level"), user=u.get("user"))
                for u in invalid_users
            )
            error_parts.append(_("Users not found: {0}").format(user_list))

        disabled_users = validation.get("disabled_users") or []
        if disabled_users:
            user_list = ", ".join(
                _("Level {level}: {user}").format(level=u.get("level"), user=u.get("user"))
                for u in disabled_users
            )
            error_parts.append(_("Users disabled: {0}").format(user_list))

        if error_parts:
            frappe.throw(
                _("Invalid approvers: {0}. Update Expense Approval Setting.").format("; ".join(error_parts))
            )

    def _get_route_snapshot(self) -> dict:
        """Get stored approval route."""
        from imogi_finance.approval import parse_route_snapshot

        snapshot = getattr(self, "approval_route_snapshot", None)
        parsed = parse_route_snapshot(snapshot)
        if parsed:
            return parsed

        return {f"level_{l}": {"user": getattr(self, f"level_{l}_user", None)} for l in (1, 2, 3)}

    def _has_approver(self, route: dict | None) -> bool:
        """Check if route has at least one approver."""
        from imogi_finance.approval import has_approver_in_route
        return has_approver_in_route(route)

    # ===================== Utility =====================

    def _get_company(self) -> str | None:
        """Derive company from the doc's company field or approval_cost_center."""
        # First try direct company field on the doc
        company = getattr(self, "company", None)
        if company:
            return company
        # Fallback: derive from approval_cost_center
        approval_cc = getattr(self, "approval_cost_center", None)
        if approval_cc:
            return frappe.db.get_value("Cost Center", approval_cc, "company")
        return None

    def _get_expense_accounts(self) -> tuple[str, ...]:
        """Get expense accounts from items."""
        accounts = getattr(self, "expense_accounts", None)
        if accounts:
            return accounts

        _, accounts = accounting.summarize_request_items(self.get("items"))
        return accounts

    @staticmethod
    def _get_value(source, field):
        if hasattr(source, "get"):
            return source.get(field)
        return getattr(source, field, None)

    def _get_previous_doc(self):
        previous = getattr(self, "_doc_before_save", None)
        if not previous and hasattr(self, "get_doc_before_save"):
            try:
                previous = self.get_doc_before_save()
            except Exception:
                pass
        return previous

@frappe.whitelist()
def apply_expense_action(docname: str, action: str) -> dict:
    """Apply Approve or Reject directly without depending on Frappe workflow engine.

    This bypasses frappe.model.workflow.apply_workflow which requires the Workflow
    document to be configured in the database (only synced on bench migrate).
    """
    if action not in ("Approve", "Reject"):
        frappe.throw(_("Invalid action: {0}").format(action), title=_("Invalid Action"))

    doc = frappe.get_doc("Advanced Expense Request", docname)

    if doc.docstatus != 1:
        frappe.throw(_("Only submitted documents can be approved or rejected."))

    if doc.workflow_state != "Pending Review" and doc.status != "Pending Review":
        frappe.throw(
            _("This document is not in Pending Review state. Current state: {0}").format(
                doc.workflow_state or doc.status
            )
        )

    # Permission check: must be a designated approver, System Manager, or Expense Approver
    current_user = frappe.session.user
    approvers = [doc.level_1_user, doc.level_2_user, doc.level_3_user]
    approvers = [u for u in approvers if u]
    current_roles = set(frappe.get_roles())
    has_role = bool(current_roles & {"System Manager", "Expense Approver"})

    if not has_role and approvers and current_user not in approvers:
        frappe.throw(_("You are not authorized to {0} this request.").format(action), title=_("Not Authorized"))

    next_state = "Approved" if action == "Approve" else "Rejected"

    # Run before_workflow_action hook (validates approver, level, etc.)
    try:
        doc.before_workflow_action(action, next_state=next_state)
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.throw(str(e))

    # Update state fields
    doc.db_set("workflow_state", next_state, update_modified=True)
    doc.db_set("status", next_state, update_modified=True)
    doc.workflow_state = next_state
    doc.status = next_state

    # Run on_workflow_action hook (records timestamps, budget ops, etc.)
    try:
        doc.on_workflow_action(action, next_state=next_state)
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"on_workflow_action error: {docname}")
        frappe.throw(str(e))

    frappe.db.commit()

    return {"status": next_state, "action": action, "docname": docname}
