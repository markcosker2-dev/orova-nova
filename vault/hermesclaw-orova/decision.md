---
name: hermesclaw-orova-decision
description: Decisions already made — what, why, and when to revisit
type: doc
created: 2026-07-11
status: active
---

# Decisions

> What we decided, why, and the trigger for revisiting. Deep rationale lives
> in `40-decisions/` (ADRs) and [[profitability-plan]]; this is the index.

| # | Decision | Why | Revisit when |
|---|---|---|---|
| 1 | **Obsidian vault = the shared brain**; git is truth, production knowledge flows in via `vault_pull.py`, never git-pushes from Render (ADR-0001) | One curated place both Mark and AI read; Render disk is ephemeral | A second local process needs concurrent vault access (→ MCP server per ADR-0004) |
| 2 | **$0 / free-tier-first until revenue** | No income yet; forces lean architecture | First client signed → SerpAPI $25/mo first, then paid LLM/Render |
| 3 | **SerpAPI is the lead-discovery + owner-name source**; free registries abandoned (WA anti-bot, OpenCorporates non-commercial, CA paid) (ADR-0003, live-verified) | Only source that actually worked server-side; ~100% phone+website yield | Quota pain → paid tier; or a browser-capable worker appears |
| 4 | **ICP narrowed to 3 verticals** — exotic/luxury auto, custom home builders/remodeling, luxury RE agents; **aviation/yacht → opportunistic-only** (owner-approved 2026-07-10) | Cold-email-to-owner motion requires an owner who reads their own inbox; aviation/yacht decision-makers are family offices/brokerages | After client #1, or if a referral network into aviation/yacht opens |
| 5 | **Lead with Package 1** ($4K) in first-touch outreach; P2 is the second conversation | Lower-friction yes for a stranger with zero case studies | First case study exists |
| 6 | **Margin target 90%+** (75–80% kept as external worst-case floor) | Bottom-up 2026 vendor pricing shows ~97% realistic ([[profitability-plan]] §3) | Any vendor pricing shock |
| 7 | **Call published business lines ONLY — never personal cells** (codified in `business_context.json` compliance.calling_policy) | TCPA B2B exemption tracks the *number*, not the topic; personal cells = per-call statutory liability | Never, without legal counsel. DNC registry scrub is a pre-scale follow-up |
| 8 | **Cold email/calls/replies approval-gated** until proven; ads/spend/client-signing ALWAYS human | Wrong outreach is the existential risk pre-reputation | Flip `OUTREACH_AUTOPILOT` etc. after ~20–30 clean sends and real win-rate separation |
| 9 | **Prospeo alone for owner-email finding**; Tomba + Verifalia skipped (signups blocked for webmail/disposable emails) | Prospeo free tier (100/mo, live-verified) covers the need; guessed emails safely stay flagged `guessed` without Verifalia | A real sending domain exists (its mailbox clears those signups) |
| 10 | **Learning = Wilson-bound champion/challenger everywhere** — strategies AND skill versions (ADR-0004, Phases 1+2 shipped); retire/promote rationales are deterministic sentences, not LLM calls | Small-sample-safe; works LLM-dead; zero marginal cost | If rationale quality matters more once volume is high |
| 11 | **Drive backup must authenticate as a real user (OAuth refresh token)** — service accounts cannot upload (Google 403, live-verified 2026-07-11); `GOOGLE_CREDENTIALS_JSON` stays for Sheets + Drive reads | Google platform rule, not a code choice | Google changes SA storage policy (unlikely) or move to a Shared Drive (needs Workspace) |
| 12 | **Batch merges to main** until the backup/restore cycle is verified | Every deploy wipes learning data; leads survive via Sheets | Refresh token live + first restore verified → merge freely |
| 13 | **HermesClaw GUI is not the revenue path** — canonical GUI in `electron/`, `HermesClaw/` = mirrors; effort goes to Nova first | The FastAPI agent is where all live value is | First client retained and paying |
| 14 | **Don't rebuild working software pre-revenue** (e.g. dashboard got a surgical overflow fix, not a redesign) | Speed to client #1 beats polish | Post-revenue |
| 15 | **httpx pinned 0.27.2**; starlette/fastapi frozen with it | TestClient vs mcp/ollama constraints; 4 benign warnings documented | Coordinated fastapi/starlette/httpx upgrade, post-revenue |
