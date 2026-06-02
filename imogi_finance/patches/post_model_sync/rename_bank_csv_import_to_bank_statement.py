from __future__ import annotations

import json

import frappe
from frappe.model.rename_doc import rename_doc


OLD_DTYPE = "Bank CSV Import"
NEW_DTYPE = "Bank Statement"


def execute():
	_rename_doctype_if_needed()
	_update_workspace_links()


def _rename_doctype_if_needed():
	old_exists = frappe.db.exists("DocType", OLD_DTYPE)
	new_exists = frappe.db.exists("DocType", NEW_DTYPE)

	if old_exists and not new_exists:
		rename_doc("DocType", OLD_DTYPE, NEW_DTYPE, force=True, ignore_permissions=True)
		frappe.db.commit()


def _update_workspace_links():
	workspaces = frappe.get_all("Workspace", fields=["name", "content"], limit_page_length=0)
	for ws in workspaces:
		doc = frappe.get_doc("Workspace", ws.name)
		changed = False

		for row in doc.shortcuts or []:
			if row.link_to == OLD_DTYPE:
				row.link_to = NEW_DTYPE
				if row.label == OLD_DTYPE:
					row.label = NEW_DTYPE
				changed = True

		for row in doc.links or []:
			if row.link_to == OLD_DTYPE:
				row.link_to = NEW_DTYPE
				if row.label == OLD_DTYPE:
					row.label = NEW_DTYPE
				changed = True

		if doc.content:
			try:
				blocks = json.loads(doc.content)
			except Exception:
				blocks = None
			if isinstance(blocks, list):
				rebuilt = []
				for block in blocks:
					data = (block or {}).get("data") or {}
					if data.get("shortcut_name") == OLD_DTYPE:
						data["shortcut_name"] = NEW_DTYPE
						changed = True
					if data.get("card_name") == OLD_DTYPE:
						data["card_name"] = NEW_DTYPE
						changed = True
					if data.get("link_to") == OLD_DTYPE:
						data["link_to"] = NEW_DTYPE
						changed = True
					rebuilt.append(block)
				doc.content = json.dumps(rebuilt)

		if changed:
			doc.save(ignore_permissions=True)

	frappe.clear_cache(doctype="Workspace")
