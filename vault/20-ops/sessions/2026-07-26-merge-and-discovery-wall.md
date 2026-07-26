---
name: session-2026-07-26-merge-and-discovery-wall
description: Claude Code session — shipped the ad-signal detector, state persistence, discovery pagination and the WA L&I owner source; hit the SerpAPI wall
type: session
created: 2026-07-26
status: done
---

# Session: merge day + the discovery wall (2026-07-26)

Six PRs merged and deployed. Production verified at `build 8e4e78e34c04`,
`db: ok`, `memory: ok`, **533 tests passing**.

Then the first real hunt returned **0 leads** and revealed the actual blocker
has nothing to do with code. See [[0014-licence-registries-as-the-discovery-source]].

## What changed

**Shipped to production** (#109, #110, #112, #113, #111, #114):

| Change | Effect |
|---|---|
| Ad-signal detector (`detect_ad_signals`) | Meta Pixel + lead-marketplace badges read from homepage HTML already fetched during enrichment — zero extra requests. Substitutes for the Ad Library. |
| `ad_tier` on `/api/leads` | Computed view: hot / warm / cold / null. Not stored (store facts, compute views). |
| `lead.state` persisted | The registry router finally receives a state; without it every lead fell to the dead OpenCorporates branch. |
| SerpAPI pagination + fallback demotion | Stops discarding results already paid for; URL-only DDG leads can no longer dilute a good run. |
| WA L&I owner source (`wa_lni`) | Replaced the anti-bot-gated WA SoS endpoint. 100% owner-name + phone fill, free, no key. |
| Retell script + voicemail + inbound agent | Live in Retell; repo is now the matching source of truth. |

**Live-validated, not just unit-tested.** The detector was run against 9 real
California remodeler homepages, which exposed a bug no fixture would have
caught: `houzz` fired on **8 of 9**, inflating "paying_for_leads" to 8/9 and
making the ADR-0012 qualifier fire on nearly every prospect. A qualifier that
qualifies everyone selects nobody. Split into `paying_for_leads` (pay-per-lead)
vs `directories` (free profiles); the same 9 sites then ranked **2 hot / 2 warm
/ 5 cold**. `marketing_mature` fired 9/9 — kept, but documented as
non-qualifying since its presence carries no information.

## Why

The session's premise was "make it work". Three of the four things blocking
that turned out to be dead ends that had to be *proven* dead rather than
argued about — Meta's API, Apollo's free tier, Composio's Facebook scope. Each
was tested live and each is now recorded so it is never re-litigated.

The one that mattered most was the least expected: SerpAPI is at **250/250,
0 searches left**. Discovery was never limited by the fallback sources being
bad; it was limited by the only good source being rationed, and by that source
throttling itself (it sliced `[:count]` *before* filtering for websites, so
every hunt binned ~5 businesses already paid for).

## Things that went wrong

- **Two PRs merged into the wrong branch.** #110 and #112 were stacked; GitHub
  only auto-retargets a stacked PR when its base branch is *deleted* on merge,
  and they were merged with `--delete-branch=false`. Both landed on their
  intermediate branches, so `main` had `ad_signals` but **no `state` column and
  no pagination**. Caught only by grepping the merged code rather than trusting
  five `MERGED` statuses; recovered via #114. Had it gone unnoticed, #113's
  `wa_lni` source would have been live but **inert**, since it needs `state`.
- **Deep research and the four-agent audit both produced nothing** — session
  rate limits, 21 of 26 agents and then 4 of 4 erroring. The audit is still
  worth running, now against a current `main`.

## The 47 junk leads

Production holds 47 leads, all `ready: False` with genuine blockers — the gate
works. But the rows themselves are noise, and worse than "legacy junk"
suggests:

- `museo@adolfoalsina.gov.ar` — an Argentine government museum
- `lvellequette@crain.com` — a **named automotive journalist** at Crain's
- `jakesautomotivemt@gmail.com` — a Montana auto shop
- owner names `"Says Carmaker"`, `"Content Topics OEMs"` — scraped fragments

Note the trap: `quarantine_invalid_leads` runs at **boot** (`app/main.py:229`)
and sets `status='Invalid'` rather than deleting — so it has already run and
deliberately *kept* these. They pass the current rules. Clearing them is a
hygiene-rules change (off-ICP geography, press/government domains,
fragment-shaped owner names), not a sweep re-run, and it touches the
revenue-pipeline core.

## Follow-ups

- [ ] **WA L&I as a discovery source** — the unblock while SerpAPI is dry.
      Seam 1 of [[0014-licence-registries-as-the-discovery-source]].
- [ ] Website resolution for licence-sourced leads (they carry no domain) —
      this becomes the only rationed call in the chain.
- [ ] Extend hygiene rules to quarantine the 47 off-ICP rows. Reversible
      (`status='Invalid'`), own PR, with tests.
- [ ] Re-run the 4-way audit against current `main` once limits reset.
- [ ] Watch `/api/logs` for `wa_lni` hits on the first successful hunt —
      `WA_LNI_ENABLED` defaults ON, so it is live but has never fired against a
      real scraped business name.
- [ ] **OROVA Agency Facebook page has 2 followers**, no website field, not
      verified. Prospects will look it up mid-call. Owner action.
- [ ] `CAL_COM_EVENT_SLUG` still unset — Retell's built-in Cal.com covers phone
      bookings, but neither agent has a booking tool, so a "yes" is captured as
      email + two preferred times and flagged, never booked.

## Still true

**Zero prospect conversations have ever happened.** Every strategic artifact
remains inference. The pipeline can now, in principle, produce a callable lead;
it has not yet produced one. The next artifact that should exist here is a
transcript.

## Linked

- [[0014-licence-registries-as-the-discovery-source]] · [[session-2026-07-24-handoff]]
- [[0012-icp-rerank-and-pilot-pricing]] · [[0013-painkiller-positioning-and-real-competition]]
- [[traction-playbook]] · [[active-context]]
