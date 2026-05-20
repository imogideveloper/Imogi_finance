"""Fix get_so_business_status in Client Script (v1 patch skipped when OI text existed elsewhere)."""

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
		if 'payment_status === "Outstanding Invoice"' in script:
			continue

		updated = _patch_get_so_business_status(script)
		if updated != script:
			frappe.db.set_value("Client Script", row.name, "script", updated, update_modified=True)


def _patch_get_so_business_status(script: str) -> str:
	pattern = re.compile(
		r"(function get_so_business_status\(doc\) \{.*?const payment_status = \(doc\.custom_payment_status \|\| \"\"\)\.trim\(\);)\s*"
		r"(if \(payment_status === \"Submitted\"\) return \"Submitted\";.*?return \"Submitted\";)\s*"
		r"(\})",
		re.DOTALL,
	)
	replacement = r"""\1
  if (payment_status === "Outstanding Invoice") return "Outstanding Invoice";
  if (payment_status === "Partial Paid") return "Outstanding Invoice";
  if (payment_status === "Submitted") return "Submitted";
  if (payment_status === "Paid")         return "Paid";
  if (payment_status === "Partial Paid") return "Outstanding Invoice";
  if (payment_status === "SI Created")   return "SI Created";
  return "Submitted";
\3"""
	# Fix duplicate Partial Paid line in replacement - I made an error
	replacement = r"""\1
  if (payment_status === "Outstanding Invoice") return "Outstanding Invoice";
  if (payment_status === "Partial Paid") return "Outstanding Invoice";
  if (payment_status === "Submitted") return "Submitted";
  if (payment_status === "Paid")         return "Paid";
  if (payment_status === "SI Created")   return "SI Created";
  return "Submitted";
\3"""
	out = pattern.sub(replacement, script, count=1)

	# status_map entries
	for needle, insert in [
		('"Partial Paid": ["Partial Paid", "orange"]', '"Outstanding Invoice": ["Outstanding Invoice", "orange"],\n      "Partial Paid": ["Outstanding Invoice", "orange"]'),
		('"Partial Paid":        ["Partial Paid", "orange"]', '"Outstanding Invoice": ["Outstanding Invoice", "orange"],\n      "Partial Paid": ["Outstanding Invoice", "orange"]'),
	]:
		if "Outstanding Invoice" not in out.split("get_indicator")[0] and needle in out:
			out = out.replace(needle, insert, 1)

	return out
