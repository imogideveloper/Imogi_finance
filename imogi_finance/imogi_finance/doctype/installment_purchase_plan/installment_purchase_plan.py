# Copyright (c) 2026, Imogi and contributors
# For license information, please see license.txt

"""Installment Purchase Plan - sistem cicilan pembelian aset.

Breakdown harga aset (dikurangi DP) jadi jadwal cicilan anuitas
(declining balance): angsuran per periode tetap, tapi komposisi
pokok/bunga berubah tiap periode - periode pertama selalu 0% bunga
(full pokok), periode berikutnya bunga dihitung dari sisa saldo pokok.

Tiap PO yang di-generate otomatis punya 2 baris item (pokok & bunga)
dengan akun GL terpisah, supaya waktu di-convert ke Purchase Invoice
jurnalnya otomatis kesplit ke akun yang benar.
"""

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, add_months, flt, getdate, now_datetime, nowdate
from frappe import _

INSTALLMENT_LEAD_DAYS = 7
INSTALLMENT_PRINCIPAL_ITEM = "Angsuran Pokok"
INSTALLMENT_INTEREST_ITEM = "Angsuran Bunga"


class InstallmentPurchasePlan(Document):
	"""Doctype untuk tracking rencana & jadwal cicilan pembelian aset."""

	def validate(self):
		"""Validate and auto-generate installment schedule."""
		self.validate_amounts()
		self.principal_amount = flt(self.asset_price) - flt(self.down_payment)

		if not self.installment_schedule or self.has_value_changed("asset_price") or \
		   self.has_value_changed("down_payment") or self.has_value_changed("interest_rate_per_period") or \
		   self.has_value_changed("tenor") or self.has_value_changed("tenor_unit") or \
		   self.has_value_changed("start_date"):
			self.generate_installment_schedule()

		self.calculate_summary()

	def validate_amounts(self):
		"""Validate asset price, DP, rate, and tenor."""
		if flt(self.asset_price) <= 0:
			frappe.throw(_("Asset Price must be greater than zero"))

		if flt(self.down_payment) < 0:
			frappe.throw(_("Down Payment cannot be negative"))

		if flt(self.down_payment) >= flt(self.asset_price):
			frappe.throw(_("Down Payment must be less than Asset Price"))

		if flt(self.interest_rate_per_period) < 0:
			frappe.throw(_("Interest Rate per Period cannot be negative"))

		if not self.tenor or self.tenor <= 0:
			frappe.throw(_("Tenor must be greater than zero"))

		if not self.start_date:
			frappe.throw(_("Start Date is required"))

	def generate_installment_schedule(self):
		"""Generate installment breakdown using annuity (declining balance) method.

		Periode pertama selalu 0% bunga (full ke pokok). Periode 2..n dihitung
		pakai anuitas standar dari sisa saldo, dengan angsuran tetap:

			k = r / (1 - (1+r)^-(n-1))
			A = P * k / (1 + k)

		Periode terakhir menyerap sisa pembulatan supaya saldo pas jadi 0.
		"""
		self.installment_schedule = []

		principal = flt(self.principal_amount)
		periods = int(self.tenor)
		rate = flt(self.interest_rate_per_period) / 100.0
		start_date = getdate(self.start_date)
		is_yearly = self.tenor_unit == "Year"

		if periods == 1:
			fixed_installment = principal
		elif rate == 0:
			fixed_installment = flt(principal / periods, 2)
		else:
			denom = 1 - (1 + rate) ** -(periods - 1)
			k = rate / denom
			fixed_installment = flt(principal * k / (1 + k), 2)

		balance = principal

		for period_idx in range(periods):
			months_offset = period_idx * 12 if is_yearly else period_idx
			due_date = add_months(start_date, months_offset)
			opening_balance = balance

			if period_idx == 0:
				interest_portion = 0
				principal_portion = fixed_installment
			elif period_idx == periods - 1:
				interest_portion = flt(balance * rate, 2)
				principal_portion = balance
			else:
				interest_portion = flt(balance * rate, 2)
				principal_portion = flt(fixed_installment - interest_portion, 2)

			installment_amount = flt(principal_portion + interest_portion, 2)
			balance = flt(balance - principal_portion, 2)

			self.append("installment_schedule", {
				"period": period_idx + 1,
				"due_date": due_date,
				"opening_balance": opening_balance,
				"principal_portion": principal_portion,
				"interest_portion": interest_portion,
				"installment_amount": installment_amount,
				"status": "Pending"
			})

		self.installment_amount = fixed_installment
		self.total_interest = sum(flt(r.interest_portion) for r in self.installment_schedule)
		self.total_payable = principal + flt(self.total_interest)

		frappe.msgprint(
			_("Generated {0} installment periods, {1} per period").format(
				periods,
				frappe.format_value(fixed_installment, {"fieldtype": "Currency"})
			),
			indicator="green",
			alert=True
		)

	def calculate_summary(self):
		"""Calculate summary totals."""
		total_scheduled = 0
		total_po_created = 0

		for row in self.installment_schedule:
			total_scheduled += flt(row.installment_amount)
			if row.status == "PO Created" and row.purchase_order:
				total_po_created += flt(row.installment_amount)

		self.total_scheduled = total_scheduled
		self.total_po_created = total_po_created
		self.outstanding_amount = total_scheduled - total_po_created

		if self.docstatus == 1:
			if total_po_created >= total_scheduled:
				self.status = "Completed"
			else:
				self.status = "Active"

	def on_submit(self):
		"""On submit - schedule ready, PO will auto-create as due dates approach."""
		if not self.installment_schedule:
			frappe.throw(_("Cannot submit without installment schedule"))

		self.status = "Active"

	def on_cancel(self):
		"""On cancel - mark pending periods as cancelled."""
		self.status = "Cancelled"
		for row in self.installment_schedule:
			if row.status == "Pending":
				row.status = "Cancelled"

	def before_update_after_submit(self):
		"""Recalculate summary when rows are updated post-submit (e.g. PO created).

		Frappe does NOT call validate() for update-after-submit saves, only
		this hook, so calculate_summary() has to be triggered here instead.
		"""
		self.calculate_summary()


def _make_purchase_order(plan, row):
	"""Build (insert-only, Draft) Purchase Order for one installment row.

	2 baris item: pokok (ke principal_payable_account) dan bunga (ke
	interest_expense_account, di-skip kalau 0 - kasus periode pertama).
	"""
	po = frappe.new_doc("Purchase Order")
	po.supplier = plan.supplier
	po.company = plan.company
	po.schedule_date = row.due_date
	po.transaction_date = row.due_date
	po.append("items", {
		"item_code": INSTALLMENT_PRINCIPAL_ITEM,
		"description": _("Cicilan Pokok {0}/{1} - {2}").format(row.period, plan.tenor, plan.asset_description),
		"qty": 1,
		"rate": flt(row.principal_portion),
		"expense_account": plan.principal_payable_account,
		"schedule_date": row.due_date
	})

	if flt(row.interest_portion) > 0:
		po.append("items", {
			"item_code": INSTALLMENT_INTEREST_ITEM,
			"description": _("Cicilan Bunga {0}/{1} - {2}").format(row.period, plan.tenor, plan.asset_description),
			"qty": 1,
			"rate": flt(row.interest_portion),
			"expense_account": plan.interest_expense_account,
			"schedule_date": row.due_date
		})

	po.insert()
	return po


@frappe.whitelist()
def create_purchase_order_for_period(plan_name, period):
	"""Manually create the Draft Purchase Order for one specific period.

	Args:
		plan_name: Installment Purchase Plan name
		period: Period number to create PO for

	Returns:
		str: Created Purchase Order name
	"""
	plan = frappe.get_doc("Installment Purchase Plan", plan_name)

	if plan.docstatus != 1:
		frappe.throw(_("Plan must be submitted first"))

	period_row = None
	for row in plan.installment_schedule:
		if row.period == int(period):
			period_row = row
			break

	if not period_row:
		frappe.throw(_("Period {0} not found in schedule").format(period))

	if period_row.status == "PO Created":
		frappe.throw(_("Period {0} already has PO {1}").format(period, period_row.purchase_order))

	po = _make_purchase_order(plan, period_row)

	period_row.purchase_order = po.name
	period_row.status = "PO Created"
	period_row.po_created_date = now_datetime()

	plan.save()

	frappe.msgprint(
		_("Period {0} - Purchase Order {1} created (Draft)").format(period, po.name),
		indicator="green",
		alert=True
	)

	return po.name


@frappe.whitelist()
def create_all_due_purchase_orders(plan_name):
	"""Create Draft Purchase Orders for all pending periods of one plan.

	Args:
		plan_name: Installment Purchase Plan name

	Returns:
		dict: Summary of created POs
	"""
	plan = frappe.get_doc("Installment Purchase Plan", plan_name)

	if plan.docstatus != 1:
		frappe.throw(_("Plan must be submitted first"))

	created_pos = []
	failed = []

	for row in plan.installment_schedule:
		if row.status == "Pending":
			try:
				po_name = create_purchase_order_for_period(plan_name, row.period)
				created_pos.append(po_name)
			except Exception as e:
				failed.append({"period": row.period, "error": str(e)})

	return {
		"plan": plan_name,
		"total_created": len(created_pos),
		"purchase_orders": created_pos,
		"failed": failed
	}


def create_due_purchase_orders():
	"""Scheduled daily task: auto-create Draft PO for installments due within
	INSTALLMENT_LEAD_DAYS days on every Active plan.
	"""
	cutoff_date = add_days(nowdate(), INSTALLMENT_LEAD_DAYS)

	plan_names = frappe.get_all(
		"Installment Purchase Plan",
		filters={"docstatus": 1, "status": "Active"},
		pluck="name"
	)

	for plan_name in plan_names:
		try:
			due_rows = frappe.get_all(
				"Installment Purchase Plan Detail",
				filters={
					"parenttype": "Installment Purchase Plan",
					"parent": plan_name,
					"status": "Pending",
					"due_date": ["<=", cutoff_date]
				},
				pluck="period"
			)

			if not due_rows:
				continue

			plan = frappe.get_doc("Installment Purchase Plan", plan_name)

			for row in plan.installment_schedule:
				if row.period in due_rows and row.status == "Pending":
					po = _make_purchase_order(plan, row)
					row.purchase_order = po.name
					row.status = "PO Created"
					row.po_created_date = now_datetime()

			plan.save()
			frappe.db.commit()
		except Exception as e:
			frappe.log_error(
				title="create_due_purchase_orders failed",
				message=f"Plan {plan_name}: {e}"
			)
