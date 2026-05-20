import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Payment Status: Select + standard list filter; align legacy Submitted rows."""
	create_custom_fields(
		{
			"Sales Order": [
				{
					"fieldname": "custom_payment_status",
					"label": "Payment Status",
					"fieldtype": "Select",
					"options": "\nDraft\nSubmitted\nSI Created\nPartial Paid\nPaid\nCancelled",
					"read_only": 1,
					"in_list_view": 1,
					"in_standard_filter": 1,
					"insert_after": "order_type",
					"translatable": 0,
				}
			]
		},
		update=True,
	)

	# SO submitted, tidak ada SI aktif, status lama masih Draft/kosong → samakan dengan UI "Submitted"
	frappe.db.sql(
		"""
		UPDATE `tabSales Order` so
		SET so.custom_payment_status = 'Submitted'
		WHERE so.docstatus = 1
		  AND IFNULL(NULLIF(TRIM(so.custom_payment_status), ''), 'Draft') = 'Draft'
		  AND NOT EXISTS (
			SELECT 1
			FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus < 2
			WHERE sii.sales_order = so.name
		  )
		"""
	)

	frappe.clear_cache(doctype="Sales Order")

