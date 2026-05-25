"""Perbaiki rentang sub-periode 25–24 (Jan = 25 Des – 24 Jan, bukan 01–24 Jan)."""

import frappe
from frappe.utils import getdate

from imogi_finance.payroll.payroll_period_integration import (
	_format_sub_period_label,
	build_cutoff_sub_periods,
)


def execute():
	if not frappe.db.exists("DocType", "Payroll Period"):
		return

	has_label = frappe.get_meta("Payroll Period Date").has_field("period_label")

	for pp_name in frappe.get_all("Payroll Period", pluck="name"):
		doc = frappe.get_doc("Payroll Period", pp_name)
		if not doc.start_date or not doc.end_date:
			continue

		generated = build_cutoff_sub_periods(getdate(doc.start_date), getdate(doc.end_date))
		if not generated:
			continue

		doc.set("periods", [])
		for item in generated:
			row = {
				"start_date": item["start_date"],
				"end_date": item["end_date"],
			}
			if has_label:
				row["period_label"] = _format_sub_period_label(
					item["start_date"], item["end_date"]
				)
			doc.append("periods", row)

		doc.flags.ignore_validate = True
		doc.save(ignore_permissions=True)

	frappe.db.commit()
