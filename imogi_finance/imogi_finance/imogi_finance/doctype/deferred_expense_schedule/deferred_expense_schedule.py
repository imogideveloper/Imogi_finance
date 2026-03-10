"""Deferred Expense Schedule - Auto-generate monthly breakdown mirip Journal Entry."""

import frappe
from frappe.model.document import Document
from frappe.utils import flt, add_months, getdate, nowdate
from frappe import _


class DeferredExpenseSchedule(Document):
	"""Doctype untuk tracking deferred expense monthly breakdown."""

	def validate(self):
		"""Validate and auto-generate monthly schedule."""
		self.validate_amounts()

		# Auto-generate schedule jika belum ada atau berubah
		if not self.monthly_schedule or self.has_value_changed("total_amount") or \
		   self.has_value_changed("total_periods") or self.has_value_changed("start_date"):
			self.generate_monthly_schedule()

		self.calculate_summary()

	def validate_amounts(self):
		"""Validate total amount and periods."""
		if flt(self.total_amount) <= 0:
			frappe.throw(_("Total Amount must be greater than zero"))

		if not self.total_periods or self.total_periods <= 0:
			frappe.throw(_("Total Periods must be greater than zero"))

		if not self.start_date:
			frappe.throw(_("Start Date is required"))

	def generate_monthly_schedule(self):
		"""Generate monthly breakdown schedule - mirip Journal Entry logic.

		Contoh: 12 juta / 12 bulan = 1 juta per bulan
		"""
		self.monthly_schedule = []

		total_amount = flt(self.total_amount)
		periods = int(self.total_periods)
		start_date = getdate(self.start_date)

		# Hitung amount per period (base amount)
		monthly_amount = total_amount / periods
		remaining = total_amount

		for period_idx in range(periods):
			# Period terakhir dapat sisa (handle rounding)
			if period_idx == periods - 1:
				period_amount = remaining
			else:
				period_amount = flt(monthly_amount, 2)  # Round to 2 decimal

			# Calculate posting date - tambah bulan sesuai period
			posting_date = add_months(start_date, period_idx)

			# Tambah row ke child table
			self.append("monthly_schedule", {
				"period": period_idx + 1,
				"posting_date": posting_date,
				"period_amount": period_amount,
				"status": "Pending"
			})

			remaining -= period_amount

		frappe.msgprint(
			_("Generated {0} monthly periods with {1} per period").format(
				periods,
				frappe.format_value(monthly_amount, {"fieldtype": "Currency"})
			),
			indicator="green",
			alert=True
		)

	def calculate_summary(self):
		"""Calculate summary totals."""
		total_scheduled = 0
		total_posted = 0

		for row in self.monthly_schedule:
			total_scheduled += flt(row.period_amount)
			if row.status == "Posted" and row.journal_entry:
				total_posted += flt(row.period_amount)

		self.total_scheduled = total_scheduled
		self.total_posted = total_posted
		self.outstanding_amount = total_scheduled - total_posted

		# Update status based on progress
		if total_posted >= total_scheduled:
			self.status = "Completed"
		elif total_posted > 0:
			self.status = "Posting"
		elif self.monthly_schedule:
			self.status = "Scheduled"
		else:
			self.status = "Draft"

	def on_submit(self):
		"""On submit - schedule ready for posting."""
		if not self.monthly_schedule:
			frappe.throw(_("Cannot submit without monthly schedule"))

		self.status = "Scheduled"

	def on_cancel(self):
		"""On cancel - mark all as cancelled."""
		self.status = "Cancelled"
		for row in self.monthly_schedule:
			if not row.journal_entry:
				row.status = "Cancelled"


@frappe.whitelist()
def create_from_purchase_invoice(pi_name, item_code):
	"""Create Deferred Expense Schedule from Purchase Invoice Item.

	Args:
		pi_name: Purchase Invoice name
		item_code: Item code yang memiliki deferred expense

	Returns:
		dict: Created schedule details
	"""
	pi = frappe.get_doc("Purchase Invoice", pi_name)

	# Find deferred item
	item = None
	for pi_item in pi.items:
		if pi_item.item_code == item_code and pi_item.get("enable_deferred_expense"):
			item = pi_item
			break

	if not item:
		frappe.throw(_("Item {0} not found or not deferred in PI {1}").format(item_code, pi_name))

	# Check if schedule already exists
	existing = frappe.db.exists("Deferred Expense Schedule", {
		"purchase_invoice": pi_name,
		"item_code": item_code,
		"docstatus": ["<", 2]
	})

	if existing:
		frappe.throw(_("Deferred Expense Schedule already exists: {0}").format(existing))

	# Create new schedule
	schedule = frappe.new_doc("Deferred Expense Schedule")
	schedule.purchase_invoice = pi_name
	schedule.expense_request = pi.get("imogi_expense_request")
	schedule.item_code = item.item_code
	schedule.item_description = item.description or item.item_name
	schedule.total_amount = flt(item.amount)
	schedule.total_periods = int(item.get("deferred_expense_periods") or 12)
	schedule.start_date = item.get("service_start_date") or pi.posting_date

	# Save akan trigger auto-generate schedule
	schedule.insert()

	return {
		"schedule_name": schedule.name,
		"total_amount": schedule.total_amount,
		"total_periods": schedule.total_periods,
		"monthly_breakdown": len(schedule.monthly_schedule)
	}


@frappe.whitelist()
def post_period_to_journal_entry(schedule_name, period):
	"""Post specific period to Journal Entry.

	Args:
		schedule_name: Deferred Expense Schedule name
		period: Period number to post

	Returns:
		str: Created Journal Entry name
	"""
	schedule = frappe.get_doc("Deferred Expense Schedule", schedule_name)

	if schedule.docstatus != 1:
		frappe.throw(_("Schedule must be submitted first"))

	# Find period row
	period_row = None
	for row in schedule.monthly_schedule:
		if row.period == int(period):
			period_row = row
			break

	if not period_row:
		frappe.throw(_("Period {0} not found in schedule").format(period))

	if period_row.status == "Posted":
		frappe.throw(_("Period {0} already posted to JE {1}").format(period, period_row.journal_entry))

	# Get PI details
	pi = frappe.get_doc("Purchase Invoice", schedule.purchase_invoice)
	item = None
	for pi_item in pi.items:
		if pi_item.item_code == schedule.item_code:
			item = pi_item
			break

	if not item:
		frappe.throw(_("Item not found in Purchase Invoice"))

	# Create Journal Entry
	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Deferred Expense"
	je.posting_date = period_row.posting_date
	je.company = pi.company
	je.user_remark = _("Deferred Expense Amortization - Period {0}/{1} for {2}").format(
		period, schedule.total_periods, schedule.purchase_invoice
	)

	# Debit: Prepaid Account (decrease asset)
	prepaid_account = item.get("deferred_expense_account")
	if not prepaid_account:
		frappe.throw(_("Deferred Expense Account not found in PI item"))

	je.append("accounts", {
		"account": prepaid_account,
		"debit_in_account_currency": flt(period_row.period_amount),
		"reference_type": "Purchase Invoice",
		"reference_name": schedule.purchase_invoice
	})

	# Credit: Expense Account (recognize expense)
	expense_account = item.get("expense_account")
	if not expense_account:
		frappe.throw(_("Expense Account not found in PI item"))

	je.append("accounts", {
		"account": expense_account,
		"credit_in_account_currency": flt(period_row.period_amount),
		"reference_type": "Purchase Invoice",
		"reference_name": schedule.purchase_invoice
	})

	je.insert()
	je.submit()

	# Update period row
	period_row.journal_entry = je.name
	period_row.status = "Posted"
	period_row.posted_date = frappe.utils.now()

	# Save and recalculate summary
	schedule.save()

	frappe.msgprint(
		_("Period {0} posted to Journal Entry {1}").format(period, je.name),
		indicator="green",
		alert=True
	)

	return je.name


@frappe.whitelist()
def post_all_periods(schedule_name):
	"""Post all pending periods to Journal Entry.

	Args:
		schedule_name: Deferred Expense Schedule name

	Returns:
		dict: Summary of posted JEs
	"""
	schedule = frappe.get_doc("Deferred Expense Schedule", schedule_name)

	if schedule.docstatus != 1:
		frappe.throw(_("Schedule must be submitted first"))

	posted_jes = []
	failed = []

	for row in schedule.monthly_schedule:
		if row.status == "Pending":
			try:
				je_name = post_period_to_journal_entry(schedule_name, row.period)
				posted_jes.append(je_name)
			except Exception as e:
				failed.append({
					"period": row.period,
					"error": str(e)
				})

	return {
		"schedule": schedule_name,
		"total_posted": len(posted_jes),
		"journal_entries": posted_jes,
		"failed": failed,
		"status": schedule.status
	}
