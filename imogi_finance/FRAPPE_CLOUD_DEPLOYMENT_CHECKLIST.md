# Frappe Cloud Deployment Checklist - Tax Invoice OCR Parser

## Pre-Deployment Verification

### ✅ 1. Requirements File Ready
```bash
# Verify file exists
ls -la imogi_finance/requirements.txt

# Verify content
cat imogi_finance/requirements.txt
# Should contain: PyMuPDF>=1.23.0
```

### ✅ 2. Code Guards in Place
- [x] `extract_text_with_bbox()` returns `[]` if PyMuPDF unavailable (not throw)
- [x] `parse_line_items()` handles empty items with "Needs Review" status
- [x] `on_update()` has duplicate enqueue prevention
- [x] All errors logged with clear messages

---

## Deployment Steps

### Step 1: Commit & Push
```bash
git add imogi_finance/requirements.txt
git add imogi_finance/imogi_finance/parsers/*.py
git add imogi_finance/imogi_finance/doctype/tax_invoice_ocr_upload/*.py
git commit -m "Add Tax Invoice OCR line item parser with PyMuPDF"
git push origin main
```

### Step 2: Deploy to Frappe Cloud
1. Go to **Frappe Cloud Dashboard**
2. Select your site
3. Click **"Deploy"** tab
4. Click **"Deploy"** button (NOT "Restart"!)
5. ⚠️ **CRITICAL**: This must rebuild **BOTH web AND workers**

### Step 3: Monitor Build Logs
Watch for:
- ✅ "Installing dependencies from requirements.txt"
- ✅ "Successfully installed PyMuPDF-X.X.X"
- ❌ Any errors mentioning PyMuPDF

### Step 4: Verify Web Console
```python
# In Frappe Cloud Console
import fitz
print(f"PyMuPDF version: {fitz.version}")
print(f"PyMuPDF path: {fitz.__file__}")
```

### Step 5: Verify Worker (CRITICAL!)
```python
# In Frappe Cloud Console
import frappe

# Option A: Test with existing document
frappe.enqueue(
    "imogi_finance.imogi_finance.doctype.tax_invoice_ocr_upload.tax_invoice_ocr_upload.auto_parse_line_items",
    doc_name="TIO-00001",  # Replace with real doc name
    now=True  # Force synchronous execution
)

# Option B: Test import in worker context
def test_worker_import():
    import fitz
    return f"Worker has PyMuPDF: {fitz.version}"

result = frappe.enqueue(
    method="__main__.test_worker_import",
    now=True
)
print(result)
```

### Step 6: Functional Test
1. Upload a test Faktur Pajak PDF
2. Wait for OCR to complete (`ocr_status = "Done"`)
3. Auto-parse should trigger in background
4. Check `parse_status`:
   - ✅ "Approved" or "Needs Review" (with item data) = SUCCESS
   - ❌ "Needs Review" with "PyMuPDF not installed" = WORKER NOT REBUILT

### Step 7: If Worker Test Fails (Critical!)
```
⚠️ Console import succeeds BUT worker parse fails?

This means web container has PyMuPDF but worker doesn't.

Solution:
1. Go to Frappe Cloud → Your Site → Settings
2. Click "Clear Cache & Deploy" button
3. Wait for complete deployment (5-10 minutes)
4. Repeat Step 5 worker test
5. Should now succeed

Why: Regular deploy sometimes only updates web.
"Clear Cache & Deploy" forces full rebuild of all services.
```

---

## Troubleshooting Guide

### Issue: "PyMuPDF not installed on server"

**Symptoms:**
- `validation_summary` shows yellow warning
- Error Log: "PyMuPDF Not Installed"
- No line items extracted

**Solutions:**
1. **Check requirements.txt location**: Must be `imogi_finance/requirements.txt`
2. **Check build logs**: Search for PyMuPDF installation
3. **Try Clear Cache & Deploy**: Sometimes build cache causes issues
4. **Verify full rebuild**: Workers must be rebuilt, not just web

### Issue: Works in Console, Fails in Worker

**Root Cause:**
- Console runs in web container
- Background jobs run in worker container
- These are DIFFERENT environments!

**Solution:**
```bash
# Force full rebuild of ALL services
1. Go to Frappe Cloud Dashboard
2. Try "Clear Cache & Deploy"
3. Wait for COMPLETE deployment (web + workers)
4. Test with enqueue(..., now=True) again
```

### Issue: Duplicate Parse Jobs

**Symptoms:**
- Multiple parse attempts for same document
- Queue flooded with jobs

**Verification:**
- Check `on_update()` conditions
- Verify `parse_status` is set after first parse
- Check Error Log for enqueue spam

**Should Not Happen:**
- Code has deduplication via:
  - `parse_status in [Draft, None, ""]` check
  - Unique `job_name` parameter
  - Existing queue check (production)

---

## Success Criteria Checklist

### ✅ Deployment Success
- [ ] Build logs show PyMuPDF installation
- [ ] Console import fitz succeeds
- [ ] Worker enqueue test succeeds
- [ ] No errors in Error Log

### ✅ Functional Success
- [ ] PDF upload works
- [ ] OCR completes
- [ ] Auto-parse triggers
- [ ] Line items extracted
- [ ] `parse_status` set correctly
- [ ] `validation_summary` shows status

### ✅ Error Handling Success
- [ ] Empty items → "Needs Review" with clear message
- [ ] PyMuPDF missing → warning (not crash)
- [ ] Duplicate saves → no job spam
- [ ] All errors in Error Log with context

---

## Post-Deployment Monitoring

### First 24 Hours
Monitor:
1. Error Log for "PyMuPDF" or "auto_parse" errors
2. Background Jobs queue for stuck jobs
3. User feedback on parsing accuracy

### Ongoing
- Check `parse_status` distribution (Approved vs Needs Review)
- Review `parsing_debug_json` for common patterns
- Monitor `token_count` in debug info (should be >100 for typical FP)

---

**Last Updated**: February 8, 2026  
**Status**: ✅ Production Ready - No Silent Failures
