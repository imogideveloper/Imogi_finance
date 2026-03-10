# Multi-Branch Reporting & Automation

This document summarizes the new reporting scaffolding for IMOGI-FINANCE. It is intentionally modular so future API and UI work can extend the same primitives.

## Core capabilities

- **Branch-aware aggregation**: `build_daily_report` partitions transactions per branch, calculates opening/in/out/closing balances, and builds a consolidated “All Branches” view.
- **Signer blocks**: `resolve_signers` merges global settings with ad-hoc overrides to keep report signatures consistent between daily and monthly flows.
- **Monthly reconciliation**: `build_monthly_reconciliation` compares ledger activity with imported bank statements (CSV/Excel), records matches/missing rows, and can automatically mark the period closed when no gaps remain.
- **Dashboard payloads**: `build_dashboard_snapshot` returns a JSON-friendly structure that feeds Chart.js/Plotly dashboards via `public/js/report_dashboard.js`.
- **Scheduler abstraction**: `ReportScheduler` prefers APScheduler when available and falls back to an in-memory collector, letting us define daily/monthly jobs without forcing a background worker in tests.

## Backend entry points

- `imogi_finance.reporting.build_daily_report` — calculate per-branch and consolidated totals for a given date.
- `imogi_finance.reporting.build_monthly_reconciliation` — compute matches/gaps between ledger rows and bank statements for a month key (e.g., `"2024-03"`).
- `imogi_finance.reporting.parse_statement_rows` — parse CSV/Excel-style content for manual reconciliation uploads.
- `imogi_finance.reporting.build_dashboard_snapshot` — prepare dashboard-ready JSON.
- `imogi_finance.api.reporting.preview_daily_report` — lightweight API preview using current settings and no data (safe for UI bootstraps).
- `imogi_finance.api.reporting.plan_reporting_jobs` — returns schedule definitions for daily and monthly jobs without starting a worker.

## Frontend hook

`imogi_finance/public/js/report_dashboard.js` reads the snapshot API and renders either Chart.js or Plotly charts, plus a simple numeric summary. Add elements with `data-report-dashboard-chart`, `data-report-dashboard-plotly`, or `data-report-dashboard-summary` attributes to wire the dashboard.

## Extending the system

- Replace the placeholder data providers with real REST controllers that pull ledger/bank statement data.
- Attach PDF/Excel exporters by passing `serialize_for_export(bundle, reconciliation)` output to your templating engine.
- Swap the in-memory scheduler with Celery beat or APScheduler by instantiating `ReportScheduler(activate=True)` in a long-lived worker process.
