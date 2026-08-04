"""
Backfill komisi_is_override for existing Delivery Order Towing records.

komisi_is_override is a new flag introduced to distinguish "override
intentionally set to 0" from "never overridden" (previously both looked
like 0 and were treated as "use the Towing Commission Rate"). Any DO that
already had a positive komisi_override value before this flag existed was
an active manual override — mark it as such so the Rekap Komisi Driver
report keeps showing that value instead of silently falling back to the
rate lookup.
"""

import frappe


def execute():
	doctype = "Delivery Order Towing"

	if not frappe.db.exists("DocType", doctype):
		return
	if not frappe.db.has_column(doctype, "komisi_is_override"):
		return
	if not frappe.db.has_column(doctype, "komisi_override"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabDelivery Order Towing`
		SET komisi_is_override = 1
		WHERE komisi_override > 0
			AND (komisi_is_override IS NULL OR komisi_is_override = 0)
		"""
	)
	frappe.db.commit()
