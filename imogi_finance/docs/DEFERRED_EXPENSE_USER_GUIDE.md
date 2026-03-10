# Deferred Expense User Guide

## 1) Setup Deferrable Accounts in Settings

1. Open **Expense Deferred Settings**.
2. Ensure **Enable Deferred Expense** is checked.
3. (Optional) Set **Default Prepaid Account**.
4. Add rows in **Deferrable Accounts**:
   - **Prepaid Account** (Asset)
   - **Expense Account** (Expense)
   - **Default Periods**
   - **Is Active**

Only active prepaid accounts in this whitelist can be used on deferred items.

## 2) Create Expense Request with Deferred Items

1. Add items to the request.
2. For each deferred item, check **Deferred Expense** on the item row.
3. Fill in:
   - **Prepaid Account** (must be in the whitelist)
   - **Deferred Start Date**
   - **Deferred Periods**
4. The system auto-fills **Expense Account** and **Deferred Periods** when the Prepaid Account matches the settings mapping.

Non-deferred items continue to use the standard expense account behavior.

## 3) Auto-Processing (ERPNext Native Deferred Accounting)

When a deferred item is posted to a Purchase Invoice, ERPNext v15’s native deferred accounting fields are populated.
The monthly amortization is created by the standard **Process Deferred Accounting** scheduler.

## 4) Monitoring via Deferred Expense Tracker Report

Use **Deferred Expense Tracker** to monitor:
- Expense Request and item details
- Prepaid vs expense account pairing
- Linked Purchase Invoice status
- Outstanding balance for each deferred item

Filters are available for date ranges and account selection.

## 5) Mixed Items Best Practice

You may mix deferred and non-deferred items in a single request. Ensure each deferred item has complete deferred fields so the system can generate the amortization schedule.

## 6) Cutoff Date Announcement

This feature is effective starting on **[set your go-live date]**.
Existing Purchase Invoices created before this date are not backfilled automatically.
