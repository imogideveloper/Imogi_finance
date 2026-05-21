"""Helpers for Workspace shortcut/link maintenance."""

from __future__ import annotations

import json

import frappe


def workspace_link_exists(link_to: str | None, link_type: str | None = None) -> bool:
	if not link_to:
		return False

	link_type = (link_type or "DocType").strip()
	if link_type == "DocType":
		return bool(frappe.db.exists("DocType", link_to))
	if link_type == "Report":
		return bool(frappe.db.exists("Report", link_to))
	if link_type == "Page":
		return bool(frappe.db.exists("Page", link_to))
	if link_type == "Dashboard":
		return bool(frappe.db.exists("Dashboard", link_to))
	return True


def sanitize_workspace_missing_links(ws) -> list[str]:
	"""Remove child shortcuts and content blocks pointing at missing DocTypes/Reports."""
	removed_labels: set[str] = set()

	for row in list(ws.shortcuts or []):
		link_to = row.link_to
		if not link_to:
			continue
		if workspace_link_exists(link_to, row.type):
			continue
		removed_labels.add(row.label or link_to)
		ws.remove(row)

	if not removed_labels:
		return []

	try:
		content = json.loads(ws.content or "[]")
	except (TypeError, json.JSONDecodeError):
		return sorted(removed_labels)

	cleaned = []
	for block in content:
		if block.get("type") == "shortcut":
			name = block.get("data", {}).get("shortcut_name")
			if name in removed_labels:
				continue
		cleaned.append(block)

	ws.content = json.dumps(cleaned)
	return sorted(removed_labels)
