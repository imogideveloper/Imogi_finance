from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, Optional

import frappe
from frappe import _

# Import helpers for centralized settings access
from imogi_finance.settings.utils import (
    get_finance_control_settings,
    get_gl_account,
)
from imogi_finance.settings.gl_purposes import (
    DIGITAL_STAMP_EXPENSE,
    DIGITAL_STAMP_PAYMENT,
)
from imogi_finance.settings.branch_defaults import BRANCH_SETTING_DEFAULTS


def get_receipt_control_settings():
    """Fetch Finance Control Settings with sane defaults.
    
    Uses centralized helper to get settings, with fallback defaults
    for fields that may not exist on legacy systems.
    """
    defaults = frappe._dict(
        {
            "enable_customer_receipt": 0,
            "receipt_mode": "OFF",
            "allow_mixed_payment": 0,
            "default_receipt_design": None,
            "enable_digital_stamp": 0,
            "digital_stamp_policy": "Optional",
            "digital_stamp_threshold_amount": 0,
            "materai_minimum_amount": 10000000,
            "allow_physical_stamp_fallback": 0,
            "digital_stamp_provider": None,
            "provider_mode": None,
            "digital_stamp_cost": 10000,
        }
    )
    defaults.update(BRANCH_SETTING_DEFAULTS)

    if not frappe.db.exists("DocType", "Finance Control Settings"):
        return defaults

    try:
        settings = get_finance_control_settings()
    except Exception:
        # Avoid breaking desk if single is missing in early migrations
        return defaults

    for key in defaults.keys():
        defaults[key] = getattr(settings, key, defaults[key])

    return defaults


def get_digital_stamp_accounts(company: str | None = None) -> tuple[str, str]:
    """Get digital stamp GL accounts (expense and payment) from GL Account Mappings.
    
    Retrieves the configured GL accounts for digital stamp posting.
    Must be called only when digital_stamp is enabled.
    
    Args:
        company: Company code for multi-company support (optional)
        
    Returns:
        Tuple of (expense_account, payment_account)
        
    Raises:
        frappe.ValidationError: If mappings are not configured
    """
    expense_account = get_gl_account(DIGITAL_STAMP_EXPENSE, company=company, required=True)
    payment_account = get_gl_account(DIGITAL_STAMP_PAYMENT, company=company, required=True)
    return expense_account, payment_account


def terbilang_id(amount: float | int | Decimal, suffix: str = "rupiah") -> str:
    """Convert numbers into Indonesian words.

    This is intentionally lightweight to avoid additional dependencies while
    remaining suitable for printing on receipts.
    """

    units = [
        "",
        "satu",
        "dua",
        "tiga",
        "empat",
        "lima",
        "enam",
        "tujuh",
        "delapan",
        "sembilan",
    ]

    def _spell_below_thousand(value: int) -> str:
        hundreds, rem = divmod(value, 100)
        tens, ones = divmod(rem, 10)
        words = []
        if hundreds:
            if hundreds == 1:
                words.append("seratus")
            else:
                words.append(f"{units[hundreds]} ratus")
        if tens > 1:
            words.append(f"{units[tens]} puluh")
            if ones:
                words.append(units[ones])
        elif tens == 1:
            if ones == 0:
                words.append("sepuluh")
            elif ones == 1:
                words.append("sebelas")
            else:
                words.append(f"{units[ones]} belas")
        else:
            if ones:
                words.append(units[ones])
        return " ".join(words).strip()

    def _spell_chunk(value: int, magnitude: str) -> str:
        return f"{_spell_below_thousand(value)} {magnitude}".strip()

    def _split_chunks(number: int) -> Iterable[int]:
        while number:
            number, remainder = divmod(number, 1000)
            yield remainder

    magnitudes = ["", "ribu", "juta", "miliar", "triliun"]

    quantized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    integer_part = int(quantized)
    fraction = int((quantized - Decimal(integer_part)) * 100)

    if integer_part == 0:
        words = "nol"
    else:
        words = []
        for idx, chunk in enumerate(_split_chunks(integer_part)):
            if not chunk:
                continue
            if idx == 1 and chunk == 1:
                words.append("seribu")
            else:
                words.append(_spell_chunk(chunk, magnitudes[idx]))
        words = " ".join(reversed(words))

    if fraction:
        words = f"{words} koma {_spell_below_thousand(fraction)}"

    if suffix:
        words = f"{words} {suffix}".strip()

    return words


def requires_materai(receipt_amount: float | Decimal) -> bool:
    """Check if the receipt amount requires materai (stamp duty).
    
    Args:
        receipt_amount: The total amount on the customer receipt.
        
    Returns:
        True if the amount meets or exceeds the minimum threshold for materai.
    """
    settings = get_receipt_control_settings()
    min_amount = float(settings.get("materai_minimum_amount", 10000000))
    
    return float(receipt_amount or 0) >= min_amount


def record_stamp_cost(customer_receipt: str, cost: float | Decimal) -> str:
    """Create and submit a Journal Entry for the given stamp cost.

    Args:
        customer_receipt: The Customer Receipt identifier for context.
        cost: The monetary value of the stamp duty.

    Returns:
        The name of the submitted Journal Entry.
        
    Raises:
        frappe.ValidationError: If GL account mappings are not configured
    """

    cost_amount = float(cost or 0)
    if cost_amount <= 0:
        frappe.throw(_("Stamp cost must be greater than zero."))

    receipt_meta = frappe.db.get_value(
        "Customer Receipt", customer_receipt, ["company", "branch"], as_dict=True
    )
    if not receipt_meta:
        frappe.throw(_("Customer Receipt {0} not found.").format(customer_receipt))

    # Get GL accounts from central mapping (no more hardcoded)
    try:
        expense_account, payment_account = get_digital_stamp_accounts(
            company=receipt_meta.company
        )
    except frappe.ValidationError:
        frappe.throw(
            _(
                "Digital stamp GL accounts are not configured. "
                "Please set 'digital_stamp_expense' and 'digital_stamp_payment' "
                "in Finance Control Settings → GL Account Mappings."
            ),
            title=_("Missing GL Account Configuration")
        )

    # Validate accounts exist in company's chart of accounts
    for account in (expense_account, payment_account):
        if not frappe.db.exists(
            "Account", {"name": account, "company": receipt_meta.company}
        ):
            frappe.throw(
                _(
                    "Account {0} not found for company {1}. "
                    "Please verify GL Account Mappings configuration."
                ).format(account, receipt_meta.company),
                title=_("Invalid GL Account")
            )

    journal_entry = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "voucher_type": "Journal Entry",
            "posting_date": frappe.utils.nowdate(),
            "company": receipt_meta.company,
            "branch": receipt_meta.get("branch"),
            "user_remark": _("Stamp duty cost for {0}").format(customer_receipt),
            "accounts": [
                {
                    "account": expense_account,
                    "debit_in_account_currency": cost_amount,
                    "reference_type": "Customer Receipt",
                    "reference_name": customer_receipt,
                    "branch": receipt_meta.get("branch"),
                },
                {
                    "account": payment_account,
                    "credit_in_account_currency": cost_amount,
                    "reference_type": "Customer Receipt",
                    "reference_name": customer_receipt,
                    "branch": receipt_meta.get("branch"),
                },
            ],
        }
    )
    journal_entry.insert(ignore_permissions=True)
    journal_entry.submit()
    return journal_entry.name


def build_verification_url(pattern: Optional[str], stamp_ref: Optional[str]) -> Optional[str]:
    if not pattern or not stamp_ref:
        return None
    return pattern.replace("{{stamp_ref}}", stamp_ref)


def get_default_receipt_design():
    """Return default receipt design as a safe dict for Jinja templates"""
    import frappe
    return frappe._dict({
        "custom_wording_title": "KUITANSI",
        "show_detail_table": 1,
        "stamp_mode_default": "Physical",
        "stamp_position": "Bottom Right",
        "stamp_width_mm": 35,
        "stamp_height_mm": 40,
        "digital_stamp_opacity_pct": 100,
        "show_qr": 0,
        "custom_logo": None,
        "logo_mode": "Company Default"
    })
