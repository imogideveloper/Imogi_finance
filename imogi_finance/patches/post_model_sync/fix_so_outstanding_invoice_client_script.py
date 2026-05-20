"""Client Script list SO still mapped Outstanding Invoice → Submitted; fix scripts in DB."""

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


def _patch_script(script: str) -> str:
	out = script

	if "get_so_business_status" in out:
		old_fn = """  if (payment_status === "Submitted") return "Submitted";
  if (payment_status === "Paid")         return "Paid";
  if (payment_status === "Partial Paid") return "Partial Paid";
  if (payment_status === "SI Created")   return "SI Created";
  return "Submitted";"""

		new_fn = """  if (payment_status === "Outstanding Invoice") return "Outstanding Invoice";
  if (payment_status === "Partial Paid") return "Outstanding Invoice";
  if (payment_status === "Submitted") return "Submitted";
  if (payment_status === "Paid")         return "Paid";
  if (payment_status === "SI Created")   return "SI Created";
  return "Submitted";"""

		if old_fn in out:
			out = out.replace(old_fn, new_fn)

		for needle, insert in [
			('"Partial Paid": "orange",', '"Outstanding Invoice": "orange",\n    "Partial Paid": "orange",'),
			('"Partial Paid": ["Partial Paid", "orange"],', '"Outstanding Invoice": ["Outstanding Invoice", "orange"],\n      "Partial Paid": ["Outstanding Invoice", "orange"],'),
			('"Partial Paid":        ["Partial Paid", "orange"],', '"Outstanding Invoice": ["Outstanding Invoice", "orange"],\n      "Partial Paid": ["Outstanding Invoice", "orange"],'),
		]:
			if insert.split("\n")[0] not in out and needle in out:
				out = out.replace(needle, insert)

	# Simpler list script (Sales Order Status)
	out = out.replace(
		"'Partial Paid': ['Partial Paid', 'orange'],",
		"'Outstanding Invoice': ['Outstanding Invoice', 'orange'],\n            'Partial Paid': ['Outstanding Invoice', 'orange'],",
	)
	out = out.replace(
		"'Partial Paid': 'orange',",
		"'Outstanding Invoice': 'orange',\n                'Partial Paid': 'orange',",
	)

	return out
