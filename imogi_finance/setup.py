import frappe

def set_workspace_order():
    """Set urutan sidebar workspace"""
    sequences = {
        "Access Studio": 0.03,
        "HRIS Imogi": 0.05,
        "FINANCE IMOGI": 0.1,
        "Budget Control": 0.2,
        "Asset Management": 0.3,
        "Tax & Compliance": 0.4,
        "Finance Operations": 0.5,
        "Treasury & Payments": 0.6,
        "Accounting & Reporting": 0.7,
        "Company List": 0.8,
        # ERPNext - sesuai urutan aslinya
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
