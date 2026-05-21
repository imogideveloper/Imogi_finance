"""Access Studio workspace hanya untuk role Administrator."""

from __future__ import annotations

import frappe

WORKSPACE_NAME = "Access Studio"
ALLOWED_ROLES = ("Administrator",)


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE_NAME):
		return

	ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
	ws.roles = []
	for role in ALLOWED_ROLES:
		ws.append("roles", {"role": role})
	ws.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Workspace")
