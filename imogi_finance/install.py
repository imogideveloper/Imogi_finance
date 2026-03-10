import frappe


def before_install():
    """Setup required roles before installation."""
    ensure_role_exists("Budget Controller")


def ensure_role_exists(role_name: str) -> None:
    """Ensure the specified role exists to satisfy link validations during install."""
    if frappe.db.exists("Role", {"role_name": role_name}):
        return

    role = frappe.new_doc("Role")
    role.role_name = role_name
    role.desk_access = 1
    role.insert(ignore_permissions=True)
