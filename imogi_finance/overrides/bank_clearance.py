from __future__ import annotations

import frappe
from frappe import _, msgprint
from frappe.utils import getdate
from erpnext.accounts.doctype.bank_clearance.bank_clearance import BankClearance


class CustomBankClearance(BankClearance):
	"""Fixes an ERPNext regression where clearance_date_updated is referenced
	before assignment when payment_entries is empty (UnboundLocalError)."""

	@frappe.whitelist()
	def update_clearance_date(self):
		clearance_date_updated = False
		for d in self.get("payment_entries"):
			if d.clearance_date:
				if not d.payment_document:
					frappe.throw(_("Row #{0}: Payment document is required to complete the transaction"))

				if d.cheque_date and getdate(d.clearance_date) < getdate(d.cheque_date):
					frappe.throw(
						_("Row #{0}: For {1} Clearance date {2} cannot be before Cheque Date {3}").format(
							d.idx,
							frappe.utils.get_link_to_form(d.payment_document, d.payment_entry),
							d.clearance_date,
							d.cheque_date,
						)
					)

			if d.clearance_date or self.include_reconciled_entries:
				if not d.clearance_date:
					d.clearance_date = None

				if d.payment_document == "Sales Invoice":
					frappe.db.set_value(
						"Sales Invoice Payment",
						{"parent": d.payment_entry, "account": self.get("account"), "amount": [">", 0]},
						"clearance_date",
						d.clearance_date,
					)
				else:
					frappe.db.set_value(
						d.payment_document, d.payment_entry, "clearance_date", d.clearance_date
					)

				clearance_date_updated = True

		if clearance_date_updated:
			self.get_payment_entries()
			msgprint(_("Clearance Date updated"))
		else:
			msgprint(_("Clearance Date not mentioned"))
