import frappe

@frappe.whitelist()
def get_list_settings(doctype=None):
    if not doctype:
        return {}
    try:
        return frappe.get_cached_doc("List View Settings", doctype)
    except frappe.DoesNotExistError:
        frappe.clear_messages()
EOF
