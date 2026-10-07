---
name: 0021-agentmail-is-inbound-reply-only
description: AgentMail cannot initiate OROVA prospect outreach; Nova may prepare contact briefs and handle verified inbound replies.
type: decision
created: 2026-09-23
status: active
tags: [decision, outreach, email, agentmail, provider-policy]
---

# ADR-0021 — AgentMail is inbound-reply only

## Status

Accepted by Mark's 2026-09-23 instruction to stop Nova emailing found leads.
Implementation is local until separately merged and deployed.

## Context

The prior `send_outreach` stop depended on `ZERO_BUDGET_MODE=1`. Turning that
setting off, setting a postal address or consuming an old approval could reopen
AgentMail sends from hunt, drip, escalation, orchestrator or planner paths.
AgentMail's [Terms §10](https://www.agentmail.to/legal/terms) prohibit spam and
unsolicited messaging. An otherwise lawful B2B email or an approval is not
provider permission. The current first-contact path is an individual,
researched message through a permitted channel, not a cold-email campaign.

## Decision

- AgentMail prospect outreach fails closed at `send_outreach`, regardless of
  budget mode, sender configuration or approval. No send or approval request
  occurs for that path.
- Nova's planner no longer offers AgentMail or generic Gmail send actions, nor
  new cold-drip enrolment. It may research, draft, and handle verified inbound
  AgentMail replies under recipient, suppression and approval checks.
- The lead hunt stores and syncs discovered prospects only. It neither composes
  a cold email nor requests approval or enrolls an automated email sequence,
  even when `$0` mode is later changed.
- A blocked send must never be counted as a successful touch or advance a
  campaign. The CRM may retain a published business email as contact data;
  possession of that address is not permission to send.
- Reopening a prospect-email channel requires a separate provider-policy and
  compliance review, explicit owner decision, sink-level safeguards and tests.
  It must not be a single environment flag.

## Consequences

Found leads remain research inventory in the production database and
canonical Google Sheet, not an email campaign. This ADR changes no live
behavior until a backup-gated deployment. Verified inbound replies remain
available.

Linked: [[zero-budget-operations-2026-09-21]] · [[active-context]]
