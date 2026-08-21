import frappe


def before_install():
    """Setup required roles before installation."""
    ensure_role_exists("Budget Controller")
    ensure_hidden_mandatory_fields_have_defaults()


# garage's property_setter.json fixture hides several core fields that are
# `reqd: 1` in their own base doctype JSON (e.g. Sales Invoice.base_net_total)
# without reliably landing a matching "default" Property Setter first. Core
# Frappe refuses to even validate a doctype (check_hidden_and_mandatory) once
# it sees hidden+mandatory+no-default on ANY field - and that validation runs
# every time a Custom Field is inserted, not just at migrate time (migrate
# skips it via frappe.flags.in_migrate). On a fresh Frappe Cloud install this
# surfaces the moment imogi_finance's own custom_field.json tries to add
# anything to that same doctype, aborting the whole install. Force a safe
# default here, before any fixture sync starts, regardless of what order or
# state garage's own fixtures land in.
_HIDDEN_MANDATORY_FIELD_DEFAULTS = [
    ("Sales Invoice", "base_net_total", "0"),
    ("Payment Entry", "base_paid_amount", "0"),
    ("Payment Entry", "base_received_amount", "0"),
]


def ensure_hidden_mandatory_fields_have_defaults():
    for doctype, fieldname, default_value in _HIDDEN_MANDATORY_FIELD_DEFAULTS:
        ps_name = f"{doctype}-{fieldname}-default"
        if frappe.db.exists("Property Setter", ps_name):
            if frappe.db.get_value("Property Setter", ps_name, "value") != default_value:
                frappe.db.set_value("Property Setter", ps_name, "value", default_value, update_modified=False)
            continue

        frappe.make_property_setter(
            {
                "doctype": doctype,
                "doctype_or_field": "DocField",
                "fieldname": fieldname,
                "property": "default",
                "value": default_value,
                "property_type": "Text",
            },
            ignore_validate=True,
            is_system_generated=0,
        )


def ensure_role_exists(role_name: str) -> None:
    """Ensure the specified role exists to satisfy link validations during install."""
    if frappe.db.exists("Role", {"role_name": role_name}):
        return

    role = frappe.new_doc("Role")
    role.role_name = role_name
    role.desk_access = 1
    role.insert(ignore_permissions=True)
