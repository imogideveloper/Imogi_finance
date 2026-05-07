import frappe

def set_workspace_order():
    """Set urutan sidebar workspace"""
    sequences = {
        "Towing Imogi": -1,      # ← tambahkan ini
        "HRIS Imogi": 0.05,
        "FINANCE IMOGI": 0.1,
        "Budget Control": 0.2,
        "Asset Management": 0.3,
        "Tax & Compliance": 0.4,
        "Finance Operations": 0.5,
        "Treasury & Payments": 0.6,
        "Accounting & Reporting": 0.7,
        "Company List": 0.8,
        "Home": 1,
        "Accounting": 2,
        "Payables": 3,
        "Receivables": 4,
        "Buying": 5,
        "Financial Reports": 5,
        "Selling": 6,
        "Assets": 7,
        "Stock": 7,
        "Manufacturing": 8,
        "Quality": 9,
        "Projects": 11,
        "Support": 12,
        "Users": 13,
        "Website": 14,
        "CRM": 17,
        "Tools": 17,
        "ERPNext Settings": 19,
        "Integrations": 20,
        "ERPNext Integrations": 21,
        "Build": 27,
    }

    for name, seq in sequences.items():
        if frappe.db.exists("Workspace", name):
            frappe.db.sql(
                "UPDATE `tabWorkspace` SET sequence_id = %s WHERE name = %s",
                (seq, name)
            )

    frappe.db.commit()

def install_towing_doctypes():
    """Install DO Towing DocTypes jika belum ada di production."""
    import os
    from frappe.modules.import_file import import_file_by_path

    # Urutan penting: child table dulu sebelum parent
    doctypes = [
        "do_towing_kondisi_item",
        "so_towing_kendaraan",
        "delivery_order_towing",
    ]

    for folder in doctypes:
        dt_name = folder.replace("_", " ").title()
        # Fix nama yang tidak standard
        name_map = {
            "Do Towing Kondisi Item": "DO Towing Kondisi Item",
            "So Towing Kendaraan": "SO Towing Kendaraan",
            "Delivery Order Towing": "Delivery Order Towing",
        }
        dt_name = name_map.get(dt_name, dt_name)

        if frappe.db.exists("DocType", dt_name):
            print(f"⚠️ {dt_name} sudah ada, skip")
            continue

        app_path = frappe.get_app_path("imogi_finance")
        # Towing doctypes ada di imogi_finance/doctype/ (bukan imogi_finance/imogi_finance/doctype/)
        path = os.path.join(os.path.dirname(app_path), "doctype", folder, f"{folder}.json")

        if not os.path.exists(path):
            print(f"❌ File tidak ditemukan: {path}")
            continue

        try:
            import_file_by_path(path, ignore_version=True)
            frappe.db.commit()
            print(f"✅ {dt_name} berhasil diinstall")
        except Exception as e:
            print(f"❌ Gagal install {dt_name}: {e}")
            frappe.log_error(str(e), f"Install DocType {dt_name}")


def ensure_towing_workflow_consistency():
    """
    Keep Delivery Order Towing workflow metadata in sync after migrate.
    This avoids runtime validation errors when workflow introduces a new
    state but DocType select options are not yet aligned in DB metadata.
    """
    doctype_name = "Delivery Order Towing"
    status_fieldname = "status"
    awaiting_state = "Awaiting Dokument"

    # Force reload DocType model so DB schema (columns) stays in sync
    # with app code before workflow/status updates touch new fields.
    frappe.reload_doc("imogi_finance", "doctype", "delivery_order_towing", force=True)

    required_status_options = [
        "Draft",
        "Submitted",
        "Assigned",
        "Pick Up",
        "Delivered",
        "Done",
        awaiting_state,
        "Cancelled",
    ]

    # 1) Ensure Workflow State master exists
    if not frappe.db.exists("Workflow State", awaiting_state):
        ws = frappe.new_doc("Workflow State")
        ws.workflow_state_name = awaiting_state
        ws.style = "Warning"
        ws.insert(ignore_permissions=True)

    # Ensure Workflow Action Master exists for Awaiting Dokument action
    if not frappe.db.exists("Workflow Action Master", awaiting_state):
        wam = frappe.new_doc("Workflow Action Master")
        wam.workflow_action_name = awaiting_state
        wam.insert(ignore_permissions=True)

    # 2) Ensure DocField options for status includes Awaiting Dokument
    field = frappe.db.get_value(
        "DocField",
        {"parent": doctype_name, "fieldname": status_fieldname},
        ["name", "options"],
        as_dict=True,
    )
    if field:
        current_options = [x.strip() for x in (field.options or "").split("\n") if x.strip()]
        merged = []
        for opt in required_status_options:
            if opt not in merged:
                merged.append(opt)

        # Preserve any non-standard options that may already exist
        for opt in current_options:
            if opt not in merged:
                merged.append(opt)

        new_options = "\n".join(merged)
        if (field.options or "") != new_options:
            frappe.db.set_value("DocField", field.name, "options", new_options, update_modified=False)

    # 3) Ensure invoice fields exist and only show on Awaiting Dokument
    def ensure_docfield(fieldname: str, spec: dict):
        existing = frappe.db.get_value(
            "DocField",
            {"parent": doctype_name, "fieldname": fieldname},
            ["name"],
            as_dict=True,
        )
        if existing:
            # insert_after is not a DB column, remove before set_value
            update_spec = {k: v for k, v in spec.items() if k != "insert_after"}
            frappe.db.set_value("DocField", existing.name, update_spec, update_modified=False)
            return

        docfield = frappe.get_doc({
            "doctype": "DocField",
            "parent": doctype_name,
            "parenttype": "DocType",
            "parentfield": "fields",
            "fieldname": fieldname,
            **spec,
        })
        docfield.insert(ignore_permissions=True)

    ensure_docfield(
        "attachment_invoice",
        {
            "label": "Attachment Invoice",
            "fieldtype": "Attach",
            "insert_after": "sales_order",
            "depends_on": "",
            "allow_on_submit": 1,
            "hidden": 0,
            "reqd": 0,
            "permlevel": 0,
        },
    )
    ensure_docfield(
        "tanggal_invoice",
        {
            "label": "Tanggal Invoice",
            "fieldtype": "Date",
            "insert_after": "attachment_invoice",
            "depends_on": "",
            "mandatory_depends_on": "eval:doc.status=='Awaiting Dokument'",
            "allow_on_submit": 1,
            "hidden": 0,
            "reqd": 0,
            "permlevel": 0,
        },
    )

    # 4) Ensure workflow has action from Awaiting Dokument -> Done
    #    and does NOT keep Done -> Awaiting Dokument (Done must be final).
    workflow_name = "DO Towing Workflow"
    if frappe.db.exists("Workflow", workflow_name):
        wf = frappe.get_doc("Workflow", workflow_name)
        removed = False
        for t in list(wf.transitions):
            if t.state == "Done" and t.next_state == "Awaiting Dokument":
                wf.remove(t)
                removed = True

        has_transition = any(
            t.state == "Awaiting Dokument"
            and t.next_state == "Done"
            and t.action == "Konfirmasi Dokumen"
            for t in wf.transitions
        )
        if not has_transition:
            wf.append("transitions", {
                "state": "Awaiting Dokument",
                "action": "Konfirmasi Dokumen",
                "next_state": "Done",
                "allowed": "System Manager",
                "allow_self_approval": 1,
                "send_email_to_creator": 0,
            })
            removed = True

        if removed:
            wf.save(ignore_permissions=True)

    frappe.clear_cache(doctype=doctype_name)
    frappe.db.commit()