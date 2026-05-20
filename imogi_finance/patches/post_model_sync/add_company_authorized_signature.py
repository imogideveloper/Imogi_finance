import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Attach Image on Company for invoice/receipt print blocks (e.g. Hormat Kami)."""
	create_custom_fields(
		{
			"Company": [
				{
					"fieldname": "authorized_signature",
					"label": "Tanda Tangan Resmi (Cetak)",
					"fieldtype": "Attach Image",
					"insert_after": "company_logo",
					"description": "Gambar tanda tangan/stempel untuk print Sales Invoice dan dokumen serupa.",
				}
			]
		},
		update=True,
	)
	frappe.clear_cache(doctype="Company")
