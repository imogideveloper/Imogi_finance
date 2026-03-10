# Deferred Expense Tracker - Period Status Indicators

## 📊 Status Period yang Ditampilkan

Saat "Show Monthly Breakdown" diaktifkan, setiap period akan menampilkan status untuk memudahkan monitoring:

### Status Indicators

| Status | Symbol | Arti | Warna/Indikator |
|--------|--------|------|-----------------|
| **✓ Posted** | ✓ | Period sudah di-posting ke Journal Entry | Hijau / Selesai |
| **⚠ Overdue** | ⚠ | Tanggal sudah lewat tapi belum di-post | Merah / Perlu Action |
| **→ Current** | → | Period bulan ini (sedang berjalan) | Biru / Active |
| **○ Upcoming** | ○ | Period masa depan (belum saatnya) | Abu-abu / Waiting |

---

## 🎯 Cara Kerja Logic Status

### 1. ✓ Posted (Sudah Di-posting)
```
Kondisi:
- Ada Journal Entry dengan posting_date sama dengan period_date
- JE status = Submitted (docstatus = 1)
- JE voucher_type = 'Deferred Expense'
- JE reference = Purchase Invoice terkait

Action:
✅ Tidak perlu action (sudah complete)
```

### 2. ⚠ Overdue (Terlambat)
```
Kondisi:
- period_date < today (tanggal sudah lewat)
- TIDAK ada Journal Entry untuk period ini
- Seharusnya sudah di-post tapi belum

Action:
🚨 URGENT: Post period ini segera!
Gunakan: "Post Period" button atau batch posting
```

### 3. → Current (Bulan Ini)
```
Kondisi:
- period_date tahun dan bulan sama dengan hari ini
- Belum ada Journal Entry
- Sedang dalam window posting

Action:
📅 Siap untuk di-post (dalam periode yang tepat)
Recommended: Post sebelum bulan berakhir
```

### 4. ○ Upcoming (Akan Datang)
```
Kondisi:
- period_date > today (tanggal di masa depan)
- Belum saatnya untuk posting

Action:
⏳ Tunggu sampai periode tiba
No action needed yet
```

---

## 📅 Contoh Timeline (Feb 2026)

### Scenario: 12-month schedule starting Jan 2026

```
┌────────┬──────────────┬─────────────┬────────────────┐
│ Period │ Date         │ Amount      │ Status         │
├────────┼──────────────┼─────────────┼────────────────┤
│ 1      │ 02-01-2026   │ 1,000,000   │ ✓ Posted       │ ← Already done
│ 2      │ 02-02-2026   │ 1,000,000   │ → Current      │ ← Act now! (Feb 2026)
│ 3      │ 02-03-2026   │ 1,000,000   │ ○ Upcoming     │ ← Wait (March)
│ 4      │ 02-04-2026   │ 1,000,000   │ ○ Upcoming     │ ← Wait (April)
│ ...    │ ...          │ ...         │ ○ Upcoming     │
│ 12     │ 02-12-2026   │ 1,000,000   │ ○ Upcoming     │ ← Wait (Dec)
└────────┴──────────────┴─────────────┴────────────────┘
```

### Scenario: Terlambat posting beberapa period

```
┌────────┬──────────────┬─────────────┬────────────────┐
│ Period │ Date         │ Amount      │ Status         │
├────────┼──────────────┼─────────────┼────────────────┤
│ 1      │ 28-11-2025   │ 1,000,000   │ ⚠ Overdue      │ ← Urgent! (Nov passed)
│ 2      │ 28-12-2025   │ 1,000,000   │ ⚠ Overdue      │ ← Urgent! (Dec passed)
│ 3      │ 28-01-2026   │ 1,000,000   │ ⚠ Overdue      │ ← Urgent! (Jan passed)
│ 4      │ 28-02-2026   │ 1,000,000   │ → Current      │ ← Post now (Feb 2026)
│ 5      │ 28-03-2026   │ 1,000,000   │ ○ Upcoming     │ ← Wait (March)
└────────┴──────────────┴─────────────┴────────────────┘

Action Needed:
1. Post Period 1-3 segera (backdate ke tanggal asli)
2. Post Period 4 di bulan ini
3. Schedule Period 5+ untuk bulan depan
```

---

## 🚨 Priority Matrix

### High Priority (Action Required)
```
⚠ Overdue - POST IMMEDIATELY
- Period sudah lewat tanggalnya
- Harus di-post dengan backdate
- Impact: Late recognition di GL

→ Current - POST THIS MONTH
- Period bulan ini
- Ideal window untuk posting
- Impact: On-time recognition
```

### Low Priority (Monitoring Only)
```
✓ Posted - ALREADY DONE
- No action needed
- Monitor JE link

○ Upcoming - WAIT
- Future periods
- Schedule posting saat tiba
```

---

## 📈 Dashboard View Concept

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃          PERIOD STATUS SUMMARY                   ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛

Total Periods: 36 (across all schedules)

┌─────────────────┬─────────┬──────────────────┐
│ Status          │ Count   │ Action Required  │
├─────────────────┼─────────┼──────────────────┤
│ ✓ Posted        │   12    │ ✅ None          │
│ → Current       │    3    │ 📅 Post now      │
│ ⚠ Overdue       │    5    │ 🚨 Urgent!       │
│ ○ Upcoming      │   16    │ ⏳ Wait          │
└─────────────────┴─────────┴──────────────────┘

Next Actions:
1. Post 5 overdue periods (backdate)
2. Post 3 current periods (this month)
3. Monitor 16 upcoming periods
```

---

## 🔍 Filtering by Status

### Quick Filters (Conceptual)

```sql
-- Show only overdue periods
SELECT * FROM breakdown
WHERE period_status = '⚠ Overdue';

-- Show current + overdue (actionable)
SELECT * FROM breakdown
WHERE period_status IN ('⚠ Overdue', '→ Current');

-- Show completed
SELECT * FROM breakdown
WHERE period_status = '✓ Posted';

-- Show pending (not posted)
SELECT * FROM breakdown
WHERE period_status != '✓ Posted';
```

---

## ✅ Best Practices

### Weekly Monitoring Checklist
- [ ] Check for ⚠ Overdue periods → Post immediately
- [ ] Review → Current periods → Schedule posting
- [ ] Verify ✓ Posted periods have valid JE links
- [ ] Plan ahead for ○ Upcoming periods

### Monthly Workflow
```
Week 1:
- Review last month's periods
- Post any ⚠ Overdue from previous month
- Check → Current month period ready

Week 2-3:
- Monitor → Current period
- Post if not yet done

Week 4:
- Verify → Current posted before month end
- Prepare for next month's period
```

### Automation Recommendations
1. **Alert System**: Email notification for ⚠ Overdue
2. **Auto-posting**: Schedule JE creation for → Current
3. **Dashboard**: Real-time status count
4. **Reports**: Monthly posting compliance %

---

## 💡 Tips

### Color Coding (Manual or CSS)
```css
.period-posted { color: green; }    /* ✓ Posted */
.period-overdue { color: red; }     /* ⚠ Overdue */
.period-current { color: blue; }    /* → Current */
.period-upcoming { color: gray; }   /* ○ Upcoming */
```

### Icon Meanings
- **✓** = Checkmark (Done)
- **⚠** = Warning (Action needed)
- **→** = Arrow (Active/Current)
- **○** = Circle (Waiting/Pending)

---

## 🎯 Expected Outcomes

### Proper Status Progression
```
Month 1: ○ Upcoming → → Current → ✓ Posted
Month 2: ○ Upcoming → → Current → ✓ Posted
Month 3: ○ Upcoming → → Current → ✓ Posted
...

Goal: Never see ⚠ Overdue!
```

### Ideal Report View
```
All periods showing:
- Past: ✓ Posted (all green)
- Present: → Current (1 period, blue)
- Future: ○ Upcoming (remaining, gray)
- None: ⚠ Overdue (zero red!)
```

---

**Last Updated:** February 3, 2026
**Feature:** Period Status Indicators
**Report:** Deferred Expense Tracker
