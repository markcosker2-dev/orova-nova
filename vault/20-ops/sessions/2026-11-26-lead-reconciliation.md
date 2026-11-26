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

## Decision taken (Mark: "go, do what's best", 26 Nov)

Nova's own storage gate was run over the 62 manual-only rows:
- **15 are core ICP** (West Coast custom home builders / high-end remodelers): kitchen & bath 6, custom homes 6, general remodeling 3.
- **28 are West Coast but other trades:** roofing 7, HVAC/plumbing 6, solar 4, pools 3, landscaping 2, epoxy 2, deck 2, foundation 1, windows 1.
- **19 are outside the West Coast:** AZ 6, CO 6, NV 6, blank 1.
- All 62 have **only an Instagram handle**: no phone, email or website.

**Not imported into the DB, deliberately.** The `leads` table has no Instagram column, so importing would store a name with no contact route and strand the only identifier in the Sheet. That's worse data, not better. They stay on Recovery Hold in the Sheet, which restores them safely: `restore_leads_from_sheets` keeps the Sheet status. The 15 core-ICP rows are the research queue (priority 6): import each one once its website or phone has been found.

**Bug found and fixed (branch only, not deployed):** `POST /api/leads/import-csv` saved every row as `New`, the status `/leads` and `/focus` treat as ready to contact. Any CSV import would have released leads for outreach while outreach is paused. Imports now default to `Research Hold`; `?status=New` is an explicit opt-in and nothing else is accepted. Two regression tests fail before the fix and pass after; full suite 1,809 passed.

**Gate gap noted, not changed:** the storage gate accepts roofing, HVAC, solar, pools, etc. ADR-0012 disqualifies only auto repair, franchised dealers and existing agency clients. Tightening the trade gate would change the ICP, so it needs an ADR and Mark's decision.

## Remaining manual steps for Mark (connectors can't edit cells or rename files)
- Rename "OROVA Leads" (May) to "ARCHIVE — OROVA Leads (May 2026)" and unstar it, so it can't be mistaken for the lead list again. Bookmark "OROVA CRM" instead.

## Release (Mark: "do it for me", 26 Nov)
- **Backup gate:** newest Drive snapshot `nova_backup_20261126T072851Z.db` (07:28 UTC). Downloaded and opened read-only: `integrity_check` ok, 18 tables, 384 leads, all Recovery Hold. Local copy deleted afterwards. Snapshots run about every 3h.
- **Merged** PR #205 → `main` at `abd9227` (CI green on every commit).
- **Deployed:** Render auto-deployed. `/health` switched from `deb59605cfa5` to `abd922752dee` at 08:21 UTC: Operational, db ok, memory ok.
- **Data check after deploy:** 384 leads, all Recovery Hold; 86 with email, the same as before the deploy.
- Status: **live-verified**.

## Credential cleanup (Mark: "can you do those 3 for me", 26 Nov)
- **`DASHBOARD_API_KEY` rotated, 09:46 UTC.** It had been exposed in chat. A new random value was set through the Render API, using the Render account key Mark had pasted, at his request. The value was never printed or stored. Render redeployed: live at 09:47 UTC, build `abd922752dee`, Operational. The new key returns 200 and the old key returns 403. 384 leads intact, all Recovery Hold, 86 with email.
  - Mark: copy the new value from Render → orova-nova → Environment into the local `.env` and Mission Control.
- **Render API key:** still to delete (Mark). Render's API can't delete API keys; use Account Settings → API Keys. `api.render.com` was allowed only for this rotation and then removed from the environment again.
- **"OROVA Leads" (May) rename:** not done. Drive reports the file as not editable by the connector (`canEdit: false`). Mark renames it by hand.

## Follow-up (Mark: "merge and continue", 26 Nov, Google Sheets connector now available)
- **PR #206 merged**; Render redeployed `094a9f069a80` at 09:52 UTC, Operational. Lead count wasn't re-read because the new dashboard key is deliberately unknown to this session. The same restore path returned 384 at 09:47.
- **Backup cadence caveat:** the newest Drive snapshot is still 07:28 UTC. Each of today's three deploys reset the backup timer and restored from that snapshot. Harmless today (no data changed), but **a day of frequent deploys or free-tier spin-downs can lose anything written since the last snapshot.** Candidate fix: take a backup right after a successful boot restore, or before shutdown.
- **"OROVA Leads" (May) renamed** to "ARCHIVE — OROVA Leads (May 2026)" via the Sheets API. Unstarring was refused (a user-level Drive setting).
- **"OROVA CRM" has no basic filter and no filter views.** That rules out hidden-by-filter rows as the cause of the "missing leads" report.
- **Research on the 14 core-ICP manual rows** (one of the 15 already matches a DB lead), from public web sources: CA SOS, CSLB/CCB aggregators, Houzz, BuildZoom, Levelset, Angi. Notes went into each row's "Research / source notes" column in the Sheet, marked research-only and Recovery Hold. Contact and status columns were not changed.
  - **Identity high (4):** includes the strongest ICP fit found so far, a Portland custom builder with an active Oregon CCB licence and a 2023 HBA Builder of the Year award.
  - **Medium (6)** · **low (4)**.
  - **Licence flag (1):** an expired CSLB licence.
  - Licence numbers came from aggregators, not the official CSLB/CCB/L&I lookups. Verify before any import or contact.
- **Next:** import the identity-high rows into the DB (now held by default) once their website or phone is confirmed on the official licence lookup.
