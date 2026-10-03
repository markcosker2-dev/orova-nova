---
name: 2026-09-30-telegram-reply-nvidia-and-profile-incident
description: Evidence-backed reply diagnosis, NVIDIA feasibility and suspected Telegram profile-access incident.
type: session
created: 2026-09-30
status: investigating
tags: [telegram, security, llm, zero-budget]
---

# Telegram replies, NVIDIA feasibility and bot-profile incident

Mark requested a check of Nova's replies and asked whether a free NVIDIA API
could replace her current LLM. He supplied repeated pruning/learning reports,
then reported unrelated adult-advertising text in the bio of @orovaNOVA_bot.
The OROVA operator skill preserved the $0 and live-change boundaries.
The incident-response skill prioritized credential/profile triage rather than
treating the bio as an LLM tone problem. No source or live setting was changed.

## Fresh evidence — September 30, about 21:27 Singapore

- Public Nova health returned operational, DB/memory OK, build
  `bd33ab8ffbab`. The repair branch/PR201 is not that live build.
- A bounded authenticated read of the latest 100 log entries contained three
  Groq text-success markers and no AI-failure markers. This is not a complete
  history, free-account billing proof or evidence that every reply is correct.
- That build's source uses Groq `openai/gpt-oss-120b` as primary, Gemini next,
  then OpenRouter. The current shared AI client has no NVIDIA provider adapter.
- All six read-only Telegram checks using the locally configured token returned
  HTTP 401: getMe, default/English descriptions and getWebhookInfo.
  The local token may be stale, revoked or incorrect; 401 alone does not prove
  compromise or identify the current production credential.
- A direct GET of the public `https://t.me/orovaNOVA_bot` page returned 200.
  Its profile description contained the reported adult-advertising markers and
  no OROVA wording. The spam links were not opened or preserved here.
- No matching bio-setting calls or spam markers were found in current app,
  scripts, workflows or tests. Unauthorized profile access is suspected;
  its actor, entry point and scope are not established.
- **147 targeted offline tests passed**, one deprecation warning, across chat,
  Telegram voice/access/autonomy, zero-budget scheduler, storage and free-only
  fallback coverage. These tests mock AI/providers; they do not score real
  model prose. Current tracked-content secret scan passed. Neither test result
  proves an invalid token safe or resolves the profile incident.

## Reply findings

`app/core/self_improvement.py:335` gives the report LLM only selected framework,
hour and niche, then asks for blunt claims about winning data and a shipped
change. It supplies no measured counts, baseline, timeframe, opens, clicks,
conversion comparison or statistical test. PAS and 10 AM can be defaults on no
data/error; seed entries explicitly have sample_size=0. The owner's supplied
percentage lifts, significance assertions, broad-audience pivot and campaign
rollout statements are unsupported by this caller contract. A different model
could still invent the same story.

`prune_dead_leads` treats old `updated_at` as inactivity and includes untouched
`New` leads along with Contacted/Email Sent. It sends the same proposal each
run without a changed-evidence notification guard. The live scheduler invokes
the loop every six hours. This explains repeated proposals and learning
reports. Do not approve pruning the 141 records simply because they aged.

The repair branch's $0 scheduler skips this learning/pruning job. That protection
is not deployed. The underlying report should still be made evidence-only and
the prune eligibility/notification behavior corrected before authorized reuse;
this diagnostic request did not authorize implementing or deploying a fix.

The bare business name `cambridge.org` in Mark's hunt example is explicitly
rejected by the current storage gate and its regression. That does not establish
the identity, storage path or Sheet verification of the historical hunt. New
notification code can name a verified CRM projection; the old unconditional
“They're in the sheet” is not durable-write evidence.

Conversational replies, deterministic commands and scheduled notifications are
different paths. A provider change cannot rewrite static pruning notices or
repair their selection rules. The current chat persona is concise and safely
preparatory; broad verb routing and identity deflection can still produce
unhelpful fixed responses to legitimate owner questions. Do not claim a model
upgrade alone fixes these.

## NVIDIA: technically compatible, not a free live replacement approval

NVIDIA's hosted API uses `https://integrate.api.nvidia.com/v1/chat/completions`
and an OpenAI-style client. It lists `openai/gpt-oss-120b` as well as Nemotron,
Qwen and other models. The same GPT-OSS model on another host is not necessarily
better than Groq; model quality, latency and quotas need measured comparison.

Current official pages advertise free/unlimited prototyping, not unlimited
production or an SLA. The API trial terms restrict the API and generated output
to internal testing/evaluation absent the appropriate production subscription.
They also restrict confidential and personal/sensitive data except where an
API service expressly permits it. Nova's snapshot/history can contain owner
names and private conversation text, so an evaluation needs synthetic/redacted
fixtures, not the live pipeline. Account/model quotas were not verified and
no NVIDIA key or completion request was used.

Do not paste NVIDIA credentials into chat, vault or Git. Do not put its key into
GROQ_API_KEY or change only OPENAI_BASE_URL: Groq still runs first, and existing
OpenRouter model slugs/free-only rules do not constitute a NVIDIA adapter.
A later authorized evaluation should add an explicit provider/model selection,
bounded timeout/rate-limit/empty-response/tool-contract handling, safe failure
fallback and synthetic reply tests; preserve consent/spend gates and current
provider until account terms and measured results justify promotion. No new
weights or automatic business learning are created by a provider swap.

Sources checked:
- [NVIDIA LLM API](https://docs.api.nvidia.com/nim/reference/llm-apis)
- [NVIDIA API trial terms](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf), sections 1.2, 1.4, 2.6
- [NVIDIA developer FAQ](https://docs.api.nvidia.com/nim/docs/product)
- [NVIDIA NIM overview](https://www.nvidia.com/en-us/ai-data-science/products/nim-microservices/)
- [Telegram profile API](https://core.telegram.org/bots/api#getmyshortdescription)
- [Telegram token guidance](https://core.telegram.org/bots/features#generating-an-authentication-token)
- [Telegram account security](https://www.telegram.org/faq)

## Next action — secure bot access first

Mark confirmed @orovaNOVA_bot is still listed under /mybots in his verified
@BotFather, so ownership remains. This does not identify the profile-edit actor.
Next obtain authorization for controlled recovery, review Telegram Devices
sessions and enable two-step verification, then revoke/replace the bot token
using BotFather's token controls.
A bio rewrite alone does not remove an actor's access. The exact leak source
remains unknown; a clean current-tree secret scan does not clear public history
or third-party integrations.

Credential replacement and live bot/profile/webhook updates need explicit
recovery authorization. Do not deploy/restart Render blindly: its disk is
ephemeral and full-backup evidence remains held. Any rollout must coordinate
secure token storage, every authorized runtime/integration, webhook validation
and preservation of state; never paste or print the replacement token. Verify
getMe equals the expected bot, descriptions are OROVA-only, webhook is expected,
and profile stays clean before declaring resolved. No token was rotated,
bio overwritten, lead archived, campaign changed or provider replaced here.

Linked: [[active-context]] · [[2026-09-30-project-benchmarks-and-safety-fixes]]


## Free LLM API directory check — 2026-09-30 21:41 SGT

Mark asked for the GitHub list of free LLM APIs. Likely matches are
[mnfst/awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis)
and the broader
[golapkamal/awesome-free-llm-apis](https://github.com/golapkamal/awesome-free-llm-apis).
The exact intended repository is not confirmed. These are discovery directories,
not proof of current quota, business-use permission, privacy or reliability.
No repository was installed, credential requested, account created or provider
changed; public catalogue GET requests were not inference requests.

Official-source findings:

- Groq publishes free-plan GPT-OSS-120B limits of 30 requests/minute,
  1,000 requests/day, 8,000 tokens/minute and 200,000 tokens/day.
  [Rate limits](https://console.groq.com/docs/rate-limits).
  Nova already uses this model as primary in the inspected source; this remains
  the lowest-change candidate. Published limits are not evidence that Mark's
  account has billing disabled or matches those limits.
- OpenRouter's documentation source defines the no-credit tier as 20
  requests/minute and 50 requests/day, account-wide, not per model.
  [Limits](https://openrouter.ai/docs/api_reference/limits).
  Its public catalogue currently lists multiple free Nemotron models with tools,
  but price/tool metadata does not certify Nova quality or business permission.
  Crucially, [Nemotron Super's free endpoint](https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free)
  displays NVIDIA API Trial Terms and warns against confidential/personal data.
  Do not treat OpenRouter routing as bypassing NVIDIA trial restrictions.
  Other model/provider endpoints need their own terms and privacy checks.
- Cloudflare offers 10,000 Neurons/day on Workers Free; over-limit requests fail
  instead of automatically upgrading. Some frontier models require a paid
  billing method or prepaid credits and are outside this $0 plan.
  [Pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/).
  A free-eligible model is a candidate backup, not an integrated or tested one.
- Mistral Free mode has API access without a credit card, with limited usage;
  its help center describes the lowest tier as evaluation/prototyping.
  Free-mode input/output may be used for training unless opted out.
  [Activation](https://docs.mistral.ai/getting-started/quickstarts/studio/activate-and-generate-api-key),
  [Limits](https://help.mistral.ai/en/articles/698531-why-am-i-hitting-api-rate-limits-and-how-do-i-increase-them),
  [Data controls](https://help.mistral.ai/en/articles/347617-do-you-use-my-user-data-to-train-your-artificial-intelligence-models).
  Account quota, opt-out and intended-use terms need verification before live use.
- Cerebras currently advertises $5 in trial credit, not evidence of a continuing
  free allowance. [Official offer](https://www.cerebras.ai/inference).
- Ollama documents a hosted API without local installation and says cloud
  prompts/responses are not used to train models. Its free-plan quota and
  suitability were not verified in this check, so it is not promoted here.
  [Cloud API](https://docs.ollama.com/cloud).

Recommendation: keep Groq as the working primary while correcting evidence
contracts/repetition and securing Telegram. Evaluate a free-eligible backup
with synthetic fixtures, measured truthfulness/tool reliability/latency, account
quota and privacy checks; no automatic paid fallback. NVIDIA-hosted trial
endpoints remain evaluation-only. A new provider does not itself learn from
past mistakes, substantiate invented statistics or repair a compromised bio.
Security recovery authorization, deployment/backup gates and draft-only media
restrictions remain unchanged.
