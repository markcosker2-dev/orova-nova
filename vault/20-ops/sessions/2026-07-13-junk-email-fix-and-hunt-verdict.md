---
name: session-2026-07-13-junk-email-fix-and-hunt-verdict
description: Claude Code session — ICP decision (stay mixed), live hunt verdict, junk-email subdomain fix
type: session
created: 2026-07-13
status: done
---

# Session: Junk-email fix & hunt verdict (2026-07-13)

## What changed

- **Owner decision recorded: the ICP stays MIXED** (automotive + custom home
  builders + luxury RE + high-ticket services). The handoff's "automotive-only"
  narrowing is **rejected** — `business_context.json` and the 15-niche
  `DEFAULT_HUNT_NICHES` rotation stay as they are.
- **Live hunt re-run (prod, 09:57):** engine ran end-to-end and saved 5 leads —
  all generic auto shops ("California Auto Store/Works/Center", "Auto House of
  Clovis") with `support@`/`info@` emails. Confirms `TARGET_NICHE` on Render
  still holds a stale generic value that **overrides** the curated rotation.
  Owner action: delete `TARGET_NICHE` on Render (or set it deliberately).
- **Bug found & fixed — noise-domain filter bypassed by subdomains:** lead #6
  saved `605a…@sentry-next.wixpress.com` (Wix telemetry) as its contact email.
  `lead_gen_v3.py` used exact-match domain blocklists at 3 scrape sites, so any
  subdomain of a blocklisted domain passed, and `_prioritize_email` then ranked
  the random-hex localpart as "personal" (best). Fix: single `_is_noise_email()`
  suffix-matching helper used at all 3 sites + the AI-extraction fallback.
  3 regression tests added (suite 271 → 274).
- Also observed in prod logs: **Gemini 429 (free-tier quota exhausted)** — Groq
  carried the load; fallback behaved as designed.

## Why

The path to client #1 is Mark emailing real, on-ICP leads. Today's hunt proved
the remaining lead-quality gap is (a) the stale Render `TARGET_NICHE` (owner's
lever) and (b) junk platform emails leaking through — (b) is now fixed.

## Follow-ups

- [ ] Owner: delete (or deliberately set) `TARGET_NICHE` on Render, then re-run
      the hunt and pick the best 10 leads to email from Gmail.
- [ ] Owner: rotate the leaked `TELEGRAM_BOT_TOKEN` (still open from 07-12).
- [ ] After the next deploy: check `/api/logs` for the Drive restore line.
