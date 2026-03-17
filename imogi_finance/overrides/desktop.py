import frappe
from json import loads  # ← ganti ini
from frappe.desk.desktop import Workspace
from frappe.exceptions import DoesNotExistError


@frappe.whitelist()
def get_desktop_page(page=None):
    """Override: tambah default value untuk page agar tidak error di Frappe 15.102.x"""
    if not page:
        return {}
    try:
        workspace = Workspace(loads(page))
        workspace.build_workspace()
        return {
            "charts": workspace.charts,
            "shortcuts": workspace.shortcuts,
            "cards": workspace.cards,
            "onboardings": workspace.onboardings,
            "quick_lists": workspace.quick_lists,
            "number_cards": workspace.number_cards,
            "custom_blocks": workspace.custom_blocks,
        }
    except DoesNotExistError:
        frappe.log_error("Workspace Missing")
        return {}