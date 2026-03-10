# Copyright (c) 2026, Imogi and contributors
# For license information, please see license.txt

import frappe


def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	"""Define columns for the report"""
	return [
		{
			"fieldname": "voucher_type",
			"label": frappe._("Voucher Type"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "voucher_no",
			"label": frappe._("Voucher No"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 180
		},
		{
			"fieldname": "party_type",
			"label": frappe._("Party Type"),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "party",
			"label": frappe._("Party"),
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 180
		},
		{
			"fieldname": "posting_date",
			"label": frappe._("Posting Date"),
			"fieldtype": "Date",
			"width": 100
		},
		{
			"fieldname": "account",
			"label": frappe._("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 180
		},
		{
			"fieldname": "amount",
			"label": frappe._("Advance Amount"),
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"fieldname": "allocated_amount",
			"label": frappe._("Allocated Amount"),
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"fieldname": "outstanding_amount",
			"label": frappe._("Outstanding Amount"),
			"fieldtype": "Currency",
			"width": 150
		},
		{
			"fieldname": "allocation_status",
			"label": frappe._("Allocation Status"),
			"fieldtype": "Data",
			"width": 150
		}
	]


def get_data(filters):
	"""Get advance payment data from Payment Ledger Entry"""
	conditions = get_conditions(filters)
	
	query = """
		SELECT
			ple.voucher_type,
			ple.voucher_no,
			ple.party_type,
			ple.party,
			ple.posting_date,
			ple.account,
			ABS(SUM(ple.amount)) as amount
		FROM
			`tabPayment Ledger Entry` ple
		WHERE
			ple.docstatus = 1
			AND ple.against_voucher_type = ''
			{conditions}
		GROUP BY
			ple.voucher_type, ple.voucher_no, ple.party_type, ple.party, 
			ple.posting_date, ple.account
		ORDER BY
			ple.posting_date DESC, ple.voucher_no
	""".format(conditions=conditions)
	
	data = frappe.db.sql(query, filters, as_dict=1)
	
	# Calculate allocated and outstanding amounts properly
	for row in data:
		allocated = get_allocated_amount(row.voucher_type, row.voucher_no)
		row["allocated_amount"] = allocated
		row["outstanding_amount"] = row["amount"] - allocated
		
		# Calculate allocation status
		row["allocation_status"] = get_allocation_status(row["amount"], allocated)
	
	# Filter by allocation status if specified
	if filters.get("allocation_status"):
		data = [row for row in data if row["allocation_status"] == filters.get("allocation_status")]
	
	return data


def get_conditions(filters):
	"""Build WHERE conditions based on filters"""
	conditions = []
	
	if filters.get("company"):
		conditions.append("AND ple.company = %(company)s")
	
	if filters.get("party_type"):
		conditions.append("AND ple.party_type = %(party_type)s")
	
	if filters.get("party"):
		conditions.append("AND ple.party = %(party)s")
	
	if filters.get("from_date"):
		conditions.append("AND ple.posting_date >= %(from_date)s")
	
	if filters.get("to_date"):
		conditions.append("AND ple.posting_date <= %(to_date)s")
	
	if filters.get("account"):
		conditions.append("AND ple.account = %(account)s")
	
	return " ".join(conditions)


def get_allocated_amount(voucher_type, voucher_no):
	"""Get total allocated amount for an advance payment"""
	allocated = frappe.db.sql("""
		SELECT SUM(ABS(amount)) as allocated
		FROM `tabPayment Ledger Entry`
		WHERE 
			against_voucher_type = %s
			AND against_voucher_no = %s
			AND docstatus = 1
	""", (voucher_type, voucher_no))
	
	return allocated[0][0] if allocated and allocated[0][0] else 0


def get_allocation_status(amount, allocated_amount):
	"""Calculate allocation status based on amount and allocated amount"""
	if not amount or amount == 0:
		return "Unallocated"
	
	if not allocated_amount or allocated_amount == 0:
		return "Unallocated"
	elif allocated_amount >= abs(amount):
		return "Fully Allocated"
	else:
		return "Partially Allocated"
