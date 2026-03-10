# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document


class CoreTaxColumnMapping(Document):
    """Child table for CoreTax column mapping configuration.
    
    Maps document fields or computed values to CoreTax export columns.
    Used within CoreTax Export Settings to define the structure of exported data.
    """

    def validate(self):
        """Validate column mapping configuration."""
        self.validate_source_field()
    
    def validate_source_field(self):
        """Validate that source field is properly configured based on source_type."""
        if not self.source_type:
            frappe.throw(
                _("Source Type is required for column mapping")
            )
        
        # Only validate source field if type requires it
        if self.source_type == "Document Field" and not self.source:
            frappe.throw(
                _("Source field is required when Source Type is 'Document Field'")
            )
        elif self.source_type == "Fixed Value" and not self.fixed_value:
            frappe.throw(
                _("Fixed Value is required when Source Type is 'Fixed Value'")
            )
