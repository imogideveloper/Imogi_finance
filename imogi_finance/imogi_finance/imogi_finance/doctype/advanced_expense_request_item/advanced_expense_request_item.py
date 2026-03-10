# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.model.document import Document


class AdvancedExpenseRequestItem(Document):
    """Child table for line items within an Advanced Expense Request.

    Each item carries its own cost_center for per-item budget allocation.
    """

    pass
