"""Drop workspace shortcuts that point to DocTypes/Reports not installed on this site."""

from __future__ import annotations

import frappe

from imogi_finance.workspace_utils import sanitize_workspace_missing_links

WORKSPACES = (
	"FINANCE IMOGI",
	"Receivables",
	"Accounting",
	"Finance Monitor",
	"Access Studio",
)


def execute():
	for name in WORKSPACES:
		if not frappe.db.exists("Workspace", name):
			continue
		ws = frappe.get_doc("Workspace", name)
		removed = sanitize_workspace_missing_links(ws)
		if removed:
			ws.save(ignore_permissions=True)
			frappe.logger().info(
				"Removed missing workspace shortcuts from %s: %s", name, ", ".join(removed)
			)

	frappe.clear_cache(doctype="Workspace")
