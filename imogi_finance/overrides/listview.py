import frappe


@frappe.whitelist()
def get_list_settings(doctype=None):
	if not doctype:
		return {"page_length": 2500}
	try:
		doc = frappe.get_cached_doc("List View Settings", doctype)
		result = doc.as_dict()
		result["page_length"] = 2500
		return result
	except frappe.DoesNotExistError:
		frappe.clear_messages()
		return {"page_length": 2500}