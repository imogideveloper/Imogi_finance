"""Finance Monitor: add Dashboard Management shortcut next to Finance Monitor Dashboard."""

from __future__ import annotations

import json

import frappe

from imogi_finance.workspace_utils import sanitize_workspace_missing_links

REPORT_NAME = "Dashboard Management"
WORKSPACE_NAME = "Finance Monitor"
SHORTCUT_LABEL = REPORT_NAME
NEW_BLOCK_ID = "s_dm"
ANCHOR_BLOCK_ID = "s_fmd"  # existing "Finance Monitor Dashboard" shortcut block id


def execute():
	# sanitize_workspace_missing_links() below strips any shortcut whose
	# link_to doesn't exist yet - post_model_sync patches can run before
	# this app's own Report JSON has been synced into the DB, so force it
	# here rather than silently losing the shortcut we're about to add.
	frappe.reload_doc("Imogi Finance", "report", "dashboard_management")

	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
	content = json.loads(ws.content or "[]")

	# idempotent: strip any previous run's block first
	content = [b for b in content if b.get("id") != NEW_BLOCK_ID]

	new_block = {
		"id": NEW_BLOCK_ID,
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
		content.append(new_block)

	ws.content = json.dumps(content)

	for row in list(ws.shortcuts or []):
		if row.link_to == REPORT_NAME:
			ws.remove(row)
	ws.append(
		"shortcuts",
		{
			"type": "Report",
			"label": SHORTCUT_LABEL,
			"link_to": REPORT_NAME,
			"report_ref_doctype": "Sales Invoice",
			"color": "Blue",
			"icon": "dashboard",
		},
	)

	sanitize_workspace_missing_links(ws)
	ws.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Workspace")
