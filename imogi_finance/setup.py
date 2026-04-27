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
    from frappe import get_app_path

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

        path = get_app_path("imogi_finance", "doctype", folder, f"{folder}.json")

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