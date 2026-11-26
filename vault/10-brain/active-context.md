---
name: active-context
description: What's true about OROVA right now, with verification dates. Read this first every session
type: brain
created: 2026-07-03
status: active
tags: [brain, active, session-start]
---

# 🧭 Active Context — rewritten 2026-11-26

**Mode: preparation only. Outreach is PAUSED by owner order.** Leads stay stored, researched and held. Nothing is sent, called, posted, deployed or spent without fresh owner approval. Budget is **$0** until the first paying client.

**Deployed and live-verified 26 Nov 2026 08:21 UTC:** PR #205 merged; `/health` reports Operational, build `abd922752dee`, db ok, memory ok. 384 leads survived the deploy, all Recovery Hold. The CSV-import hold fix is live.
**Everything else was last verified ~16–20 Oct 2026 and is stale.** Recheck before repeating any of the following as current:
- Leads **reconciled 26 Nov:** live DB 384, all Recovery Hold. The canonical Sheet is **"OROVA CRM" → `Leads` tab**: 446 rows, all held, **0 DB leads missing**, plus 62 manual-queue-only rows (mostly IG handles, many off-ICP). The "missing leads" came from the wrong sheet (the brief linked "OROVA IG Post Log"; the starred "OROVA Leads" is stale since May). See [[2026-11-26-lead-reconciliation]].
- Google OAuth/Drive backup repaired; Google app moved to Production with no new scopes.
- Telegram @orovaNOVA_bot: spam About/Description **replaced with neutral private-bot text on 26 Nov** (owner-reported via BotFather; name/botpic not yet checked). Token rotation still pending, and must be done together with updating Render's env.

**Next priority: production reliability.** Rotate the exposed dashboard key (Mark, in Render). The 62 Sheet-only rows (IG handles only; 15 core ICP) stay held; the 15 are the research queue.

Full operating rules: [[operating-brief]]. Owner judgement: [[hermesclaw-orova/playbook/README|playbook]]. History before this rewrite: [[active-context-history-2026-07-to-10]].

---

## Status board

| Area | State | Last verified |
|---|---|---|
| Render deploy | `abd922752dee` (PR #205) Operational; 384 leads intact | **26 Nov 2026** |
| Lead Sheet | "OROVA CRM"/Leads complete: 446 rows ⊇ all 384 DB leads | **26 Nov 2026** |
| Outreach | Paused — no sends, no calls, no AgentMail cold email | owner order |
| Nova Telegram | Truthfulness/`/status`/`/focus` fixes merged in #201/#202 | code only |
| Telegram bot identity | Bio spam replaced (owner-reported); name/botpic and token rotation pending | 26 Nov 2026 |
| Drive backup | Running every ~3h; 07:28 UTC snapshot integrity-checked, 384 leads | **26 Nov 2026** |
| Retell inbound demo | HOLD — unpublished, legacy Cal tools, unfunded | 30 Sep 2026 |
| Calendar `/away` | Code + tests exist; runtime credential proof pending | not live |
| Instagram | Draft-only; Sheets queue cutover; Make scenarios reported 9881852 / 9333477 | ~Oct 2026 |
| LLM routing | Groq `gpt-oss-120b` → Gemini → OpenRouter free; no paid fallback | 23 Sep 2026 |
| Apollo | Small manual research only (~175 credits when checked) | ~Oct 2026 |

## What changed in tooling (2026-11-26)

Work moved from Codex to **Claude Code**. `CLAUDE.md` is now the single agent entry point. `AGENTS.md` only points to it. Cloud Claude sessions **cannot see the OneDrive vault**, and by default they cannot reach Render, so they work on this repo vault. Pull the branch into the OneDrive checkout to sync. See [[2026-11-26-claude-code-migration-and-vault-cleanup]].

## Business, in one paragraph

OROVA sells Meta lead generation, plus consent-based AI lead qualification and booking, to service businesses. ICP: West Coast US custom home builders and high-end remodelers first, luxury real-estate top producers second. Med spas are excluded ([[0015-med-spas-are-not-and-never-were-the-icp]]). OROVA has no paying client, no case studies and no business-domain email. Never invent results, offers, prices, trials, urgency or consent. The unsupported "47 qualified calls in 21 days" claim stays retracted.

## Approved first-conversation path (when outreach is released)

Individual, researched DM on a public business channel → the prospect *chooses* to call the inbound demo number → disclosed simulation → Mark takes the meeting ([[0018-the-prospect-initiates-the-demo-call]]). The number stays out of all copy until the Retell gate passes and usage is funded. No automated cold calls, bulk DMs or cold email ([[0021-agentmail-is-inbound-reply-only]]).

## Open items, in priority order

1. **Lead cleanup:** done 26 Nov ([[2026-11-26-lead-reconciliation]]). Mark is still to archive the stale "OROVA Leads" sheet.
2. **Live re-verification:** Render `/health` build, Drive backup, Telegram webhook/identity, Make/Meta status.
3. **Nova quality:** no regression to repetitive or fabricated reports ([[0022-learning-observations-and-no-age-only-pruning]]).
4. **Calendar proof:** service account, target calendar ID, free/busy only, idempotent test.
5. **Instagram:** audit queue and publisher; Reel drafts with voiceover; nothing published unverified.
6. **Prospect research briefs** for held leads (Apollo/public sources, no sending).
7. **Retell inbound demo:** only when funded, verified and approved.

## Standing constraints — don't "fix" these

- `ZERO_BUDGET_MODE=1` and `CALLS_AUTOPILOT=0` stay on.
- `httpx==0.27.2` stays pinned.
- Sheets is a projection and a partial recovery tier, not a full DB backup.
- Never start the app locally with production `.env`: it re-registers the Telegram webhook and starts jobs.
- Mark merges and approves deploys.
