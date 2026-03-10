import pytest

from imogi_finance.reporting import (
    ReportScheduler,
    build_daily_report,
    build_monthly_reconciliation,
    parse_statement_rows,
    resolve_signers,
)


def test_daily_report_partitions_and_consolidates():
    transactions = [
        {"branch": "BR-1", "amount": 100, "direction": "in", "reference": "TX-1"},
        {"branch": "BR-1", "amount": 50, "direction": "out", "reference": "TX-2"},
        {"branch": "BR-2", "amount": 200, "direction": "out", "reference": "TX-3"},
    ]

    signers = resolve_signers({"prepared_by": "Alice", "approved_by": "Bob"})
    bundle = build_daily_report(
        transactions,
        opening_balances={"BR-1": 1000, "BR-2": 300},
        signers=signers,
        status="published",
    )

    branch_totals = {branch.branch: branch for branch in bundle.branches}
    assert branch_totals["BR-1"].closing_balance == pytest.approx(1050)
    assert branch_totals["BR-2"].closing_balance == pytest.approx(100)
    assert bundle.consolidated.closing_balance == pytest.approx(1150)
    assert bundle.consolidated.signers.prepared_by == "Alice"


def test_daily_report_respects_branch_filter():
    transactions = [
        {"branch": "BR-1", "amount": 100, "direction": "in"},
        {"branch": "BR-2", "amount": 40, "direction": "out"},
    ]

    bundle = build_daily_report(transactions, allowed_branches=["BR-2"])

    assert [branch.branch for branch in bundle.branches] == ["BR-2"]
    assert bundle.consolidated.closing_balance == pytest.approx(-40)


def test_monthly_reconciliation_detects_gaps():
    ledger = [
        {"amount": 200, "direction": "in", "reference": "DEP-1", "posting_date": "2024-03-01"},
        {"amount": 50, "direction": "out", "reference": "PAY-1", "posting_date": "2024-03-02"},
    ]
    statements = [
        {"amount": 200, "reference": "DEP-1", "direction": "in", "posting_date": "2024-03-01"},
        {"amount": 75, "reference": "DEP-UNMATCHED", "direction": "in", "posting_date": "2024-03-03"},
    ]

    result = build_monthly_reconciliation(
        ledger_transactions=ledger,
        bank_statements=statements,
        month="2024-03",
        tolerance=0.1,
        auto_close=True,
    )

    assert result.matches and result.matches[0]["ledger"]["reference"] == "DEP-1"
    assert result.missing_from_bank[0]["reference"] == "PAY-1"
    assert result.missing_from_ledger[0]["reference"] == "DEP-UNMATCHED"
    assert result.closing_status == "open"


def test_statement_parser_handles_branch_and_direction():
    content = "branch,amount,direction,reference,date\nBR-1,100,in,DEP-1,2024-03-01\n,,out,DEP-2,2024-03-02\n"
    rows = parse_statement_rows(content, branch="BR-DEFAULT")

    assert rows[0]["branch"] == "BR-1"
    assert rows[0]["direction"] == "in"
    assert rows[1]["branch"] == "BR-DEFAULT"
    assert rows[1]["direction"] == "out"


def test_scheduler_collects_jobs_without_activation():
    scheduler = ReportScheduler(activate=False)
    scheduler.schedule_daily_report(lambda **kwargs: None, branches=["BR-1"])
    scheduler.schedule_monthly_reconciliation(lambda: None)

    assert len(scheduler.jobs) == 2
    assert scheduler.jobs[0].name == "daily-report"
    assert scheduler.jobs[1].name == "monthly-reconciliation"
    assert scheduler.backend in {"in-memory", "BackgroundScheduler"}
