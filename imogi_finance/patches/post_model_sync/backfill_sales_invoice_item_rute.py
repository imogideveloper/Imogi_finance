"""
Backfill custom_rute on existing Sales Invoice Item rows created by the
towing invoice flow.

custom_rute (Rute) is a new field that wasn't populated by
_build_si_item_from_do() before it existed, so invoices created earlier
have it empty. Each such item's description ends with the originating
Delivery Order Towing name (see extract_delivery_order_from_item) - use
that to look up the DO's route (SO Towing Kendaraan.so_item_code) and
fill it in.
"""

import frappe


def execute():
	if not frappe.db.has_column("Sales Invoice Item", "custom_rute"):
		return

	from imogi_finance.overrides.sales_invoice_towing import extract_delivery_order_from_item

	rows = frappe.db.sql(
		"""
		SELECT name, description
		FROM `tabSales Invoice Item`
		WHERE description LIKE %s
			AND (custom_rute IS NULL OR custom_rute = '')
		""",
		("%DO-TOW-%",),
		as_dict=True,
	)
	if not rows:
		return

	do_names = set()
	item_do_map = {}
	for row in rows:
		do_name = extract_delivery_order_from_item({"description": row.description})
		if do_name:
			item_do_map[row.name] = do_name
			do_names.add(do_name)

	if not do_names:
		return

	do_routes = {
		r.delivery_order: r.so_item_code
		for r in frappe.db.sql(
			"""
			SELECT delivery_order, so_item_code
			FROM `tabSO Towing Kendaraan`
			WHERE delivery_order IN %(do_names)s
			""",
			{"do_names": list(do_names)},
			as_dict=True,
		)
	}

	for item_name, do_name in item_do_map.items():
		route = do_routes.get(do_name)
		if route:
			frappe.db.set_value(
				"Sales Invoice Item", item_name, "custom_rute", route, update_modified=False
			)

	frappe.db.commit()
