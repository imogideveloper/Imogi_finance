"""Consolidated branch control settings defaults.

Single source of truth for all branch-related configuration defaults.
All modules must import from here instead of defining separately.
"""

BRANCH_SETTING_DEFAULTS = {
    "enable_multi_branch": 0,
    "inherit_branch_from_cost_center": 1,
    "default_branch": None,
    "enforce_branch_on_links": 1,
}
