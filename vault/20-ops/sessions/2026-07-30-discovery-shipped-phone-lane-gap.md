---
name: session-2026-07-30-discovery-shipped-phone-lane-gap
description: Three PRs shipped (ICP gate fix, WA L&I discovery, docs corrections), cold email settled as contractually dead, and the phone lane found to be architecturally downstream of email
type: session
created: 2026-07-30
status: active
---

# Session 2026-07-30 — discovery shipped, phone lane is the new blocker

## What shipped

| PR | What | Verified |
|---|---|---|
| #118 | Outreach safety gates, Phase 2/3 fixes, config contract | deployed `359d8fbac904` |
| #119 | ICP gate reads business NAME, not just vertical | on main `14c54a8` |
| #120 | WA L&I licence registry as a discovery source (ADR-0014 seam 1) | deployed `612b8245e53a` |

**718 tests passing** (628 baseline + 46 + 44).

## 🔴 The finding that matters: nothing will dial the new leads

Discovery is fixed. The blocker moved, and it is an **architecture** problem.

Lane 4 (`escalate_cold_leads` in `app/worker.py`) is the only *scheduled*
dialler. It selects leads via `_lead_repo.get_cold_leads`, which requires:

```sql
WHERE status IN ('Email Sent','Contacted')
  AND datetime(updated_at) < datetime('now','-5 days')
```

Licence-sourced leads are stored `status='New'`, so **they can never be
selected**. Lane 4 is an *escalation* lane — built for "we emailed, no reply in
5 days, now phone them" — which makes it structurally DOWNSTREAM of email. With
cold email deliberately deferred and fail-closed, Lane 4's input set is
permanently empty.

Net effect: seam 1 can discover ~4,280 on-ICP, phone-verified, callable WA
remodelers and **not one of them will be dialled** by any scheduled lane.

**Paths that CAN dial without a prior email (all already built):**
- `outreach_orchestrator.make_call(phone, context)` — the right primitive:
  daily cap, business-hours gate, rate limiting already inside.
- `worker._execute_approved_call` — Google Sheet row set to "Approved" (manual).
- The planner's `trigger_retell_call` tool via `POST /api/agents/run`.

**Next code task — a phone-first lane:** select
`status='New' AND phone != '' AND outreach_ready.callable`, call `make_call`.
Reuses the existing primitive and caps, so it extends rather than adds an
abstraction. This is the last thing between the repo and its first transcript.

## Corrections made this session (all by querying, not reading)

1. **ADR-0014's "6,249 on-ICP rows" overcounts.** Specialty `GENERAL` does not
   mean "general contractor" — the bucket is full of landscapers, window
   cleaners, drywall, tile and one-person handymen. With licence *type* and a
   business-name filter: **~4,280** (28.4% of 15,069). 100% fill on
   name/owner/phone/address confirmed.
2. **#118's ICP gate had a live bypass.** Production held exactly one lead,
   "Keith's Auto Repair", vertical EMPTY, status `Contacted`. The boot sweep ran
   the new gate over it and logged `[HYGIENE] sweep clean: 1 leads OK` — a
   general auto repair shop passed because every leg keyed on `vertical` and
   nothing read the name. Fixed in #119. The licence registries carry no
   vertical at all, so this was about to become the common case.
3. **Drive backups are dead again** — `invalid_grant: Token has been expired or
   revoked`. Sheets fallback restored **1 of 4 leads**, which is why production
   went ~51 rows → 1. Broke exactly 7 days after the last fix, which is how long
   Google expires refresh tokens for an OAuth app still in *Testing* status.
   **Owner action: re-auth + publish the consent screen**, or it dies weekly.
4. **`emails_sent` is not a send counter.** It is
   `COUNT(*) FROM leads WHERE status IN ('Contacted','Email Sent')` — a
   projection of current rows. "48 emails sent" was 48 rows in Contacted, not an
   audited send log. When the rows vanished the number became 1.

## Cold email: settled, and for a different reason than assumed

Researched against vendor ToS/AUP pages plus live DNS. Two prior beliefs were
wrong:

- **A shared sending domain CAN pass SPF/DKIM/DMARC.** Verified by DNS:
  `_dmarc.agentmail.to` = `v=DMARC1; p=reject`, `mail.agentmail.to` =
  `v=spf1 include:amazonses.com -all` (SES Custom MAIL FROM). Authentication
  already passes. "No domain means no auth" is false.
- **The `550 5.4.1 Access denied` bounces were invalid-recipient rejections**
  (Microsoft Directory-Based Edge Blocking), NOT reputation or auth. The guessed
  addresses simply did not exist. That makes the 48-send incident a
  **data-quality** failure, and means `_guess_email`'s output is unreliable.
  The auth-rejection code would have been `550 5.7.515`, never seen.

**The real blocker is contractual: 0 of 8 providers permit cold outreach.**
AgentMail's own ToS §10 bans "unsolicited messaging" (§21 allows immediate
termination) — so Nova was in breach, and losing that inbox would also kill the
reply-handling the phone channel needs. MailerSend explicitly bans web-scraped
addresses, which kills the licence-board→email path by name. Amazon SES is no
longer perpetually free. Realistic floor for compliant cold email is
**~$40–80/month**, not $12/yr; buying a domain does not fix the AUP or warmup
problems.

**Keep: post-call follow-up email is NOT cold email.** After a phone
conversation it is solicited and transactional — ToS-clean essentially
everywhere and trivially inside free tiers. **Phone manufactures the consent
that makes email legitimate.** Sequence the channels; don't choose.

## Pricing guidance given (owner asked)

Recommended **against** lowering the list price to widen the ICP. ADR-0012's ICP
filter is a deal-size ratio, not affordability, so cutting price widens
*downward* into worse ad economics; and cheap testimonials buy cheap clients
(proof is segment-specific, anchoring is real, referrals form inside the segment
sold to). Also flagged that "$4–5K" had drifted into the conversation as the
baseline when ADR-0012 says **all-in $6.5–7.5K**.

Recommended: list stays **$6,500**; pilot **$2,000/mo for 60 days**, capped at 3
clients, with the step to **$4,500** written into the agreement *at signature*;
floor $2,000, never discount to close (shorten the term instead). If a cheaper
tier is wanted, tier by **segment** (med spas at $3–4K, where 1–2 patients/mo
covers it), not by discount. And put the price question into the 20 discovery
calls rather than deciding it from inference.

## Housekeeping

Ran `/doctor`. Disabled 16 unused plugins (none used in a 9-day, 41-session
window; 12 never used), which cut the skill listing from ~180 entries to ~31 —
it had been ~4× over its context budget and was visibly truncating skill
descriptions, degrading routing. Enabled auto mode as the default permission
mode. Kept `sales` (call prep — directly relevant to the 20 calls),
`anthropic-skills`, `claude-council`.

Also noted: **`claude-council` is not actually loading** — 56 lifetime uses but
`/claude-council:ask` is absent from the skills list, so CLAUDE.md's council
protocol has been silently inert. The guard clause meant nothing broke.

## The number that matters

**0 calls made. 0 meetings booked. 0 prospect conversations, ever.**

Discovery is no longer the constraint — ~4,280 callable on-ICP leads are
reachable for free. The constraint is now a single missing lane. The next
artifact this repo needs is still **a transcript**.

## Linked
- [[0014-licence-registries-as-the-discovery-source]] · [[0012-icp-rerank-and-pilot-pricing]]
- [[0013-painkiller-positioning-and-real-competition]] · [[session-2026-07-29-handoff]]
- [[active-context]]
