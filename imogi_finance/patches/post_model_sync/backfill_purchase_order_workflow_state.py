"""Isi workflow_state untuk Purchase Order yang sudah ada sebelum workflow dipasang.

Begitu sebuah Workflow aktif terpasang pada satu doctype, Frappe mengharapkan setiap dokumen
punya nilai workflow_state. Dokumen lama dibuat sebelum itu ada, jadi nilainya NULL - list view
menampilkan kolom kosong dan get_transitions() melempar WorkflowStateError saat dokumennya
dibuka. Backfill ini memetakan docstatus yang sudah ada ke state yang setara, sehingga PO lama
tidak ikut masuk antrean approval dan tidak terlihat rusak.
"""

from __future__ import annotations

import frappe

WORKFLOW = "Purchase Order Workflow"

# docstatus -> state yang setara maknanya
BY_DOCSTATUS = {
	0: "Draft",
	1: "Approved",
	2: "Rejected",
}


def execute():
	if not frappe.db.exists("Workflow", WORKFLOW):
		return
	if not frappe.db.has_column("Purchase Order", "workflow_state"):
		return

	for docstatus, state in BY_DOCSTATUS.items():
		frappe.db.sql(
			"""
			update `tabPurchase Order`
			set workflow_state = %(state)s
			where docstatus = %(docstatus)s
			  and (workflow_state is null or workflow_state = '')
			""",
			{"state": state, "docstatus": docstatus},
		)

	frappe.db.commit()
