"""Garage: add the Pusat Approval page shortcut beside Dashboard Manager."""

from __future__ import annotations

import json

import frappe

from imogi_finance.workspace_utils import sanitize_workspace_missing_links

PAGE_NAME = "approval-center"
WORKSPACE_NAME = "Garage"
SHORTCUT_LABEL = "Pusat Approval"
SHORTCUT_BLOCK_ID = "s_approval_center"
ANCHOR_BLOCK_ID = "s_dashboard_manager"


def execute():
	# sanitize_workspace_missing_links() strips shortcuts whose target doesn't exist yet, and a
	# post_model_sync patch can run before this app's own Page JSON is in the DB - so force it.
	frappe.reload_doc("Imogi Finance", "page", "approval_center")

	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
	content = json.loads(ws.content or "[]")

	# idempotent: drop any previous run's block, then re-insert after Dashboard Manager
	content = [b for b in content if b.get("id") != SHORTCUT_BLOCK_ID]
	new_block = {
		"id": SHORTCUT_BLOCK_ID,
		"type": "shortcut",
		"data": {"shortcut_name": SHORTCUT_LABEL, "col": 4},
	}
	inserted = False
	for idx, block in enumerate(content):
		if block.get("id") == ANCHOR_BLOCK_ID:
			content.insert(idx + 1, new_block)
			inserted = True
			break
	if not inserted:
		content.insert(0, new_block)

	ws.content = json.dumps(content)

	for row in list(ws.shortcuts or []):
		if row.link_to == PAGE_NAME:
			ws.remove(row)
	ws.append(
		"shortcuts",
		{
			"type": "Page",
			"label": SHORTCUT_LABEL,
			"link_to": PAGE_NAME,
			"color": "Orange",
			"icon": "check",
		},
	)

	sanitize_workspace_missing_links(ws)
	ws.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Workspace")
