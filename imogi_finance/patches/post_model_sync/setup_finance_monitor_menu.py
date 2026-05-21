"""Finance Monitor: sidebar workspace + shortcuts (visible without search)."""

from __future__ import annotations

import json

import frappe

from imogi_finance.workspace_utils import sanitize_workspace_missing_links

REPORT_NAME = "Finance Monitor Dashboard"
WORKSPACE_NAME = "Finance Monitor"
SHORTCUT_LABEL = REPORT_NAME


def execute():
	_create_finance_monitor_workspace()
	_add_to_finance_imogi_workspace()
	_setup_embedded_shortcuts()


def _create_finance_monitor_workspace():
	content = [
		{
			"id": "hdr_fm",
			"type": "header",
			"data": {
				"text": "<span class='h5'>Klik kartu di bawah untuk chart, KPI, dan tabel piutang</span>",
				"col": 12,
			},
		},
		{
			"id": "s_fmd",
			"type": "shortcut",
			"data": {"shortcut_name": SHORTCUT_LABEL, "col": 4},
		},
		{"id": "sp_fm", "type": "spacer", "data": {"col": 12}},
		{
			"id": "hdr_fm_links",
			"type": "header",
			"data": {"text": "Lihat Juga", "col": 12},
		},
		{
			"id": "s_fm_ar",
			"type": "shortcut",
			"data": {"shortcut_name": "Accounts Receivable", "col": 3},
		},
		{
			"id": "s_fm_si",
			"type": "shortcut",
			"data": {"shortcut_name": "Sales Invoice", "col": 3},
		},
		{
			"id": "s_fm_pe",
			"type": "shortcut",
			"data": {"shortcut_name": "Payment Entry", "col": 3},
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
			"icon": "dashboard",
			"indicator_color": "orange",
			"public": 1,
			"sequence_id": 0.05,
			"content": json.dumps(content),
		}
	)

	ws.shortcuts = []
	ws.append(
		"shortcuts",
		{
			"type": "Report",
			"label": SHORTCUT_LABEL,
			"link_to": REPORT_NAME,
			"report_ref_doctype": "Sales Invoice",
			"color": "Orange",
			"icon": "dashboard",
			"format": "{} Open",
			"stats_filter": '{"outstanding_amount": [">", 0], "docstatus": 1}',
		},
	)
	for label, link_to, link_type, ref in [
		("Accounts Receivable", "Accounts Receivable", "Report", "Sales Invoice"),
		("Sales Invoice", "Sales Invoice", "DocType", None),
		("Payment Entry", "Payment Entry", "DocType", None),
	]:
		ws.append(
			"shortcuts",
			{
				"type": link_type,
				"label": label,
				"link_to": link_to,
				"report_ref_doctype": ref,
			},
		)

	sanitize_workspace_missing_links(ws)
	ws.save(ignore_permissions=True)


def _add_to_finance_imogi_workspace():
	if not frappe.db.exists("Workspace", "FINANCE IMOGI"):
		return

	ws = frappe.get_doc("Workspace", "FINANCE IMOGI")
	content = json.loads(ws.content or "[]")
	content = _strip_finance_monitor_blocks(content)

	prefix = [
		{
			"id": "hdr_fm_monitor",
			"type": "header",
			"data": {"text": "Monitoring Keuangan (AR & Kas)", "col": 12},
		},
		{
			"id": "s_fm_dashboard",
			"type": "shortcut",
			"data": {"shortcut_name": REPORT_NAME, "col": 3},
		},
		{"id": "spacer_fm_monitor", "type": "spacer", "data": {"col": 12}},
	]
	ws.content = json.dumps(prefix + content)

	_has = any(s.link_to == REPORT_NAME for s in ws.shortcuts)
	if not _has:
		ws.append(
			"shortcuts",
			{
				"type": "Report",
				"label": SHORTCUT_LABEL,
				"link_to": REPORT_NAME,
				"report_ref_doctype": "Sales Invoice",
				"color": "Orange",
				"icon": "dashboard",
			},
		)

	sanitize_workspace_missing_links(ws)
	ws.save(ignore_permissions=True)


def _setup_embedded_shortcuts():
	_placements = [
		("Towing Imogi", "hdr_keuangan"),
		("Receivables", "vikWSkNm6_"),
		("Accounting", "vikWSkNm6_"),
	]
	block = {
		"id": "s_finance_monitor",
		"type": "shortcut",
		"data": {"shortcut_name": REPORT_NAME, "col": 3},
	}

	for workspace_name, after_block_id in _placements:
		if not frappe.db.exists("Workspace", workspace_name):
			continue

		ws = frappe.get_doc("Workspace", workspace_name)
		content = _strip_finance_monitor_blocks(json.loads(ws.content or "[]"))
		if not _insert_after_id(content, after_block_id, dict(block)):
			for idx, row in enumerate(content):
				if row.get("type") == "header":
					content.insert(idx + 1, dict(block))
					break
			else:
				content.insert(0, dict(block))

		ws.content = json.dumps(content)

		for row in list(ws.shortcuts):
			if row.link_to == REPORT_NAME:
				ws.remove(row)
		ws.append(
			"shortcuts",
			{
				"type": "Report",
				"label": SHORTCUT_LABEL,
				"link_to": REPORT_NAME,
				"report_ref_doctype": "Sales Invoice",
				"color": "Orange",
				"icon": "dashboard",
			},
		)
		sanitize_workspace_missing_links(ws)
		ws.save(ignore_permissions=True)

	frappe.clear_cache(doctype="Workspace")


def _strip_finance_monitor_blocks(content: list) -> list:
	skip_ids = {
		"s_finance_monitor",
		"hdr_fm_monitor",
		"s_fm_dashboard",
		"spacer_fm_monitor",
	}
	cleaned = []
	for block in content:
		if block.get("id") in skip_ids:
			continue
		if (
			block.get("type") == "shortcut"
			and block.get("data", {}).get("shortcut_name") == REPORT_NAME
		):
			continue
		cleaned.append(block)
	return cleaned


def _insert_after_id(content: list, block_id: str, new_block: dict) -> bool:
	for idx, block in enumerate(content):
		if block.get("id") == block_id:
			content.insert(idx + 1, new_block)
			return True
	return False
