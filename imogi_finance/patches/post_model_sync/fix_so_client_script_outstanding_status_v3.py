"""Ensure Sales Order Client Script maps Outstanding Invoice correctly (v3 robust patch)."""

import re

import frappe


def execute():
	for row in frappe.get_all(
		"Client Script",
		filters={"dt": "Sales Order", "enabled": 1, "view": "List"},
		fields=["name", "script"],
	):
		script = row.script or ""
		if "get_so_business_status" not in script:
			continue

		updated = _patch_script(script)
		if updated != script:
			frappe.db.set_value("Client Script", row.name, "script", updated, update_modified=True)

	frappe.clear_cache(doctype="Client Script")


def _patch_script(script: str) -> str:
	out = script

	# Normalize helper status function body regardless previous variants.
	func_pattern = re.compile(
		r"function get_so_business_status\(doc\)\s*\{[\s\S]*?\n\}",
		re.MULTILINE,
	)
	new_func = """function get_so_business_status(doc) {
  if (cint_so(doc.docstatus) === 2) return "Cancelled";
  if (cint_so(doc.docstatus) === 0) return "Draft";
  const payment_status = (doc.custom_payment_status || "").trim();
  if (payment_status === "Outstanding Invoice") return "Outstanding Invoice";
  if (payment_status === "Partial Paid") return "Outstanding Invoice";
  if (payment_status === "Submitted") return "Submitted";
  if (payment_status === "Paid") return "Paid";
  if (payment_status === "SI Created") return "SI Created";
  return "Submitted";
}"""
	out = func_pattern.sub(new_func, out, count=1)

	# Ensure Outstanding Invoice exists in color map.
	color_pattern = re.compile(
		r"function get_so_status_color\(status\)\s*\{[\s\S]*?\n\}",
		re.MULTILINE,
	)
	new_color_func = """function get_so_status_color(status) {
  const color_map = {
    "Draft": "grey",
    "Submitted": "blue",
    "SI Created": "blue",
    "Outstanding Invoice": "orange",
    "Partial Paid": "orange",
    "Paid": "green",
    "Cancelled": "red",
  };
  return color_map[status] || "grey";
}"""
	out = color_pattern.sub(new_color_func, out, count=1)

	return out
