---
name: 2026-11-26-lead-reconciliation
description: Live DB vs OROVA CRM Sheet reconciliation — every DB lead is in the Sheet; the "missing leads" were a wrong-sheet problem
type: session
created: 2026-11-26
status: done
---

# 2026-11-26 — Lead source-of-truth reconciliation

Read-only. Nothing was written to the DB or the Sheet. Aggregates only; no lead rows are stored here.

## Sources checked (26 Nov 2026)
- **Live DB:** `GET /api/leads?include_invalid=true` on Render (build `deb59605cfa5`).
- **Sheet:** Google Drive file **"OROVA CRM"**, tab `Leads`. Last modified 17 Oct 2026, when the IG DM Queue was consolidated into it. Backups exist: "OROVA CRM — backup before consolidation 2026-10-17" and "OROVA DM Queue — backup before consolidation 2026-10-17". The original queue was renamed "ARCHIVE — OROVA IG DM Queue — consolidated into CRM 2026-10-17".

## Result

| | Count |
|---|---|
| DB leads | **384**, all `Recovery Hold`; IDs 1–384; created 26 Aug – 6 Oct |
| Sheet `Leads` rows | **446**, all `Recovery Hold` |
| DB leads missing from the Sheet | **0** |
| Sheet rows from Nova (IDs match DB) | 380, plus 4 "Nova + manual DM queue" |
| Manual-queue-only rows (not in DB) | 62. Nearly all are Instagram-handle-only; 61 are flagged "Research/identity/ICP review required" |
| Duplicate business names | 1 in the DB; 2 groups in the Sheet, already flagged "Same business name has multiple Nova IDs" |
| EmailSent / Called | all `Unverified` |

**The Sheet is complete. The "Sheet doesn't show all leads" report is a wrong-sheet problem, not lost data:**
1. The master brief's Sheet link pointed at **"OROVA IG Post Log"**, the Instagram post log, not the lead sheet.
2. A starred, older sheet, **"OROVA Leads"**, was last modified May 2026. If that's the bookmark Mark opens, it will look nearly empty.
3. A filter view inside "OROVA CRM" could also hide rows. The export can't show filter views, so check in the browser.

## Open decisions for Mark (not done)
- **The 62 manual-only rows live only in the Sheet**, so the Sheet is acting as a second writer, against the single-source-of-truth rule. Many are off-ICP: roofing 9, HVAC 5, pools 5, landscaping 4, plus AZ/CO/NV. Options: (a) import the ICP-fit ones into the DB through the storage gate (`validate_lead_for_storage`), and (b) mark the rest `Disqualified — off ICP` rather than deleting them.
- **Tidy the Drive:** rename "OROVA Leads" (May) to "ARCHIVE — OROVA Leads (May 2026)" and unstar it. That needs owner approval; nothing was renamed.
