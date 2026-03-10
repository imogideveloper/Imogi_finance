from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import frappe
from frappe import _
from frappe.utils import flt


def _safe_throw(message: str):
    marker = getattr(frappe, "ThrowMarker", None)
    throw_fn = getattr(frappe, "throw", None)

    if callable(throw_fn):
        try:
            throw_fn(message)
            return
        except BaseException as exc:  # noqa: BLE001
            if (
                marker
                and isinstance(marker, type)
                and issubclass(marker, BaseException)
                and not isinstance(exc, marker)
            ):
                Combined = type("CombinedThrowMarker", (exc.__class__, marker), {})  # noqa: N806
                raise Combined(str(exc))
            raise

    if marker:
        raise marker(message)
    raise Exception(message)


class FinanceValidator:
    """Shared finance validations for amounts and tax fields."""

    @staticmethod
    def ensure_items(items: Iterable[Any]):
        if not items:
            _safe_throw(_("Please add at least one item."))

    @staticmethod
    def validate_amounts(items: Iterable[Any]) -> tuple[float, tuple[str, ...]]:
        total = 0.0
        accounts: list[str] = []
        for item in items or []:
            # Skip variance items from expense total calculation
            # Variance items are system-generated adjustments that should not affect
            # the expense base used for PPN/PPh/budget calculations
            if getattr(item, "is_variance_item", 0):
                continue

            # Use net_amount if available (amount after discount), otherwise use amount
            net_amount = flt(getattr(item, "net_amount", None))
            if net_amount:
                # net_amount is already calculated as (amount - discount_amount)
                amount = net_amount
            else:
                # Fallback to regular amount calculation
                qty = flt(getattr(item, "qty", 0)) or 0
                rate = flt(getattr(item, "rate", 0)) or flt(getattr(item, "amount", 0))
                amount = flt(getattr(item, "amount", qty * rate))

            total += amount
            account = getattr(item, "expense_account", None)
            if account:
                accounts.append(account)
        accounts_tuple = tuple(sorted({acc for acc in accounts if acc}))
        return total, accounts_tuple

    @staticmethod
    def validate_tax_fields(doc):
        items = getattr(doc, "items", None) or []
        errors = []

        # ============================================================================
        # Validate PPN Configuration
        # ============================================================================
        is_ppn_applicable = getattr(doc, "is_ppn_applicable", 0)
        if is_ppn_applicable and not getattr(doc, "ppn_template", None):
            errors.append(_("PPN is applicable but PPN Template is not selected. Please select a PPN Template in Tab Tax."))

        # ============================================================================
        # Validate PPh Configuration
        # ============================================================================
        item_pph_applicable = [item for item in items if getattr(item, "is_pph_applicable", 0)]
        header_pph_applicable = getattr(doc, "is_pph_applicable", 0)

        # PPh Type required if EITHER header checkbox OR any item has Apply WHT
        if item_pph_applicable or header_pph_applicable:
            pph_type = getattr(doc, "pph_type", None)
            if not pph_type:
                if item_pph_applicable and not header_pph_applicable:
                    # Item-level PPh without header checkbox
                    errors.append(
                        _("Found {0} item(s) with 'Apply WHT' checked but PPh Type is not selected. Please select PPh Type in Tab Tax.").format(
                            len(item_pph_applicable)
                        )
                    )
                else:
                    # Header-level PPh
                    errors.append(_("PPh is applicable but PPh Type is not selected. Please select a PPh Type in Tab Tax."))

            # Validate header-level PPh Base Amount
            if header_pph_applicable and not item_pph_applicable:
                base_amount = getattr(doc, "pph_base_amount", None)
                if not base_amount or base_amount <= 0:
                    errors.append(_("PPh is applicable at header level but PPh Base Amount is not entered. Please enter PPh Base Amount in Tab Tax."))

            # Validate item-level PPh Base Amount
            for item in item_pph_applicable:
                base_amount = getattr(item, "pph_base_amount", None)
                if not base_amount or base_amount <= 0:
                    item_desc = (
                        getattr(item, "description", None)
                        or getattr(item, "expense_account", None)
                        or f"Row {getattr(item, 'idx', '?')}"
                    )
                    errors.append(
                        _("PPh is applicable for {0} but PPh Base Amount is not entered. Please enter PPh Base Amount.").format(
                            item_desc
                        )
                    )

        # ============================================================================
        # Show All Errors at Once (Better UX)
        # ============================================================================
        if errors:
            # Separate PPN and PPh errors for clarity
            ppn_errors = [e for e in errors if "PPN" in str(e) or "ppn" in str(e).lower()]
            pph_errors = [e for e in errors if "PPh" in str(e) or "pph" in str(e).lower()]

            error_msg = []
            if ppn_errors:
                error_msg.append("<b>PPN Configuration Issues:</b>")
                error_msg.extend([f"• {e}" for e in ppn_errors])

            if pph_errors:
                if ppn_errors:
                    error_msg.append("<br>")
                error_msg.append("<b>PPh Configuration Issues:</b>")
                error_msg.extend([f"• {e}" for e in pph_errors])

            _safe_throw("<br>".join(error_msg))


def validate_document_tax_fields(doc, method=None):
    """DocEvent wrapper to enforce PPN/PPh requirements on tax-bearing documents.

    IMPORTANT: This validator is designed for Expense Request which has fields:
    - is_ppn_applicable, ppn_template
    - is_pph_applicable, pph_type, pph_base_amount

    Purchase Invoice uses different fields (imogi_pph_type, tax_withholding_category)
    and handles tax configuration differently via accounting.py, so we skip validation.
    """
    # Skip validation for Purchase Invoice - it uses different field structure
    # Tax fields on PI are handled by accounting.py create_purchase_invoice_from_request()
    if doc.doctype == "Purchase Invoice":
        return

    FinanceValidator.validate_tax_fields(doc)
