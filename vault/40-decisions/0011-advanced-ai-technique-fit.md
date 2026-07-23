---
name: 0011-advanced-ai-technique-fit
description: Which advanced ML/RL/inference techniques fit a hosted-API, quota-bound, human-gated SDR — most don't, and the ones that do are prompting-level and premature
type: decision
created: 2026-07-23
status: accepted
---

# ADR-0011 — Advanced AI technique fit for OROVA/Nova

## Status
Accepted (owner asked 2026-07-23 to research 10 techniques and add the useful ones;
this is the evaluation + the decision). Extends the subtraction/consolidation
philosophy of [[0006-sdr-refocus-and-subtraction]] and [[0010-consolidation-before-features]].

## Context
The techniques cluster into ways to make a **frontier model** smarter — via
*training* or via *heavy inference-time compute*. OROVA/Nova is neither of those
things:

- **We do not train models.** Nova calls hosted LLM APIs (Groq `llama-3.3-70b`,
  Gemini, OpenRouter free). `grep` confirms **zero** `torch`/`transformers`/`trl`/
  `sklearn`/`.fit()`/`.train()` anywhere in `app/`. No GPU, $0 budget, 512 MB.
- **The binding constraint is quota starvation, not model IQ.** Groq + Gemini free
  tiers 429 *together* under load ([[groq-gemini-free-tier-limits]]). Every extra
  token/sample per task brings the whole system closer to failing.
- **The pipeline is deterministic and human-gated by mandate.** hunt→enrich→score→
  approve→send; the never-fabricate rule and the Telegram approval gate are
  load-bearing.
- **The real bottleneck is data quality + the first send**, not reasoning depth
  (three-things rule; [[session-2026-07-22-improvement-research]]).

So the honest test isn't "is this technique good?" (several are excellent) — it's
"does it fit *this* system without breaking a constraint or a mandate?"

## Decision — per-technique verdict

| Technique | What it is | Verdict for OROVA | Why |
|---|---|---|---|
| **Chain-of-thought** | step-by-step reasoning in the prompt | **Adopt-lite** | Pure prompting (hosted-API-safe). Use only in the few genuine judgment prompts (lead qualification, reply-intent). Not a subsystem — extra tokens cost quota, and most SDR tasks are simple. |
| **In-context learning (few-shot)** | winning examples in the prompt to steer output | **Adopt — deferred** | The **$0, hosted-API form of "learning."** Feed proven-winning outreach as few-shot examples so quality compounds without training. Premature until real campaign outcomes exist (zero today). This is the practical successor to the Wilson loop. |
| **Best-of-N sampling** | generate N candidates, pick the best | **Adopt-lite** | N× LLM calls = N× quota. Justify only for the single highest-stakes message (first reply to a HOT lead), gated. `email_proofreader` (generate→critique→revise) is already a cheaper version. |
| **PPO** | RL training algorithm (RLHF) | **Reject — N/A** | Requires training a model. No training infra, GPU, or budget. |
| **GRPO** | RL training algorithm (reasoning) | **Reject — N/A** | Same — requires training. |
| **Process reward model** | *trained* scorer of reasoning steps | **Reject — N/A** | Requires training a reward model + a reasoning-search harness. Nova already uses **deterministic** outcome scoring (`score_lead_icp`, `contact_confidence`) — the right-sized substitute. |
| **MCTS** | search over reasoning/action trees | **Reject** | The SDR is a deterministic pipeline, not a search problem; many LLM rollouts per decision blow quota + 512 MB. Contradicts the deterministic-pipeline direction. |
| **Test-time compute scaling** | more inference compute → better output | **Reject as a strategy** | The system is compute/quota-**starved**; scaling *up* per task is directly counterproductive. Only the targeted best-of-N slice above survives. |
| **Emergence / situational awareness** | model-scale properties / AI-safety topic | **Reject as a feature** | Not something you "add." The product-sense version — the agent knowing live pipeline state — already exists as grounded context (`nova_chat`, never fabricates). Situational awareness in the safety sense is a risk to *monitor*, not a feature. |
| **Recursive self-improvement** | an AI that rewrites/improves itself in a loop | **Reject / avoid** | Conflicts head-on with the human-approval mandate, never-fabricate, and consolidation-before-features. The **bounded** version — the Wilson champion/challenger bandit (`self_improvement.py`) that tunes *strategies* from real outcomes — is the correct and safe ceiling. True RSI on the revenue pipeline is exactly what the semantic-firewall/approval gates exist to prevent. |

## The pattern
OROVA already runs the **right-sized version** of every genuinely-useful idea here,
without the frontier-lab machinery:

- "Learn from reward" → **Wilson bandit** over strategies (no training).
- "Self-refine / best-of-N" → **email proofreader** (critique→revise).
- "Reward model" → **deterministic scorers** (ICP + contact confidence).
- "Situational awareness" → **grounded live-data context**.

The load-bearing insight: **OROVA's edge is data quality + trust (never-fabricate),
not model intelligence.** These techniques optimize model IQ — the wrong lever for
this system at this stage. Optimizing it would also violate consolidation-before-
features while the pipeline hasn't sent a single email.

## What is actually adopted
Nothing is built now. Adopted as *guidance*:
1. **In-context learning (few-shot)** is the sanctioned path for improving outreach
   quality — built **after** real winning examples exist, feeding the same
   outcome data the Wilson loop already collects.
2. **CoT / best-of-N** are permitted only as *targeted, quota-conscious* touches on
   the highest-value judgment/message, never as system-wide defaults.
3. Everything else is explicitly **not** adopted — recorded here so it isn't
   re-proposed and doesn't accrete into the AI-OS that ADR-0006/0010 are removing.

## Consequences
- A durable guardrail against re-litigating "should we add RL / MCTS / RSI." The
  answer and its *reasons* (no training infra; quota starvation; human-gating) are
  written down.
- If OROVA ever earns revenue and moves to paid, self-hosted models, PPO/GRPO/PRM
  become *possible* — but that's a different company; revisit then, not now.

## Linked
- [[0006-sdr-refocus-and-subtraction]] · [[0010-consolidation-before-features]] · [[claude-brain]] · [[groq-gemini-free-tier-limits]] · [[session-2026-07-22-improvement-research]]
