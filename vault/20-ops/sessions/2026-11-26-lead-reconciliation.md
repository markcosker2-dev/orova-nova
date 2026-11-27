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
- **Backup cadence caveat:** the newest Drive snapshot is still 07:28 UTC. Each of today's three deploys reset the backup timer and restored from that snapshot. Harmless today (no data changed), but **a day of frequent deploys or free-tier spin-downs can lose anything written since the last snapshot.** **Root cause found and fixed:** the lifespan shutdown backup already exists, but it never ran. The Dockerfile started `sh -c "uvicorn ..."`; dash stayed PID 1 and didn't forward Render's SIGTERM, so uvicorn was SIGKILLed after the grace period. Reproduced locally with dash 0.5.12 (the same major version as python:3.12-slim): plain `sh -c` means the child never gets SIGTERM; `exec` means it does. Fix: `exec uvicorn` in the Dockerfile CMD, plus `tests/test_dockerfile_signals.py` (fails before, passes after). Full suite 1,810 passed.
- **"OROVA Leads" (May) renamed** to "ARCHIVE — OROVA Leads (May 2026)" via the Sheets API. Unstarring was refused (a user-level Drive setting).
- **"OROVA CRM" has no basic filter and no filter views.** That rules out hidden-by-filter rows as the cause of the "missing leads" report.
- **Research on the 14 core-ICP manual rows** (one of the 15 already matches a DB lead), from public web sources: CA SOS, CSLB/CCB aggregators, Houzz, BuildZoom, Levelset, Angi. Notes went into each row's "Research / source notes" column in the Sheet, marked research-only and Recovery Hold. Contact and status columns were not changed.
  - **Identity high (3)** (corrected 27 Nov from 4): includes the strongest ICP fit found so far, a Portland custom builder with an active Oregon CCB licence and a 2023 HBA Builder of the Year award. A fourth is medium-high.
  - **Medium (6, incl. the medium-high one)** · **low (4)**.
  - **Licence flag (1):** an expired CSLB licence.
  - Licence numbers came from aggregators, not the official CSLB/CCB/L&I lookups. Verify before any import or contact.
- **Next:** import the identity-high rows into the DB (now held by default) once their website or phone is confirmed on the official licence lookup.

## Backup fix deployed and licence checks (Mark: "go", 26 Nov)
- **PR #207 merged and deployed** (`715c4bcb01c8`, Operational, 10:05 UTC). It contains the `exec uvicorn` fix. **To prove it:** the *next* deploy or restart should leave a `nova_backup_*` file timestamped at shutdown. This deploy's shutdown was still handled by the old container.
- **Official licence verification is not automatable.** The CSLB and Oregon CCB lookups are both behind a reCAPTCHA (a human-only control), so I didn't automate past them. Their hosts were allowed briefly, then removed again. Licence facts in the Sheet remain aggregator-sourced. Mark can check the four identity-high prospects by hand in about 30 seconds each, before any import.
- **Import still pending:** it needs the rotated dashboard key, entered through the secure credential form (never in chat).

## Backup-fix result (26 Nov, after PR #208 deploy)
- PR #208 merged; live `f5c2bfe10df3` at 10:13 UTC, Operational.
- **No shutdown snapshot appeared** (newest is still 07:28 UTC), so the `exec uvicorn` fix was necessary but **not sufficient**. Remaining suspects: Render's free-tier stop grace is shorter than the 20s upload cap, or the Drive upload fails during shutdown. Next step: read the shutdown log line (`💾 Shutdown backup:` / `⚠️ Shutdown backup failed`) with the dashboard key (`python scripts/nova.py logs`).
- Exposure is smaller than first stated: `persist_leads_durably` already triggers a Drive backup after hunts and CSV imports, so leads are covered. What's exposed between the 3h backups is non-lead state: chat context, approvals, state_store.
- Mark chose to **keep the Render API key** for now (26 Nov). It remains in the chat transcript, so rotate it if that transcript is ever shared.

## Merging the backlog (Mark: "merge everything that needs to be merged", 26 Nov)
All four open PRs were brought into one branch and tested together against current `main`:
- **#204** (dnspython 2.6.1 → 2.9.2, a security fix): merged clean.
- **#199** (August: AI-call jurisdiction gate, Package 3 tier pricing, consent restored from Sheets on boot, server-side `brief --research`): merged clean. Two newer dialler tests needed the same `AI_CALL_ALLOWED_STATES` precondition #199 gives its own tests. That's #199's stricter gate working as designed: no cleared state means no AI call.
- **#200** (August: privacy rule 3 in `check_secrets.py`, redacted fixtures, Retell sync tool, spelled-number duration linter): merged, with conflicts resolved:
  - **Retell inbound script:** kept `main`'s September owner-approved version (consent-first, recording permission, labelled simulation). #200's August copy is superseded.
  - **Email-reply opt-out gate:** kept `main`'s fuller gate and dropped #200's weaker duplicate. #200's tests were adapted to `main`'s contract, and a mutation check showed they fail when the gate is disabled.
  - **`active-context.md`:** kept the 26 Nov rewrite.
- **Found by the merged checks and fixed:**
  - Two real prospect phone numbers in #199's tests, replaced with fiction-range numbers that keep the same area code.
  - Two outbound-script lines still promising a "ten minutes" call (canonical is 15).
- **Result:** 1,832 passed, 1 skipped; knowledge, secrets and security lint OK.
- **Still open from #200 (owner decision):** git *history* still contains a real prospect name and mobile (`cf7e7a1^`, and commit `04b2084`'s message). Remedies: GitHub Support purge, knowing acceptance, or contacting the person. A history rewrite alone doesn't clear merged PR diffs.

## Shutdown backup, second fix (27 Nov)
- **Reproduced locally (uvicorn 0.29.0, Nova's pinned version):** while any request is still open, uvicorn waits *without limit* before running the lifespan shutdown. A held connection left the shutdown hook unrun 8s after SIGTERM. With `--timeout-graceful-shutdown 3` it ran.
- **Likely cause on Render:** an in-flight request (e.g. a Telegram webhook awaiting an LLM reply) holds uvicorn past Render's ~30s grace window, so the backup in `app/main.py` never starts.
- **Fix:** Dockerfile CMD adds `--timeout-graceful-shutdown 5` (5s + the backup's 20s cap < 30s). `tests/test_dockerfile_signals.py` asserts the bound (fails before, passes after). Full suite 1,833 passed.
- **Proof still pending:** the deploy *after* this one should leave a `nova_backup_*` file timestamped at shutdown. If it doesn't, the next suspect is the Drive upload itself at shutdown, which needs the logs.

## Prospect briefs (27 Nov)
- A private Google Doc in Mark's Drive, "OROVA — Prospect briefs (DRAFT, DO NOT SEND) — 27 Nov 2026", holds briefs and one draft opening DM each for the top 4 (3 identity-high + 1 medium-high).
- The drafts follow the playbook: under 75 words, about their business, no past-client claims, no results, no offer or price, no demo number, one diagnostic question.
- Each brief carries a pre-contact checklist: verify the licence on the official site, check Instagram and website, confirm the offer, send manually one at a time.
- **Nothing sent; all stay on Recovery Hold.** The details live in Drive, not the public repo.
