import frappe

def set_workspace_order():
    """Set urutan sidebar workspace"""
    sequences = {
        "Towing Imogi": -1,
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

    doctypes = [
        "do_towing_kondisi_item",
        "so_towing_kendaraan",
        "delivery_order_towing",
    ]

    for folder in doctypes:
        dt_name = folder.replace("_", " ").title()
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
    """
    doctype_name = "Delivery Order Towing"
    status_fieldname = "status"
    awaiting_state = "Awaiting Dokument"

    # Pastikan role towing tersedia sebelum workflow diproses
    for role_name in ["Admin Towing", "Towing Driver"]:
        if not frappe.db.exists("Role", role_name):
            role = frappe.new_doc("Role")
            role.role_name = role_name
            role.desk_access = 1
            role.insert(ignore_permissions=True)
            frappe.db.commit()
            print(f"[setup] Created role: {role_name}")

    # Force reload DocType model
    frappe.reload_doc("imogi_finance", "doctype", "delivery_order_towing", force=True)

    # Paksa reset field properties setelah reload_doc
    field_overrides = {
        "lokasi_pickup":      {"reqd": 0},
        "lokasi_tujuan":      {"reqd": 0},
        "harga_jasa":         {"reqd": 0, "hidden": 1},
        "tipe_kendaraan":     {"reqd": 0},
        "merk_kendaraan":     {"reqd": 0},
        "nomor_polisi":       {"reqd": 0},
        "uang_jalan_status":  {"read_only": 1},
    }
    for fn, updates in field_overrides.items():
        field_rec = frappe.db.get_value(
            "DocField",
            {"parent": "Delivery Order Towing", "fieldname": fn},
            "name",
            as_dict=True,
        )
        if field_rec:
            frappe.db.set_value("DocField", field_rec.name, updates, update_modified=False)
            print(f"[setup] Force-set {fn}: {updates}")

    required_status_options = [
        "Draft",
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

    if not frappe.db.exists("Workflow Action Master", awaiting_state):
        wam = frappe.new_doc("Workflow Action Master")
        wam.workflow_action_name = awaiting_state
        wam.insert(ignore_permissions=True)

    # 2) Ensure DocField options for status — TIDAK include Submitted
    field = frappe.db.get_value(
        "DocField",
        {"parent": doctype_name, "fieldname": status_fieldname},
        ["name", "options"],
        as_dict=True,
    )
    if field:
        merged = []
        for opt in required_status_options:
            if opt not in merged:
                merged.append(opt)

        new_options = "\n".join(merged)
        if (field.options or "") != new_options:
            frappe.db.set_value("DocField", field.name, "options", new_options, update_modified=False)
            print(f"[setup] Status options updated")

    # 3) Ensure invoice fields exist
    def ensure_docfield(fieldname: str, spec: dict):
        existing = frappe.db.get_value(
            "DocField",
            {"parent": doctype_name, "fieldname": fieldname},
            ["name"],
            as_dict=True,
        )
        if existing:
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
            "depends_on": "eval:doc.status=='Awaiting Dokument' || doc.status=='Done'",
            "mandatory_depends_on": "",
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
            "depends_on": "eval:doc.status=='Awaiting Dokument' || doc.status=='Done'",
            "mandatory_depends_on": "eval:doc.status=='Awaiting Dokument'",
            "allow_on_submit": 1,
            "hidden": 0,
            "reqd": 0,
            "permlevel": 0,
        },
    )

    # 4) Sync DO Towing Workflow
    workflow_name = "DO Towing Workflow"
    if frappe.db.exists("Workflow", workflow_name):
        wf = frappe.get_doc("Workflow", workflow_name)
        changed = False

        # Hapus state Submitted
        for s in list(wf.states):
            if s.state == "Submitted":
                wf.remove(s)
                changed = True
                print("[setup] Removed state: Submitted")

        # Hapus transition yang melibatkan Submitted
        for t in list(wf.transitions):
            if t.state == "Submitted" or t.next_state == "Submitted":
                wf.remove(t)
                changed = True
                print(f"[setup] Removed transition involving Submitted")

        # Hapus transition Done → Awaiting Dokument
        for t in list(wf.transitions):
            if t.state == "Done" and t.next_state == "Awaiting Dokument":
                wf.remove(t)
                changed = True

        # Hapus semua transition dengan role yang tidak ada di database
        for t in list(wf.transitions):
            if t.allowed and not frappe.db.exists("Role", t.allowed):
                print(f"[setup] Removed invalid role transition: {t.state} → {t.next_state} [{t.allowed}]")
                wf.remove(t)
                changed = True

        # Hapus transisi System Manager — semua aksi DO Towing dikontrol
        # via role spesifik (Admin Towing, Sales Manager, Towing Driver)
        for t in list(wf.transitions):
            if t.allowed == "System Manager":
                print(f"[setup] Removed System Manager transition: {t.state} → {t.next_state}")
                wf.remove(t)
                changed = True

        # Definisi transisi yang harus ada (role spesifik, tanpa System Manager)
        required_transitions = [
            # Draft → Assigned (hanya Admin/Manager, BUKAN Driver)
            {"state": "Draft",     "action": "Assign Driver",       "next_state": "Assigned",         "allowed": "Admin Towing"},
            {"state": "Draft",     "action": "Assign Driver",       "next_state": "Assigned",         "allowed": "Sales Manager"},
            # Assigned → Pick Up (Admin + Driver)
            {"state": "Assigned",  "action": "Konfirmasi Pick Up",  "next_state": "Pick Up",          "allowed": "Admin Towing"},
            {"state": "Assigned",  "action": "Konfirmasi Pick Up",  "next_state": "Pick Up",          "allowed": "Sales Manager"},
            {"state": "Assigned",  "action": "Konfirmasi Pick Up",  "next_state": "Pick Up",          "allowed": "Towing Driver"},
            # Pick Up → Delivered (Admin + Driver)
            {"state": "Pick Up",   "action": "Konfirmasi Delivered","next_state": "Delivered",        "allowed": "Admin Towing"},
            {"state": "Pick Up",   "action": "Konfirmasi Delivered","next_state": "Delivered",        "allowed": "Sales Manager"},
            {"state": "Pick Up",   "action": "Konfirmasi Delivered","next_state": "Delivered",        "allowed": "Towing Driver"},
            # Delivered → Awaiting Dokument (Admin + Driver, BUKAN hanya Admin)
            {"state": "Delivered", "action": "Selesaikan DO",       "next_state": "Awaiting Dokument","allowed": "Admin Towing"},
            {"state": "Delivered", "action": "Selesaikan DO",       "next_state": "Awaiting Dokument","allowed": "Sales Manager"},
            {"state": "Delivered", "action": "Selesaikan DO",       "next_state": "Awaiting Dokument","allowed": "Towing Driver"},
            # Awaiting Dokument → Done (hanya Admin, BUKAN Driver)
            {"state": "Awaiting Dokument", "action": "Konfirmasi Dokumen", "next_state": "Done",     "allowed": "Admin Towing"},
            {"state": "Awaiting Dokument", "action": "Konfirmasi Dokumen", "next_state": "Done",     "allowed": "Sales Manager"},
            # Cancel (hanya Admin)
            {"state": "Assigned",  "action": "Cancel",              "next_state": "Cancelled",        "allowed": "Admin Towing"},
            {"state": "Assigned",  "action": "Cancel",              "next_state": "Cancelled",        "allowed": "Sales Manager"},
        ]

        for req in required_transitions:
            # Skip jika role tidak ada di DB
            if not frappe.db.exists("Role", req["allowed"]):
                continue
            exists = any(
                t.state == req["state"]
                and t.next_state == req["next_state"]
                and t.action == req["action"]
                and t.allowed == req["allowed"]
                for t in wf.transitions
            )
            if not exists:
                wf.append("transitions", {
                    "state": req["state"],
                    "action": req["action"],
                    "next_state": req["next_state"],
                    "allowed": req["allowed"],
                    "allow_self_approval": 1,
                    "send_email_to_creator": 0,
                })
                changed = True
                print(f"[setup] Added: {req['state']} → {req['next_state']} [{req['allowed']}]")

        if changed:
            wf.save(ignore_permissions=True)
            print("[setup] DO Towing Workflow saved")

    frappe.clear_cache(doctype=doctype_name)
    frappe.db.commit()


def ensure_finance_manager_role():
    """
    Pastikan Role 'Finance Manager' ada di sistem.
    Kalau belum ada → buat baru.
    Idempotent: aman dipanggil berulang kali.
    """
    role_name = "Finance Manager"

    if frappe.db.exists("Role", role_name):
        # Pastikan role tidak disabled
        is_disabled = frappe.db.get_value("Role", role_name, "disabled")
        if is_disabled:
            frappe.db.set_value("Role", role_name, "disabled", 0)
            frappe.db.commit()
            print(f"[Imogi Finance] Re-enabled existing Role: {role_name}")
        return

    try:
        role = frappe.new_doc("Role")
        role.role_name = role_name
        role.desk_access = 1   # boleh akses ke Frappe Desk
        role.disabled = 0
        role.is_custom = 1     # tandai sebagai custom role
        role.flags.ignore_permissions = True
        role.insert(ignore_permissions=True)
        frappe.db.commit()
        print(f"[Imogi Finance] Created Role: {role_name}")
    except Exception as e:
        frappe.log_error(
            f"Gagal create Role '{role_name}': {e}",
            "Finance Manager Role Setup Error"
        )