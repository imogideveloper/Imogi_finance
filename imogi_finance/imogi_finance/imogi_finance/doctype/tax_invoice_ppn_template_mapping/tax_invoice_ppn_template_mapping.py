# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class TaxInvoicePPNTemplateMapping(Document):
    """Child table: PPN Type → Purchase/Sales Tax Template mapping.

    Configured once in Tax Invoice OCR Settings.
    Drives automatic template suggestion in Tax Invoice OCR Upload.
    """
    pass
