import frappe
from json import loads

from frappe.desk.desktop import Workspace
from frappe.desk.desktop import get_workspace_sidebar_items as frappe_get_workspace_sidebar_items
from frappe.exceptions import DoesNotExistError

from imogi_finance.workspace_visibility import (
	filter_allowed_workspace_pages,
	filter_workspace_content_json,
	filter_workspace_page_data,
)


@frappe.whitelist()
def get_workspace_sidebar_items():
	"""Filter workspace layout JSON when sidebar/boot pages are refreshed."""
	result = frappe_get_workspace_sidebar_items()
	result["pages"] = filter_allowed_workspace_pages(result.get("pages") or [])
	for page in result.get("pages") or []:
		workspace_name = page.get("name") or page.get("title")
		if page.get("content"):
			page["content"] = filter_workspace_content_json(page["content"], workspace_name)
	return result


@frappe.whitelist()
def get_desktop_page(page=None):
    """Override: default page + filter hidden workspace sections from UI settings."""
    if not page:
        return {}
    try:
        workspace = Workspace(loads(page))
        workspace.build_workspace()
        page_data = {
            "charts": workspace.charts,
            "shortcuts": workspace.shortcuts,
            "cards": workspace.cards,
            "onboardings": workspace.onboardings,
            "quick_lists": workspace.quick_lists,
            "number_cards": workspace.number_cards,
            "custom_blocks": workspace.custom_blocks,
        }
        return filter_workspace_page_data(page_data, workspace.page_name)
    except DoesNotExistError:
        frappe.log_error("Workspace Missing")
        return {}