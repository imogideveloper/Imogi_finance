# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate, formatdate


def execute(filters=None):
	"""
	VAT OUT Batch Register Report
	
	Returns columns and data for VAT OUT batch monitoring and reconciliation.
	Includes drill-down to batch details and group-level breakdown.
	"""
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart_data(data, filters)
	
	return columns, data, None, chart


def get_columns():
	"""Define report columns"""
	return [
		{
			"label": _("Batch"),
			"fieldname": "batch_name",
			"fieldtype": "Link",
			"options": "VAT OUT Batch",
			"width": 180
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 150
		},
		{
			"label": _("Period From"),
			"fieldname": "date_from",
			"fieldtype": "Date",
			"width": 100
		},
		{
			"label": _("Period To"),
			"fieldname": "date_to",
			"fieldtype": "Date",
			"width": 100
		},
		{
			"label": _("Status"),
			"fieldname": "docstatus",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("Upload Status"),
			"fieldname": "coretax_upload_status",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("Groups"),
			"fieldname": "group_count",
			"fieldtype": "Int",
			"width": 80
		},
		{
			"label": _("Invoices"),
			"fieldname": "invoice_count",
			"fieldtype": "Int",
			"width": 90
		},
		{
			"label": _("Total DPP"),
			"fieldname": "total_dpp",
			"fieldtype": "Currency",
			"width": 140
		},
		{
			"label": _("Total PPN"),
			"fieldname": "total_ppn",
			"fieldtype": "Currency",
			"width": 140
		},
		{
			"label": _("Template Version"),
			"fieldname": "template_version",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("Exported On"),
			"fieldname": "exported_on",
			"fieldtype": "Datetime",
			"width": 150
		},
		{
			"label": _("Submitted By"),
			"fieldname": "submitted_by",
			"fieldtype": "Link",
			"options": "User",
			"width": 150
		},
		{
			"label": _("Submitted On"),
			"fieldname": "submitted_on",
			"fieldtype": "Datetime",
			"width": 150
		}
	]


def get_data(filters):
	"""Query and aggregate VAT OUT batch data from Sales Invoices"""
	conditions = get_conditions(filters)
	
	data = frappe.db.sql(f"""
		SELECT 
			b.name as batch_name,
			b.company,
			b.date_from,
			b.date_to,
			CASE 
				WHEN b.docstatus = 0 THEN 'Draft'
				WHEN b.docstatus = 1 THEN 'Submitted'
				WHEN b.docstatus = 2 THEN 'Cancelled'
			END as docstatus,
			b.coretax_upload_status,
			COUNT(DISTINCT si.out_fp_group_id) as group_count,
			COUNT(DISTINCT si.name) as invoice_count,
			COALESCE(SUM(si.out_fp_dpp), 0) as total_dpp,
			COALESCE(SUM(si.out_fp_ppn), 0) as total_ppn,
			b.template_version,
			b.exported_on,
			b.owner as submitted_by,
			b.modified as submitted_on
		FROM `tabVAT OUT Batch` b
		LEFT JOIN `tabSales Invoice` si ON si.out_fp_batch = b.name AND si.docstatus = 1
		WHERE 1=1 {conditions}
		GROUP BY b.name
		ORDER BY b.date_from DESC, b.creation DESC
	""", filters, as_dict=1)
	
	return data


def get_conditions(filters):
	"""Build WHERE clause conditions"""
	conditions = ""
	
	if filters.get("company"):
		conditions += " AND b.company = %(company)s"
	
	if filters.get("from_date"):
		conditions += " AND b.date_from >= %(from_date)s"
	
	if filters.get("to_date"):
		conditions += " AND b.date_to <= %(to_date)s"
	
	if filters.get("docstatus"):
		if filters.get("docstatus") == "Draft":
			conditions += " AND b.docstatus = 0"
		elif filters.get("docstatus") == "Submitted":
			conditions += " AND b.docstatus = 1"
		elif filters.get("docstatus") == "Cancelled":
			conditions += " AND b.docstatus = 2"
	
	if filters.get("upload_status"):
		conditions += " AND b.coretax_upload_status = %(upload_status)s"
	
	return conditions


def get_chart_data(data, filters):
	"""Generate chart for batch statistics"""
	if not data:
		return None
	
	# Group by month
	labels = []
	dpp_values = []
	ppn_values = []
	
	monthly_data = {}
	for row in data:
		if row.get("date_from"):
			month_key = getdate(row.get("date_from")).strftime("%Y-%m")
			if month_key not in monthly_data:
				monthly_data[month_key] = {"dpp": 0, "ppn": 0}
			monthly_data[month_key]["dpp"] += flt(row.get("total_dpp"))
			monthly_data[month_key]["ppn"] += flt(row.get("total_ppn"))
	
	# Sort by month
	sorted_months = sorted(monthly_data.keys())
	for month in sorted_months:
		labels.append(month)
		dpp_values.append(monthly_data[month]["dpp"])
		ppn_values.append(monthly_data[month]["ppn"])
	
	chart = {
		"data": {
			"labels": labels,
			"datasets": [
				{
					"name": _("Total DPP"),
					"values": dpp_values
				},
				{
					"name": _("Total PPN"),
					"values": ppn_values
				}
			]
		},
		"type": "bar",
		"colors": ["#469fcf", "#f39c12"]
	}
	
	return chart
