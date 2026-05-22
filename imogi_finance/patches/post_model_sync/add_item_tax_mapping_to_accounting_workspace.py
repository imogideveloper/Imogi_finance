"""Tambah shortcut Item Tax Mapping di workspace Accounting (kolom kanan bawah shortcuts)."""

from __future__ import annotations

import json

import frappe

from imogi_finance.workspace_utils import sanitize_workspace_missing_links

WORKSPACE = "Accounting"
SHORTCUT_LABEL = "Item Tax Mapping"
LINK_TO = "Item Tax Template"
# Setelah Learn Accounting = kolom ke-4 baris ke-3 (posisi kotak merah di layout 4 kolom)
INSERT_AFTER = ("Learn Accounting", "General Ledger", "Sales Order")


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	ws = frappe.get_doc("Workspace", WORKSPACE)
	content = json.loads(ws.content or "[]")

	if not _has_content_shortcut(content):
		inserted = False
		for anchor in INSERT_AFTER:
			for i, block in enumerate(content):
				if block.get("type") != "shortcut":
					continue
				if block.get("data", {}).get("shortcut_name") != anchor:
					continue
				content.insert(
					i + 1,
					{
						"id": "s_item_tax_mapping_acct",
						"type": "shortcut",
						"data": {"shortcut_name": SHORTCUT_LABEL, "col": 3},
					},
				)
				inserted = True
				break
			if inserted:
				break

		if not inserted:
			# Sisipkan sebelum header Reports & Masters / spacer setelah blok shortcuts
			for i, block in enumerate(content):
				if block.get("type") == "header" and "Reports" in (block.get("data") or {}).get(
					"text", ""
				):
					content.insert(
						i,
						{
							"id": "s_item_tax_mapping_acct",
							"type": "shortcut",
							"data": {"shortcut_name": SHORTCUT_LABEL, "col": 3},
						},
					)
					inserted = True
					break

		if not inserted:
			content.append(
				{
					"id": "s_item_tax_mapping_acct",
					"type": "shortcut",
					"data": {"shortcut_name": SHORTCUT_LABEL, "col": 3},
				}
			)

		ws.content = json.dumps(content)

	if not _has_shortcut_row(ws):
		ws.append(
			"shortcuts",
			{
				"type": "DocType",
				"label": SHORTCUT_LABEL,
				"link_to": LINK_TO,
				"color": "Purple",
				"icon": "percentage",
				"description": "Mapping pajak per produk (Item Tax Template).",
			},
		)

	sanitize_workspace_missing_links(ws)
	ws.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Workspace")


def _has_content_shortcut(content: list) -> bool:
	return any(
		block.get("type") == "shortcut"
		and block.get("data", {}).get("shortcut_name") == SHORTCUT_LABEL
		for block in content
	)


def _has_shortcut_row(ws) -> bool:
	return any(
		(s.label or "") == SHORTCUT_LABEL or (s.link_to or "") == LINK_TO for s in ws.shortcuts or []
	)
