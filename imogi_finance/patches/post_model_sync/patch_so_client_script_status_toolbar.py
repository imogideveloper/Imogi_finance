"""Call status toolbar from Sales Order list Client Script (runs after __custom_list_js)."""

import frappe


def execute():
	for row in frappe.get_all(
		"Client Script",
		filters={"dt": "Sales Order", "enabled": 1, "view": "List"},
		fields=["name", "script"],
	):
		script = row.script or ""
		if "init_imogi_so_status_toolbar" in script:
			continue

		needles = [
			(
				"      sched(700);\r\n    });",
				"      sched(700);\r\n"
				"      if (typeof window.init_imogi_so_status_toolbar === \"function\") {\r\n"
				"        window.init_imogi_so_status_toolbar(listview);\r\n"
				"      }\r\n"
				"    });",
			),
			(
				"      sched(700);\n    });",
				"      sched(700);\n"
				"      if (typeof window.init_imogi_so_status_toolbar === \"function\") {\n"
				"        window.init_imogi_so_status_toolbar(listview);\n"
				"      }\n"
				"    });",
			),
		]
		replaced = False
		for needle, insert in needles:
			if needle in script:
				script = script.replace(needle, insert, 1)
				replaced = True
				break
		if not replaced:
			frappe.log_error(
				title="patch_so_client_script_status_toolbar",
				message=f"Could not patch Client Script {row.name}",
			)
			continue

		frappe.db.set_value("Client Script", row.name, "script", script, update_modified=True)

	frappe.clear_cache(doctype="Client Script")
