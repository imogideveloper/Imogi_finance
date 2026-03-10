"""GL Account Mapping purposes.

Central constants for all GL account purposes used throughout the application.
Prevents typos and enables audit of all GL account usage.
"""

# Digital Stamp (Materai) Accounts
DIGITAL_STAMP_EXPENSE = "digital_stamp_expense"
DIGITAL_STAMP_PAYMENT = "digital_stamp_payment"

# Transfer Application Accounts
DEFAULT_PAID_FROM = "default_paid_from"
# NOTE: DEFAULT_PAID_TO removed - paid_to must come from party account per beneficiary

# Deferred Expense Accounts
DEFAULT_PREPAID = "default_prepaid"

# Tax Variance Accounts
DPP_VARIANCE = "dpp_variance"
PPN_VARIANCE = "ppn_variance"

# All purposes (for validation/audit)
ALL_PURPOSES = {
    DIGITAL_STAMP_EXPENSE,
    DIGITAL_STAMP_PAYMENT,
    DEFAULT_PAID_FROM,
    DEFAULT_PREPAID,
    DPP_VARIANCE,
    PPN_VARIANCE,
}
