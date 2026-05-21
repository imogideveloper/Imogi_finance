"""Biarkan toolbar Sales Invoice yang mengatur grouping; Client Script hanya period UI legacy."""

import frappe


def execute():
	for row in frappe.get_all(
		"Client Script",
		filters={"dt": "Sales Invoice", "enabled": 1, "view": "List"},
		fields=["name", "script"],
	):
		script = row.script or ""
		if "__imogi_si_toolbar_active" in script:
			continue

		updated = _patch_script(script)
		if updated != script:
			frappe.db.set_value("Client Script", row.name, "script", updated, update_modified=True)
		else:
			frappe.log_error(
				title="patch_si_client_script_defer_grouping_to_toolbar",
				message=f"Could not patch Client Script {row.name}",
			)

	frappe.clear_cache(doctype="Client Script")


def _patch_script(script: str) -> str:
	apply_needles = [
		(
			"function applyGrouping() {\r\n",
			"function applyGrouping() {\r\n      if (window.__imogi_si_toolbar_active) return;\r\n",
		),
		(
			"function applyGrouping() {\n",
			"function applyGrouping() {\n      if (window.__imogi_si_toolbar_active) return;\n",
		),
	]
	inject_needles = [
		(
			"function injectUI(){\r\n      $(\"#erg-wrap\").remove();",
			'function injectUI(){\r\n      if (window.__imogi_si_toolbar_active) return false;\r\n      $("#erg-wrap").remove();',
		),
		(
			'function injectUI(){\n      $("#erg-wrap").remove();',
			'function injectUI(){\n      if (window.__imogi_si_toolbar_active) return false;\n      $("#erg-wrap").remove();',
		),
	]

	for needle, insert in apply_needles:
		if needle in script and "if (window.__imogi_si_toolbar_active) return" not in script:
			script = script.replace(needle, insert, 1)
			break

	for needle, insert in inject_needles:
		if needle in script and "if (window.__imogi_si_toolbar_active) return false" not in script:
			script = script.replace(needle, insert, 1)
			break

	return script
