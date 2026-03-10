# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import now, nowdate, getdate


class VATOUTBatch(Document):
	def autoname(self):
		"""Generate name using company abbreviation and sequential number."""
		# Fetch company abbreviation
		if self.company and not self.company_abbr:
			self.company_abbr = frappe.db.get_value("Company", self.company, "abbr")

		# Build naming series prefix
		year = getdate(self.date_from or nowdate()).year
		abbr = self.company_abbr or "XX"

		# Format: VO-{abbr}-.{YYYY}.-.##### (contoh: VO-TPT-.2026.-.00001)
		# make_autoname format: prefix + ".#####" where prefix ends without dot
		naming_series = f"VO-{abbr}-.{year}.-..#####"

		# Generate name with auto-incrementing number
		self.name = make_autoname(naming_series)

	def validate(self):
		"""Validate batch data."""
		if self.flags.get("ignore_validate"):
			return

		# Validate date range
		if getdate(self.date_from) > getdate(self.date_to):
			frappe.throw(_("Date From cannot be greater than Date To"))

		# Update computed status
		self._update_status()

	def on_submit(self):
		"""Lock and finalize batch data."""
		# Prevent submit without FP numbers
		invoices = self.get_batch_invoices()
		if not invoices:
			frappe.throw(_("Cannot submit empty batch. Please add invoices first."))

		missing_fp = [inv.name for inv in invoices if not inv.out_fp_no]
		if missing_fp:
			frappe.throw(
				_("Cannot submit batch. {0} invoices missing FP numbers: {1}").format(
					len(missing_fp), ", ".join(missing_fp[:5])
				)
			)

		# Update submission metadata
		self.db_set("submit_on", now(), update_modified=False)
		self._update_status()

	def on_cancel(self):
		"""Unlink all Sales Invoices from this batch but preserve FP numbers."""
		invoices = self.get_batch_invoices()

		for inv in invoices:
			frappe.db.set_value(
				"Sales Invoice",
				inv.name,
				{
					"out_fp_batch": None,
					"out_fp_group_id": None
				},
				update_modified=False
			)

		self._update_status()
		frappe.msgprint(
			_("All {0} invoices unlinked from batch. FP numbers preserved.").format(len(invoices))
		)

	def _update_status(self):
		"""Update batch status based on state."""
		if self.docstatus == 0:
			if self.exported_on:
				self.status = "Exported"
			else:
				self.status = "Draft"
		elif self.docstatus == 1:
			self.status = "Submitted"
		elif self.docstatus == 2:
			self.status = "Cancelled"

	@frappe.whitelist()
	def get_available_invoices(self, force_rebuild=False):
		"""Get Sales Invoices available for this batch and auto-group them.

		Args:
			force_rebuild: If True, reset all grouping. If False, preserve manual edits.
		"""
		# Query Sales Invoices with idempotent filter
		invoices = frappe.db.get_all(
			"Sales Invoice",
			filters={
				"docstatus": 1,
				"company": self.company,
				"posting_date": ["between", [self.date_from, self.date_to]],
				"out_fp_status": "Verified"
			},
			or_filters=[
				["out_fp_batch", "is", "not set"],
				["out_fp_batch", "=", self.name]
			],
			fields=[
				"name",
				"posting_date",
				"customer",
				"customer_name",
				"grand_total",
				"out_fp_no_faktur",
				"out_fp_ppn",
				"out_fp_dpp",
				"out_fp_combine",
				"out_fp_customer_npwp",
				"out_fp_batch",
				"out_fp_group_id"
			],
			order_by="posting_date, customer"
		)

		if not invoices:
			frappe.msgprint(_("No available invoices found for selected date range."))
			return []

		# Auto-group by customer and out_fp_combine flag
		groups = self._auto_group_invoices(invoices)

		# Assign group IDs and link to batch
		self._assign_and_link_groups(groups, force_rebuild=force_rebuild)

		return {
			"total_invoices": len(invoices),
			"total_groups": len(groups),
			"groups": groups
		}

	def _auto_group_invoices(self, invoices):
		"""
		Auto-group invoices based on out_fp_combine flag and customer.

		Logic:
		- out_fp_combine = 1: Group with other combine=1 invoices from same customer
		- out_fp_combine = 0: Each invoice gets its own group (no combining)
		"""
		groups = []
		combine_groups = {}  # {customer: [invoices]}

		for inv in invoices:
			if inv.out_fp_combine:
				# Combine with other invoices from same customer
				key = f"{inv.customer}|{inv.out_fp_customer_npwp or ''}"
				if key not in combine_groups:
					combine_groups[key] = []
				combine_groups[key].append(inv)
			else:
				# Single invoice group
				groups.append({
					"customer": inv.customer,
					"customer_name": inv.customer_name,
					"customer_npwp": inv.out_fp_customer_npwp,
					"invoice_count": 1,
					"total_dpp": inv.out_fp_dpp or 0,
					"total_ppn": inv.out_fp_ppn or 0,
					"invoices": [inv]
				})

		# Process combine groups
		for key, inv_list in combine_groups.items():
			customer = inv_list[0].customer
			customer_name = inv_list[0].customer_name
			customer_npwp = inv_list[0].out_fp_customer_npwp

			groups.append({
				"customer": customer,
				"customer_name": customer_name,
				"customer_npwp": customer_npwp,
				"invoice_count": len(inv_list),
				"total_dpp": sum(inv.out_fp_dpp or 0 for inv in inv_list),
				"total_ppn": sum(inv.out_fp_ppn or 0 for inv in inv_list),
				"invoices": inv_list
			})

		return groups

	def _assign_and_link_groups(self, groups, force_rebuild=False):
		"""Assign sequential group IDs and link Sales Invoices to this batch.

		Args:
			groups: List of group dictionaries with invoices
			force_rebuild: If True, overwrite existing assignments. If False, preserve manual edits.
		"""
		for idx, group in enumerate(groups, start=1):
			group_id = idx

			# Update all invoices in group
			for inv in group["invoices"]:
				# Preserve manual edits unless force_rebuild
				if not force_rebuild and inv.out_fp_batch == self.name and inv.out_fp_group_id:
					continue

				frappe.db.set_value(
					"Sales Invoice",
					inv.name,
					{
						"out_fp_batch": self.name,
						"out_fp_group_id": group_id
					},
					update_modified=False
				)

			# Store group_id in return data
			group["group_id"] = group_id

	def get_batch_invoices(self):
		"""Get all Sales Invoices linked to this batch."""
		return frappe.db.get_all(
			"Sales Invoice",
			filters={"out_fp_batch": self.name, "docstatus": 1},
			fields=[
				"name",
				"posting_date",
				"customer",
				"customer_name",
				"grand_total",
				"out_fp_no",
				"out_fp_no_seri",
				"out_fp_no_faktur",
				"out_fp_date",
				"out_fp_dpp",
				"out_fp_ppn",
				"out_fp_group_id",
				"out_fp_customer_npwp",
				"out_fp_combine"
			],
			order_by="out_fp_group_id, posting_date"
		)

	def get_groups_summary(self):
		"""Get summary of groups in this batch."""
		invoices = self.get_batch_invoices()

		groups_map = {}
		for inv in invoices:
			gid = inv.out_fp_group_id or 0
			if gid not in groups_map:
				groups_map[gid] = {
					"group_id": gid,
					"customer": inv.customer,
					"customer_name": inv.customer_name,
					"customer_npwp": inv.out_fp_customer_npwp,
					"invoice_count": 0,
					"total_dpp": 0,
					"total_ppn": 0,
					"fp_number": inv.out_fp_no or "",
					"invoices": []
				}

			groups_map[gid]["invoice_count"] += 1
			groups_map[gid]["total_dpp"] += inv.out_fp_dpp or 0
			groups_map[gid]["total_ppn"] += inv.out_fp_ppn or 0
			groups_map[gid]["invoices"].append(inv.name)

		return list(groups_map.values())

	def _validate_not_exported(self):
		"""Validate that batch has not been exported (groups not locked)."""
		if self.exported_on:
			frappe.throw(_("Groups locked after export. Cannot modify grouping."))

	@frappe.whitelist()
	def add_invoice_to_group(self, invoice_name, group_id):
		"""Add an invoice to a specific group.

		Args:
			invoice_name: Sales Invoice name
			group_id: Target group ID
		"""
		# Permission check
		self.check_permission("write")

		# Validate not exported
		self._validate_not_exported()

		# Validate invoice
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if invoice.docstatus != 1:
			frappe.throw(_("Invoice {0} must be submitted").format(invoice_name))

		if invoice.out_fp_status != "Verified":
			frappe.throw(_("Invoice {0} must have Verified tax invoice status").format(invoice_name))

		# Check if already in another batch
		if invoice.out_fp_batch and invoice.out_fp_batch != self.name:
			frappe.throw(_("Invoice {0} is already in batch {1}").format(invoice_name, invoice.out_fp_batch))

		# Validate customer match with target group
		group_customer = frappe.db.get_value(
			"Sales Invoice",
			{"out_fp_batch": self.name, "out_fp_group_id": group_id},
			"customer",
			limit=1
		)
		if group_customer and group_customer != invoice.customer:
			frappe.throw(_("Customer mismatch: Invoice customer {0} does not match group customer {1}").format(
				invoice.customer, group_customer
			))

		# Assign to group
		frappe.db.set_value(
			"Sales Invoice",
			invoice_name,
			{"out_fp_batch": self.name, "out_fp_group_id": group_id},
			update_modified=False
		)

		# Audit trail
		self.add_comment(
			"Info",
			f"Added {invoice_name} to group {group_id} by {frappe.session.user}"
		)

		return self.get_groups_summary()

	@frappe.whitelist()
	def create_new_group_with_invoice(self, invoice_name):
		"""Create a new group and add invoice to it.

		Args:
			invoice_name: Sales Invoice name
		"""
		# Permission check
		self.check_permission("write")

		# Validate not exported
		self._validate_not_exported()

		# Validate invoice
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if invoice.docstatus != 1:
			frappe.throw(_("Invoice {0} must be submitted").format(invoice_name))

		if invoice.out_fp_status != "Verified":
			frappe.throw(_("Invoice {0} must have Verified tax invoice status").format(invoice_name))

		# Check if already in another batch
		if invoice.out_fp_batch and invoice.out_fp_batch != self.name:
			frappe.throw(_("Invoice {0} is already in batch {1}").format(invoice_name, invoice.out_fp_batch))

		# Calculate next group ID
		max_group_id = frappe.db.get_value(
			"Sales Invoice",
			{"out_fp_batch": self.name},
			"max(out_fp_group_id)"
		) or 0
		next_group_id = max_group_id + 1

		# Assign to new group
		frappe.db.set_value(
			"Sales Invoice",
			invoice_name,
			{"out_fp_batch": self.name, "out_fp_group_id": next_group_id},
			update_modified=False
		)

		# Audit trail
		self.add_comment(
			"Info",
			f"Created new group {next_group_id} with {invoice_name} by {frappe.session.user}"
		)

		return {"group_id": next_group_id, "groups": self.get_groups_summary()}

	@frappe.whitelist()
	def remove_invoice_from_batch(self, invoice_name):
		"""Remove an invoice from this batch.

		Args:
			invoice_name: Sales Invoice name
		"""
		# Permission check
		self.check_permission("write")

		# Validate not exported
		self._validate_not_exported()

		# Clear batch and group
		frappe.db.set_value(
			"Sales Invoice",
			invoice_name,
			{"out_fp_batch": None, "out_fp_group_id": None},
			update_modified=False
		)

		# Audit trail
		self.add_comment(
			"Info",
			f"Removed {invoice_name} from batch by {frappe.session.user}"
		)

		return self.get_groups_summary()

	@frappe.whitelist()
	def move_invoice_to_group(self, invoice_name, new_group_id):
		"""Move an invoice to a different group.

		Args:
			invoice_name: Sales Invoice name
			new_group_id: Target group ID
		"""
		# Permission check
		self.check_permission("write")

		# Validate not exported
		self._validate_not_exported()

		# Get current invoice data
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		old_group_id = invoice.out_fp_group_id

		# Validate customer match with target group
		group_customer = frappe.db.get_value(
			"Sales Invoice",
			{"out_fp_batch": self.name, "out_fp_group_id": new_group_id},
			"customer",
			limit=1
		)
		if group_customer and group_customer != invoice.customer:
			frappe.throw(_("Customer mismatch: Invoice customer {0} does not match group customer {1}").format(
				invoice.customer, group_customer
			))

		# Move to new group
		frappe.db.set_value(
			"Sales Invoice",
			invoice_name,
			{"out_fp_batch": self.name, "out_fp_group_id": new_group_id},
			update_modified=False
		)

		# Audit trail
		self.add_comment(
			"Info",
			f"Moved {invoice_name} from group {old_group_id} to group {new_group_id} by {frappe.session.user}"
		)

		return self.get_groups_summary()

	@frappe.whitelist()
	def export_csv_template(self):
		"""Generate CSV template for bulk Tax Invoice Upload creation.

		Returns:
			dict: CSV content, filename, and metadata
		"""
		import csv
		import io
		import re

		self.check_permission("read")

		# Get batch invoices
		invoices = self.get_batch_invoices()
		if not invoices:
			frappe.throw(_("No invoices found in batch"))

		# Prepare CSV data
		csv_buffer = io.StringIO()
		csv_writer = csv.writer(csv_buffer)

		# Write headers
		csv_writer.writerow([
			'fp_number',
			'sales_invoice',
			'dpp',
			'ppn',
			'fp_date',
			'customer_npwp'
		])

		# Normalize FP number (extract 16 digits)
		def normalize_fp(fp_no_faktur):
			if not fp_no_faktur:
				return ''
			# Extract only digits
			digits = re.sub(r'\D', '', fp_no_faktur)
			# Return last 16 digits if longer, otherwise return as is
			return digits[-16:] if len(digits) >= 16 else digits

		missing_fp_count = 0

		# Write data rows
		for inv in invoices:
			fp_number = normalize_fp(inv.out_fp_no_faktur)
			if not fp_number or len(fp_number) != 16:
				missing_fp_count += 1

			# Get amounts - gracefully handle missing fields
			dpp = inv.get('out_fp_dpp') or inv.get('base_net_total') or 0
			ppn = inv.get('out_fp_ppn') or inv.get('base_tax_total') or 0
			fp_date = inv.get('out_fp_date') or inv.posting_date or ''
			customer_npwp = inv.get('out_fp_customer_npwp') or inv.get('tax_id') or ''

			csv_writer.writerow([
				fp_number,
				inv.name,
				dpp,
				ppn,
				fp_date,
				customer_npwp
			])

		csv_content = csv_buffer.getvalue()
		csv_buffer.close()

		return {
			'csv_content': csv_content,
			'filename': f'VAT_OUT_{self.name}_template.csv',
			'total_invoices': len(invoices),
			'missing_fp_count': missing_fp_count
		}
