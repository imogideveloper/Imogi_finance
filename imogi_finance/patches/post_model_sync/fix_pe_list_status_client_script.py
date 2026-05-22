"""Merge Payment Entry list Client Script with listview_settings (preserve get_indicator)."""

import frappe

MERGE_MARKER = "_pe_prev_onload"


def execute():
	_patch_client_script()
	backfill()


def backfill():
	from imogi_finance.payment_entry_status import backfill_all_payment_status

	backfill_all_payment_status()


def _patch_client_script():
	name = "Filter Date Payment Entry"
	if not frappe.db.exists("Client Script", name):
		return

	script = frappe.db.get_value("Client Script", name, "script") or ""
	old = 'frappe.listview_settings["Payment Entry"] = {'
	if old not in script:
		return

	new = f"""(function () {{
  const _pe_lv = frappe.listview_settings["Payment Entry"] || {{}};
  const {MERGE_MARKER} = _pe_lv.onload;
  frappe.listview_settings["Payment Entry"] = Object.assign({{}}, _pe_lv, {{"""

	script = script.replace(old, new, 1)

	onload_open = "onload: function(listview) {"
	onload_call = (
		f"onload: function(listview) {{\r\n    if ({MERGE_MARKER}) {MERGE_MARKER}(listview);\r\n"
	)
	if onload_open in script:
		script = script.replace(onload_open, onload_call, 1)

	for ending in ("\n  }\r\n};", "\n  }\n};"):
		idx = script.rfind(ending)
		if idx != -1:
			script = script[:idx] + "\n  }\r\n});\r\n})();"
			break
	else:
		frappe.log_error(
			title="fix_pe_list_status_client_script",
			message="Could not find closing brace for Filter Date Payment Entry",
		)
		return

	frappe.db.set_value("Client Script", name, "script", script, update_modified=True)
	frappe.clear_cache(doctype="Client Script")
