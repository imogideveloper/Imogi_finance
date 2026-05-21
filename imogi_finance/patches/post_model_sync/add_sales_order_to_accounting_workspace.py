"""Tambah shortcut Sales Order di workspace Accounting (selaras Sales Invoice)."""

from __future__ import annotations

import json

import frappe

from imogi_finance.workspace_utils import sanitize_workspace_missing_links

WORKSPACE = "Accounting"
DOCTYPE = "Sales Order"


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	ws = frappe.get_doc("Workspace", WORKSPACE)
	content = json.loads(ws.content or "[]")

	if not any(
		block.get("type") == "shortcut" and block.get("data", {}).get("shortcut_name") == DOCTYPE
		for block in content
	):
		# Sisipkan setelah Sales Invoice di blok shortcuts bila ada
		inserted = False
		for i, block in enumerate(content):
			if block.get("type") == "shortcut" and block.get("data", {}).get("shortcut_name") == "Sales Invoice":
				content.insert(
					i + 1,
					{"id": "s_sales_order_acct", "type": "shortcut", "data": {"shortcut_name": DOCTYPE, "col": 3}},
				)
				inserted = True
				break
		if not inserted:
			content.append(
				{"id": "s_sales_order_acct", "type": "shortcut", "data": {"shortcut_name": DOCTYPE, "col": 3}}
			)
		ws.content = json.dumps(content)

	if not any(s.link_to == DOCTYPE for s in ws.shortcuts):
		ws.append(
			"shortcuts",
			{
				"type": "DocType",
				"label": DOCTYPE,
				"link_to": DOCTYPE,
				"color": "Blue",
			},
		)

	sanitize_workspace_missing_links(ws)
	ws.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Workspace")
