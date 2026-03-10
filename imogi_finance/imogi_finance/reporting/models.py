from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class ReportSigners:
    prepared_by: str | None = None
    approved_by: str | None = None
    acknowledged_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prepared_by": self.prepared_by,
            "approved_by": self.approved_by,
            "acknowledged_by": self.acknowledged_by,
        }


@dataclass
class BranchReport:
    branch: str
    opening_balance: float = 0.0
    inflow: float = 0.0
    outflow: float = 0.0
    closing_balance: float = 0.0
    transactions: list[dict[str, Any]] = field(default_factory=list)
    signers: ReportSigners | None = None
    status: str = "draft"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "branch": self.branch,
            "opening_balance": self.opening_balance,
            "inflow": self.inflow,
            "outflow": self.outflow,
            "closing_balance": self.closing_balance,
            "transactions": self.transactions,
            "status": self.status,
        }
        if self.signers:
            payload["signers"] = self.signers.to_dict()
        return payload


@dataclass
class DailyReportBundle:
    report_date: date
    branches: list[BranchReport]
    consolidated: BranchReport
    signers: ReportSigners | None = None
    template: str = "daily_report"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date.isoformat(),
            "branches": [branch.to_dict() for branch in self.branches],
            "consolidated": self.consolidated.to_dict(),
            "signers": self.signers.to_dict() if self.signers else None,
            "template": self.template,
        }


@dataclass
class MonthlyReconciliationResult:
    month: str
    matches: list[dict[str, Any]] = field(default_factory=list)
    missing_from_bank: list[dict[str, Any]] = field(default_factory=list)
    missing_from_ledger: list[dict[str, Any]] = field(default_factory=list)
    closing_status: str = "open"
    closing_balance: float = 0.0
    statement_balance: float = 0.0
    ledger_balance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "month": self.month,
            "matches": self.matches,
            "missing_from_bank": self.missing_from_bank,
            "missing_from_ledger": self.missing_from_ledger,
            "closing_status": self.closing_status,
            "closing_balance": self.closing_balance,
            "statement_balance": self.statement_balance,
            "ledger_balance": self.ledger_balance,
        }


@dataclass
class ScheduledJob:
    name: str
    trigger: str
    schedule: str
    target: str
    kwargs: dict[str, Any] = field(default_factory=dict)
    backend: str = "in-memory"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "trigger": self.trigger,
            "schedule": self.schedule,
            "target": self.target,
            "kwargs": self.kwargs,
            "backend": self.backend,
        }
