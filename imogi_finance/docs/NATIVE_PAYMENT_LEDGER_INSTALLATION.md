# Installation & Setup Guide - Native Payment Ledger Enhancement

**Quick Start Guide untuk Deploy IMOGI Finance Native Payment Ledger Enhancement**

---

## 📋 Prerequisites

- ERPNext v15 or higher (Payment Ledger native support)
- IMOGI Finance app installed
- Python 3.10+
- Frappe Framework v15+

---

## 🚀 Installation

### Step 1: Pull Latest Code

```bash
cd frappe-bench/apps/imogi_finance
git pull origin main
```

### Step 2: Install/Update App

```bash
# If first time
bench --site [your-site] install-app imogi_finance

# If updating
bench --site [your-site] migrate
```

### Step 3: Clear Cache

```bash
bench --site [your-site] clear-cache
bench --site [your-site] clear-website-cache
bench restart
```

---

## ✅ Verification

### Test 1: Check Payment Ledger Exists

```bash
bench --site [your-site] execute imogi_finance.test_native_payment_ledger.test_payment_ledger
```

**Expected Output**:
```
======================================================================
TESTING NATIVE PAYMENT LEDGER FEATURES
======================================================================

[Test 1] Checking Payment Ledger Entry DocType...
✓ Payment Ledger Entry DocType exists

[Test 2] Counting Payment Ledger Entries...
✓ Total Payment Ledger Entries: XXX

[Test 3] Recent Payment Ledger Entries (last 10)...
Voucher         Party                Amount         Status
--------------------------------------------------------------------------------
PE-00001        SUPP-001             10,000,000     🟢 ADVANCE (Unallocated)
PE-00002        CUST-001              5,000,000     🔵 → Purchase Invoice: PI-00001

[Test 4] Finding Unallocated Advances...
✓ Found X unallocated advances

[Test 5] Checking Native Reports...
✓ Advance Payment Ledger report exists
✓ Payment Ledger report exists

[Test 6] Checking Payment Entry Integration...
✓ Purchase Invoice has 'advances' field
✓ Sales Invoice has 'advances' field

======================================================================
TEST SUMMARY
======================================================================

Native Payment Ledger is working! ✅
```

### Test 2: Verify Custom Dashboard Report

```bash
# Login to ERPNext
# Go to: Accounting → Reports → Advance Payment Dashboard
# Should see new report in list
```

### Test 3: Verify Expense Claim Integration

```bash
# Check hooks installed
bench --site [your-site] console
```

```python
import frappe
hooks = frappe.get_hooks("doc_events")
print(hooks.get("Expense Claim"))

# Expected output:
# {
#   'on_submit': ['imogi_finance.advance_payment_native.expense_claim_advances.link_employee_advances'],
#   ...
# }
```

---

## 🔧 Configuration

### 1. Setup Advance Accounts

Create default advance accounts if not exists:

```bash
bench --site [your-site] console
```

```python
import frappe

def create_advance_accounts():
    company = frappe.get_all("Company", limit=1)[0].name
    parent_account = "Current Assets - " + frappe.get_cached_value("Company", company, "abbr")
    
    accounts = [
        {
            "account_name": "Advances Paid - Supplier",
            "account_type": "Receivable",
            "parent_account": parent_account
        },
        {
            "account_name": "Advances Received - Customer",
            "account_type": "Receivable",
            "parent_account": parent_account
        },
        {
            "account_name": "Advances Paid - Employee",
            "account_type": "Receivable",
            "parent_account": parent_account
        }
    ]
    
    for acc in accounts:
        if not frappe.db.exists("Account", acc["account_name"] + " - " + frappe.get_cached_value("Company", company, "abbr")):
            doc = frappe.get_doc({
                "doctype": "Account",
                "account_name": acc["account_name"],
                "account_type": acc["account_type"],
                "parent_account": acc["parent_account"],
                "company": company,
                "is_group": 0
            })
            doc.insert()
            print(f"✓ Created: {doc.name}")
        else:
            print(f"⚠  Already exists: {acc['account_name']}")

create_advance_accounts()
frappe.db.commit()
```

### 2. Add Custom Report to Workspace

```bash
bench --site [your-site] console
```

```python
import frappe

def add_report_to_workspace():
    workspace = frappe.get_doc("Workspace", "Accounting")
    
    # Check if already exists
    existing = [l for l in workspace.links if l.label == "Advance Payment Dashboard"]
    if existing:
        print("⚠  Report link already exists in workspace")
        return
    
    # Add report link
    workspace.append("links", {
        "label": "Advance Payment Dashboard",
        "type": "Link",
        "link_type": "Report",
        "link_to": "Advance Payment Dashboard",
        "icon": "chart",
        "description": "Enhanced advance payment tracking with status visualization"
    })
    
    workspace.save()
    print("✓ Added Advance Payment Dashboard to Accounting workspace")

add_report_to_workspace()
frappe.db.commit()
```

### 3. Create Client Script for Expense Claim

**Via UI**: Setup → Customization → Client Script

**Name**: Expense Claim - Get Employee Advances  
**DocType**: Expense Claim  
**Script Type**: Form Script

**Script**:
```javascript
frappe.ui.form.on('Expense Claim', {
    refresh: function(frm) {
        if (frm.doc.docstatus === 0 && frm.doc.employee) {
            // Add "Get Employee Advances" button
            frm.add_custom_button(__('Get Employee Advances'), function() {
                get_employee_advances(frm);
            }, __('Get Items From'));
        }
    }
});

function get_employee_advances(frm) {
    frappe.call({
        method: 'imogi_finance.advance_payment_native.expense_claim_advances.get_employee_advances',
        args: {
            employee: frm.doc.employee,
            company: frm.doc.company,
            expense_claim: frm.doc.name
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                show_advance_dialog(frm, r.message);
            } else {
                frappe.msgprint(__('No unallocated advances found for this employee'));
            }
        }
    });
}

function show_advance_dialog(frm, advances) {
    let d = new frappe.ui.Dialog({
        title: __('Select Employee Advances'),
        fields: [
            {
                fieldname: 'advances_html',
                fieldtype: 'HTML'
            }
        ],
        primary_action_label: __('Allocate'),
        primary_action: function() {
            // Process allocations
            frappe.msgprint(__('Advances will be allocated on submit'));
            d.hide();
        }
    });
    
    // Build HTML table
    let html = '<table class="table table-bordered"><thead><tr>';
    html += '<th>Payment Entry</th><th>Date</th><th>Amount</th><th>Available</th><th>Allocate</th>';
    html += '</tr></thead><tbody>';
    
    advances.forEach(adv => {
        html += `<tr>
            <td>${adv.payment_entry}</td>
            <td>${adv.posting_date}</td>
            <td>${format_currency(adv.advance_amount)}</td>
            <td>${format_currency(adv.unallocated_amount)}</td>
            <td><input type="number" class="form-control" value="0" max="${adv.unallocated_amount}"></td>
        </tr>`;
    });
    
    html += '</tbody></table>';
    
    d.fields_dict.advances_html.$wrapper.html(html);
    d.show();
}
```

---

## 📊 Setup Dashboard

### Option 1: Add to Desk Page

```bash
bench --site [your-site] console
```

```python
import frappe

def create_dashboard_chart():
    # Create chart for advance payment overview
    chart = frappe.get_doc({
        "doctype": "Dashboard Chart",
        "chart_name": "Advance Payment Overview",
        "chart_type": "Report",
        "report_name": "Advance Payment Dashboard",
        "is_public": 1,
        "owner": "Administrator"
    })
    
    if not frappe.db.exists("Dashboard Chart", chart.chart_name):
        chart.insert()
        print(f"✓ Created chart: {chart.chart_name}")
    else:
        print("⚠  Chart already exists")
    
    # Add to Accounting dashboard
    dashboard = frappe.get_doc("Dashboard", "Accounting")
    
    existing = [c for c in dashboard.charts if c.chart == "Advance Payment Overview"]
    if not existing:
        dashboard.append("charts", {
            "chart": "Advance Payment Overview",
            "width": "Full"
        })
        dashboard.save()
        print("✓ Added chart to Accounting dashboard")
    else:
        print("⚠  Chart already in dashboard")

create_dashboard_chart()
frappe.db.commit()
```

---

## 🧪 Testing

### Create Test Advance Payment

```bash
bench --site [your-site] console
```

```python
import frappe
from frappe.utils import nowdate

def create_test_advance():
    # Get first supplier
    supplier = frappe.get_all("Supplier", limit=1)
    if not supplier:
        print("✗ No suppliers found")
        return
    
    supplier_name = supplier[0].name
    company = frappe.defaults.get_user_default("Company")
    
    # Create Payment Entry
    pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "payment_type": "Pay",
        "party_type": "Supplier",
        "party": supplier_name,
        "company": company,
        "posting_date": nowdate(),
        "paid_from": frappe.db.get_value("Company", company, "default_bank_account"),
        "paid_to": frappe.db.get_value("Party Account", {
            "parenttype": "Supplier",
            "parent": supplier_name,
            "company": company
        }, "account"),
        "paid_amount": 10000000,
        "received_amount": 10000000,
        "reference_no": "TEST-ADV-001",
        "reference_date": nowdate()
    })
    
    pe.insert()
    print(f"✓ Created Payment Entry: {pe.name}")
    
    # Submit
    pe.submit()
    print(f"✓ Submitted: {pe.name}")
    
    # Check Payment Ledger Entry
    ple = frappe.get_all(
        "Payment Ledger Entry",
        filters={"voucher_no": pe.name},
        fields=["name", "amount", "against_voucher_type"]
    )
    
    if ple:
        print(f"✓ Payment Ledger Entry created: {ple[0].name}")
        print(f"  Amount: {ple[0].amount:,.0f}")
        print(f"  Status: {'ADVANCE' if not ple[0].against_voucher_type else 'ALLOCATED'}")
    else:
        print("✗ No Payment Ledger Entry found!")
    
    return pe.name

# Run test
pe_name = create_test_advance()
frappe.db.commit()

print(f"\n✅ Test completed! Check Payment Entry: {pe_name}")
```

### Test Expense Claim Allocation

```python
def test_expense_claim_allocation():
    from imogi_finance.advance_payment_native.expense_claim_advances import get_employee_advances
    
    # Get first employee
    employee = frappe.get_all("Employee", limit=1)
    if not employee:
        print("✗ No employees found")
        return
    
    emp_name = employee[0].name
    company = frappe.defaults.get_user_default("Company")
    
    # Check advances
    advances = get_employee_advances(emp_name, company)
    
    if advances:
        print(f"✓ Found {len(advances)} employee advances:")
        for adv in advances:
            print(f"  - {adv['payment_entry']}: Rp {adv['unallocated_amount']:,.0f}")
    else:
        print("⚠  No employee advances found")
        print("  Create test employee advance first")

test_expense_claim_allocation()
```

---

## 🔄 Migration from Old APE Module

### Step 1: Verify Data Consistency

```python
import frappe

def verify_ape_vs_payment_ledger():
    """Compare old APE data with Payment Ledger"""
    
    # Get all APE entries
    ape_entries = frappe.get_all(
        "Advance Payment Entry",
        filters={"docstatus": 1},
        fields=["name", "payment_entry", "total_amount", "allocated_amount", "unallocated_amount"]
    )
    
    print(f"Found {len(ape_entries)} Advance Payment Entries")
    
    discrepancies = []
    
    for ape in ape_entries:
        # Check corresponding Payment Ledger
        ple_total = frappe.db.sql("""
            SELECT 
                SUM(amount) as total,
                SUM(COALESCE(allocated_amount, 0)) as allocated
            FROM `tabPayment Ledger Entry`
            WHERE voucher_no = %s
              AND delinked = 0
        """, ape.payment_entry, as_dict=True)
        
        if ple_total:
            ple = ple_total[0]
            if abs(ple.total - ape.total_amount) > 0.01:
                discrepancies.append({
                    "ape": ape.name,
                    "ape_amount": ape.total_amount,
                    "ple_amount": ple.total,
                    "diff": ple.total - ape.total_amount
                })
    
    if discrepancies:
        print(f"\n⚠  Found {len(discrepancies)} discrepancies:")
        for d in discrepancies:
            print(f"  {d['ape']}: APE={d['ape_amount']:,.0f} vs PLE={d['ple_amount']:,.0f} (diff={d['diff']:,.0f})")
    else:
        print("\n✓ All data consistent between APE and Payment Ledger")
    
    return len(discrepancies) == 0

# Run verification
verify_ape_vs_payment_ledger()
```

### Step 2: Archive Old APE Module

```python
def archive_ape_module():
    """Mark APE as deprecated without deleting"""
    
    # Add archived flag to all APE entries
    frappe.db.sql("""
        UPDATE `tabAdvance Payment Entry`
        SET custom_archived = 1,
            custom_archive_date = NOW(),
            custom_archive_note = 'Migrated to Native Payment Ledger'
        WHERE docstatus = 1
    """)
    
    frappe.db.commit()
    print("✓ All APE entries marked as archived")
    
    # Disable APE DocType (don't delete, keep for reference)
    if frappe.db.exists("DocType", "Advance Payment Entry"):
        dt = frappe.get_doc("DocType", "Advance Payment Entry")
        dt.disabled = 1
        dt.save()
        print("✓ APE DocType disabled (kept for reference)")

# Run if ready to migrate
# archive_ape_module()
```

---

## 🐛 Troubleshooting Installation

### Issue: Report not showing

```bash
# Rebuild report list
bench --site [your-site] --force rebuild-global-search
bench --site [your-site] clear-cache
```

### Issue: Hooks not working

```bash
# Check hooks loaded
bench --site [your-site] console
```

```python
import frappe
print(frappe.get_hooks("doc_events"))
```

### Issue: Import errors

```bash
# Check module exists
ls -la apps/imogi_finance/imogi_finance/advance_payment_native/

# Reinstall
bench --site [your-site] uninstall-app imogi_finance --no-backup
bench --site [your-site] install-app imogi_finance
```

---

## ✅ Post-Installation Checklist

- [ ] Native Payment Ledger verified working
- [ ] Custom dashboard report accessible
- [ ] Expense Claim integration working
- [ ] Client script added for Expense Claim
- [ ] Test advance payment created successfully
- [ ] Test allocation working
- [ ] Users trained on native workflow
- [ ] Documentation distributed
- [ ] Old APE module deprecated (if applicable)

---

## 📚 Next Steps

1. ✅ Read [User Guide](./NATIVE_PAYMENT_LEDGER_USER_GUIDE.md)
2. ✅ Train accounting team
3. ✅ Create test scenarios
4. ✅ Go live with pilot users
5. ✅ Monitor for 2 weeks
6. ✅ Roll out to all users

---

**Installation Support**: imogi.indonesia@gmail.com  
**Version**: 1.0  
**Last Updated**: 2026-01-23
