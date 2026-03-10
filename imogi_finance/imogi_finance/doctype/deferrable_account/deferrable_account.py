# Copyright (c) 2024, IMOGI and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class DeferrableAccount(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		default_periods: DF.Int | None
		expense_account: DF.Link | None
		is_active: DF.Check
		prepaid_account: DF.Link
	# end: auto-generated types

	pass
