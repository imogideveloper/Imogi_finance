# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TaxInvoiceType(Document):
    """
    Tax Invoice Type Master - Kode jenis faktur pajak sesuai DJP.
    
    Struktur kode faktur pajak (3 digit pertama):
    - Digit 1-2: Kode transaksi (01-09)
    - Digit 3: Status (0=Normal, 1=Pengganti)
    
    Referensi: PER-03/PJ/2022, PER-11/PJ/2022
    """
    
    def validate(self):
        """Validate Tax Invoice Type data."""
        # Validate fp_prefix format (must be 3 digits)
        if self.fp_prefix and len(self.fp_prefix) != 3:
            frappe.throw("Tax Invoice Prefix must be exactly 3 digits")
        
        # Validate transaction_code and status_code are valid
        if self.transaction_code and not self.transaction_code.isdigit():
            frappe.throw("Transaction Code must be numeric")
        
        if self.status_code and not self.status_code.isdigit():
            frappe.throw("Status Code must be numeric")
    
    def get_expected_ppn_types_list(self):
        """Get list of expected PPN types for this invoice type."""
        if not self.expected_ppn_types:
            return []
        
        # Split by comma and strip whitespace
        return [ppn_type.strip() for ppn_type in self.expected_ppn_types.split(",")]
    
    def matches_ppn_type(self, ppn_type_selected: str) -> tuple[bool, str]:
        """
        Check if selected PPN Type matches expected types.
        
        Returns:
            (is_valid, message): Tuple of validation result and message
        """
        # ✅ Skip validation for Custom/Other - user knows what they're doing
        if "custom" in ppn_type_selected.lower() or "other" in ppn_type_selected.lower():
            return True, ""
        
        expected_types = self.get_expected_ppn_types_list()
        
        if not expected_types:
            # No expected types defined, allow any
            return True, ""
        
        # Check if selected type contains any expected type
        for expected in expected_types:
            if expected.lower() in ppn_type_selected.lower():
                return True, ""
        
        # Not matching - return warning
        message = (
            f"Tax Invoice Type '{self.fp_prefix}' ({self.transaction_description}) "
            f"biasanya menggunakan: {', '.join(expected_types)}. "
            f"Anda memilih: {ppn_type_selected}. Mohon verifikasi kembali."
        )
        return False, message
