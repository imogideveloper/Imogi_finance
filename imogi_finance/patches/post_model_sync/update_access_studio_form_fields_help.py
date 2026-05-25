"""Refresh Access Studio help text for hide form fields."""

from imogi_finance.patches.post_model_sync.setup_access_studio_workspace import (
	_create_access_studio_workspace,
)


def execute():
	_create_access_studio_workspace()
