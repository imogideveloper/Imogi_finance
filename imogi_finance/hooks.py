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
        "public/js/item_tax_mapping.js", 
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
        "public/js/sales_invoice_down_payment.js",
        "public/js/item_tax_mapping.js",
    ],
    "Delivery Order Towing": "public/js/delivery_order_towing.js",
    "Workspace UI Settings": "public/js/workspace_ui_settings.js",
    "Quotation":       "public/js/item_tax_mapping.js", 
    "Purchase Order":  [
        "public/js/item_tax_mapping.js",
        "public/js/purchase_order_tax_invoice.js",
    ],
    "Item Tax Mapping": "public/js/item_tax_mapping.js",
    "Salary Structure Assignment": "public/js/salary_structure_assignment.js",
    "Salary Structure": "public/js/salary_structure.js",
    "Salary Slip": "public/js/salary_slip.js",
    "Payroll Entry": "public/js/payroll_entry.js",
    "Bank Statement": "public/js/bank_statement_form.js",
    "Bank CSV Import": "public/js/bank_statement_form.js",
}

app_include_js = [
    "/assets/imogi_finance/js/bank_statement_form.js",
    "/assets/imogi_finance/js/payment_entry_allocation_status.js",
    "/assets/imogi_finance/js/imogi_finance.js",
    "/assets/imogi_finance/js/workspace_visibility.js",
    "/assets/imogi_finance/js/form_field_visibility.js",
    "/assets/imogi_finance/js/finance_monitor_workspace.js",
    "/assets/imogi_finance/js/imogi_service_item_qty.js",
    "/assets/imogi_finance/js/sales_invoice_item_tax.js",
    "/assets/imogi_finance/js/ssa_contract_reminder_toast.js",
]

boot_session = "imogi_finance.workspace_visibility.update_boot_session"


doctype_list_js = {
    "Sales Invoice": [
        "public/js/sales_invoice_list.js",
        "public/js/sales_invoice_list_toolbar.js",
    ],
    # "Sales Order" list JS intentionally NOT registered here - garage app
    # already owns Sales Order's list view (colored status-badge card
    # layout, see garage/public/js/sales_order_list.js) for this site, and
    # having both apps register doctype_list_js for the same doctype meant
    # whichever loaded last silently overrode the other's rendering -
    # explicit user request (2026-08-19) to keep garage's card view intact.
    "Bank Statement": "imogi_finance/imogi_finance/doctype/bank_csv_import/bank_csv_import_list.js",
    "Bank CSV Import": "imogi_finance/imogi_finance/doctype/bank_csv_import/bank_csv_import_list.js",
    "Administrative Payment Voucher": "imogi_finance/doctype/administrative_payment_voucher/administrative_payment_voucher_list.js",
    "Expense Request": "imogi_finance/doctype/expense_request/expense_request_list.js",
    "Advanced Expense Request": "imogi_finance/doctype/advanced_expense_request/advanced_expense_request_list.js",
    "Payment Entry": "public/js/payment_entry_list.js",
    "Budget": "public/js/budget_list.js",
    "Tax Invoice OCR Upload": "public/js/tax_invoice_ocr_upload_list.js",
    "Salary Structure Assignment": "public/js/salary_structure_assignment_list.js",
    "Payroll Entry": "public/js/payroll_entry_list.js",
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
        # Workshop Imogi - tambahan baru
        "Service Booking",
        "Vehicle Reception",
        "Complaint Log",
        "After Service Follow Up"
    ]]]},
    
    # 2. Customizations
    {"doctype": "Custom Field"},
    {"doctype": "Property Setter"},
    {"doctype": "Client Script", "filters": [["enabled", "=", 1]]},
    {"doctype": "List View Settings", "filters": [["name", "in", ["Sales Order", "Sales Invoice", "Expense Request", "Delivery Order Towing", "Payroll Period", "Payroll Entry"]]]},
    
    # 3. Master Data
    {"doctype": "Item", "filters": [["name", "=", "JASA-TOWING-001"]]},
    
    # 4. Workflow (urutan penting!)
    # Was scoped to DO Towing's own states/actions/workflow only (set when
    # DO Towing fixtures were first added, 2026-04-23) - the other 9 finance
    # workflows (Budget Request, Expense Request, Payment Voucher, etc.)
    # already existed and worked locally the whole time, but were never
    # actually in this fixture net, so they never made it to any deploy.
    # Widened to cover those 9 and everything their own states/transitions
    # reference - explicit request (2026-08-27).
    #
    # "DO Towing Workflow" itself is deliberately left OUT of this list, not
    # merged back in: its own document_type, "Delivery Order Towing", isn't
    # actually an installed DocType on either this bench or production
    # (frappe.get_meta("Delivery Order Towing") raises DoesNotExistError on
    # both - a pre-existing break, unrelated to this change) - and Frappe's
    # fixture sync SKIPS THE ENTIRE FILE, not just the one bad entry, the
    # moment any Workflow in it references a document_type that doesn't
    # resolve. With "DO Towing Workflow" still in the list that took every
    # other workflow down with it on every single migrate, silently (no
    # error - just a log line, "Skipping fixture syncing from the file
    # workflow.json"). Confirmed live: it already was silently failing this
    # way before this change too, so this isn't a regression - fixing DO
    # Towing's own missing DocType is a separate, unrelated task.
    {"doctype": "Workflow State", "filters": [["workflow_state_name", "in",
        ["Approved", "Approved for Transfer", "Awaiting Bank Confirmation",
         "Cancelled", "Draft", "Finance Review", "Generated", "Issued",
         "PI Created", "Paid", "Partially Approved", "Partially Paid",
         "Pending Approval", "Pending L1 Approval", "Pending L2 Approval",
         "Pending L3 Approval", "Pending Review", "Posted", "Printed",
         "Rejected"]]]},
    # Most of these 9 workflows' own transitions reference an "action" that
    # has no matching Workflow Action Master record at all (a required Link
    # field - e.g. "Submit for Approval" is used by 3+ transitions but no
    # such master record exists anywhere in this database). That's already
    # true right now, on the already-working local copies of these
    # workflows - not something this change introduces or should paper
    # over by inventing new master records nobody asked for. Only "Approve"
    # and "Reject" both exist AND are used here; that's all there is to
    # export.
    {"doctype": "Workflow Action Master", "filters": [["workflow_action_name", "in",
        ["Approve", "Reject"]]]},
    {"doctype": "Workflow", "filters": [["name", "in", [
        "Additional Budget Request Workflow",
        "Administrative Payment Voucher Workflow",
        "Advanced Expense Request Workflow",
        "Budget Reclass Request Workflow",
        "Cash Bank Daily Report Workflow",
        "Customer Receipt Workflow",
        "Expense Request Workflow",
        "Internal Charge Request Workflow",
        "Transfer Application Workflow",
    ]]]},
    
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
    "Salary Structure Assignment": "imogi_finance.overrides.salary_structure_assignment.CustomSalaryStructureAssignment",
}

# Document Events
doc_events = {
    "Tax Invoice OCR Upload": {
        "validate": [
            "imogi_finance.events.metadata_fields.set_created_by",
        ],
        "on_submit": [
            "imogi_finance.events.metadata_fields.set_submit_on",
        ],
        "after_save": [
            "imogi_finance.events.tax_invoice_ocr_upload.auto_link_to_sales_invoice",
        ],
    },

    "Bank Statement Import": {
        "before_insert": "imogi_finance.imogi_finance.events.bank_statement_import_handler.bank_statement_import_on_before_insert",
        "before_submit": "imogi_finance.imogi_finance.events.bank_statement_import_handler.bank_statement_import_before_submit",
    },

    "Purchase Order": {
        "before_submit": "imogi_finance.events.purchase_order.validate_before_submit",
    },

    "Purchase Invoice": {
        "before_insert": "imogi_finance.events.purchase_invoice.carry_tax_invoice_from_po",
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
            "imogi_finance.services.sales_invoice_list_status.sync_imogi_status_and_late_days",
            "imogi_finance.events.sales_invoice.reapply_imogi_so_down_payment",
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
    },

    "Sales Order": {
        "validate": "imogi_finance.events.sales_order.compute_outstanding_amount",
        "on_update_after_submit": [
            "imogi_finance.events.sales_order.compute_outstanding_amount",
            "imogi_finance.sales_order_payment_status.update_from_sales_order",
        ],
        "on_submit": [
            "imogi_finance.sales_order_payment_status.update_from_sales_order",
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
            "imogi_finance.payment_entry_status.update_payment_status_on_validate",
        ],
        "after_insert": [
            "imogi_finance.events.payment_entry.after_insert",
        ],
        "on_update": [
            "imogi_finance.events.payment_entry.on_update",
        ],
        "before_submit": [
            "imogi_finance.receipt_control.payment_entry_hooks.validate_customer_receipt_link",
        ],
        "on_submit": [
            "imogi_finance.events.payment_entry.on_submit",
            "imogi_finance.receipt_control.payment_entry_hooks.record_payment_entry",
            "imogi_finance.transfer_application.payment_entry_hooks.on_submit",
            "imogi_finance.events.sales_order.update_sales_order_outstanding_from_payment",
            "imogi_finance.sales_order_payment_status.update_from_payment_entry",
            "imogi_finance.imogi_finance.doctype.expense_request.expense_request.update_er_status_on_payment",
            "imogi_finance.payment_entry_status.update_payment_status_on_submit",
        ],
        "on_update_after_submit": [
            "imogi_finance.events.payment_entry.on_update_after_submit",
            "imogi_finance.sales_order_payment_status.update_from_payment_entry",
            "imogi_finance.payment_entry_status.update_payment_status_on_submit",
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
            "imogi_finance.payment_entry_status.update_payment_status_on_cancel",
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
    },
    "Workspace UI Settings": {
        "on_update": "imogi_finance.workspace_visibility.clear_workspace_cache",
    },
    "Salary Structure Assignment": {
        "validate": (
            "imogi_finance.payroll.salary_structure_assignment"
            ".validate_salary_structure_assignment"
        ),
        "on_submit": (
            "imogi_finance.payroll.salary_structure_assignment"
            ".handle_salary_structure_assignment_submit"
        ),
        "on_update_after_submit": (
            "imogi_finance.payroll.salary_structure_assignment"
            ".update_submitted_salary_structure_assignment"
        ),
    },
    "Salary Structure": {
        "validate": (
            "imogi_finance.payroll.employer_contributions"
            ".sync_salary_structure_employer_display"
        ),
    },
    "Payroll Entry": {
        "validate": [
            "imogi_finance.payroll.payroll_period_integration.validate_payroll_entry",
            "imogi_finance.payroll.payroll_entry_summary.sync_summary_on_validate",
        ],
    },
    "Payroll Period": {
        "validate": (
            "imogi_finance.payroll.payroll_period_integration.validate_payroll_period"
        ),
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
        "imogi_finance.payroll.salary_structure_assignment.sync_expired_salary_structure_assignments",
    ],
    "daily_maintenance": [
        "imogi_finance.services.sales_invoice_list_status.sync_all_submitted_sales_invoices",
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
    "imogi_finance.patches.post_model_sync.setup_finance_monitor_menu.execute",
    "imogi_finance.patches.post_model_sync.fix_bpjs_base_formula_from_fixed_income.execute",
    "imogi_finance.patches.post_model_sync.enforce_ssa_contract_workflow.execute",
    "imogi_finance.patches.post_model_sync.fix_payroll_entry_list_salary_month.execute",
    "imogi_finance.patches.post_model_sync.fix_payroll_entry_grouping_date_field.execute",
    "imogi_finance.services.sales_invoice_list_status.sync_all_submitted_sales_invoices",
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
    "hrms.payroll.doctype.payroll_entry.payroll_entry.employee_query":
        "imogi_finance.payroll.payroll_entry.employee_query",
    "frappe.desk.desktop.get_desktop_page":
        "imogi_finance.overrides.desktop.get_desktop_page",
    "frappe.desk.desktop.get_workspace_sidebar_items":
        "imogi_finance.overrides.desktop.get_workspace_sidebar_items",
    "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_journal_entry_bts":
        "imogi_finance.overrides.bank_reconciliation_tool.create_journal_entry_bts",
    "erpnext.accounts.doctype.bank_reconciliation_tool.bank_reconciliation_tool.create_journal_entry_bts":
        "imogi_finance.overrides.bank_reconciliation_tool.create_journal_entry_bts",
    "erpnext.accounts.doctype.bank_statement_import.bank_statement_import.start_import":
        "imogi_finance.overrides.bank_statement_import.start_import",
}

ignore_links_on_delete = ["Payment Ledger Entry", "GL Entry"]