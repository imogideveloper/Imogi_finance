# Copyright (c) 2026, Imogi and contributors
"""Keep SO unit price visible on DP Sales Invoices while billing a lower amount."""

from __future__ import annotations

import erpnext.controllers.taxes_and_totals as taxes_and_totals_module

_ORIGINAL_CALCULATE_ITEM_VALUES = taxes_and_totals_module.calculate_taxes_and_totals.calculate_item_values


def _patched_calculate_item_values(self):
	if not getattr(self.doc.flags, "imogi_preserve_dp_lines", False):
		return _ORIGINAL_CALCULATE_ITEM_VALUES(self)

	for item in self._items:
		preserved = getattr(item, "_imogi_preserved", None)
		if not preserved:
			continue

		item.rate = preserved["rate"]
		item.qty = preserved["qty"]
		item.amount = preserved["amount"]
		item.net_amount = preserved["amount"]
		item.net_rate = preserved["net_rate"]
		item.price_list_rate = preserved["contract_rate"]
		if hasattr(item, "imogi_contract_rate"):
			item.imogi_contract_rate = preserved["contract_rate"]

		self._set_in_company_currency(
			item, ["price_list_rate", "rate", "net_rate", "amount", "net_amount"]
		)
		item.item_tax_amount = 0.0


def apply_patch() -> None:
	taxes_and_totals_module.calculate_taxes_and_totals.calculate_item_values = _patched_calculate_item_values
