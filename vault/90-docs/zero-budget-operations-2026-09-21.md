---
name: zero-budget-operations-2026-09-21
description: Codex operating handoff — evidence-backed Telegram repair and a realistic pre-revenue contact workflow
type: doc
created: 2026-09-21
status: active
---

# Nova on a $0 budget

This note supersedes older setup directions for current operations. It does not
erase the history or change Mark's commercial terms. The laptop's open Obsidian
vault was on `docs/registry-survey-2026-08-05`; GitHub and live Nova were on
`bd33ab8ffbab`. Do not mistake that old local checkout for production.

## Business

Get the first paying client. Lead with custom builders/high-end remodelers;
luxury real-estate top producers are secondary. Never pivot to med spas. Work
the existing prospects before accumulating hundreds more.

Diagnose: empty pipeline -> lead generation; existing enquiries needing
qualification -> standalone qualification; both -> combined service. The
canonical services contain three packages, but the offer is still owner-gated.
No invented discounts, free trials, results, clients, or promises of funded demos.

Older close-kit, traction-playbook and pilot-pricing notes are historical drafts.
They are not authorization to quote their old trials/prices, broaden the ICP,
or promote a paid phone demo under the current $0 constraint.

## Evidence from production, September 21

- The service was healthy on the expected SHA; that alone did not mean the
  business process worked.
- The database rejected a lead with ID -2, yet the hunt requested email approval
  for it. Negative save results must never enter outreach or discovery events.
- A follow-up blocked for missing postal-address configuration was still marked
  Contacted and its campaign advanced. Only a successful send may advance it.
- Telegram passed no history. `/status` relabelled accumulated CRM counts as
  today's activity and presented seeded strategy numbers as learned results.
- The local OpenRouter key returned HTTP 401. Its former first-choice free model
  was also absent from the current public catalogue. Groq model access returned
  HTTP 200. A model-list check does not prove the account's billing tier.
- Drive backup returned `invalid_grant`. Sheets reconciliation succeeded for
  lead identities, but Sheets is not a full backup of the database.

## Repair behavior (requires deployment)

- `/status`: literal CRM status counts, explicitly not daily sends or independently
  verified delivery totals.
- `/leads`: up to five eligible, uncontacted stored prospects.
- `/contact ID`: recorded source/contact details and an unsent manual opening
  message. No fabricated owner, guessed address, proven pain or verified social
  profile. Suppressed leads are excluded.
- `/forget`: clears only this chat's recent context, not leads or business records.
- Recent turns are bounded and isolated by chat in SQLite. They survive process
  restarts with the DB; on Render they still need a working full backup to survive
  ephemeral-disk loss.
- Chat cannot execute free-form outreach instructions. It must not claim to have
  sent, called, searched or booked when it only generated text.
- Telegram webhooks authenticate even when an explicit webhook-secret variable
  was not configured. Only configured operator chats can reach approvals or data.

`ZERO_BUDGET_MODE=1` is the production default. It blocks paid Retell calls and
automated cold outreach at the sending functions. It suppresses scheduled cold
calling, email drips, speculative CEO tasks, learning loops and repetitive
pipeline-health chatter. Reply monitoring and backups remain. Scheduled hunting
pauses while at least 20 leads are already stored; explicit dashboard hunts remain.
No libraries, contact records or historical notes need to be deleted to get this
leaner operating mode. No existing live credentials are removed.

Groq/Gemini must be on free accounts with billing disabled. Nova cannot infer
that from an API key. OpenRouter remains free-model-only in $0 mode even if an
old `OPENROUTER_ALLOW_PAID` flag exists. Do not enable paid fallback to hide quota
failures; deterministic Telegram commands work without an LLM.

## How to contact prospects today

1. `/leads`, then `/contact ID`.
2. Check the business's own site/profile. A search link is not a verified handle.
3. Review the short question, then use the business's permitted public contact
   channel individually. Nova prepares it; it does not secretly send it.
4. Bring the actual reply back for a draft response. Stop on an opt-out; don't
   pitch a paid demo, a price or an unverified booking slot.

AgentMail's current terms prohibit unsolicited messaging; simply adding a postal
address does not grant provider permission. Instagram's official messaging API
is for eligible conversations, not a bulk cold-DM sender. Do not work around
platform restrictions with account-risking automation.

Sources checked September 21:
[AgentMail terms](https://www.agentmail.to/legal/terms),
[Meta Instagram Send API](https://www.postman.com/meta/instagram/folder/uxudqu0/send-api),
[OpenRouter catalogue](https://openrouter.ai/api/v1/models).

## Release blockers / owner actions

- Re-authorize Google Drive and remove the OAuth app's testing-mode token-expiry
  trap where appropriate. Verify a new complete snapshot before any restart or
  deployment; don't remove OAuth and assume a service account has Drive storage.
- Confirm merge/deployment permission. Preserve the old local branch and its
  four edited historical notes; do not reset or force-push them.
- Replace the invalid OpenRouter key with a valid free-account key if that
  fallback is wanted. Never paste secrets into a note, chat, PR or test fixture.
- Confirm the final commercial offer personally before Nova quotes it.

Tests and code changes do not prove that prospects have been contacted, that a
meeting was booked, or that a deployment happened. Record each separately.

## Continuation, September 22

The completed local suite passes 1,510 tests. Additional regressions cover
bounded chat history, addressed Telegram commands, webhook authorization,
suppressed contact pagination, inbound-only email replies, empty AI completions,
scheduler failures and truthful backup results. Knowledge, secrets and security
lint remain release checks. Code is prepared on `codex/zero-budget-repair`;
local success is not a deployment claim.

Read-only checks still found the old live build `bd33ab8ffbab`. Local Google
OAuth refresh returned `invalid_grant`; a complete production snapshot is not
verified. Re-authorization and verified backup remain prerequisites for deploy.

The existing OROVA Outreach - IG DM Queue has 61 rows marked `Not yet sent`
and no recorded response outcomes. Do not describe that queue as successful
outreach, derive a winning script from it, or create another tracking system.
Use individual, researched messages from the existing account where permitted;
stop on refusal and do not repeatedly message nonresponders. Agency email
replies can use AgentMail after the existing recipient and approval checks.
Its terms prohibit unsolicited messaging, so it is not the cold-email lane.
