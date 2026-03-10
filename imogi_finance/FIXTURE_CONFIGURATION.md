"""
FIXTURE CONFIGURATION DOCUMENTATION

Standard fixtures untuk IMOGI Finance settings consolidation.
   
8. ppn_type → ti_fp_tax_category (transform: strip)
   Maps OCR-extracted tax category/type to PI tax category field
   
9. notes → ti_verification_notes (transform: strip)
   Maps OCR-extracted notes to PI verification notes field

All mappings are enabled by default and use appropriate transforms:
- strip: Remove leading/trailing whitespace
- date: Parse and format as date
- currency: Convert to decimal, handle IDR formatting
- none: No transformation

=== GL ACCOUNT MAPPING ITEM FIXTURE ===
File: imogi_finance/fixtures/gl_account_mapping_item.json

Defines standard GL account mappings for 7 required purposes:

1. digital_stamp_expense → "Biaya Materai Digital"
   GL account for posting digital stamp/materai costs
   
2. digital_stamp_payment → "Kas"
   GL account for digital stamp payment source
   
3. default_paid_from → "Kas"
   Default GL account for transfer application source
   
4. default_paid_to → "Utang Usaha"
   Default GL account for transfer application destination
   
5. default_prepaid → "Beban Dibayar Dimuka"
   Default GL account for deferred expense prepaid/advance
   
6. dpp_variance → "Selisih DPP"
   GL account for DPP (taxable amount) discrepancies
   
7. ppn_variance → "Selisih PPN"
   GL account for PPN (tax amount) discrepancies

All mappings:
- Company: empty (global default, applies to all companies)
- Required: 1 (system will enforce these must exist)
- Can be overridden: Yes (users can modify in Finance Control Settings)

=== NOTES ===

1. These are SEED fixtures - they provide default mappings on fresh deploy
2. Account names assume Indonesian chart of accounts (customize as needed)
3. Users can override/modify these mappings in Finance Control Settings UI
4. All 7 GL mapping purposes MUST have at least one account configured
5. Multi-company: Can add company-specific mappings alongside global defaults
6. OCR field mappings are optional - users enable/disable based on needs

=== INSTALLATION ===

These fixtures are automatically loaded during:
- Fresh app installation (via hooks.py fixtures)
- Bench migrate

To reload fixtures:
  bench --site [site] reload-doc imogi_finance "DocType" "GL Account Mapping Item"
  bench --site [site] reload-doc imogi_finance "DocType" "Tax Invoice OCR Field Mapping"
"""
