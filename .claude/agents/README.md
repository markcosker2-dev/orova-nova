# Dev-time agents

Claude Code subagents available to any session working on this repo. These are
**development** agents — they do not ship to Render and Nova's runtime never
loads them. Nova's own personas live in `app/personas/` and are dispatched by
`app/core/agent_router.py`.

## Provenance

Four agents here are adapted from
[msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents)
(MIT licensed, ~330 agents across 17 divisions). Copyright belongs to the
upstream authors; the MIT licence text is reproduced in `LICENSE-agency-agents`.

They are **adapted, not mirrored.** Every one was read in full and edited to
respect OROVA's hard constraints before landing here:

| Agent | Upstream | What changed |
|---|---|---|
| `discovery-coach` | `sales/sales-discovery-coach.md` | Retargeted to Nova's outbound cold call; price/budget-negotiation guidance removed (`commercial_terms` UNRESOLVED). **Question content deliberately not copied** — `business_context.json > discovery_questions` is the canonical owner, and this file points at it rather than duplicating it |
| `meta-paid-social-strategist` | `paid-media/paid-media-paid-social-strategist.md` | LinkedIn/TikTok/Pinterest/Snapchat sections dropped — OROVA sells Meta only; Google Ads MCP tooling section dropped |
| `ad-creative-strategist` | `paid-media/paid-media-creative-strategist.md` | Google RSA / PMax / Shopping sections dropped; kept the Meta creative and testing craft |
| `minimal-change-engineer` | `engineering/engineering-minimal-change-engineer.md` | Unchanged in substance — it already states the repo's own subtraction-over-expansion mandate |

## Why only four

The upstream catalogue is ~330 agents. Most are wrong-altitude for a solo
founder cold-calling licensed WA contractors — MEDDPICC deal desks, QBR
facilitation, RFP proposals, Xiaohongshu, Solidity. The four here each clear
the three-things rule in `CLAUDE.md`:

- `discovery-coach` → **conversion rate.** The Retell call is the only live
  channel and the only path to a booked meeting.
- `meta-paid-social-strategist`, `ad-creative-strategist` → **conversion rate.**
  When a contractor asks *"what would you actually do for me?"*, the answer has
  to be specific. Today `business_context.json` is all Nova has.
- `minimal-change-engineer` → **operational reliability.**

Agents that were considered and rejected: `sales-offer-lead-gen-strategist`
(offer/price construction — `commercial_terms` is UNRESOLVED), `sales-outbound-
strategist` and `marketing-email-strategist` (both prescribe cold-email
sequences — ADR-0014, 0/9 providers permit it), `sales-pipeline-analyst`
(no pipeline yet — 0 calls), `paid-media-auditor` (no ad accounts to audit),
and the deal-desk set (`deal-strategist`, `account-strategist`,
`proposal-strategist`, `sales-engineer`, `sales-coach`).

## Hard constraints these agents inherit

Anything touching outreach must respect, without exception:

1. **No price, ever.** `commercial_terms` is UNRESOLVED. Do not state, imply,
   anchor, or negotiate a number.
2. **No cold email.** ADR-0014. Phone (Retell) is the live channel.
3. **The gates hold.** DNC gate, consent gate, approval gate,
   `BUSINESS_POSTAL_ADDRESS` — never loosened.
4. **Five touches, ever.** The cadence cap in
   `.claude/skills/sales-intelligence/SKILL.md` is a hard cap.
5. **The past is closed.** No past-client claims, names, numbers, or verticals.
