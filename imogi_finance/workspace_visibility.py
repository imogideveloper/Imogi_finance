"""Filter ERPNext workspace cards/shortcuts based on Workspace UI Settings."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import strip_html


def _normalize_label(label: str | None) -> str:
	return (label or "").strip().casefold()


def _workspace_aliases(workspace_ref: str | None) -> set[str]:
	"""Return workspace aliases (name/title) for robust matching."""
	workspace_ref = (workspace_ref or "").strip()
	if not workspace_ref:
		return set()

	aliases = {workspace_ref}

	title = frappe.db.get_value("Workspace", workspace_ref, "title")
	if title:
		aliases.add(title.strip())
		return aliases

	name = frappe.db.get_value("Workspace", {"title": workspace_ref}, "name")
	if name:
		aliases.add(name.strip())
	return aliases


def _workspace_matches(rule_workspace: str | None, current_workspace: str | None) -> bool:
	"""Match workspace by either name or title."""
	rule_aliases = {_normalize_label(v) for v in _workspace_aliases(rule_workspace)}
	current_aliases = {_normalize_label(v) for v in _workspace_aliases(current_workspace)}
	if not rule_aliases or not current_aliases:
		return False
	return bool(rule_aliases.intersection(current_aliases))


def _header_section_text(data: dict | None) -> str:
	"""Plain text from EditorJS header block (may contain HTML)."""
	if not data:
		return ""
	text = data.get("text") or ""
	return strip_html(text).strip()


@frappe.whitelist()
def get_pickable_workspaces() -> list[dict]:
	"""Public workspaces for the hide-workspace picker (System Manager / settings form)."""
	if not frappe.has_permission("Workspace UI Settings", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	return frappe.get_all(
		"Workspace",
		filters={"public": 1},
		fields=["name", "title", "module"],
		order_by="title asc, name asc",
		limit_page_length=0,
	)


@frappe.whitelist()
def get_workspace_sections(workspace: str) -> list[dict]:
	"""Return card breaks, shortcuts, and content blocks for a workspace (picker)."""
	if not workspace or not frappe.db.exists("Workspace", workspace):
		frappe.throw(_("Workspace {0} not found.").format(workspace))

	doc = frappe.get_cached_doc("Workspace", workspace)
	seen: set[str] = set()
	sections: list[dict] = []

	def add(label: str | None, section_type: str, source: str) -> None:
		label = (label or "").strip()
		if not label:
			return
		key = _normalize_label(label)
		if key in seen:
			return
		seen.add(key)
		sections.append({"label": label, "section_type": section_type, "source": source})

	for row in doc.links:
		if row.type == "Card Break":
			add(row.label, "card", "links")

	for row in doc.shortcuts:
		add(row.label, "shortcut", "shortcuts")

	if doc.content:
		try:
			blocks = json.loads(doc.content)
		except json.JSONDecodeError:
			blocks = []
		for block in blocks:
			block_type = block.get("type")
			data = block.get("data") or {}
			if block_type == "shortcut":
				add(data.get("shortcut_name"), "content_shortcut", "content")
			elif block_type == "card":
				add(data.get("card_name"), "content_card", "content")
			elif block_type == "header":
				add(_header_section_text(data), "header", "content")

	sections.sort(key=lambda row: (row["section_type"], row["label"]))
	return sections


def _rule_applies_to_user(row, user: str | None = None) -> bool:
	"""Row with empty user = global; row with user = only that login."""
	row_user = (getattr(row, "user", None) or "").strip()
	if not row_user:
		return True
	return row_user == (user or frappe.session.user)


def get_hidden_workspace_names(user: str | None = None) -> set[str]:
	"""Workspace names to remove entirely from desk sidebar for this user."""
	user = user or frappe.session.user
	if not frappe.db.exists("DocType", "Workspace UI Settings"):
		return set()

	try:
		settings = frappe.get_cached_doc("Workspace UI Settings")
	except frappe.DoesNotExistError:
		return set()

	if not settings.enabled:
		return set()

	hidden: set[str] = set()
	for row in getattr(settings, "hidden_workspaces", None) or []:
		if not row.hidden:
			continue
		if not _rule_applies_to_user(row, user):
			continue
		name = (row.workspace or "").strip()
		if name:
			hidden.add(name)
	return hidden


def filter_allowed_workspace_pages(pages: list | None, user: str | None = None) -> list:
	"""Drop pages whose workspace name is in hidden_workspaces."""
	pages = list(pages or [])
	hidden = get_hidden_workspace_names(user)
	if not hidden:
		return pages

	hidden_norm = set()
	for ref in hidden:
		for alias in _workspace_aliases(ref):
			hidden_norm.add(_normalize_label(alias))

	def is_hidden(page: dict) -> bool:
		page_refs = [
			(page.get("name") or "").strip(),
			(page.get("title") or "").strip(),
		]
		for page_ref in page_refs:
			if _normalize_label(page_ref) in hidden_norm:
				return True
		return False

	return [page for page in pages if not is_hidden(page)]


def get_hidden_rules(workspace_name: str | None, user: str | None = None) -> list[dict]:
	"""Active hide rules for a workspace (current session user unless user= passed)."""
	if not workspace_name:
		return []

	if not frappe.db.exists("DocType", "Workspace UI Settings"):
		return []

	try:
		settings = frappe.get_cached_doc("Workspace UI Settings")
	except frappe.DoesNotExistError:
		return []

	if not settings.enabled:
		return []

	rules = []
	for row in settings.hidden_sections or []:
		if not row.hidden:
			continue
		if not _rule_applies_to_user(row, user):
			continue
		if not _workspace_matches((row.workspace or "").strip(), workspace_name):
			continue
		label = (row.section_label or "").strip()
		if not label:
			continue
		rules.append(
			{
				"label": label,
				"label_key": _normalize_label(label),
				"hide_card_section": bool(row.hide_card_section),
				"hide_shortcuts": bool(row.hide_shortcuts),
			}
		)
	return rules


def get_hidden_section_labels(workspace_name: str | None, user: str | None = None) -> list[str]:
	"""Labels to hide in workspace content blocks (shortcuts + cards)."""
	return [rule["label"] for rule in get_hidden_rules(workspace_name, user)]


def filter_workspace_content_blocks(
	blocks: list, workspace_name: str | None, user: str | None = None
) -> list:
	"""Remove hidden sections from workspace EditorJS content (headers, cards, shortcuts)."""
	rules = get_hidden_rules(workspace_name, user)
	if not blocks:
		return blocks

	def normalize_block(block: dict) -> dict:
		"""Normalize unsupported EditorJS block types for Desk renderer."""
		if not isinstance(block, dict):
			return block
		block_type = block.get("type")
		if block_type != "text":
			return block

		data = block.get("data") or {}
		text = data.get("text")
		if not text:
			return block

		normalized = dict(block)
		normalized["type"] = "paragraph"
		normalized["data"] = {"text": text}
		return normalized

	blocks = [normalize_block(block) for block in blocks]
	if not rules:
		return blocks

	section_keys = {rule["label_key"] for rule in rules}
	card_keys = {rule["label_key"] for rule in rules if rule["hide_card_section"]}
	shortcut_keys = {rule["label_key"] for rule in rules if rule["hide_shortcuts"]}

	filtered = []
	in_hidden_section = False

	for block in blocks:
		data = block.get("data") or {}
		block_type = block.get("type")

		if block_type == "header":
			if _label_matches(_header_section_text(data), section_keys):
				in_hidden_section = True
				continue
			in_hidden_section = False
			filtered.append(block)
			continue

		if in_hidden_section:
			continue

		if block_type == "shortcut" and _label_matches(data.get("shortcut_name"), shortcut_keys):
			continue
		if block_type == "card" and _label_matches(data.get("card_name"), card_keys):
			continue
		filtered.append(block)
	return filtered


def filter_workspace_content_json(
	content: str | None, workspace_name: str | None, user: str | None = None
) -> str:
	if not content:
		return content or ""
	try:
		blocks = json.loads(content)
	except json.JSONDecodeError:
		return content
	if not isinstance(blocks, list):
		return content
	return json.dumps(filter_workspace_content_blocks(blocks, workspace_name, user))


def filter_boot_workspaces(bootinfo, user: str | None = None) -> None:
	"""Filter workspace layout JSON bundled in desk boot (main workspace page source)."""
	user = user or getattr(bootinfo, "user", None) or frappe.session.user
	pages = filter_allowed_workspace_pages(bootinfo.get("allowed_workspaces") or [], user)
	bootinfo.allowed_workspaces = pages
	for page in pages:
		workspace_name = page.get("name") or page.get("title")
		if page.get("content"):
			page["content"] = filter_workspace_content_json(
				page["content"], workspace_name, user
			)


def _label_matches(label: str | None, hidden_keys: set[str]) -> bool:
	"""Match raw or translated workspace labels."""
	if not hidden_keys:
		return False
	key = _normalize_label(label)
	if key in hidden_keys:
		return True
	try:
		translated = _normalize_label(_(label))
		return translated in hidden_keys
	except Exception:
		return False


def filter_workspace_page_data(
	page_data: dict, workspace_name: str | None, user: str | None = None
) -> dict:
	"""Remove hidden cards/shortcuts from get_desktop_page payload."""
	rules = get_hidden_rules(workspace_name, user)
	if not rules:
		page_data["hidden_sections"] = []
		return page_data

	card_keys = {rule["label_key"] for rule in rules if rule["hide_card_section"]}
	shortcut_keys = {rule["label_key"] for rule in rules if rule["hide_shortcuts"]}
	content_keys = {
		rule["label_key"]
		for rule in rules
		if rule["hide_card_section"] or rule["hide_shortcuts"]
	}

	cards = page_data.get("cards") or {}
	card_items = cards.get("items") or []
	if card_keys:
		cards["items"] = [
			card for card in card_items if not _label_matches(card.get("label"), card_keys)
		]
	page_data["cards"] = cards

	shortcuts = page_data.get("shortcuts") or {}
	shortcut_items = shortcuts.get("items") or []
	if shortcut_keys:
		shortcuts["items"] = [
			item
			for item in shortcut_items
			if not _label_matches(item.get("label"), shortcut_keys)
		]
	page_data["shortcuts"] = shortcuts

	page_data["hidden_sections"] = sorted({rule["label"] for rule in rules if rule["label_key"] in content_keys})
	return page_data


@frappe.whitelist()
def add_hidden_workspace(workspace: str, user: str | None = None) -> dict:
	"""Quick-add a row to hide an entire workspace from the sidebar."""
	user = (user or "").strip() or None
	if not workspace or not frappe.db.exists("Workspace", workspace):
		frappe.throw(_("Workspace {0} not found.").format(workspace))

	settings = frappe.get_single("Workspace UI Settings")
	settings.enabled = 1

	for row in getattr(settings, "hidden_workspaces", None) or []:
		row_user = (getattr(row, "user", None) or "").strip() or None
		if row.workspace == workspace and row_user == user:
			row.hidden = 1
			settings.save(ignore_permissions=True)
			clear_workspace_cache()
			return {"status": "updated"}

	settings.append(
		"hidden_workspaces",
		{"user": user, "workspace": workspace, "hidden": 1},
	)
	settings.save(ignore_permissions=True)
	clear_workspace_cache()
	return {"status": "created"}


@frappe.whitelist()
def add_hidden_section(workspace: str, section_label: str, user: str | None = None) -> dict:
	"""Quick-add a hidden section row from the settings form."""
	user = (user or "").strip() or None
	workspace = (workspace or "").strip()
	section_label = (section_label or "").strip()
	if not workspace or not section_label:
		frappe.throw(_("Workspace and section label are required."))

	available_sections = {row.get("label") for row in get_workspace_sections(workspace)}
	if section_label not in available_sections:
		frappe.throw(
			_(
				"Section '{0}' tidak ditemukan di workspace '{1}'. Pilih section melalui picker agar sesuai."
			).format(section_label, workspace)
		)

	settings = frappe.get_single("Workspace UI Settings")
	settings.enabled = 1

	for row in settings.hidden_sections or []:
		row_user = (getattr(row, "user", None) or "").strip() or None
		if row.workspace == workspace and row.section_label == section_label and row_user == user:
			row.hidden = 1
			row.hide_card_section = 1
			row.hide_shortcuts = 1
			settings.save(ignore_permissions=True)
			clear_workspace_cache()
			return {"status": "updated"}

	settings.append(
		"hidden_sections",
		{
			"user": user,
			"workspace": workspace,
			"section_label": section_label,
			"hidden": 1,
			"hide_card_section": 1,
			"hide_shortcuts": 1,
		},
	)
	settings.save(ignore_permissions=True)
	clear_workspace_cache()
	return {"status": "created"}


def get_workspace_hidden_map(user: str | None = None) -> dict[str, list[str]]:
	"""Workspace name -> section labels to hide for the given user (desk boot)."""
	user = user or frappe.session.user
	if not frappe.db.exists("DocType", "Workspace UI Settings"):
		return {}

	try:
		settings = frappe.get_cached_doc("Workspace UI Settings")
	except frappe.DoesNotExistError:
		return {}

	if not settings.enabled:
		return {}

	hidden_map: dict[str, list[str]] = {}
	for row in settings.hidden_sections or []:
		if not row.hidden:
			continue
		if not _rule_applies_to_user(row, user):
			continue
		workspace = (row.workspace or "").strip()
		label = (row.section_label or "").strip()
		if not workspace or not label:
			continue
		if not row.hide_card_section and not row.hide_shortcuts:
			continue
		for alias in _workspace_aliases(workspace):
			hidden_map.setdefault(alias, [])
			if label not in hidden_map[alias]:
				hidden_map[alias].append(label)
	return hidden_map


def _filter_module_wise_workspaces(bootinfo, user: str | None = None) -> None:
	hidden = get_hidden_workspace_names(user)
	module_map = bootinfo.get("module_wise_workspaces") or {}
	if not hidden or not module_map:
		return
	for module, names in list(module_map.items()):
		module_map[module] = [name for name in (names or []) if name not in hidden]
	bootinfo.module_wise_workspaces = module_map


def get_hidden_form_fields_map(user: str | None = None) -> dict[str, list[str]]:
	"""DocType name -> fieldnames to hide on form for the given user."""
	user = user or frappe.session.user
	if not frappe.db.exists("DocType", "Workspace UI Settings"):
		return {}

	try:
		settings = frappe.get_cached_doc("Workspace UI Settings")
	except frappe.DoesNotExistError:
		return {}

	if not settings.enabled:
		return {}

	hidden_map: dict[str, list[str]] = {}
	for row in getattr(settings, "hidden_form_fields", None) or []:
		if not row.hidden:
			continue
		if not _rule_applies_to_user(row, user):
			continue
		doctype = (row.ref_doctype or "").strip()
		fieldname = (row.fieldname or "").strip()
		if not doctype or not fieldname:
			continue
		hidden_map.setdefault(doctype, [])
		if fieldname not in hidden_map[doctype]:
			hidden_map[doctype].append(fieldname)
	return hidden_map


@frappe.whitelist()
def get_hidden_form_fields_for_doctype(doctype: str) -> list[str]:
	"""Fresh hidden form fields for a DocType.

	The desk boot payload can be stale until a full reload. This endpoint lets
	the client re-read Workspace UI Settings when a form opens.
	"""
	if not doctype:
		return []
	return get_hidden_form_fields_map().get(doctype, [])


@frappe.whitelist()
def get_doctype_form_fields(doctype: str) -> list[dict]:
	"""Fields available for hiding on a DocType form."""
	if not frappe.has_permission("Workspace UI Settings", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not doctype or not frappe.db.exists("DocType", doctype):
		frappe.throw(_("DocType {0} not found.").format(doctype))

	skip_types = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Fold"}
	fields = []
	for df in frappe.get_meta(doctype).fields:
		if df.fieldtype in skip_types or not df.fieldname:
			continue
		fields.append(
			{
				"fieldname": df.fieldname,
				"label": df.label or df.fieldname,
				"fieldtype": df.fieldtype,
			}
		)
	fields.sort(key=lambda row: (row["label"] or row["fieldname"]).lower())
	return fields


@frappe.whitelist()
def add_hidden_form_field(
	ref_doctype: str, fieldname: str, user: str | None = None, field_label: str | None = None
) -> dict:
	"""Quick for hide a form field rule from Access Studio picker."""
	user = (user or "").strip() or None
	if not ref_doctype or not fieldname:
		frappe.throw(_("DocType and fieldname are required."))

	if not field_label:
		meta = frappe.get_meta(ref_doctype)
		df = meta.get_field(fieldname)
		field_label = (df.label if df else None) or fieldname

	settings = frappe.get_single("Workspace UI Settings")
	settings.enabled = 1

	for row in getattr(settings, "hidden_form_fields", None) or []:
		row_user = (getattr(row, "user", None) or "").strip() or None
		if (
			row.ref_doctype == ref_doctype
			and row.fieldname == fieldname
			and row_user == user
		):
			row.hidden = 1
			row.field_label = field_label
			settings.save(ignore_permissions=True)
			clear_workspace_cache()
			return {"status": "updated"}

	settings.append(
		"hidden_form_fields",
		{
			"user": user,
			"ref_doctype": ref_doctype,
			"fieldname": fieldname,
			"field_label": field_label,
			"hidden": 1,
		},
	)
	settings.save(ignore_permissions=True)
	clear_workspace_cache()
	return {"status": "created"}


def update_boot_session(bootinfo):
	user = getattr(bootinfo, "user", None) or frappe.session.user
	bootinfo.imogi_hidden_workspaces = sorted(get_hidden_workspace_names(user))
	bootinfo.imogi_workspace_hidden = get_workspace_hidden_map(user)
	bootinfo.imogi_hidden_form_fields = get_hidden_form_fields_map(user)
	filter_boot_workspaces(bootinfo, user)
	_filter_module_wise_workspaces(bootinfo, user)
	# Pastikan desk client membaca setting pajak dari item (sysdefaults)
	if bootinfo.get("sysdefaults") is not None:
		bootinfo.sysdefaults["add_taxes_from_item_tax_template"] = frappe.db.get_single_value(
			"Accounts Settings", "add_taxes_from_item_tax_template"
		) or 0


def clear_workspace_cache(doc=None, method=None):
	"""Clear desk cache after visibility settings change."""
	frappe.clear_cache()
