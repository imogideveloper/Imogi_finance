# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
from __future__ import annotations
import frappe
from frappe import _
from frappe.model.document import Document


class ItemTaxMapping(Document):
    def validate(self):
        self._validate_has_taxes()
        self._validate_account_company()

    def _validate_has_taxes(self):
        if not self.taxes:
            frappe.throw(_("Minimal satu baris akun pajak harus diisi."))

    def _validate_account_company(self):
        for row in self.taxes:
            if not row.account_head:
                continue
            account_company = frappe.db.get_value("Account", row.account_head, "company")
            if account_company and account_company != self.company:
                frappe.throw(
                    _("Baris #{0}: Akun <b>{1}</b> milik company <b>{2}</b>, bukan <b>{3}</b>.").format(
                        row.idx, row.account_head, account_company, self.company
                    )
                )