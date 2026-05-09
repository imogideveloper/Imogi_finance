import frappe

def execute():
    frappe.db.set_value(
        "Custom Field", 
        "Employee-has_bpjs", 
        "description", 
        "Centang jika karyawan ini tidak dikenakan potongan BPJS (deduction tetap muncul tapi nilainya 0)"
    )
    frappe.db.commit()
