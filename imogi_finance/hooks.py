app_name = "imogi_finance"
app_title = "Imogi Finance"
app_publisher = "Imogi"
app_description = "App for Manage Expense IMOGI"
app_email = "imogi.indonesia@gmail.com"
app_license = "mit"
app_color = "#2490EF"

from imogi_finance.api.payroll_sync import is_payroll_installed

# Includes in <head>
app_include_css = "/assets/imogi_finance/css/custom.css"

# include js in doctype views
doctype_js = {
    "Sales Order": "public/js/sales_order.js",
    "Tax Invoice OCR Upload": "public/js/tax_invoice_ocr_upload_form.js",
    "VAT OUT Batch": "public/js/vat_out_batch_form.js",
    "Bank Transaction": "public/js/bank_transaction.js",
    "Bank Reconciliation Tool": [
        "public/js/bank_reconciliation_tool.js",
        "public/js/bank_reconciliation_tool_prefill.js",
    ],
    "Payment Entry": [
        "public/js/payment_entry.js",
        "public/js/payment_entry_djp.js",
    ],
    "Payment Request": "public/js/payment_request.js",
    "Purchase Invoice": [
        "public/js/purchase_invoice_tax_invoice.js",
        "public/js/payment_reconciliation_helper.js",
        "public/js/purchase_invoice_amortization.js",
    ],
    "Expense Claim": [
        "public/js/expense_claim.js",
        "public/js/payment_reconciliation_helper.js",
    ],
    "Payroll Entry": [
        "public/js/payment_reconciliation_helper.js",
    ],
    "Sales Invoice": [
        "public/js/sales_invoice_tax_invoice.js",
        "public/js/payment_reconciliation_helper.js",
    ],
    "Delivery Order Towing": "public/js/delivery_order_towing.js",
    "Sales Order": "public/js/delivery_order_towing.js",  # ← tambahkan ini
}

app_include_js = "/assets/imogi_finance/js/imogi_finance.js"


doctype_list_js = {
    "Sales Order": "public/js/sales_order_list.js",  # ← duplikat dihapus
    "Bank CSV Import": "imogi_finance/imogi_finance/doctype/bank_csv_import/bank_csv_import_list.js",
    "Administrative Payment Voucher": "imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher_list.js",
    "Expense Request": "imogi_finance/doctype/expense_request/expense_request_list.js",
    "Advanced Expense Request": "imogi_finance/doctype/advanced_expense_request/advanced_expense_request_list.js",
    "Payment Entry": "public/js/payment_entry_list.js",
    "Budget": "public/js/budget_list.js",
    "Tax Invoice OCR Upload": "public/js/tax_invoice_ocr_upload_list.js",
}

# Jinja
jinja = {
    "methods": [
        "imogi_finance.receipt_control.utils.terbilang_id",
        "imogi_finance.receipt_control.utils.build_verification_url",
        "imogi_finance.receipt_control.utils.requires_materai",
        "imogi_finance.receipt_control.utils.get_default_receipt_design",
    ]
}

# Installation
before_install = "imogi_finance.install.before_install"
# after_install = "imogi_finance.utils.ensure_coretax_export_doctypes"

# Fixtures
# Fixtures — tidak ada perubahan yang diperlukan
fixtures = [
    # 1. DocTypes
   {"doctype": "DocType", "filters": [["name", "in", [
        "Delivery Order Towing",
        "DO Towing Kondisi Item",
        # "SO Towing Kendaraan",  # temporary disabled to avoid deploy conflict
    ]]]},
    
    # 2. Customizations
    {"doctype": "Custom Field"},
    {"doctype": "Property Setter"},
    {"doctype": "Client Script", "filters": [["enabled", "=", 1]]},
    {"doctype": "List View Settings", "filters": [["name", "in", ["Sales Order", "Expense Request", "Delivery Order Towing"]]]},
    
    # 3. Master Data
    {"doctype": "Item", "filters": [["name", "=", "JASA-TOWING-001"]]},
    
    # 4. Workflow (urutan penting!)
    {"doctype": "Workflow State", "filters": [["workflow_state_name", "in", 
        ["Draft", "Submitted", "Assigned", "Pick Up", "Delivered", "Done", "Awaiting Dokument", "Cancelled"]]]},
    {"doctype": "Workflow Action Master", "filters": [["workflow_action_name", "in", 
        ["Assign Driver", "Konfirmasi Pick Up", "Konfirmasi Delivered", "Selesaikan DO", "Awaiting Dokument", "Cancel"]]]},
    {"doctype": "Workflow", "filters": [["name", "=", "DO Towing Workflow"]]},
    
    # 5. Reports & UI
    {"doctype": "Report"},
    {"doctype": "Print Format", "filters": [["module", "=", "Imogi Finance"]]},
    {"doctype": "Workspace"},
]
# DocType Class
override_doctype_class = {
    "Sales Invoice": "imogi_finance.overrides.sales_invoice.CustomSalesInvoice",
    "Payment Request": "imogi_finance.overrides.payment_request.CustomPaymentRequest",
    "Bank Statement Import": "imogi_finance.overrides.bank_statement_import.CustomBankStatementImport",
}

# Document Events
doc_events = {
    "Tax Invoice OCR Upload": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
       "on_submit": [
            "imogi_finance.sales_order_payment_status.update_from_sales_order",
        ],
        "after_save": [
            "imogi_finance.events.tax_invoice_ocr_upload.auto_link_to_sales_invoice",
        ],
    },

    "Bank Statement Import": {
        "before_insert": "imogi_finance.imogi_finance.events.bank_statement_import_handler.bank_statement_import_on_before_insert",
        "before_submit": "imogi_finance.imogi_finance.events.bank_statement_import_handler.bank_statement_import_before_submit",
    },

    "Purchase Invoice": {
        "onload": "imogi_finance.events.utils.normalize_tax_invoice_ppn_types",
        "validate": [
            "imogi_finance.events.purchase_invoice.prevent_double_wht_validate",
            "imogi_finance.tax_operations.validate_tax_period_lock",
            "imogi_finance.validators.finance_validator.validate_document_tax_fields",
            "imogi_finance.events.purchase_invoice.manage_ppn_variance_validate",
            "imogi_finance.events.purchase_invoice.manage_direct_pi_ppn_variance",
        ],
        "before_submit": [
            "imogi_finance.events.purchase_invoice.validate_before_submit",
            "imogi_finance.imogi_finance.doctype.tax_period_closing.tax_period_closing.check_period_is_closed",
        ],
        "on_submit": "imogi_finance.events.purchase_invoice.on_submit",
        "on_update_after_submit": "imogi_finance.events.purchase_invoice.sync_expense_request_status_from_pi",
        "before_cancel": "imogi_finance.events.purchase_invoice.before_cancel",
        "on_cancel": "imogi_finance.events.purchase_invoice.on_cancel",
        "before_delete": "imogi_finance.events.purchase_invoice.before_delete",
        "on_trash": "imogi_finance.events.purchase_invoice.on_trash",
    },

    "Sales Invoice": {
        "onload": "imogi_finance.events.utils.normalize_tax_invoice_ppn_types",
        "validate": [
            "imogi_finance.tax_operations.validate_tax_period_lock",
            "imogi_finance.validators.finance_validator.validate_document_tax_fields",
        ],
        "before_submit": [
            "imogi_finance.imogi_finance.doctype.tax_period_closing.tax_period_closing.check_period_is_closed",
        ],
        "on_submit": [
            "imogi_finance.sales_order_payment_status.update_from_sales_invoice",
            "imogi_finance.events.sales_invoice.fix_rounding_status",
        ],
        "on_cancel": [
            "imogi_finance.sales_order_payment_status.update_from_sales_invoice",
        ],
        "on_update_after_submit": [
            "imogi_finance.events.sales_invoice.on_update_after_submit",
            "imogi_finance.sales_order_payment_status.update_from_sales_invoice",
        ],
        "before_insert": [
            "imogi_finance.overrides.delivery_order_towing.validate_invoice_do_completion",
            "imogi_finance.overrides.sales_invoice_towing.before_insert",
        ],
    },

    "Sales Order": {
        "validate": "imogi_finance.events.sales_order.compute_outstanding_amount",
        "on_update_after_submit": [
            "imogi_finance.events.sales_order.compute_outstanding_amount",
            "imogi_finance.sales_order_payment_status.update_from_sales_order",
        ],
        "on_submit": [
            "imogi_finance.sales_order_payment_status.update_from_sales_order",
            "imogi_finance.overrides.delivery_order_towing.create_do_from_sales_order",
        ],
        "on_cancel": [
            "imogi_finance.sales_order_payment_status.update_from_sales_order",
        ],
        "after_insert": [
            "imogi_finance.sales_order_payment_status.update_from_sales_order",
        ],
    },

    "Expense Claim": {
        "before_submit": "imogi_finance.expense_claim_integration.expense_claim_advances.set_approval_status",
        "on_submit": "imogi_finance.expense_claim_integration.expense_claim_advances.link_employee_advances",
    },

    "Expense Request": {
        "validate": [
            "imogi_finance.tax_operations.validate_tax_period_lock",
            "imogi_finance.events.expense_request.validate_workflow_action",
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_update": [
            "imogi_finance.events.expense_request.sync_status_with_workflow",
            "imogi_finance.events.expense_request.handle_budget_workflow",
        ],
        "on_update_after_submit": [
            "imogi_finance.events.expense_request.sync_status_with_workflow",
            "imogi_finance.events.expense_request.handle_budget_workflow",
            "imogi_finance.events.expense_request_ocr.sync_tax_invoice_usage",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
            "imogi_finance.events.expense_request_ocr.mark_tax_invoice_as_used_on_submit",
            "imogi_finance.events.expense_request_ocr.sync_tax_invoice_usage",
            "imogi_finance.events.tax_invoice_ocr_upload.sync_tax_invoice_from_expense",
        ],
        "on_cancel": [
            "imogi_finance.events.expense_request_ocr.release_tax_invoice_on_cancel",
            "imogi_finance.events.tax_invoice_ocr_upload.release_tax_invoice_on_cancel",
        ],
    },

    "Advanced Expense Request": {
        "validate": [
            "imogi_finance.tax_operations.validate_tax_period_lock",
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },

    "Internal Charge Request": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_update": [
            "imogi_finance.events.internal_charge_request.sync_status_with_workflow",
        ],
        "on_update_after_submit": [
            "imogi_finance.events.internal_charge_request.sync_status_with_workflow",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
        "on_workflow_action": "imogi_finance.events.internal_charge_request.on_workflow_action",
    },

    "Additional Budget Request": {
        "on_workflow_action": "imogi_finance.events.additional_budget_request.on_workflow_action",
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
            "imogi_finance.events.additional_budget_request.on_submit",
        ],
    },

    "Administrative Payment Voucher": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },

    "Budget": {
        "before_delete": "imogi_finance.events.budget.before_delete",
        "on_trash": "imogi_finance.events.budget.before_delete",
        "before_cancel": "imogi_finance.events.budget.before_cancel",
        "validate": "imogi_finance.events.budget.prevent_duplicate_cost_center_budget",
        "before_save": "imogi_finance.events.budget.set_budget_display_fields",
    },

    "Budget Control Entry": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },

    "Budget Reclass Request": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },

    "Cash Bank Daily Report": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },

    "Customer Receipt": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },

    "Tax Invoice Upload": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },

    "Tax Payment Batch": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },

    "Tax Period Closing": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
            "imogi_finance.events.tax_period_closing.validate_period_completeness",
        ],
        "before_submit": [
            "imogi_finance.events.tax_period_closing.before_submit_checks",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
            "imogi_finance.events.tax_period_closing.on_period_closed",
        ],
        "on_cancel": [
            "imogi_finance.events.tax_period_closing.on_period_reopened",
        ],
    },

    "Transfer Application": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
            "imogi_finance.events.transfer_application.sync_status_with_workflow",
        ],
        "on_update": [
            "imogi_finance.events.transfer_application.sync_status_with_workflow",
        ],
        "on_update_after_submit": [
            "imogi_finance.events.transfer_application.sync_status_with_workflow",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
    },

    "Payment Entry": {
        "validate": [
            "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
            "imogi_finance.transfer_application.payment_entry_hooks.validate_transfer_application_link",
        ],
        "after_insert": [
            "imogi_finance.events.payment_entry.after_insert",
        ],
        "on_update": [
            "imogi_finance.events.payment_entry.on_update",
        ],
        "before_submit": [
            "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
            "imogi_finance.events.payment_entry.generate_towing_remarks",
        ],
        "on_submit": [
            "imogi_finance.events.payment_entry.on_submit",
            "imogi_finance.receipt_control.payment_entry_hooks.record_payment_entry",
            "imogi_finance.transfer_application.payment_entry_hooks.on_submit",
            "imogi_finance.events.sales_order.update_sales_order_outstanding_from_payment",
            "imogi_finance.sales_order_payment_status.update_from_payment_entry",
            "imogi_finance.imogi_finance.doctype.expense_request.expense_request.update_er_status_on_payment",
            "imogi_finance.overrides.delivery_order_towing.update_do_payment_status",
        ],
        "on_update_after_submit": [
            "imogi_finance.events.payment_entry.on_update_after_submit",
            "imogi_finance.sales_order_payment_status.update_from_payment_entry",
        ],
        "before_cancel": [
            "imogi_finance.events.payment_entry.before_cancel",
            "imogi_finance.events.payment_entry.clean_payment_ledger",
        ],
        "on_cancel": [
            "imogi_finance.events.payment_entry.on_cancel",
            "imogi_finance.receipt_control.payment_entry_hooks.remove_payment_entry",
            "imogi_finance.transfer_application.payment_entry_hooks.on_cancel",
            "imogi_finance.events.sales_order.update_sales_order_outstanding_from_payment",
            "imogi_finance.sales_order_payment_status.update_from_payment_entry",
            "imogi_finance.imogi_finance.doctype.expense_request.expense_request.revert_er_status_on_payment_cancel",
        ],
        "before_delete": "imogi_finance.events.payment_entry.before_delete",
        "on_trash": [
            "imogi_finance.events.payment_entry.on_trash",
        ],
    },

    "Payroll Entry": {},
    "Delivery Order Towing": {
        "after_save": "imogi_finance.overrides.delivery_order_towing.after_save",
        "on_update_after_submit": "imogi_finance.overrides.delivery_order_towing.on_update_after_submit",
        "on_submit": "imogi_finance.overrides.delivery_order_towing.on_submit",
    },
    "Purchase Order": {
        "on_update": "imogi_finance.overrides.delivery_order_towing.update_do_from_po",
        "on_submit": "imogi_finance.overrides.delivery_order_towing.update_do_from_po",
        "on_cancel": "imogi_finance.overrides.delivery_order_towing.update_do_from_po",
    },
}

if is_payroll_installed():
    doc_events.setdefault("Salary Slip", {}).update(
        {
            "validate": "imogi_finance.overrides.pph21_exemption.validate_pph21_exemption",
            "on_submit": "imogi_finance.api.payroll_sync.handle_salary_slip_submit",
            "on_cancel": "imogi_finance.api.payroll_sync.handle_salary_slip_cancel",
        }
    )

# Scheduled Tasks
scheduler_events = {
    "daily": [
        "imogi_finance.reporting.tasks.run_daily_reporting",
        "imogi_finance.services.tax_invoice_service.sync_pending_tax_invoices",
    ],
    "monthly": [
        "imogi_finance.reporting.tasks.run_monthly_reconciliation",
    ],
    "cron": {
        "*/15 * * * *": [
            "imogi_finance.tax_invoice_ocr.recover_stale_ocr_jobs"
        ]
    },
}

before_migrate = [
    "imogi_finance.fixtures.sanitize_fixture_files",
    "imogi_finance.utils.ensure_coretax_export_doctypes",
]

after_migrate = [
    "imogi_finance.utils.ensure_coretax_export_doctypes",
    "imogi_finance.utils.ensure_advances_allow_on_submit",
    "imogi_finance.imogi_finance.utils.ensure_budget_control_settings",
    "imogi_finance.setup.set_workspace_order",
    "imogi_finance.utils.patch_round_floats_compatibility",  # ← tambahkan ini
    "imogi_finance.setup.install_towing_doctypes",  # ← tambahkan
    "imogi_finance.setup.ensure_towing_workflow_consistency",
]

before_job = "imogi_finance.overrides.bank_statement_import.patch_start_import"

# Overriding Methods
override_whitelisted_methods = {
    "erpnext.accounts.doctype.budget.budget.validate_budget_records":
        "imogi_finance.overrides.budget_validation.validate_budget_records",
    "erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry":
        "imogi_finance.overrides.payment_entry.get_payment_entry",
    "frappe.desk.reportview.get_count":
        "imogi_finance.api.reportview_patch.get_count",
    "frappe.desk.listview.get_list_settings":
        "imogi_finance.overrides.listview.get_list_settings",
    "frappe.desk.desktop.get_desktop_page":
        "imogi_finance.overrides.desktop.get_desktop_page",
    "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_journal_entry_bts":
        "imogi_finance.overrides.bank_reconciliation_tool.create_journal_entry_bts",
    "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_journal_entry_bts":
        "imogi_finance.overrides.bank_reconciliation_tool.create_journal_entry_bts",
    "erpnext.accounts.doctype.bank_statement_import.bank_statement_import.start_import": 
        "imogi_finance.overrides.bank_statement_import.start_import",
    "erpnext.accounts.doctype.bank_statement_import.bank_statement_import.form_start_import": 
        "imogi_finance.overrides.bank_statement_import.form_start_import"
}

ignore_links_on_delete = ["Payment Ledger Entry", "GL Entry"]

on_session_creation = "imogi_finance.utils.patch_round_floats_compatibility"