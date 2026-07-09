---
name: owner-contact-research
description: how to get SMB owner direct email + phone reality
type: session
created: 2026-07-05
status: active
---

# Session: Owner-Direct Email + Phone Reality Research (2026-07-05)

**Scope:** Read-only research. No code changed. Builds on
[[lead-engine-research]] and [[owner-name-engine]] (2026-07-04), which solved
*owner-NAME* discovery (registry-first pipeline in `app/skills/owner_finder.py`).
This session covers the next step once a name is known: the owner's **direct
email**, the **phone reality** (cell vs. business line + TCPA), a **GitHub
scan** for HTTP-only enrichment libs, and a live check of the `/` prospecting
skills.

---

## Job 1 — Email-finder tool comparison (free/freemium tiers)

All figures below are from July-2026 vendor pricing pages (via web search;
not independently re-verified against a live API call — treat monthly caps
as "vendor-stated," they change without notice). **None of these are wired
into Nova today** except Apollo and Hunter, which already have graceful
skip-if-unset code paths (`app/skills/light_enrich.py` Steps 3-4,
`app/skills/apollo_enrichment.py`) — their env vars (`APOLLO_API_KEY`,
`HUNTER_API_KEY`) are declared in `.env.example` but unset in `.env`.

| Tool | Free tier | API endpoint (finder) | Finds a *specific person* by name+domain? | Accuracy / notes |
|---|---|---|---|---|
| **Hunter.io** | 50 credits/mo, 1 seat. **API access requires Growth tier (€104/yr) or higher** — the free/Starter tier is UI+Chrome-extension only, no programmatic API key issued. | `GET /v2/email-finder?domain=X&first_name=Y&last_name=Z` (Growth+); `GET /v2/domain-search?domain=X` (returns all known emails at a domain, pattern included) | Yes (Email Finder), but **not reachable on the free tier** — already gated in code (`light_enrich.py` Step 3 uses `domain-search`, not `email-finder`, so it doesn't need a specific name) | Domain Search alone (no name match) is usable free-tier-adjacent since it's bundled with the 50 free credits once you *do* have any paid seat; genuinely free-tier programmatic access is the blocker, not the endpoint shape. |
| **Snov.io** | 50 credits/mo on signup. Domain Search (count-only) is free/uncounted; each actual prospect pull costs 1 credit. | `POST /v1/get-emails-from-names` (bulk, name+domain → email); `GET /v2/domain-emails-with-info` | Yes — `get-emails-from-names` is exactly a by-name+domain lookup | API access on the free plan requires emailing `help@snov.io` to enable it — not self-serve, adds a manual step. |
| **Apollo.io** | Free tier cut in late 2025: **100 email credits/mo on a personal/non-corporate domain, 10,000/mo if signing up with a company email domain**. 5 mobile-phone credits/mo, 10 export credits/mo. | `POST /v1/people/match` (name/domain → email+phone, "waterfall" style); `POST /v1/mixed_people/api_search` (search, no contact data) | Yes — `people/match` is a direct name+domain→contact lookup | **API access is not available on the free/Basic plan at all** — confirmed by 2026 pricing docs. This directly matches what's already in Nova's code: `light_enrich.py` Step 4 calls the real REST API, which only works once a *paid* Apollo key exists — "free tier" language in `.env.example` is optimistic; Apollo's free plan is UI-only for API purposes. |
| **RocketReach** | 5 lookups/mo total (not recurring credits — a hard trial cap), email-only. | `GET /v2/person/lookup?name=X&current_employer=Y` | Yes | **Full API access requires the Ultimate tier ($2,099/yr)** — free tier is web-UI trial only, not usable as an ongoing pipeline component. Exclude. |
| **FindThatLead** | 50 email + 2 mobile credits, but **only for a 7-day trial**, then hard cutoff to paid. | `GET /v1/search.json?domain=X&name=Y` | Yes | Not a sustainable free tier (one-time trial, not monthly) — exclude for a recurring $0 pipeline. |
| **Prospeo** | **75 email credits/mo recurring**, includes finder + verifier, API access included starting at Basic ($39/mo) — but the *free* 75/mo tier is explicitly listed as including "email finder and verifier" with no separate API-access paywall mentioned for basic lookups. | `POST /email-finder` (name/domain → email, LinkedIn-URL-based lookup also supported); `POST /email-verifier` | Yes | Best-documented recurring free allowance of the paid-style tools; verify at signup whether the 75/mo actually includes REST API calls vs. UI-only (some sources conflict — Basic $39/mo explicitly "includes API access," ambiguous whether free tier does too). Worth a signup pass before relying on it. |
| **Anymail Finder** | 100 one-time credits at signup, usable across UI + API, but **expire after 14 days** — not a recurring monthly allowance. Free re-searches of the same query within 30 days don't recharge credits. | `POST /v5.0/search/person.json` (name+domain → email) | Yes (also has a "decision-maker" mode: domain-only → best-guess exec, 2 credits) | One-time trial, not sustained free tier — usable for an initial batch test, not an ongoing $0 pipeline. |
| **Dropcontact** | 50 one-time test credits, **no permanent free plan**; API access gated to Business tier (~€74-99/mo). | `POST /batch` (name/domain → email, GDPR-native, EU servers) | Yes | Best compliance story (GDPR-by-design, no third-party data resale) but zero sustainable free/API tier — exclude for a $0 pipeline; worth remembering if EU leads ever enter scope. |
| **Tomba.io** | **25 finder searches + 50 verifications/month, recurring, no card required**, and — critically — **failed/no-result searches are not charged**. API access included on the free tier (REST API + SDKs). | `GET /v1/email-finder?domain=X&full_name=Y` (person finder); `GET /v1/domain-search?domain=X` (all known emails + detected pattern) | Yes | **Best genuinely-recurring free API tier of the group** for a low-volume $0 pipeline — 25/mo is small, but it's real, renews monthly, and specifically includes the by-name+domain finder endpoint via API (not just UI). Verification is bundled free instead of metered separately, which matters for Job 2 below. |

**Bottom line on Job 1:** Apollo and Hunter (already wired into Nova's code)
turn out to have **no usable free-tier API access at all** for the
specific by-name lookup — Apollo's `people/match` and Hunter's
`email-finder` both require a paid seat to even get an API key, contrary to
the "[FREE TIER]" label in `.env.example`. The domain-level, no-name-required
endpoints (Hunter `domain-search`, Snov `domain-emails-with-info`) are closer
to genuinely free/cheap but only return a list of already-known emails at a
domain plus a detected pattern — not a name-targeted lookup. **Tomba.io** and
**Prospeo** are the two tools in this list with a real, recurring, small free
API allowance that includes the specific by-name+domain finder endpoint —
see Job 4 ranking.

---

## Job 1b — Email pattern generation

Nova already implements this (`app/skills/light_enrich.py :: _guess_emails_ranked`,
lines 1332-1379): given an owner name + domain + any observed same-domain
emails, it ranks `{first}@`, `{first}.{last}@`, `{f}{last}@`, `{first}{last}@`,
`{first}_{last}@`, `{last}@`, learning the domain's actual pattern from any
already-observed email at that domain first. This is a solid implementation —
no need to rebuild it. What's missing is the **verification step gating it**
(see Job 1c) being MX-only today; HTTP-based deliverability/catch-all checks
would raise confidence before handing a guessed email to outreach.

Public reference for the general technique (not something to import, since
Nova's own version already covers this): `apifyforge/email-pattern-finder`
(MIT) — infers the pattern from 5 signal sources (provided emails, website
scrape, GitHub commit search, RDAP/WHOIS, optional Hunter key) and scores 12
pattern templates; conceptually validates that Nova's simpler
observed-then-fallback approach is the right shape, just with fewer signal
sources feeding the pattern-detection step.

## Job 1c — HTTP-based email verification (Render blocks SMTP)

Today: `light_enrich.py :: _verify_mx()` checks MX records only (via
`dnspython` in a thread executor) before accepting a *guessed* email — this
confirms the domain can receive mail, not that the specific mailbox exists,
and does not detect catch-all domains (a domain that accepts mail to any
local-part, which would make MX-only verification falsely "pass" a wrong
guess).

Free/freemium **HTTP REST** verification APIs (no SMTP handshake needed
client-side — the provider does that server-side and returns JSON), useful
as a real "is this specific mailbox real" check on top of the pattern guess:

| API | Free tier | Catch-all detection? | Notes |
|---|---|---|---|
| **Verifalia** | 25 credits/day (~750/mo), free tier includes API access | Yes | Best free-tier ceiling of this group and the only one confirmed to expose API access at the $0 tier without a card — strongest candidate to slot in after Nova's MX check. |
| **Abstract API (Email Validation)** | 100/mo, no card required | Yes, but accuracy is "a step below dedicated providers" per review coverage | Simple HTTP GET, easy to wire; treat as a secondary/cheap gate, not a strong final say on catch-alls. |
| **Emailable** | 250 free credits (appears to be a one-time signup grant, not confirmed recurring) | Yes | Confirm recurring-vs-one-time before relying on it long-term. |
| **EmailListVerify** | 100 free checks, then ~$5/1,000 | Yes | Cheapest paid fallback if free tiers run out; not $0 but very low friction to add as a last-resort paid gate later. |
| Tomba.io verifier (from Job 1) | 50/mo, bundled free with the finder tier | Not explicitly confirmed | Already free if Tomba is adopted for finding — no separate integration needed. |

**Recommendation for Job 1c:** keep the existing MX check as the cheap
first gate (already free, already implemented, correctly non-blocking), and
add **Verifalia** as a second HTTP-only gate specifically for guessed emails
before they're marked `email_status="guessed"` and routed to outreach — 750/mo
free comfortably covers Nova's current lead volume (worker.py's
`MAX_CALLS_PER_DAY=5` and the broader daily hunt cap are both far below
that). This closes the catch-all gap MX-only checking has today without
needing SMTP (which Render blocks) and without spending SerpAPI's already
shared 250/mo quota (see Job 4 note on quota sharing).

---

## Job 2 — Owner phone reality (blunt version)

**Can a personal cell be obtained free/legally?** Not reliably, and not as
an automatable HTTP pipeline. Confirmed from this session's research:

- Cell numbers essentially never appear in free public directories or
  structured registries (unlike owner *names*, which CA/WA/OR registries
  legally require — see [[lead-engine-research]] Job 2). The realistic free
  paths are: (a) whatever phone number the business's own website/Google
  Business Profile/Yelp page lists — which is a **business line**, not a
  personal cell, in the overwhelming majority of cases; (b) manual LinkedIn
  outreach asking the person directly; (c) paid people-search/skip-trace
  tools (Spokeo, BeenVerified, Apollo/Lusha mobile credits) — none free at
  volume, and Apollo's own free tier only grants **5 mobile-phone credits/mo**
  (Job 1 table).
- Nova's own `smart_scraper.py` (an ad-hoc AI tool, not on the scheduled
  hunt path per [[lead-engine-research]] Job 1.1) already encodes the right
  instinct at the extraction-schema level: it asks its LLM to flag
  `is_verified_mobile` only when a number is "explicitly labeled as a
  mobile/cell number" or appears in a "Contact the Owner" context — i.e. the
  codebase already knows *conceptually* that business-line and personal-cell
  numbers need to be distinguished. **Nothing downstream currently enforces
  that distinction before a number reaches Retell.** `app/worker.py`'s call
  lanes (`run_lead_hunt_slow_lane`, the escalation path around line 723, and
  the lane around line 812) pass whatever `lead["phone"]` holds straight to
  `trigger_retell_call()` with only a `MAX_CALLS_PER_DAY` cap (default 5) —
  no cell/landline classification gate exists on that path today.

**TCPA implications of cold-calling US cells with an automated dialer
(Retell) — this is the part to take seriously:**

1. **The FCC's Feb 2024 Declaratory Ruling puts AI-generated voices squarely
   inside the TCPA's "artificial or prerecorded voice" category.** A Retell
   call to a cell phone is legally an "artificial voice" call, full stop —
   there is no AI-specific carve-out.
2. **Consent tier for marketing calls to a cell = Prior Express Written
   Consent (PEWC)** in every state except TX/LA/MS (5th Circuit, Feb 2026,
   requires only "prior express consent," not written — but that ruling
   does not bind the other 47 states, so a nationwide op should still
   operate on the written-consent standard). PEWC means an actual signed/
   clicked agreement specifically authorizing autodialed/AI calls — not
   "they gave us their number once," not a scraped website phone number.
3. **The B2B exemption is real but narrower than it sounds.** Calls to a
   business's *published business line* soliciting a business-to-business
   sale are generally treated as exempt from the TSR's DNC provisions. Calls
   to an owner's **personal cell** are explicitly **not** covered by that
   exemption "even if you only want to discuss business" — the exemption
   tracks the *number*, not the *topic*. This is the single most important
   line item for Nova's design: **the exemption only protects calling the
   business line Nova already scrapes from Yelp/Google Maps/the website —
   it does NOT extend to a personal cell even if one were somehow obtained.**
4. **DNC scrub cadence**: safe-harbor compliance requires re-checking the
   National DNC Registry (plus the ~11 state registries that maintain their
   own) **no more than 31 days before calling**. Nova's codebase has
   **zero DNC-scrub logic anywhere** — confirmed by grep across `app/` for
   TCPA/DNC/consent terms (see Job 2b below). `app/core/compliance.py` is
   thorough for **email** law (CAN-SPAM/GDPR/CASL/PECR, opt-out tables,
   10-business-day honor window) but has no phone/DNC/TCPA equivalent at
   all — this is a real, currently-unaddressed compliance gap for the
   calling lane, independent of anything else in this research.
5. **Penalties are severe and per-call, strict liability**: $500-$1,500 per
   violation with no aggregate cap (statutory damages, no need to prove
   harm) on the TCPA side, plus up to **$53,088 per violation** (2025-
   inflation-adjusted) on the FTC Telemarketing Sales Rule side for DNC
   violations specifically. This is not a "worth the risk at $0 cost"
   calculation — a single wrongly-called cell phone number, called weekly
   for a month, is a real five-figure exposure.

### Job 2b — Confirmed: no TCPA/DNC logic exists in the codebase today

`grep -riE "TCPA|do.not.call|DNC|consent|opt.?out" app/` hits 8 files, but
every hit is **email**-side compliance (`compliance.py`'s CAN-SPAM/GDPR/CASL/
PECR classes, `agentmail_skill.py`, `guardrails.py`'s generic content
filters) or unrelated (`worker.py`'s `cancelled` task-status strings). There
is no `phone_consent` table, no DNC-registry check function, and no
cell-vs-landline gate anywhere between `owner_finder.py`/`light_enrich.py`
(which populate `lead["phone"]`) and `outbound_dialer.py`'s
`trigger_retell_call()` (which dials it).

### Compliant recommendation

**Call the business line, not a personal cell — and don't build a
personal-cell-acquisition pipeline for the Retell lane at all.** Concretely:

- Keep Nova's phone lane targeting whatever number the business publishes on
  its own website/Google Business Profile/Yelp listing (already what
  `light_enrich.py` and `lead_gen_v3.py` scrape) — this is the number the
  B2B exemption actually protects, provided the call is genuinely soliciting
  a B2B service (Meta-ads management is a clean fit) and not disguised
  consumer solicitation.
- **Do not** add any skip-tracing/people-search integration aimed at
  obtaining an owner's personal mobile for the automated dialer — every free
  path for that returns unreliable data, and even a *correct* personal cell
  number would need PEWC Nova has no mechanism to collect, making it a
  straight TCPA violation on the very first ring.
- **Do** add — as a real, scoped follow-up, separate from this email-focused
  research — a DNC-scrub step before `trigger_retell_call()`: check the
  number against the National DNC Registry (first 5 area codes are free to
  download; a paid full-registry subscription or a wrapper service like
  RealValidito's free 100-lookup tier could cover initial testing) with a
  ≤31-day cache, and log/skip on a hit. This closes a real compliance gap
  independent of the email-pipeline work below and should be flagged as its
  own task rather than folded into this email research.
- Retell disclosure: have the agent identify itself as automated/AI when
  asked (best practice in all states, required in a growing number) —
  `app/skills/outbound_dialer.py`'s dynamic-variable payload doesn't
  currently include a self-identification line; worth adding to the Retell
  prompt/agent config (not this codebase) alongside the DNC-scrub follow-up.

---

## Job 3 — GitHub scan: HTTP-only, Render-friendly enrichment libraries

All confirmed plain-HTTP (no Playwright/Selenium/headless-Chrome) via
WebFetch inspection or search-result descriptions; none of these are
currently imported anywhere in `app/`.

| Repo | What it does | License | HTTP-only? | Verdict |
|---|---|---|---|---|
| **apifyforge/email-pattern-finder** | Detects a company's email naming convention from 5 signal sources (provided emails, website scrape via CheerioCrawler/static HTML — explicitly *no* JS rendering, GitHub commit search, RDAP/WHOIS, optional Hunter key), scores 12 pattern templates | MIT | Yes (CheerioCrawler = static HTML parse, not a browser) | Good reference implementation to compare against Nova's own `_guess_emails_ranked` — Nova's version is simpler (no GitHub-commit-search or multi-source pattern voting) but already covers the core "learn pattern from an observed email, else rank common templates" logic. Not worth importing wholesale (built for Apify's actor runtime), but the GitHub-commit-search signal is a genuinely free, HTTP-only idea Nova doesn't have — a person's `git config user.email` often leaks their real work address in public commit history. |
| **laramies/theHarvester** | Classic OSINT recon tool — emails, subdomains, names from a domain, pulling from many free sources (`hunter` with a 10/day free-tier cap noted in its own docs, `thc` free subdomain enum with no key, plus public search engines) | GPL-3.0 (note: copyleft — bundling it into Nova's proprietary codebase would need a separate-process/subprocess boundary, not a direct import, to avoid GPL contamination of `app/`) | Yes | High name recognition, actively maintained, but its per-source rate limits (10/day on the free Hunter path) and GPL license make it a poor fit to vendor directly into `app/skills/`; more useful as a one-off manual research tool than a wired-in dependency. |
| **[author varies] Mail-Hunter** (OSINT python tool, business-domain → professional emails) | Domain → candidate professional emails, no browser | Not confirmed from search snippets — check before use | Yes (per description) | Smaller/less-maintained than theHarvester; worth a manual look before adopting, license unconfirmed so do not vendor without checking. |
| **[Node/TS] enrichment-kit** | "Open-source alternative" multi-vendor email-enrichment wrapper, bring-your-own API keys across several providers (waterfall pattern) | Not confirmed from search snippets | Presumably yes (wraps REST APIs) | Conceptually the closest match to what Nova's `light_enrich.py` already does by hand (try Hunter, then Apollo, then DDG, in sequence) — worth a closer look as a possible *pattern reference* for a cleaner waterfall abstraction, not as a dependency (Node, and Nova's stack is Python). |
| **Devrax/opencorpdrscrapper** | Scrapes OpenCorporates company data including officer info | Not confirmed | Presumably yes (OpenCorporates is a web target, not JS-heavy) | Redundant with `owner_finder.py`'s existing direct OpenCorporates API client (`_opencorporates_lookup`) — Nova already calls the real API directly with a token, which is cleaner than scraping OpenCorporates' own site. No action needed. |
| **SEC-API-io/sec-api-python**, **dgunning/edgartools**, **areed1192/python-sec** | SEC EDGAR filing access (10-K/8-K/Form 3/4/5 insider/officer data) | MIT (edgartools, python-sec) / commercial (sec-api-python, paid tiers beyond free query allowance) | Yes, EDGAR is a plain REST/HTTP target | **Low relevance to Nova's ICP** — EDGAR only covers SEC-registered (i.e. publicly traded or securities-issuing) entities; the CLAUDE.md target ICP (luxury West-Coast SMBs — remodeling, auto, aviation, real estate) is almost entirely private companies that never file with the SEC. Noted for completeness per the task brief, not recommended for integration. |

**Bottom line on Job 3:** no single GitHub repo is a drop-in replacement for
what `app/skills/light_enrich.py` + `app/skills/owner_finder.py` already do
— Nova's hand-rolled pipeline is, if anything, more sophisticated than most
of what's publicly available in this exact niche (structured-registry-first
+ website-scrape + pattern-guess + MX-check). The one genuinely new, free,
HTTP-only idea surfaced here that Nova doesn't have: **mining GitHub's public
commit-search API for a person's real email** when their name is known and
they have any public GitHub activity (a real signal for owner-operators of
small technical/trades businesses who might maintain a scheduling site or
a WordPress fork) — cheap to add as one more Stage-2-adjacent fallback in
`_guess_emails_ranked`'s neighborhood, not a replacement for anything.

---

## Job 4 — `/` skill evaluation (owner-contact data)

All three could not be exercised to completion in this session — each
requires an auth flow this non-interactive research session cannot finish
(per this session's own operating constraints: read-only, no code changes,
no completing OAuth/connector flows on Mark's behalf). Confirmed rather than
assumed for each:

- **`vpai:vibe-prospecting`** — invoked. Requires either (a) an MCP connector
  (`mcp__*__fetch-entities`-pattern tools) that must be installed/authorized
  from the Cowork connector store, or (b) the `npx @vibeprospecting/vpai@latest`
  CLI authenticated via a mounted `~/.config/vpai/config.json` or
  `VP_API_KEY` env var. Checked this environment directly: `npx` exists
  (v11.6.2) but **no `~/.config/vpai` directory and no `VP_API_KEY`/
  `EXPLORIUM` env var are present** — confirmed unauthenticated, not
  attempted further (the skill's own instructions explicitly forbid falling
  back to an OAuth URL or unauthenticated CLI call).
- **`apollo:prospect`** / **`apollo:enrich-lead`** — invoked `enrich-lead`.
  Both route through `mcp__c9dd27e7-ce6b-4ab5-b654-ecd03a6c24c5__apollo_*`
  tools (`apollo_people_match`, `apollo_mixed_people_api_search`,
  `apollo_organizations_enrich`), which the session's own system context
  flagged as requiring authorization the user must grant via claude.ai
  connector settings — this session cannot complete that flow. Separately,
  every one of these tools carries a **mandatory-confirmation credit-cost
  warning** in its own schema (e.g. "Enriching X will consume 1 credit... Do
  you want to proceed?") — even if authenticated, this research session
  should not spend a real Apollo credit against Mark's account without his
  explicit sign-off, so the call was correctly not attempted. Checked for a
  local fallback key too: no `APOLLO` env var present locally either.
- **Net finding**: none of the three `/` skills returned owner contact data
  in this session — all three are gated behind an unauthenticated
  connector/CLI, exactly as the task brief anticipated. This doesn't change
  the ranking below, since none of them are $0/freemium-HTTP-only fits for
  Render anyway (Apollo and Explorium/vpai are both paid-credit platforms
  under the hood) — they're useful as a **manual, human-in-the-loop**
  research aid for Mark himself (via claude.ai chat, once he authorizes the
  connectors), not as something `app/skills/` should call autonomously from
  Render.

---

## Ranked recommendation: $0/freemium owner-direct-email pipeline

Building on the existing registry-first owner-**name** pipeline
(`owner_finder.py`, already built per [[owner-name-engine]]) — once a name
is known, resolve the **email** in this order:

1. **Website-scrape + MX-verified pattern guess (existing, keep as primary)**
   — `light_enrich.py`'s Steps 2 (crawl) → 5 (guess+MX) already do this for
   $0, no new signup needed, and are the highest-volume, lowest-friction
   source since they run on every lead regardless of quota. Expected hit
   rate: **moderate** for direct/explicit emails (depends on the site
   publishing one), **near-100% for *a* guess** once an owner name + live
   domain are known (a guess always exists; the question is whether it's
   *correct*).
2. **NEW: Verifalia HTTP verification gate** on any guessed email (Job 1c)
   before it's marked `email_status="guessed"` — free (750/mo), catches
   catch-all-domain false positives the current MX-only check cannot,
   doesn't touch the shared SerpAPI quota. Add as a new function alongside
   `_verify_mx()` in `light_enrich.py`, gated by a new `VERIFALIA_API_KEY`
   (skip cleanly if unset, same pattern as every other optional key in this
   codebase).
3. **Tomba.io as a recurring-free-tier name+domain finder fallback** — only
   for leads where Step 1's website scrape found *no* email at all (not even
   candidates to guess from) but a domain and owner name are both known.
   25/mo is small, so ration it the same way `owner_finder.py` already
   rations SerpAPI/OpenCorporates (SQLite-backed monthly counter, cache
   hits). Expected incremental hit rate: **small but real** — this is a
   genuine name+domain→email lookup against Tomba's own index, which may
   have already-verified emails Nova's own scrape missed (e.g. a listed
   email on a partner directory, not the business's own site).
4. **Prospeo as a second freemium finder fallback**, same rationing pattern,
   only invoked if Tomba's monthly allowance is already spent for the
   period — treat as a same-tier alternate rather than layering both on
   every lead (75/mo free, similar shape to Tomba, no reason to spend both
   quotas on the same lead).
5. **Apollo/Hunter REST calls (existing code, unchanged) — but flag to Mark
   that "free tier" in `.env.example` is currently inaccurate**: both
   require a **paid** seat before an API key is even issued (Job 1 finding).
   If Mark is not planning to pay for either, these two steps will simply
   never fire (which is exactly what's happening today — both keys are
   unset) — no code change needed either way since both already skip
   cleanly when the key is absent, but the `.env.example` comment should be
   corrected in a future edit to stop implying a usable free API tier
   exists for either.
6. **DDG snippet search (existing, unchanged)** — keep purely as the
   already-implemented last resort; this session's research reconfirms
   [[lead-engine-research]]'s Job 2 finding that DDG scraping carries real
   ToS/block risk and should never be promoted above a structured API
   source.

**Expected overall hit rate (directional, not measured):** for a lead with
a known owner name and a live, non-parked domain, this pipeline should
return *some* email (guessed-and-verified, or a finder hit) for the large
majority of leads — the open question the codebase can't answer today is
what fraction of *guessed* emails are the *correct* mailbox vs. a
plausible-but-wrong pattern match, which is precisely the gap Verifalia
(step 2) is meant to narrow without adding SMTP (blocked on Render).

**Quota-sharing note (important — don't double-count SerpAPI capacity):**
`owner_finder.py`'s `_serpapi_fallback` (owner-name search) and
`lead_gen_v3.py`'s `_source_serpapi_maps` (lead *discovery*) already share
one 250/mo SerpAPI budget (confirmed via code comment at
`lead_gen_v3.py:955`). Nothing in this email pipeline recommendation adds a
third consumer of that same quota — Verifalia/Tomba/Prospeo are all
independent budgets, which is why they were chosen over stretching SerpAPI
further.

### Integration notes for `app/skills/`

- **New file or extend `light_enrich.py`**: add `_verify_email_http(email:
  str) -> Optional[bool]` calling Verifalia's REST endpoint
  (`https://api.verifalia.com/v2.4/email-validations`, HTTP Basic Auth with
  a free-tier API key), returning `True`/`False`/`None` (None = check itself
  failed, don't block on it — same "fail open on infra hiccup" philosophy
  already used throughout `owner_finder.py`'s ration-check helper). Call it
  right after `_guess_emails_ranked()` produces a candidate, before setting
  `email_status="guessed"`; if verified, upgrade status to `"verified"`
  instead.
- **New functions for Tomba/Prospeo fallback**: mirror the exact shape of
  `owner_finder.py`'s `_opencorporates_lookup` — async, httpx, wrapped in
  try/except returning an empty-result sentinel, gated by an env-var API
  key check, rationed via the same `_ration_check_and_increment(counter_key,
  cap, period)` helper already defined there (it's generic enough to reuse
  as-is for a new `"email_finder:tomba_monthly"` / `"email_finder:prospeo_monthly"`
  counter key — no need to duplicate that logic).
- **New env vars for `.env.example`**: `VERIFALIA_API_KEY=`,
  `TOMBA_API_KEY=` + `TOMBA_SECRET_KEY=` (Tomba's API needs both a key and
  secret per their docs), `PROSPEO_API_KEY=` — all `[FREE TIER]`-labeled
  with the *actual* confirmed monthly numbers from Job 1/1c in the comment,
  learning from the Apollo/Hunter mislabeling problem found in this session.
- **All HTTP-only, all Render-safe** — no new dependency beyond `httpx`
  (already pinned 0.27.2) is needed for any of Verifalia/Tomba/Prospeo; all
  three are plain REST/JSON.
- **Not recommended for `app/skills/`**: any TCPA/DNC work belongs in a
  *separate*, explicitly-scoped follow-up (flagged below), not bundled into
  this email-pipeline change — different risk profile, different
  reviewer attention needed (compliance-sensitive, not just an enrichment
  quality improvement).

---

## Key files referenced (absolute paths)

- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\owner_finder.py` (existing registry-first owner-name pipeline; ration-check helper reusable for new email-finder quotas)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\light_enrich.py` (`enrich_lead_lite`, `_verify_mx`, `_guess_emails_ranked` — insertion points for Job 1c/ranked-pipeline changes)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\lead_enrichment.py` (older free-only enrichment pass, `enrich_with_linkedin`)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\apollo_enrichment.py`, `app\skills\apollo_free_scraper.py`, `app\skills\apollo_scraper\scraper.py` (Apollo REST + browser-based variants; browser ones inert on Render, confirmed again this session)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\lead_validator.py` (`validate_email_address`, `validate_phone_number` — existing format-only validation, distinct from the HTTP-deliverability gap in Job 1c)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\outbound_dialer.py` (`trigger_retell_call` — no DNC/consent gate exists before this call, Job 2b)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\worker.py` (`MAX_CALLS_PER_DAY` cap at lines 83/184/723/812/876 — the only guardrail on the call lane today)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\core\compliance.py` (thorough email-compliance classes; zero phone/TCPA/DNC equivalent — the gap named in Job 2b)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\smart_scraper.py` (lines 75-113: extraction schema already distinguishes `is_verified_mobile` conceptually, but this file is an ad-hoc AI tool, not on the scheduled hunt path, and nothing downstream enforces the distinction)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\.env.example` (APOLLO_API_KEY/HUNTER_API_KEY labeled "[FREE TIER]" — confirmed inaccurate per Job 1; both require a paid seat for API access)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\vault\20-ops\sessions\2026-07-04-lead-engine-research.md` (prior session: owner-NAME sourcing, this session's direct predecessor)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\vault\20-ops\sessions\2026-07-04-owner-name-engine.md` (prior session: what got built/reviewed/tested for owner-finder.py)

## Follow-ups

- [ ] Sign up for Verifalia + Tomba.io + Prospeo free tiers, smoke-test each
      against 5 known leads before wiring into `light_enrich.py` for real.
- [ ] Correct `.env.example`'s "[FREE TIER]" labels on `APOLLO_API_KEY` /
      `HUNTER_API_KEY` to note both require a paid seat for API access (not
      a code change, just an accurate comment).
- [ ] **Separate, compliance-focused follow-up** (do not bundle with the
      email pipeline change): add a DNC-scrub gate + phone-consent tracking
      ahead of `outbound_dialer.py :: trigger_retell_call()`, mirroring the
      opt-out table pattern already in `app/core/compliance.py` but for
      phone/TCPA instead of email. This is the single highest-severity gap
      surfaced by this session (uncapped per-call statutory damages) and
      deserves its own scoped review, not a quiet add-on.
- [ ] Confirm with Mark whether Apollo/Hunter paid seats are worth budgeting
      for, now that this session has confirmed neither has a usable free
      API tier — if not, consider whether to keep carrying the dead code
      paths or document them as "will only activate if paid."
- [ ] Revisit the GitHub-commit-search email signal (Job 3) as a small
      addition to `_guess_emails_ranked`'s fallback chain for
      technical/trades owner-operators with public GitHub activity.
