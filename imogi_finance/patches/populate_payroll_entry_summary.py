import frappe


def execute():
    """Populate periode, total_karyawan, total_amount for existing Payroll Entry records."""
    bulan = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

    entries = frappe.get_all(
        "Payroll Entry",
        filters={"docstatus": 1},
        fields=["name", "start_date"]
    )

    for e in entries:
        if not e.start_date:
            continue

        d = frappe.utils.getdate(e.start_date)
        periode = f"{bulan[d.month - 1]} {d.year}"

        slips = frappe.get_all(
            "Salary Slip",
            filters={"payroll_entry": e.name, "docstatus": 1},
            fields=["net_pay"]
        )
        total_karyawan = len(slips)
        total_amount = sum(s.net_pay or 0 for s in slips)

        frappe.db.set_value("Payroll Entry", e.name, {
            "periode": periode,
            "total_karyawan": total_karyawan,
            "total_amount": total_amount
        })

    frappe.db.commit()