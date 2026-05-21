"""Add Finance Monitor Dashboard shortcut to Towing Imogi workspace."""

from __future__ import annotations

import json

import frappe

from imogi_finance.workspace_utils import sanitize_workspace_missing_links


def execute():
	if not frappe.db.exists("Workspace", "Towing Imogi"):
		return

	ws = frappe.get_doc("Workspace", "Towing Imogi")
	content = json.loads(ws.content or "[]")

	already = any(
		block.get("type") == "shortcut"
		and block.get("data", {}).get("shortcut_name") == "Finance Monitor Dashboard"
		for block in content
	)
	if already:
		return

	content.append(
		{
			"id": "s_finance_monitor",
			"type": "shortcut",
			"data": {"shortcut_name": "Finance Monitor Dashboard", "col": 3},
		}
	)
	ws.content = json.dumps(content)

	if not any(s.link_to == "Finance Monitor Dashboard" for s in ws.shortcuts):
		ws.append(
			"shortcuts",
			{
				"type": "Report",
				"label": "Finance Monitor Dashboard",
				"link_to": "Finance Monitor Dashboard",
				"report_ref_doctype": "Sales Invoice",
			},
		)

	sanitize_workspace_missing_links(ws)
	ws.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Workspace")
