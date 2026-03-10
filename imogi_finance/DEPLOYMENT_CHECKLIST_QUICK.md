# Quick Deployment Checklist - Tax Invoice OCR v1.5.0

**Release Date:** February 10, 2026
**⏱️ Estimated Time:** 30-45 minutes
**📋 Print this page for quick reference during deployment**

---

## Pre-Flight Checklist (15 minutes)

### Code Verification
- [ ] `git log -1` → Verify v1.5.0 commit
- [ ] `python -m py_compile normalization.py` → No syntax errors
- [ ] Run all test suites → All pass
- [ ] Test environment validated → Export invoices work

### Backup Everything
- [ ] Database backup created
- [ ] Code backup created
- [ ] Backup files verified (can extract)
- [ ] Backup location documented: `~/backups/pre_v1.5.0_[timestamp]`

### Team Readiness
- [ ] On-call engineer assigned: _______________
- [ ] Team notified of deployment window
- [ ] Rollback procedure printed and ready
- [ ] Emergency contacts list available

---

## Deployment Steps (15 minutes)

### Test Environment First
```bash
# 1. SSH to test server
ssh user@test.imogi.com

# 2. Deploy code
cd ~/frappe-bench/apps/imogi_finance
git pull origin develop

# 3. Restart
cd ~/frappe-bench
bench --site test.imogi.com migrate
bench --site test.imogi.com clear-cache
bench --site test.imogi.com restart
```

- [ ] Test site loads
- [ ] Upload standard 11% invoice → Approved ✅
- [ ] Upload export invoice (0%) → **Approved ✅ (NEW!)**
- [ ] Check logs → No errors

### Production Deployment
**⚠️ Run during low-traffic hours (2-4 AM)**

```bash
# 1. Enable maintenance mode
ssh user@imogi.com
cd ~/frappe-bench
bench --site imogi.com set-maintenance-mode on

# 2. Deploy code
cd apps/imogi_finance
git pull origin main

# 3. Restart
cd ~/frappe-bench
bench --site imogi.com migrate
bench --site imogi.com clear-cache
bench --site imogi.com restart

# 4. Disable maintenance mode
bench --site imogi.com set-maintenance-mode off
```

- [ ] Production site loads
- [ ] Test with standard invoice → Works
- [ ] Monitor logs for 5 minutes → No errors
- [ ] Check server resources → Normal

---

## Post-Deployment Verification (15 minutes)

### Functional Tests
- [ ] **Export Invoice Test:** Upload Faktur 020 → Status "Approved" ✅
- [ ] **Standard 11% Test:** Process normally → No regression ✅
- [ ] **Standard 12% Test:** Process normally → No regression ✅
- [ ] **Performance Test:** Average < 70ms → Faster ✅

### Monitoring Setup
- [ ] Grafana dashboard showing metrics
- [ ] Alerts configured and firing tests
- [ ] Error tracking showing structured errors
- [ ] Zero-rated transaction counter active

### Success Criteria
- [ ] Export invoices approve automatically (was failing before)
- [ ] Processing time < 70ms (was 100ms before)
- [ ] No new critical errors in logs
- [ ] Approval rate maintained or improved

---

## Quick Rollback (If Needed)

**If export invoices still failing OR standard invoices breaking:**

```bash
# 1. Enable maintenance
bench --site imogi.com set-maintenance-mode on

# 2. Rollback code
cd ~/frappe-bench/apps/imogi_finance
git checkout <PREVIOUS_COMMIT>  # Get from git log

# 3. Restart
cd ~/frappe-bench
bench --site imogi.com restart
bench --site imogi.com set-maintenance-mode off

# 4. Notify team immediately
```

**Rollback Decision:** On-call engineer or DevOps lead

---

## Monitoring Checklist (First 24 Hours)

### Hour 1 (Critical)
- [ ] Check error logs every 15 minutes
- [ ] Monitor zero-rated transaction count
- [ ] Verify no spike in "Needs Review" status
- [ ] Check server CPU/memory

### Hour 2-8 (High)
- [ ] Check logs every hour
- [ ] Review invoice approval rates
- [ ] Monitor performance metrics
- [ ] Check support tickets

### Hour 9-24 (Standard)
- [ ] Check logs every 4 hours
- [ ] Review daily metrics summary
- [ ] Prepare status report for team

---

## Key Metrics to Watch

| Metric | Target | Alert If |
|--------|--------|----------|
| **Processing Time** | < 70ms avg | > 100ms |
| **Throughput** | > 14/sec | < 10/sec |
| **Export Approval** | 100% | < 95% |
| **Overall Approval** | > 85% | < 80% |
| **Error Rate** | < 5% | > 10% |
| **CPU Usage** | < 70% | > 90% |

---

## Quick SQL Checks

**Check export invoices are working:**
```sql
-- Should return ZERO rows (all should be approved now)
SELECT COUNT(*)
FROM `tabTax Invoice`
WHERE faktur_type LIKE '020%'
    AND status != 'Approved'
    AND creation >= NOW() - INTERVAL 1 HOUR;
```

**Check zero-rated detection:**
```sql
-- Should return COUNT of export invoices
SELECT COUNT(*)
FROM `tabTax Invoice`
WHERE tax_rate = 0.0
    AND ppn = 0
    AND creation >= NOW() - INTERVAL 1 HOUR;
```

**Check performance:**
```sql
-- Average processing time (should be < 70ms)
SELECT AVG(processing_time_ms)
FROM `tabTax Invoice`
WHERE creation >= NOW() - INTERVAL 1 HOUR;
```

---

## Emergency Contacts

| Issue | Contact | Phone | Action |
|-------|---------|-------|--------|
| **System Down** | On-Call Engineer | +62-XXX | Call immediately |
| **Data Issues** | DevOps Lead | +62-XXX | Call within 30 min |
| **Questions** | Deployment Lead | +62-XXX | Slack/email OK |

---

## Status Updates

**Update Team Every:**
- **T+15min:** Deployment complete ✅
- **T+1hr:** Initial monitoring complete ✅
- **T+8hr:** First day summary ✅
- **T+24hr:** Full day report ✅

**Slack Channel:** #deployments
**Status Page:** https://status.imogi.com

---

## Success Declaration

**Deployment is successful when ALL of these are true:**

✅ Export invoices (Faktur 020) auto-approve
✅ Standard invoices (11%, 12%) work normally
✅ Processing time < 70ms average
✅ No new critical errors
✅ No rollback needed for 24 hours
✅ User complaints = 0

**Sign-off after 24 hours of stable operation.**

---

## Notes Section

**Deployment Date:** _______________
**Deployed By:** _______________
**Start Time:** _______________
**End Time:** _______________

**Issues Encountered:**
```
_______________________________________________
_______________________________________________
_______________________________________________
```

**Resolution:**
```
_______________________________________________
_______________________________________________
_______________________________________________
```

**Final Status:** ☐ Success  ☐ Rolled Back  ☐ Partial

**Sign-off:** _______________ Date: _______________

---

**END OF QUICK CHECKLIST**

📖 **Full Guide:** See [DEPLOYMENT_GUIDE_V1.5.0.md](DEPLOYMENT_GUIDE_V1.5.0.md) for detailed procedures.
