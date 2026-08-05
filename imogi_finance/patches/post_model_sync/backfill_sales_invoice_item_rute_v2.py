"""
Second pass backfill for Sales Invoice Item.custom_rute.

The first pass (backfill_sales_invoice_item_rute) matched items by parsing
the Delivery Order Towing name out of the item's Description text, which
misses invoices whose description doesn't end with the DO name (older
invoices predating that format). This pass instead matches directly via
Delivery Order Towing.sales_invoice (always set once a DO is invoiced) and
nomor_rangka, since item_name is always built as
f"Jasa Towing - {nomor_rangka}" - no text parsing required.
"""

import frappe


def execute():
	if not frappe.db.has_column("Sales Invoice Item", "custom_rute"):
		return
	if not frappe.db.has_column("Delivery Order Towing", "sales_invoice"):
		return

	dos = frappe.db.sql(
		"""
		SELECT name, sales_invoice, nomor_rangka
		FROM `tabDelivery Order Towing`
		WHERE sales_invoice IS NOT NULL AND sales_invoice != '' AND nomor_rangka IS NOT NULL
		""",
		as_dict=True,
	)
	if not dos:
		return

	do_names = [d.name for d in dos]
	routes = {
		r.delivery_order: r.so_item_code
		for r in frappe.db.sql(
			"""
			SELECT delivery_order, so_item_code
			FROM `tabSO Towing Kendaraan`
			WHERE delivery_order IN %(do_names)s
			""",
			{"do_names": do_names},
			as_dict=True,
		)
	}

	for do in dos:
		route = routes.get(do.name)
		if not route:
			continue

		frappe.db.sql(
			"""
			UPDATE `tabSales Invoice Item`
			SET custom_rute = %(route)s
			WHERE parent = %(sales_invoice)s
				AND item_name = %(item_name)s
				AND (custom_rute IS NULL OR custom_rute = '')
			""",
			{
				"route": route,
				"sales_invoice": do.sales_invoice,
				"item_name": f"Jasa Towing - {do.nomor_rangka}",
			},
		)

	frappe.db.commit()
