"""Tests for Internal Charge Request workflow and multi-cost-center approval."""

from __future__ import annotations

import types
from datetime import datetime

import pytest

import frappe
from imogi_finance.budget_control import utils
from imogi_finance.imogi_finance.doctype.internal_charge_request.internal_charge_request import (
    InternalChargeRequest,
    _advance_line_status,
)


def _patch_settings(monkeypatch, **kwargs):
    """Patch budget control settings."""
    settings_dict = {
        "doctype": "Budget Control Setting",
        "enable_internal_charge": kwargs.get("enable_internal_charge", 1),
        "internal_charge_required_before_er_approval": kwargs.get("internal_charge_required_before_er_approval", 0),
        "internal_charge_posting_mode": kwargs.get("internal_charge_posting_mode", "Manual"),
        **kwargs,
    }

    def mock_get_settings():
        return settings_dict

    monkeypatch.setattr(utils, "get_settings", mock_get_settings)
    return settings_dict


class TestInternalChargeWorkflowState:
    """Test workflow state synchronization with approval levels."""

    def test_workflow_state_maps_to_pending_l1(self, monkeypatch):
        """Test workflow_state is set to 'Pending L1 Approval' when lines are Pending L1."""
        _patch_settings(monkeypatch, enable_internal_charge=1)
        monkeypatch.setattr(frappe, "get_roles", lambda: ["All"])
        monkeypatch.setattr("frappe.session", types.SimpleNamespace(user="user@test.com"))

        doc = InternalChargeRequest()
        doc.status = "Pending Approval"
        doc.internal_charge_lines = [
            types.SimpleNamespace(line_status="Pending L1", current_approval_level=1)
        ]

        doc._sync_workflow_state()

        assert doc.workflow_state == "Pending L1 Approval"

    def test_workflow_state_maps_to_pending_l2(self, monkeypatch):
        """Test workflow_state is set to 'Pending L2 Approval' when lines are Pending L2."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        doc = InternalChargeRequest()
        doc.status = "Pending Approval"
        doc.internal_charge_lines = [
            types.SimpleNamespace(line_status="Pending L2", current_approval_level=2)
        ]

        doc._sync_workflow_state()

        assert doc.workflow_state == "Pending L2 Approval"

    def test_workflow_state_maps_to_pending_l3(self, monkeypatch):
        """Test workflow_state is set to 'Pending L3 Approval' when lines are Pending L3."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        doc = InternalChargeRequest()
        doc.status = "Pending Approval"
        doc.internal_charge_lines = [
            types.SimpleNamespace(line_status="Pending L3", current_approval_level=3)
        ]

        doc._sync_workflow_state()

        assert doc.workflow_state == "Pending L3 Approval"

    def test_workflow_state_maps_to_approved(self, monkeypatch):
        """Test workflow_state is set to 'Approved' when all lines are Approved."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        doc = InternalChargeRequest()
        doc.status = "Approved"
        doc.internal_charge_lines = [
            types.SimpleNamespace(line_status="Approved", current_approval_level=0)
        ]

        doc._sync_workflow_state()

        assert doc.workflow_state == "Approved"

    def test_workflow_state_maps_to_partially_approved(self, monkeypatch):
        """Test workflow_state is set to 'Partially Approved' when some lines are approved."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        doc = InternalChargeRequest()
        doc.status = "Partially Approved"
        doc.internal_charge_lines = [
            types.SimpleNamespace(line_status="Approved", current_approval_level=0),
            types.SimpleNamespace(line_status="Pending L1", current_approval_level=1),
        ]

        doc._sync_workflow_state()

        assert doc.workflow_state == "Partially Approved"

    def test_workflow_state_maps_to_rejected(self, monkeypatch):
        """Test workflow_state is set to 'Rejected' when any line is rejected."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        doc = InternalChargeRequest()
        doc.status = "Rejected"
        doc.internal_charge_lines = [
            types.SimpleNamespace(line_status="Rejected", current_approval_level=0)
        ]

        doc._sync_workflow_state()

        assert doc.workflow_state == "Rejected"


class TestMultiCostCenterApproval:
    """Test approval with multiple cost centers (per-line approval)."""

    def test_different_approvers_per_cost_center(self, monkeypatch):
        """Test that different cost centers can have different approvers."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        # CC-A requires User1 for L1
        # CC-B requires User2 for L1
        route_a = {
            "level_1": {"user": "user1@test.com"},
            "level_2": {"user": None},
            "level_3": {"user": None},
        }
        route_b = {
            "level_1": {"user": "user2@test.com"},
            "level_2": {"user": None},
            "level_3": {"user": None},
        }

        routes = {"CC-A": route_a, "CC-B": route_b}

        def mock_get_approval_route(cc, accounts, amount, setting_meta=None):
            return routes.get(cc, route_a)

        monkeypatch.setattr(
            "imogi_finance.imogi_finance.doctype.internal_charge_request.internal_charge_request.get_approval_route",
            mock_get_approval_route,
        )

        doc = InternalChargeRequest()
        line_a = types.SimpleNamespace(
            target_cost_center="CC-A",
            amount=100,
            line_status="Pending L1",
            current_approval_level=1,
            level_1_approver="user1@test.com",
            level_1_role=None,
            level_2_approver=None,
            level_2_role=None,
            level_3_approver=None,
            level_3_role=None,
            route_snapshot='{"level_1": {"user": "user1@test.com"}, "level_2": {"user": null}, "level_3": {"user": null}}',
        )
        line_b = types.SimpleNamespace(
            target_cost_center="CC-B",
            amount=200,
            line_status="Pending L1",
            current_approval_level=1,
            level_1_approver="user2@test.com",
            level_1_role=None,
            level_2_approver=None,
            level_2_role=None,
            level_3_approver=None,
            level_3_role=None,
            route_snapshot='{"level_1": {"user": "user2@test.com"}, "level_2": {"user": null}, "level_3": {"user": null}}',
        )

        doc.internal_charge_lines = [line_a, line_b]

        # User1 should only be able to approve CC-A
        monkeypatch.setattr(frappe, "get_roles", lambda: ["All"])
        monkeypatch.setattr("frappe.session", types.SimpleNamespace(user="user1@test.com"))

        try:
            doc._validate_approve_permission()
            # If we get here, User1 was able to approve (which is correct for CC-A)
            # Line A should be in approvable_lines, Line B should not
        except frappe.ValidationError:
            # User1 couldn't approve anything, which would be wrong
            pytest.fail("User1 should be able to approve CC-A lines")

    def test_partial_approval_status(self, monkeypatch):
        """Test that status is 'Partially Approved' when some lines are approved."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        doc = InternalChargeRequest()
        doc.internal_charge_lines = [
            types.SimpleNamespace(target_cost_center="CC-A", line_status="Approved"),
            types.SimpleNamespace(target_cost_center="CC-B", line_status="Pending L1"),
            types.SimpleNamespace(target_cost_center="CC-C", line_status="Pending L1"),
        ]

        doc._sync_status()

        assert doc.status == "Partially Approved"

    def test_all_approved_status(self, monkeypatch):
        """Test that status is 'Approved' when all lines are approved."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        doc = InternalChargeRequest()
        doc.internal_charge_lines = [
            types.SimpleNamespace(target_cost_center="CC-A", line_status="Approved"),
            types.SimpleNamespace(target_cost_center="CC-B", line_status="Approved"),
            types.SimpleNamespace(target_cost_center="CC-C", line_status="Approved"),
        ]

        doc._sync_status()

        assert doc.status == "Approved"

    def test_rejected_status(self, monkeypatch):
        """Test that status is 'Rejected' if any line is rejected."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        doc = InternalChargeRequest()
        doc.internal_charge_lines = [
            types.SimpleNamespace(target_cost_center="CC-A", line_status="Approved"),
            types.SimpleNamespace(target_cost_center="CC-B", line_status="Rejected"),
        ]

        doc._sync_status()

        assert doc.status == "Rejected"


class TestApprovalLevelAdvancement:
    """Test level-by-level approval advancement per cost center."""

    def test_advance_from_l1_to_l2(self, monkeypatch):
        """Test advancement from L1 to L2 when L2 is configured."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        line = types.SimpleNamespace(
            current_approval_level=1,
            line_status="Pending L1",
            level_2_role="Approver",
            level_2_approver=None,
            level_3_role=None,
            level_3_approver=None,
            approved_by=None,
            approved_on=None,
        )

        _advance_line_status(line, session_user="user@test.com")

        assert line.line_status == "Pending L2"
        assert line.current_approval_level == 2

    def test_advance_from_l1_to_approved(self, monkeypatch):
        """Test advancement to 'Approved' when no L2/L3 configured."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        line = types.SimpleNamespace(
            current_approval_level=1,
            line_status="Pending L1",
            level_2_role=None,
            level_2_approver=None,
            level_3_role=None,
            level_3_approver=None,
            approved_by=None,
            approved_on=None,
        )

        _advance_line_status(line, session_user="user@test.com")

        assert line.line_status == "Approved"
        assert line.current_approval_level == 0
        assert line.approved_by == "user@test.com"

    def test_advance_from_l2_to_l3(self, monkeypatch):
        """Test advancement from L2 to L3 when L3 is configured."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        line = types.SimpleNamespace(
            current_approval_level=2,
            line_status="Pending L2",
            level_2_role="Approver",
            level_2_approver=None,
            level_3_role="Senior Approver",
            level_3_approver=None,
            approved_by=None,
            approved_on=None,
        )

        _advance_line_status(line, session_user="user@test.com")

        assert line.line_status == "Pending L3"
        assert line.current_approval_level == 3

    def test_advance_from_l3_to_approved(self, monkeypatch):
        """Test advancement to 'Approved' when L3 is the final level."""
        _patch_settings(monkeypatch, enable_internal_charge=1)

        line = types.SimpleNamespace(
            current_approval_level=3,
            line_status="Pending L3",
            level_3_role="Senior Approver",
            level_3_approver=None,
            approved_by=None,
            approved_on=None,
        )

        _advance_line_status(line, session_user="user@test.com")

        assert line.line_status == "Approved"
        assert line.current_approval_level == 0
        assert line.approved_by == "user@test.com"
