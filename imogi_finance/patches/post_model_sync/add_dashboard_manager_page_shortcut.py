"""Garage: add the Dashboard Manager page shortcut at the top of the workspace."""

from __future__ import annotations

import json

import frappe

from imogi_finance.workspace_utils import sanitize_workspace_missing_links

PAGE_NAME = "dashboard-manager"
WORKSPACE_NAME = "Garage"
SHORTCUT_LABEL = "Dashboard Manager"
HEADER_BLOCK_ID = "hdr_dashboard_manager"
SHORTCUT_BLOCK_ID = "s_dashboard_manager"


def execute():
	# sanitize_workspace_missing_links() below strips any shortcut whose link_to doesn't exist
	# yet - post_model_sync patches can run before this app's own Page JSON has been synced
	# into the DB, so force it here rather than silently losing the shortcut we just added.
	frappe.reload_doc("Imogi Finance", "page", "dashboard_manager")

	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
	content = json.loads(ws.content or "[]")

	# idempotent: drop any previous run's blocks before re-inserting them at the top
	content = [b for b in content if b.get("id") not in (HEADER_BLOCK_ID, SHORTCUT_BLOCK_ID)]
	content = [
		{
			"id": HEADER_BLOCK_ID,
			"type": "header",
			"data": {"text": '<span class="h4"><b>Dashboard</b></span>', "col": 12},
		},
		{
			"id": SHORTCUT_BLOCK_ID,
			"type": "shortcut",
			"data": {"shortcut_name": SHORTCUT_LABEL, "col": 4},
		},
		*content,
	]
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
			"color": "Blue",
			"icon": "dashboard",
		},
	)

	sanitize_workspace_missing_links(ws)
	ws.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Workspace")
