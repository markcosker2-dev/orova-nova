---
name: adr-lead-engine-and-subagents
description: "ADR: lead-engine enrichment rework + lightweight real sub-agents"
type: decision
created: 2026-07-04
status: active
---

# ADR-0002: Lead-engine enrichment rework + lightweight sub-agents

## Context

Two problems blocked Nova from running OROVA autonomously:

1. **Lead scraping returned empty owner/email/phone.** Root causes (see the
   code map in the buildout plan): the AI extraction step silently died on dead
   LLM keys; the website scraper's page cap cut off the `/about` & `/team` pages
   where owners actually appear; `_prioritize_email` preferred `info@` over
   personal addresses; and DuckDuckGo is rate-limited in production.
2. **Nova's "9 sub-agents" were not real code** — persona `.md` files plus a
   roster string. `dispatch_task` was a stub returning a hardcoded string, and
   the CEO brain's auto-hunt called a non-existent `run_planner`.

Constraint: Render free tier (512 MB, no browser, SMTP ports blocked).

## Decision

- **Lead engine:** keep the free multi-source pipeline (Google Maps + web scrape
  + WHOIS + registry + BBB) but (a) scan owner-bearing pages first, (b) add a
  Render-safe `UnifiedAIClient` extraction pass (no browser, falls Groq → Gemini
  → OpenRouter free), (c) fix email prioritisation to prefer the owner's personal
  address. No paid data, no browser scraper (Apollo stays optional/local).
- **Sub-agents:** do NOT build a multi-process framework. Each sub-agent is a
  *scoped run of the existing planner* — its persona injected, its toolset
  restricted to its role (Hawk hunts, Quill/Closer do outreach, Atlas builds).
  `dispatch_task` runs that; sub-agent scopes exclude `dispatch_task` so
  delegations can't recurse. Single-process, fits free tier.

## Consequences

- Owner/email/phone capture improves as soon as one LLM key is live; the code
  degrades gracefully to regex when no provider answers.
- Nova can genuinely delegate, but Unified Mode stays the default (delegation is
  opt-in), so token/cost stays controlled on free tier.
- Email verification confidence is capped: Render blocks SMTP, so we verify the
  domain (MX) only, never the exact address — guessed emails are flagged.
- Still pending (WP4): enforcing the approval gates in code and the
  reply → qualify → booking middle-mile. See [[orova-playbook]] §5.
