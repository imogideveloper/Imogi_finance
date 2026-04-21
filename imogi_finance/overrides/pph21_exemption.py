"""
Hook untuk menghandle PPh 21 Exemption di Payroll Indonesia
Tambahkan hook ini ke custom app Anda

Instalasi:
1. Copy file ini ke: {your_custom_app}/payroll_indonesia/overrides/pph21_exemption.py
2. Tambahkan hook di hooks.py:
   
   doc_events = {
       "Salary Slip": {
           "validate": "your_custom_app.payroll_indonesia.overrides.pph21_exemption.validate_pph21_exemption"
       }
   }
"""

import frappe
from frappe import _


def validate_pph21_exemption(doc, method=None):
    """
    Hook yang dipanggil saat Salary Slip di-validate.
    Jika employee punya flag 'exempt_from_pph21' = 1, 
    maka set PPh 21 deduction ke 0.
    """
    
    if not doc.employee:
        return
    
    try:
        employee = frappe.get_doc("Employee", doc.employee)
        
        if employee.get("exempt_from_pph21") == 1:
            pph21_found = False
            old_amount = 0
            
            for deduction in doc.deductions:
                if deduction.salary_component in ["PPh 21", "PPH 21", "Income Tax"]:
                    old_amount = deduction.amount
                    deduction.amount = 0
                    pph21_found = True
                    break
            
            if pph21_found:
                # PENTING: Re-calculate totals setelah ubah deduction
                doc.calculate_net_pay()  # ← TAMBAH INI
                
                frappe.msgprint(
                    msg=f"PPh 21 untuk {employee.employee_name} telah di-set ke 0 (Employee exempt dari PPh 21)",
                    indicator="blue",
                    alert=True
                )
                
                frappe.logger().info(
                    f"PPh 21 exemption applied for {employee.employee_name}. "
                    f"Amount: Rp {old_amount:,.0f} → Rp 0"
                )
                
    except Exception as e:
        frappe.logger().error(f"Error in validate_pph21_exemption: {str(e)}")

def before_calculate_tax(doc, method=None):
    """
    Alternative hook yang bisa dipanggil SEBELUM tax calculation.
    Lebih efisien karena mencegah calculation sama sekali.
    
    Hook ini bisa ditambahkan di custom Payroll Indonesia Settings
    atau di override function calculate_net_pay()
    """
    
    if not doc.employee:
        return
    
    employee = frappe.get_doc("Employee", doc.employee)
    
    if employee.get("exempt_from_pph21") == 1:
        # Flag untuk skip tax calculation
        # Custom property ini bisa dicek di logic Payroll Indonesia
        doc.skip_pph21_calculation = True
        return True
    
    return False


# =========================================
# Optional: Tambahan untuk Salary Structure
# =========================================

def validate_salary_structure_assignment(doc, method=None):
    """
    Hook untuk Salary Structure Assignment.
    Memberikan warning jika employee exempt tapi salary structure ada PPh 21.
    
    Tambahkan di hooks.py:
    doc_events = {
        "Salary Structure Assignment": {
            "validate": "your_custom_app.payroll_indonesia.overrides.pph21_exemption.validate_salary_structure_assignment"
        }
    }
    """
    
    if not doc.employee:
        return
    
    employee = frappe.get_doc("Employee", doc.employee)
    
    # Jika employee exempt dari PPh 21
    if employee.get("exempt_from_pph21") == 1:
        
        # Get salary structure
        salary_structure = frappe.get_doc("Salary Structure", doc.salary_structure)
        
        # Check jika ada PPh 21 di deductions
        has_pph21 = False
        for deduction in salary_structure.deductions:
            if deduction.salary_component in ["PPh 21", "PPH 21", "Income Tax"]:
                has_pph21 = True
                break
        
        if has_pph21:
            frappe.msgprint(
                msg=_(f"Perhatian: Employee {employee.employee_name} di-set exempt dari PPh 21, "
                      f"tetapi Salary Structure '{salary_structure.name}' masih memiliki komponen PPh 21. "
                      f"PPh 21 akan otomatis di-set ke 0 saat generate Salary Slip."),
                indicator="orange",
                alert=True
            )


# =========================================
# Utility Functions
# =========================================

def get_exempt_employees():
    """
    Utility function untuk mendapatkan list employee yang exempt dari PPh 21.
    Berguna untuk reporting atau bulk operations.
    
    Returns:
        list: List of employee names yang exempt
    """
    
    exempt_employees = frappe.get_all(
        "Employee",
        filters={"exempt_from_pph21": 1, "status": "Active"},
        fields=["name", "employee_name", "department", "designation"]
    )
    
    return exempt_employees


def bulk_set_pph21_exemption(employee_list, exempt=True):
    """
    Bulk operation untuk set/unset PPh 21 exemption untuk multiple employees.
    
    Args:
        employee_list (list): List of employee IDs
        exempt (bool): True untuk set exempt, False untuk remove exempt
    
    Returns:
        dict: Summary of operation
    """
    
    updated = []
    failed = []
    
    for emp_id in employee_list:
        try:
            employee = frappe.get_doc("Employee", emp_id)
            employee.exempt_from_pph21 = 1 if exempt else 0
            employee.save(ignore_permissions=True)
            updated.append(emp_id)
        except Exception as e:
            failed.append({"employee": emp_id, "error": str(e)})
    
    return {
        "success": len(updated),
        "failed": len(failed),
        "updated_employees": updated,
        "failed_employees": failed
    }


# =========================================
# Report Helper
# =========================================

def get_pph21_exemption_report(company=None, month=None, year=None):
    """
    Generate report untuk PPh 21 exemptions.
    
    Args:
        company (str): Company filter
        month (int): Month filter (1-12)
        year (int): Year filter
    
    Returns:
        list: Report data
    """
    
    filters = {"exempt_from_pph21": 1, "status": "Active"}
    
    if company:
        filters["company"] = company
    
    employees = frappe.get_all(
        "Employee",
        filters=filters,
        fields=["name", "employee_name", "department", "designation", 
                "company", "tax_status", "date_of_joining"]
    )
    
    # Jika ada filter bulan/tahun, cari salary slips
    if month and year:
        for emp in employees:
            salary_slips = frappe.get_all(
                "Salary Slip",
                filters={
                    "employee": emp.name,
                    "month": month,
                    "fiscal_year": year,
                    "docstatus": 1
                },
                fields=["name", "gross_pay", "net_pay"]
            )
            emp["salary_slips"] = salary_slips
    
    return employees