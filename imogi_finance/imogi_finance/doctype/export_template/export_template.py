import frappe
from frappe.model.document import Document


class ExportTemplate(Document):
	def before_insert(self):
		if not self.reference_doctype:
			frappe.throw(frappe._("Reference Doctype is required"))
