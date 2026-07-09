---
name: owner-email-finder
description: built the free-tier owner-email finder + Verifalia verify layer
type: session
created: 2026-07-10
status: active
---

# Session: Owner-Email Finder Layer (2026-07-10)

Implements the #1 revenue feature from the 2026-07-10 handoff, following the
ranked pipeline in [[owner-contact-research]]. Branch: `feat/owner-email-finder`.

## What was built

- **`app/skills/email_finder.py`** (new): once [[owner-name-engine]]'s
  resolver has a name, this resolves the owner's direct email.
  - `find_owner_email(owner, domain)` — **Tomba** (25 finds/mo free) first,
    **Prospeo** (75/mo free) only when Tomba is unset/spent/missed; never
    both quotas on one lead. Both env-gated (`TOMBA_API_KEY`+`TOMBA_SECRET`,
    `PROSPEO_API_KEY`), rationed via `owner_finder`'s SQLite-backed counter.
  - `select_best_guess(guesses)` — **Verifalia** (25 verifies/day free)
    HTTP-checks the top 3 pattern guesses in ONE job: first Deliverable →
    `email_status="verified"`; all Undeliverable → email dropped entirely
    (bounce-poison guard); no creds / API down → prior "guessed" behavior
    (fail open).
- **`light_enrich.py`**: new Step 4.7 (finders, after DDG, before guessing)
  + Step 5 now routes guesses through `select_best_guess`.
- **`owner_finder._ration_check_and_increment`** gained an `amount` param
  (Verifalia charges per email in a job, not per call).
- **`.env.example`**: new keys documented; fixed the inaccurate
  "[FREE TIER]" labels on `APOLLO_API_KEY`/`HUNTER_API_KEY` (both need paid
  seats for API access — research follow-up item).
- **`tests/test_email_finder.py`**: 23 offline tests (gating, rationing,
  parsing, 202-poll, fail-open, select logic, light_enrich wiring). Full
  suite: 183 passing.

## Signup blocker + workaround (IMPORTANT)

Tomba **rejected Mark's free signup from Gmail** ("Free plan no longer
available for webmail addresses — register using a business email").
Workaround: register with Nova's **AgentMail inbox address** — it's a real
business inbox Mark controls and not a webmail domain, which is exactly what
Tomba asks for. Same advice for Prospeo + Verifalia signups. The layer ships
Tomba-optional, so Prospeo + Verifalia alone (or even neither) still work —
each provider activates the moment its env vars land on Render.

## Env vars to set on Render once keys exist

`TOMBA_API_KEY`, `TOMBA_SECRET`, `PROSPEO_API_KEY`, `VERIFALIA_USERNAME`,
`VERIFALIA_PASSWORD` — all optional, graceful skip when unset.
