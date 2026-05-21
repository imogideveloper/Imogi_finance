"""Create Access Studio workspace — hub for Workspace UI Settings (per-user menu hiding)."""

from __future__ import annotations

import json

import frappe

from imogi_finance.workspace_utils import sanitize_workspace_missing_links

WORKSPACE_NAME = "Access Studio"
SETTINGS_DOCTYPE = "Workspace UI Settings"
ALLOWED_ROLES = ("System Manager", "Accounts Manager", "Administrator")


def execute():
	_create_access_studio_workspace()
	_update_workspace_sequence()


def _create_access_studio_workspace():
	content = [
		{
			"id": "hdr_as_main",
			"type": "header",
			"data": {
				"text": (
					"<span class='h5'><b>Access Studio</b> — atur menu workspace yang tampil "
					"per user (mis. sembunyikan <i>Point of Sale</i> hanya untuk Yugo)</span>"
				),
				"col": 12,
			},
		},
		{
			"id": "s_wui_settings",
			"type": "shortcut",
			"data": {"shortcut_name": SETTINGS_DOCTYPE, "col": 4},
		},
		{
			"id": "s_users",
			"type": "shortcut",
			"data": {"shortcut_name": "User", "col": 4},
		},
		{"id": "sp_as", "type": "spacer", "data": {"col": 12}},
		{
			"id": "hdr_as_help",
			"type": "header",
			"data": {
				"text": (
					"<span class='text-muted'>Buka <b>Workspace UI Settings</b> → tabel "
					"<b>Hidden Sections</b> → isi kolom <b>User</b> untuk aturan per user.</span>"
				),
				"col": 12,
			},
		},
	]

	if frappe.db.exists("Workspace", WORKSPACE_NAME):
		ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
	else:
		ws = frappe.new_doc("Workspace")
		ws.name = WORKSPACE_NAME
		ws.label = WORKSPACE_NAME

	ws.update(
		{
			"title": WORKSPACE_NAME,
			"module": "Imogi Finance",
			"icon": "lock",
			"indicator_color": "blue",
			"public": 1,
			"sequence_id": 0.03,
			"content": json.dumps(content),
		}
	)

	ws.shortcuts = []
	ws.links = []

	ws.append(
		"shortcuts",
		{
			"type": "DocType",
			"label": SETTINGS_DOCTYPE,
			"link_to": SETTINGS_DOCTYPE,
			"color": "Blue",
			"icon": "setting",
		},
	)
	ws.append(
		"shortcuts",
		{
			"type": "DocType",
			"label": "User",
			"link_to": "User",
			"color": "Grey",
			"icon": "users",
		},
	)

	ws.append("links", {"type": "Card Break", "label": "Pengaturan Akses Menu"})
	ws.append(
		"links",
		{
			"type": "Link",
			"label": SETTINGS_DOCTYPE,
			"link_type": "DocType",
			"link_to": SETTINGS_DOCTYPE,
			"description": "Sembunyikan section workspace per user atau untuk semua user.",
		},
	)
	ws.append(
		"links",
		{
			"type": "Link",
			"label": "User",
			"link_type": "DocType",
			"link_to": "User",
			"description": "Daftar user untuk mengisi kolom User di aturan hidden section.",
		},
	)

	ws.roles = []
	for role in ALLOWED_ROLES:
		ws.append("roles", {"role": role})

	sanitize_workspace_missing_links(ws)
	ws.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Workspace")


def _update_workspace_sequence():
	if frappe.db.exists("Workspace", WORKSPACE_NAME):
		frappe.db.set_value("Workspace", WORKSPACE_NAME, "sequence_id", 0.03, update_modified=False)
		frappe.db.commit()
