from __future__ import annotations

import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

from imogi_finance.services.letter_template_service import render_payment_letter_html
from imogi_finance.services.sales_invoice_list_status import apply_imogi_status_and_late_days


class CustomSalesInvoice(SalesInvoice):
    def get_payment_letter_html(self):
        return render_payment_letter_html(self)

    def set_status(self, update=False, status=None, update_modified=True):
        super().set_status(update=False, status=status, update_modified=False)
        apply_imogi_status_and_late_days(self)
        if update:
            self.db_set("status", self.status, update_modified=update_modified)
            self.db_set("imogi_late_days", self.imogi_late_days, update_modified=False)


@frappe.whitelist()
def get_sales_invoice_payment_letter(name: str):
    doc = frappe.get_doc("Sales Invoice", name)
    return doc.get_payment_letter_html()
