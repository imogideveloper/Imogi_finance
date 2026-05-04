import frappe

def execute():
    frappe.db.set_value(
        "Custom Field", 
        "Employee-has_jht", 
        "description", 
        "Centang jika karyawan ini tidak dikenakan potongan JHT (deduction tetap muncul tapi nilainya 0)"
    )
    frappe.db.commit()

    frappe.db.set_value(
        "Custom Field", 
        "Employee-has_jp", 
        "description", 
        "Centang jika karyawan ini tidak dikenakan potongan JP (deduction tetap muncul tapi nilainya 0)"
    )
    frappe.db.commit()
    
    frappe.db.set_value(
        "Custom Field", 
        "Employee-has_bpjs", 
        "description", 
        "Centang jika karyawan ini tidak dikenakan potongan BPJS (deduction tetap muncul tapi nilainya 0)"
    )
    frappe.db.commit()
