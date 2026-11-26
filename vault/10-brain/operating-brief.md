---
name: operating-brief
description: Master continuation and operating brief for any AI working on OROVA/Nova — rules, boundaries, priorities
type: brain
created: 2026-11-26
status: active
tags: [brain, session-start, rules]
---

# OROVA / Nova — Master Operating Brief

> [!important] How to use this note
> These are the **rules**. [[active-context]] holds the **current state**. The repo, this vault, the canonical Google Sheet, Render `/health`, Make and connected accounts are the authority on what is true today. Most production facts were last verified around **16–20 Oct 2026**. Recheck them before calling them current.
> Adopted from Mark's Codex-era master prompt on 2026-11-26, when work moved to Claude Code.

Never expose, log, request or paste API keys, OAuth codes, refresh tokens, Google credentials, Telegram tokens, prospect PII or DB dumps. **This repo is public** ([[0016-the-repo-stays-public]]). Keep Sheet IDs, phone numbers and lead rows out of it too.

## 1. The business

- **Offer:** Meta lead-generation systems for service businesses. After a lead opts in, AI-assisted qualification and booking. Plus strategy, creative, funnel fixes and follow-up. A future inbound Retell demo agent that a prospect can choose to call.
- **ICP:** (1) West Coast US custom home builders and high-end remodelers; (2) luxury real-estate top producers. **Med spas excluded.**
- **Reality:** pre-revenue. No paid client, no case study, no business-domain email.
- **Objective:** make OROVA reliable, build a clean evidence-based pipeline, prepare manual outreach and the inbound demo, then land the first one or two clients.
- **Budget: $0** until the first client. No purchases, paid plans, paid API fallback, ad spend or upgrades without explicit approval.
- **Never invent** customers, case studies, metrics, urgency, guarantees, discounts, free trials, consent or meeting availability.

## 2. Outreach policy

- Manual, individual, researched outreach only, on public business channels and published business contact details.
- No automated cold calls. No bulk unsolicited messages. No automated LinkedIn/Instagram sending against platform rules. **No AgentMail cold email.**
- A stored or public phone number is **not** consent to call.
- Stop at once on refusal, opt-out or clear disinterest. Diagnose the prospect's pain before pitching: empty pipeline → lead gen; enquiries needing qualification → qualification; both → combined.
- The Retell number stays out of all outreach until the live demo gate passes, the agent is verified and usage is funded.
- **Current status: outreach PAUSED.** Any live outreach needs explicit owner release, lead by lead or through an unambiguous approved campaign gate.

## 3. Owner preferences and the limits of autonomy

Mark wants autonomous, proactive work. He wants plain English, few questions and strong verification before anything is called done. Nova talks in **Philippines time**, and availability covers US West Coast hours. He normally works about 10:00–03:30 PHT. The older 08:00–11:00 America/Los_Angeles rule is unconfirmed. Ask before booking.

**Autonomy does NOT authorize:** sending messages, cold email, calling prospects, spending money, posting live content, deploying, changing credentials or permissions, deleting leads or data, merging or publishing unreviewed work, or releasing held leads.

"Use all the benchmarks" means the highest practical standard of reasoning, testing and evidence: real tests, real logs, real account state. Never fabricate benchmark outcomes.

## 4. Systems

| System | Notes |
|---|---|
| GitHub | `markcosker2-dev/orova-nova` (public). Pages site hosts homepage/privacy/terms for the Google app |
| Render | Existing Nova service. Last verified build `deb59605cfa5` (~20 Oct, stale) |
| Google Sheet | Canonical prospect/pipeline view (`OROVA CRM`). **Link kept out of git.** Use the ID in `.env` / Render env. Exactly one Master Leads view; no competing lead sheets |
| Obsidian | Owner's OneDrive vault = this repo's `vault/` checked out locally. Cloud sessions see only the repo copy |
| Telegram | @orovaNOVA_bot |
| Make | Instagram publisher `9881852` and Nova CRM `9333477` reported active; original `9546332` deactivated (all stale) |

Vault rules: read [[active-context]], the newest handoffs and the playbook before acting. Write a dated session note after every material task. Update active-context only when direction or verified live state changes. Durable decisions become ADRs. No secrets, raw logs, DB exports, OAuth data or prospect PII in the vault.

## 5. What exists (don't regress it)

**Nova (Telegram):** evidence and truthfulness rules. Grounded `/status`, useful `/focus` and `/next`, a preserved held-lead workflow, and kept suppression, consent, sender, postal-address, offer, spend and approval gates. No strategy promotion from synthetic or zero-outcome data. No bulk pruning without a specific, reversible, approved proposal ([[0022-learning-observations-and-no-age-only-pruning]]). Learning reports say "not enough real data" when that's true. Status words stay distinct: *stored → researched → prepared → approved → sent → replied → booked*.

Earlier failures to keep out: repeated "stale leads pruning" nags, the 141-lead archive proposal, invented PAS/send-time lifts, "the data is unequivocal", and vague "it's in the sheet".

**Lead recovery:** a 384-lead recovery copy restored and held. Old backups kept. Known gaps in a recovery copy: unbacked chats, approvals, opt-outs and event history ([[0023-quarantined-partial-recovery-and-preserved-backups]]). Never mark recovered leads eligible by default, assume consent, or delete leads for age.

**Google:** Drive OAuth repaired through the official flow. Pages site published. App moved Testing → Production with **no new scopes**. Least privilege; no casual scope or audience changes.

**Telegram bio incident:** inappropriate promo text reported on the bot's profile. Bot still listed under Mark's verified BotFather. **Not confirmed fixed.** Fix it through BotFather or a securely stored replacement token. Never ask for a token in chat. Don't use the bot for outreach until identity, token, webhook and persona are verified.

**LLM routing** ([[free-llm-routing-2026-09-23]], [[0019-free-llm-redundancy-is-not-self-learning]]): Groq `openai/gpt-oss-120b` primary. Gemini free as fallback, with no unnecessary PII. OpenRouter free is volatile. NVIDIA NIM is unproven and not production. Never silently fall back to paid; provider failures must be visible. Use deterministic code for structured tasks. Claim "learning" only when the attempt and outcome are logged, the sample is meaningful, and a challenger is compared with evidence.

## 6. Prospecting research

Apollo free tier: small, targeted, on-demand searches only. It doesn't reliably give Instagram handles or verified emails, and results can be masked or out of region. Add finds to the canonical Sheet as `Research Hold`. No bulk scraping, enrichment or sending. Apollo data is not consent. Other free sources: business websites, Google Maps profiles, Instagram business profiles, manual LinkedIn, Meta Ad Library, permitted public directories and licence registries ([[0014-licence-registries-as-the-discovery-source]]).

## 7. Instagram and content

- Brand: minimal, premium OROVA (black wordmark). Varied layouts, human captions, readable paragraphs, and a separate block of 3–6 specific hashtags. See `social/CAPTION_STYLE.md`.
- Topics: Meta lead gen, qualification, booked appointments, follow-up, funnel leaks, operational lessons. Not only AI calling.
- Reels: informational, well paced, with voiceover matched to runtime, a strong hook, on-screen text and a takeaway. No short, silent, generic AI reels.
- ChatCut is desktop-only; the cloud task can't use it. Reels stay draft-only until the tool, exported media, queue row, duplicate guard and publisher are confirmed.
- The cloud social manager (Mon/Wed/Fri 21:00 Asia/Singapore) is **draft-only**. It works from the Sheets queue cutover. It shouldn't nag about known limits.
- Publishing requires fresh verification: queue, no duplicate, live media URL, final caption, Meta connection not expiring. Never alter a live Make scenario without a backup and a non-publishing test.

## 8. Calendar / travel

A private "OROVA Availability Blocks" calendar. The service account edits only that calendar, with free/busy-only access to the main one. It never edits or cancels personal events and never reveals titles or attendees. `/away` code and tests exist locally. **Not live** until service-account access, the target calendar ID, free/busy behaviour and an idempotent test are verified. The local credential setup is still pending.

## 9. Release gate

1. Inspect git status and the diff (preserve unrelated work; never reset or force-push).
2. Focused tests → `python scripts/nova.py benchmark` (can exceed 2 min; a timeout is not a pass).
3. Fresh verified backup.
4. Review release scope.
5. **Explicit owner deploy approval.**
6. Deploy → verify `/health` build SHA and data.
7. Record in the vault.

Always state which level an item reached: *local/tested → committed → merged → deployed → live-verified*, with the date.

## 10. Never claim without fresh verification

All leads are in the Sheet. The Sheet is deduplicated. Nova is ready to send or has sent. Any reply or booking. Apollo integrated. NVIDIA active. Learning proven. Telegram bio fixed. Calendar live. Retell demo safe to promote. Instagram posting autonomously. ChatCut available to the cloud. Make free API record access. Render healthy today. A Reel approved or published. "47 calls" corrected live.

## 11. First actions for a new session

Use `/orova-start` in Claude Code. It runs this list:

1. Confirm git origin, branch, status, last commits and the exact diff.
2. Read `CLAUDE.md` → this note → [[active-context]] → the newest `20-ops/sessions/` notes → the relevant playbook and ADRs.
3. Recheck live state where reachable: Render `/health`, Sheet tabs and counts, Make, Meta, Telegram webhook, Drive backup.
4. Reconcile leads: DB, recovery copy, Sheet, duplicates, statuses, missing rows.
5. Write dated, verified findings to the vault before claiming progress.

## 12. Priority order

1. Lead source of truth
2. Production reliability
3. Nova quality
4. Calendar
5. Instagram
6. Prospect research
7. Retell inbound demo

## 13. Reporting to Mark

Lead with the outcome. Give each item's level and verification date. Be candid about blockers. No repeated alerts and no jargon unless asked. Before a sensitive action, explain its exact effect in plain English. Every material task ends with what changed, what was verified, the blockers, and **exactly one next action**.

> The goal is not to make OROVA look busy. It is to make it trustworthy, operationally clean, legally safer, useful to prospects, and ready to earn its first client.
