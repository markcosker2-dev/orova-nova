---
name: lead-engine-research
description: Audit of current lead engine + free owner-name source research
type: session
created: 2026-07-04
status: active
---

# Session: Lead Engine Research (2026-07-04)

**Scope:** Read-only research/planning session. No code changed. Goal: figure out why owner-name
yield is low today and design a free, HTTP-only, "Apollo-like" owner-name-first pipeline for
Nova's lead engine.

---

## Job 1 — Audit of the CURRENT lead engine

### 1.1 Call graph (what's actually wired up in production)

```
app/worker.py :: run_lead_hunt_slow_lane()          [runs every 60 min, per client]
  │
  ├─ imports: from app.skills.lead_gen_v3 import find_leads      (worker.py:20)
  │            find_leads = find_leads_v3                         (lead_gen_v3.py:1049)
  │
  ├─ find_leads(count, query)  ── worker.py:298
  │   └─ find_leads_v3()  (app/skills/lead_gen_v3.py:935)
  │        ├─ _source_google_maps(query, count*2)   — unauthenticated HTML scrape of
  │        │    https://www.google.com/maps/search/<query> (mobile UA), regex-parses
  │        │    window.APP_INITIALIZATION_STATE JSON blob                (lead_gen_v3.py:850)
  │        ├─ _source_duckduckgo(query, count*2)    — DDGS().text() via
  │        │    duckduckgo_search library                              (lead_gen_v3.py:900)
  │        ├─ dedup by domain
  │        └─ enrich_lead_4step(url, business_name)  per unique lead, concurrency=5
  │             (lead_gen_v3.py:728) — 6 parallel strategies merged by priority:
  │             1. _scrape_website()      — homepage + 9 pages from ABOUT_PAGES/CONTACT_PAGES,
  │                                          regex OWNER_PATTERNS, then AI pass via
  │                                          UnifiedAIClient if still missing owner/email
  │             2. _whois_lookup()        — RDAP (rdap.org) domain registrant lookup
  │             3. _state_registry_lookup() — GET to hardcoded STATE_REGISTRY_URLS[state]
  │                                          with ?q=business_name (see 1.3 below — broken)
  │             4. _ddg_owner_verification() — 6 DDGS() site-search query variants
  │             5. _bbb_lookup()          — GET bbb.org/search + regex
  │             6. _google_business_lookup() — DDGS() "<business> owner OR founder..."
  │
  ├─ for each lead: Yelp-slug owner guess (worker.py:322-334, pre-enrichment heuristic)
  │
  ├─ enrich_lead_lite(lead)   ── worker.py:338 → app/skills/light_enrich.py:876
  │     (this is a SEPARATE, more thorough enrichment pass that runs AFTER
  │     lead_gen_v3's own enrich_lead_4step — meaning every lead gets enriched TWICE
  │     by two independently-written pipelines that don't share state)
  │     Steps, in order, each only running if the field is still missing:
  │       1. Yelp page scrape (Firecrawl, if FIRECRAWL_API_KEY set) → phone, real website
  │       2. Website crawl: homepage + auto-discovered about/team/contact links (_fetch_page,
  │          2 UA rotation, Firecrawl fallback) → _extract_emails, _extract_owner_name
  │          (JSON-LD → meta author → DOM adjacency → regex OWNER_PATTERNS → spaCy NER
  │          if en_core_web_sm installed)
  │       3. Hunter.io domain-search (if HUNTER_API_KEY set)
  │       4. Apollo.io mixed_people/api_search (if APOLLO_API_KEY set) — plain HTTPS POST,
  │          NOT the browser scraper; this is Apollo's real (paid-credit) REST API
  │       5. DDG/Bing snippet search + Hawk AI (UnifiedAIClient) JSON parse of snippets
  │       6. Email-guess from name+domain pattern, MX-verified via dnspython
  │       7. LinkedIn: DDG search for a profile URL + scrape public og:title/description
  │          (app/skills/lead_enrichment.py :: enrich_with_linkedin)
  │
  ├─ score_lead() ── app/skills/lead_validator.py:59 (rule-based, company_size/industry always
  │     "unknown" here since worker.py never populates them — score is nearly constant)
  │
  └─ DatabaseManager.asave_lead(lead, ...) → app/core/_lead_repo.py:81
        SQLite `leads` table: business, owner, url, website, email, phone, vertical, status,
        notes, icebreaker, score, client_id, email_status, owner_title, linkedin_url
        Dedup: SELECT-then-INSERT in one transaction + UNIQUE index backstop on
        (lower(email), client_id)
```

**Files that exist but are NOT on this call path** (confirmed via `grep -rn "from app.skills.lead_gen_v2\|from app.skills.lead_finder"` across `app/` — zero hits from worker.py or main.py):
- `app/skills/lead_gen_v2.py` — an earlier, unused version of the same idea (Google Maps + DDG + Yelp slug parsing). Only referenced from `app/core/planner.py`/`pipeline.py` as a tool the AI planner *could* choose to call in an ad-hoc chat turn, not from the scheduled hunt.
- `app/skills/lead_finder.py` — a third, unused version (`find_leads()` here shadows the one worker.py imports from `lead_gen_v3`, but is never imported by worker.py). Wires to Tavily/Firecrawl/SerpAPI paid keys, none configured.
- `app/skills/smart_scraper.py` — ScrapeGraphAI + Groq-direct + Playwright-based Apollo browser scraper. Referenced from `planner.py`/`pipeline.py`/`deep_research.py`/`competitive_intel.py` as an ad-hoc AI tool, never from the scheduled hunt.
- `app/skills/scrapling_scraper.py` — `scrapling` (anti-bot stealth fetcher) based search/extract. Same story — ad-hoc tool only.
- `app/skills/apollo_free_scraper.py` and `app/skills/apollo_scraper/scraper.py` — Playwright/SeleniumBase browser automation of Apollo.io's UI (cookie-based login, "500 leads/day", anti-detection). Not imported by worker.py at all.
- `app/skills/crawl_skill.py` — `crawl4ai`-based "elite_scrape". Ad-hoc tool only.

### 1.2 Exactly where/how the owner name is obtained today

Two independent regex+heuristic engines run back-to-back on every lead (`enrich_lead_4step` inside `lead_gen_v3.py`, then `enrich_lead_lite` inside `light_enrich.py`), each trying ~5-8 strategies. All of them ultimately reduce to one of:
1. **Regex pattern-matching** free text (page HTML/DDG snippets) against `OWNER_PATTERNS` like `(?:owner|ceo|founder|president|...)[:\s,\-–]+([A-Za-z...]+)` — this only fires if the business's own website (or a snippet) happens to contain a sentence in that exact shape.
2. **AI extraction** (`UnifiedAIClient.chat()`) on the same scraped text, when regex comes up empty — but per `vault/10-brain/active-context.md` (2026-07-03) and confirmed by reading `.env`: **Groq returns 401, OpenRouter returns 401 ("User not found"), Google/Gemini key is empty.** `UnifiedAIClient.chat()` (app/core/ai_client.py:161) falls through all three tiers and returns `SimpleNamespace(content="[!!] No AI providers available.")` — every AI-assisted extraction step in both files is currently a no-op.
3. **RDAP/WHOIS registrant name** — often privacy-shielded (GoDaddy/Namecheap privacy proxies return "Privacy Protect LLC" style names, not the real owner) — the code has no filter for privacy-proxy registrant names, so it can insert wrong/junk names.
4. **Apollo.io REST API** (`light_enrich.py` Step 4) and **Hunter.io** (Step 3) — both real, working, plain-HTTPS APIs, but gated behind `APOLLO_API_KEY`/`HUNTER_API_KEY` which are **not set** in `.env` (only Groq/OpenRouter/empty-Google are populated).
5. **Yelp-slug guess** (`worker.py:322-334) — treats the Yelp URL slug's words as a person's name (e.g. `yelp.com/biz/casey-martin` → "Casey Martin"), which is usually the *business* name, not a person, and only "works" by coincidence for sole proprietors who name their business after themselves.

### 1.3 Concrete reasons owner-name yield is low

1. **No structured owner data source is used at all.** Every strategy is either free-text regex against uncontrolled HTML/snippets, or an AI model that is currently dead. There is no call anywhere in the current pipeline to OpenCorporates, any Secretary of State registry API, or any other structured public record that *by law* contains an owner/officer/agent name.
2. **`_state_registry_lookup()` (lead_gen_v3.py:461) is effectively non-functional as written.** It does `client.get(STATE_REGISTRY_URLS[state], params={"q": business_name})` against **HTML web pages meant for humans** (e.g. `https://bizfile.sos.ca.gov/api/businesssearch`, `https://ccfs.sos.wa.gov/api/BusinessSearch`) — these are not real query-string-driven GET APIs; CA's real portal requires a subscription-key header via `calicodev.sos.ca.gov`, and WA's real search is a different endpoint (`sos.wa.gov/corps/search_results.aspx`) with different params. The current code's regex (`Agent[:\s]+([A-Z][a-z]+...)`, `EMAIL_RE.search(text)`) is very unlikely to ever match live HTML from these portals — this strategy almost certainly returns empty every time in production, silently (all exceptions are swallowed to `logger.debug`).
3. **The SMB owner-name premise itself is weak for the regex/scrape approach**: most premium/luxury West-Coast SMB sites (per the CLAUDE.md ICP — remodeling, auto, aviation, real estate) intentionally present a *brand*, not a *founder bio*, on their public site. `/about` and `/team` pages are often missing, gated, or written in marketing copy with no name at all — this is stated directly in the task brief and confirmed by the code's own heavy reliance on 6-8 fallback strategies (a sign the maintainers already found the direct-scrape hit rate too low and kept bolting on more fallbacks rather than switching sources).
4. **DDG-based strategies (4 of the ~13 total strategies across both files) carry real block/ToS risk** (see Job 2) and are rate-limit fragile — `duckduckgo_search`'s DDGS().text() and the raw `html.duckduckgo.com/html/` scrape are both liable to return empty/403 under any real request volume, which silently degrades those strategies to no-ops too.
5. **Real paid-enrichment fallbacks exist in the code (Apollo REST API, Hunter.io) but their keys are not configured** — so the two enrichment steps most likely to reliably return a real person's name+title (light_enrich.py Steps 3-4) never fire.
6. **Duplicate, uncoordinated enrichment work**: `find_leads_v3()` already runs a 6-strategy `enrich_lead_4step()` per lead before `worker.py` calls `enrich_lead_lite()` again — meaning every lead is scraped/searched roughly 2x with different regex sets and no shared cache, doubling latency and external-request volume for no yield gain (neither pass shares its findings with the other beyond the final `lead["owner"]` dict key).
7. **No jurisdiction/state signal reaches the registry lookup.** `_state_registry_lookup(business_name)` is called with no `location`/state argument from `enrich_lead_4step` (lead_gen_v3.py:740), so it falls back to guessing CA/TX/FL/NY in sequence — even if a real API existed at those URLs, it would frequently query the wrong state for a lead that's actually in WA or OR.

### 1.4 External dependencies inventory

| Library / Service | Used by | Browser needed? | Installed on Render (per `requirements.txt`)? |
|---|---|---|---|
| `httpx` 0.27.2 | all HTTP calls | No | Yes (pinned, must stay 0.27.2) |
| `duckduckgo_search` (DDGS) | lead_gen_v3, lead_gen_v2, lead_finder, light_enrich | No | Yes |
| `beautifulsoup4` | all scraping | No | Yes |
| `phonenumbers`, `email_validator`, `dnspython` | validation/MX-check | No | Yes |
| `spacy` (+ en_core_web_sm) | light_enrich owner NER fallback | No | Yes, but model download not guaranteed at build time |
| RDAP (rdap.org), api.whois.vu | lead_gen_v3 WHOIS strategy | No | N/A (public HTTP endpoint, no lib) |
| Google Maps (unauthenticated HTML scrape) | lead_gen_v3, lead_gen_v2 `_source_google_maps` | No (fragile — scrapes internal JS state blob) | N/A |
| BBB.org (unauthenticated HTML scrape) | lead_gen_v3, lead_finder | No | N/A |
| `google-generativeai` (Gemini) | UnifiedAIClient tier 2 | No | Yes, but key currently empty |
| `openai` SDK (→ Groq / OpenRouter base_urls) | UnifiedAIClient tiers 1 & 3 | No | Yes, but both keys return 401 |
| Apollo.io REST `mixed_people/api_search` | light_enrich Step 4 | No | Yes (httpx), but `APOLLO_API_KEY` unset |
| Hunter.io `domain-search` | light_enrich Step 3 | No | Yes (httpx), but `HUNTER_API_KEY` unset |
| Tavily, Firecrawl, SerpAPI | lead_finder.py, light_enrich Yelp scrape | No | Yes (httpx) but keys mostly unset (Firecrawl only, used for Yelp bounce) |
| `scrapegraphai` | smart_scraper.py | **Yes** (Playwright config) | **Not in requirements.txt** — import fails, falls back to regex |
| `scrapling` | scrapling_scraper.py | **Yes** (StealthyFetcher) | **Only in requirements-mega.txt** (not installed on Render) — falls back to httpx |
| `playwright` | apollo_scraper/scraper.py, smart_scraper fallback | **Yes** | **Not in requirements.txt** (only requirements-mega.txt) — dead on Render |
| `seleniumbase` | apollo_free_scraper.py | **Yes** | **Not in requirements.txt** — dead on Render |
| `crawl4ai` | crawl_skill.py | **Yes** (via Playwright under the hood) | **Not in requirements.txt** — import guarded, disabled |
| `firecrawl-py` | multiple, Yelp bounce-page resolution | No (Firecrawl runs the browser on their end) | Yes, gated by `FIRECRAWL_API_KEY` |

**Bottom line on Job 1:** the pipeline that's actually live (`lead_gen_v3.py` + `light_enrich.py` via `worker.py`) is 100% HTTP-only already (good — meets the Render constraint by accident, not by design) but gets owner names almost exclusively from unstructured text pattern-matching plus a currently-dead AI layer. Every browser-dependent file in the repo (smart_scraper, scrapling_scraper, apollo_free_scraper, apollo_scraper/, crawl_skill) is inert on Render today because their required packages aren't installed, and Apollo/Hunter's real paid-tier fallbacks are wired correctly in code but unconfigured. There is currently **zero use of any structured public-records source** (OpenCorporates, any SoS registry) anywhere in the codebase.

---

## Job 2 — Free owner-name sources, ranked

### Ranking summary (owner-name yield × ease of integration × free)

| Rank | Source | Owner-yield | Integration ease | Free? | Verdict |
|---|---|---|---|---|---|
| 1 | **CA Statement of Information (bizfileOnline search)** | High for CA-registered entities | Medium (HTML search UI, needs `calicodev.sos.ca.gov` key for real API tier) | Yes | **Best single source for the ICP** — CA legally requires named officers/members |
| 2 | **OpenCorporates API** | Medium-High (when jurisdiction has officer data) | Easy (clean REST + JSON) | Yes, but tightly capped | Best cross-state normalizer, use as secondary/cross-check |
| 3 | **WA Secretary of State Corporations Search API** | Medium (agent name always; "governor" i.e. officer name often, but address suppressed since 2017) | Easy (documented query-string API, no key) | Yes | Good for WA leg of the ICP |
| 4 | **Oregon Business Registry search** | Medium (registered agent + associated names) | Medium (no documented JSON API — HTML search only) | Yes | Usable via structured HTML parse, not a real API |
| 5 | **SerpAPI free plan** | Depends entirely on what's indexed (LinkedIn/BBB/news mentions) | Easy (clean JSON) | Yes, but small (250/mo as of the June-2026 pricing page) | Good fallback for high-value leads only — ration the quota |
| 6 | **DuckDuckGo HTML endpoint (current approach)** | Low-Medium, and now the ONLY zero-signup SERP path left | Trivial (already implemented) | Yes | ToS-hostile and increasingly blocked — keep as last-resort fallback only, never primary |
| — | **Bing Web Search API** | N/A | N/A | N/A | **Dead** — fully retired Aug 11, 2025, do not use or plan around it |
| — | **Google Programmable Search (Custom Search JSON API)** | N/A | N/A | N/A | **Closed to new customers** — cannot be provisioned fresh for this project |
| — | **Brave Search API** | N/A | N/A | No (as of Feb 2026) | Free tier killed; now credit-based with mandatory card — excluded per $0 constraint |
| — | **County assessor / DBA-FBN filings** | Potentially high (DBA filings name the actual person) | Hard (fragmented per-county, no statewide free API; many require in-person/mail requests) | Yes, but not automatable at scale | Note only — not viable as an automated HTTP source today |
| — | **Google Places "owner responded" reviews** | N/A | N/A | N/A | **Not a usable source** — owner-reply data belongs to the Google Business Profile API, which requires the *business's own* OAuth consent; the public Places API never exposes it |

### Source-by-source detail

**1. OpenCorporates API**
- Base URL: `https://api.opencorporates.com/v0.4/` (e.g. `.../companies/search`, `.../companies/:jurisdiction_code/:company_number`, `.../officers/search`)
- Auth: **API key required** even for free/open-data use (`api_token` query param). Free keys are issued for open-data/non-commercial projects on request.
- Free-tier limits (confirmed): **200 requests/month, 50 requests/day**. Exceeding the quota returns **HTTP 403**.
- Officer/director fields returned by `/officers/:id` (or embedded in a full `/companies/:jurisdiction/:number` record): full name, OpenCorporates officer ID/URL, position/title (director, secretary, CEO, agent, etc.), start/end dates, address (when available), DOB (UK-heavy, rarely for US).
- **Important integration note**: `/companies/search` does **not** return officers inline — you must do a 2-step call (search → then fetch the specific company record or hit `/officers/search`), which burns 2x the daily quota per lead.
- US/West-Coast coverage: covers CA (California SOS registry, register #41) and other US states, but per OpenCorporates' own blog ("Why is it so hard to find US company data?", 2025), **US state registry data varies wildly in officer-name completeness** — some states (WA, CO, IA, TX) are praised as relatively open; CA's underlying registry itself is name-rich (see #2 below) so OpenCorporates' CA mirror should inherit that. No official statement found confirming OR coverage depth.
- Plain HTTP: yes, clean JSON REST API, no browser needed.
- ToS/legal posture: this is literally an open-data project (same license as the rest of OpenCorporates) — safe to automate within the stated rate limit.

**2. US Secretary-of-State business registries (CA / WA / OR)**
- **California**: The **Statement of Information** that every CA corporation and LLC must file is a public record and, critically, **required by law to name real people** — for corporations: CEO, Secretary, and CFO by name+address; for LLCs: at least one member or manager by name+address. Free to search at `bizfileonline.sos.ca.gov`. This is the strongest single lever available for the ICP since CLAUDE.md's target verticals (remodeling, auto, aviation, real estate) skew toward CA-registered LLCs/corps.
  - Real programmatic access exists via **`calicodev.sos.ca.gov`** (the CALICO developer portal) — requires free account registration + subscription key sent as an HTTP header; returns JSON (confirmed: "details for the top 150 entities... in JSON format"); products include Business Entity Search and Document Retrieval. Rate limits and whether the entity-search product itself carries a $0 tier were **not confirmed** from public docs (the portal's pricing page requires sign-in) — treat as "needs a signup pass to confirm cost," not assume-free.
  - Fallback if CALICO isn't free: the public `bizfileonline.sos.ca.gov/search` UI itself is free and unauthenticated but is a rendered web app, not a query-string GET API — would need to be treated as a scrape target (plain HTTP, likely calls an internal JSON XHR endpoint worth reverse-engineering via a one-time browser inspection, separate from this research pass).
  - Limitation: LLC filings are only biennial, so data can be up to ~24 months stale if an owner changed and didn't refile.
- **Washington**: Real, documented, keyless query-string API. Base: `https://www.sos.wa.gov/corps/search_results.aspx` (list search) with params `name`, `name_type` (`starts_with`/`contains`/`ends_with`), `criteria`, `start`; append `&format=json` (JSONP) or `&format=xml`. A separate detail lookup takes `ubi` (the entity's UBI number) + `format`. **No API key needed.** Returns registered-agent name always; "governor" (officer/manager) names were available but **addresses for governing persons were suppressed as of Jan 19, 2017** for privacy — so expect name-only, not name+address, for officers. Max 20 results/query (paginate via `start`). Plain HTTP/JSON, no browser.
- **Oregon**: Free public search at `secure.sos.state.or.us/cbrmanager/` — confirmed to expose registered-agent details and entity status at no cost. **No documented REST/JSON API was found** (unlike WA) — this is an HTML search form, so integration means structured HTML scraping of a government page (plain HTTP, no browser, but more brittle than WA's real API and needs its own parser).

**3. Targeted SERP for owner names (non-LinkedIn-scraping)**
- **DuckDuckGo HTML endpoint** (`html.duckduckgo.com/html/?q=...`) — what the current code already uses. Confirmed: **DuckDuckGo's ToS prohibits automated/non-personal use and it actively fights scrapers**, returning 202/403 once request patterns look automated; unofficial guidance suggests staying well under ~30 req/min/IP with randomized delays, but there's no official free quota — it's tolerated-until-blocked, not a supported API. Legal/ToS posture: **not safe to rely on as a primary strategy** — treat as an at-your-own-risk fallback only, same conclusion the existing code implicitly reached by stacking 4+ different DDG query variants (a symptom of low per-query reliability).
- **Bing Web Search API** — **fully retired August 11, 2025** (all tiers, including free F0/F1). Not usable at all, paid or free. Any residual code path assuming Bing availability (there is none currently) should not be added.
- **SerpAPI free plan** — most recent confirmed number (SerpAPI's own pricing page, reviewed mid-2026): **250 searches/month, 50/hour throughput** on the $0 plan (older reports of "100/month" appear stale). Requires signup + API key, clean JSON, plain HTTP, no browser, and — since it's a real Google-SERP proxy — a much higher-quality/less-blocked result set than raw DDG scraping. Given the small monthly cap, this is best reserved for **only the highest-scoring leads that still lack an owner name after free-registry lookups**, not as a bulk-search tier.
- **Google Programmable Search (Custom Search JSON API)** — confirmed **100 free queries/day** historically, but the API is **now closed to new customers** (existing customers only, until final shutdown Jan 1, 2027) — cannot be provisioned for this project since it's a fresh build. Exclude from the design.
- **Brave Search API** — had a genuine free tier (2,000-5,000 queries/month) as recently as Aug 2025, but **Brave killed the free tier for new signups in Feb 2026** — now requires a credit card and bills after ~1,000 queries of starter credit. Fails the "$0, free tiers only" constraint for a new integration — exclude.

**4. Other free HTTP sources**
- **County assessor / property records** — no single national free API; individual counties (e.g. Maricopa AZ) expose their own JSON APIs, but coverage is a patchwork with no CA/WA/OR-specific free aggregator found. Not viable as an automatable source today; note for a future paid-fallback slot (ATTOM/CoreLogic), out of scope per the task's constraints.
- **DBA / Fictitious Business Name (FBN) filings** — legally public and *does* name the real individual behind a business (this is often the single most direct signal for a sole-proprietor SMB), but filed at the **county** level in California with no statewide free API — some counties (LA, Sonoma, SLO) have online self-service search portals, others require in-person or mail requests. Too fragmented to automate reliably across "West Coast" as a whole; worth a narrow follow-up if the design wants to special-case LA County specifically (its portal is online and free), but not a general-purpose HTTP source today.
- **Google Places API "owner responded"** — investigated and ruled out: owner-reply data on reviews is only reachable through the **Google Business Profile API**, which is scoped to the business's own authenticated account (their OAuth), not something a third party can query for an arbitrary business via the public Places API. Not usable.
- **data.gov** — the catalog itself only indexes *metadata about* datasets (titles/descriptions/URLs), it does not host queryable business-owner data directly; not a usable source in its own right.

---

## Job 3 — Proposed owner-name-FIRST pipeline

### Design principle
Flip the current order. Today: scrape website text → regex/AI guess a name buried in prose.
Proposed: **look the business up in a legal registry that is required to name a real person first**,
then only fall back to text-mining when the registry has no hit (new business, sole proprietor with
no LLC, DBA-only, etc). AI extraction becomes an *optional enrichment pass on top of a structured hit*
(e.g., to find the person's title/LinkedIn once you already have their name), not the primary
name-finding mechanism — so the pipeline keeps working even with the LLM key dead, exactly as required.

### Stage diagram

```
STAGE 0 — Discovery (unchanged, already free/HTTP)
  Google Maps HTML scrape + DuckDuckGo business search
      → business name, address/city, phone, candidate URL
      → derive US state from address/city (new: needed for Stage 1 routing)

STAGE 1 — Registry lookup (NEW — primary owner-name source)
  route by detected state:
    CA  → bizfileOnline / CALICO Business Entity Search
            (Statement of Information: CEO/Secretary/CFO names for corps,
             member/manager names for LLCs)
    WA  → sos.wa.gov/corps/search_results.aspx (?format=json)
            (registered agent name always; governor/officer name when present)
    OR  → secure.sos.state.or.us/cbrmanager/ structured HTML parse
            (registered agent name; entity status)
    other/unknown → OpenCorporates /companies/search
                     → then /companies/:jurisdiction/:number for officers
                       (counts against the 50/day, 200/month cap — use sparingly,
                        e.g. only as the cross-state catch-all, not per-lead default)
  OUTPUT if hit: owner_name (from officer/member/manager), owner_title (CEO/Secretary/
                 CFO/Member/Manager — a REAL title, not a regex guess), source="registry",
                 confidence="high" (legally-required filing)
  OUTPUT if miss: fall through to Stage 2

STAGE 2 — Structured-parse website scrape (EXISTING code, kept, de-duplicated)
  Single enrichment pass (merge lead_gen_v3's enrich_lead_4step +
  light_enrich's enrich_lead_lite into ONE call so a lead is only scraped once):
    - homepage + /about + /team + /contact + /leadership (existing ABOUT_PAGES logic)
    - regex OWNER_PATTERNS + JSON-LD/schema.org Person parsing (existing _extract_owner_name)
    - email extraction + MX-verified email guessing (existing, keep as-is)
  OUTPUT if hit: owner_name, source="website_scrape", confidence="medium"
                 (unstructured — could be a bio subject, not necessarily the owner)

STAGE 3 — AI extraction pass (OPTIONAL — only runs if a live key exists)
  UnifiedAIClient.chat() on the same page text already fetched in Stage 2
  (no extra HTTP calls — reuses Stage 2's fetched text)
  Guarded exactly as today: if all 3 providers are dead, this stage no-ops
  and the pipeline still returns whatever Stage 1/2 found.
  OUTPUT if hit: fills gaps only (owner_name if still missing, or owner_title/email)

STAGE 4 — Targeted SERP fallback (RATIONED — only for leads still missing owner_name
                                    AND with a lead_score above a "worth spending quota on"
                                    threshold, e.g. top 20% of the day's batch)
    Primary: SerpAPI free plan (250/mo cap — track spend in SQLite state, stop calling
             once monthly budget is hit, fall through silently)
    Last resort only: DuckDuckGo HTML endpoint (existing _ddg_owner_verification-style
             queries) — kept as the final fallback exactly because it's free and
             already implemented, but explicitly documented as ToS-fragile/no-SLA,
             never the primary path
  OUTPUT if hit: owner_name, source="serp", confidence="low-medium" — same email/phone
                 extraction regex already in the codebase applies to the snippet text

STAGE 5 — Title/LinkedIn overlay (EXISTING, kept as-is)
  Once owner_name is known (from ANY stage above), run the existing
  enrich_with_linkedin() DDG-search-for-profile-URL + public-og-tag scrape
  to attach owner_title + linkedin_url — this stage doesn't change; it already
  correctly runs AFTER a name is known, not as a name-finding stage itself.

  → save_lead() (app/core/_lead_repo.py, unchanged schema: owner, owner_title,
    email, email_status, phone, linkedin_url, website, url, vertical, score)
```

### Which source feeds which field

| Field | Primary source (Stage) | Fallback source (Stage) |
|---|---|---|
| `owner_name` | CA/WA/OR registry officer or OpenCorporates officer (1) | Website scrape regex/JSON-LD (2) → AI extract (3) → SERP (4) |
| `owner_title` | Registry-stated title, e.g. "CEO"/"Manager"/"Registered Agent" (1) | LinkedIn og:title scrape (5), once name is known |
| `email` | Website scrape (existing MX-verified guess logic) (2) | AI extract (3) → SERP snippet regex (4) |
| `phone` | Existing Google Maps / website tel: link extraction (0/2) | unchanged |
| `linkedin_url` | Existing DDG-search-for-profile (5) | unchanged |
| `website`/`url` | Existing Stage 0 discovery | unchanged |

### Fallback order (name resolution only)
1. CA Statement-of-Information / WA governor-agent / OR registered-agent (state-routed)
2. OpenCorporates officer lookup (cross-state catch-all, quota-limited)
3. Existing website-scrape regex + JSON-LD (already implemented — reuse, don't rewrite)
4. AI extraction on the same scraped text (already implemented, already degrades gracefully — no change needed, just re-ordered to run AFTER registry lookup instead of interleaved with scraping)
5. SerpAPI (quota-rationed to high-score leads only)
6. DuckDuckGo HTML search (last resort, unchanged from today)

### Expected hit-rate improvement (directional, not measured)
Today: owner-name yield depends entirely on (a) the SMB's own site mentioning a name in a
matchable sentence shape, or (b) a currently-dead AI call, or (c) a state-registry strategy
that's calling the wrong URLs and almost certainly returns nothing. For the CLAUDE.md ICP
(CA-heavy luxury SMBs, likely LLCs/corps), Stage 1 alone should convert a meaningful share of
leads that have zero named person anywhere on their website, because CA legally forces a
named CEO/Secretary/CFO or LLC member/manager onto public record regardless of what the
business chooses to publish. This is the single biggest lever in this design — it doesn't
depend on the business's marketing choices or on any AI key being alive.

### Caching / rate-limit needs
- **OpenCorporates**: SQLite-backed cache keyed by `(business_name_normalized, state)` with a long TTL (registry data changes rarely) — essential given the 50/day cap; track daily call count in `app/core/database.py`'s existing state table (same pattern as `daily_hunt_counter` in worker.py) and refuse to call once the day's 50 is spent, falling through to Stage 2 instead of failing the lead.
- **CALICO (CA)**: same cache-first approach once actual free-tier limits are confirmed (flagged above as unconfirmed — needs a signup pass before this stage can be finalized).
- **WA/OR**: no key, no published rate limit found — still worth a light cache (same business gets searched once per lead-hunt run at most) purely to cut redundant outbound calls, not because of a quota.
- **SerpAPI**: hard-stop counter against the 250/month cap, persisted in SQLite (same pattern as the existing `MAX_DAILY_COST`/`daily_hunt_counter` guardrails in worker.py) — this is a hard $0-tier ceiling, not a soft preference.
- **DuckDuckGo (existing)**: keep the existing ad-hoc query pattern but consider adding a shared cooldown/backoff if 403s are observed, matching the "block risk" finding in Job 2.

### Where this plugs into existing code
- `app/skills/lead_gen_v3.py :: enrich_lead_4step()` (line 728) is the natural insertion point:
  add a new `_registry_lookup(business_name, state)` async strategy that tries CA → WA → OR
  → OpenCorporates in sequence (Stage 1) and runs it **first**, short-circuiting the rest of
  the existing 6 strategies when it returns a high-confidence hit — the existing 6 strategies
  then become Stages 2-4 exactly as designed above, requiring re-ordering/gating logic rather
  than a rewrite.
- The duplicate-enrichment problem (Job 1, finding 6) should be fixed alongside this: merge
  `light_enrich.py :: enrich_lead_lite()` into the same call so `worker.py:338` no longer runs a
  second, uncoordinated pass — `worker.py` would call one unified `enrich_lead()` entry point.
- `app/core/_lead_repo.py :: save_lead()` schema already has all needed columns
  (`owner`, `owner_title`, `email`, `email_status`, `linkedin_url`) — no schema change required;
  would only need a new `owner_source`/`owner_confidence` column if the team wants that
  provenance surfaced in the dashboard (optional, not required for the pipeline to work).
- New state env-driven keys to add to `.env.example` alongside the existing block:
  `OPENCORPORATES_API_KEY=`, `CALICO_SUBSCRIPTION_KEY=` (pending confirmation it's free),
  `SERPAPI_KEY=` (already referenced by lead_finder.py's unused path, just needs the value).

### Design-inspiration note (Job "Optional")
Ran `sales:account-research` for structural inspiration only (no live data pulled, no OAuth
needed — it just returned its own workflow doc when invoked without a connected CRM/enrichment
backend). Its documented shape is: **web search always works standalone → enrichment layer
supercharges it → CRM/output synthesizes into a structured company→person record with
qualification signals** — which maps directly onto the registry-first/scrape-second/AI-optional
layering proposed above. `vpai:vibe-prospecting` and `apollo:prospect` were not invoked since the
account-research pattern already gave the needed structural reference and both are paid-provider
tools we are explicitly not using in this design.

---

## Key files referenced (absolute paths)

- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\worker.py` (run_lead_hunt_slow_lane, lines 252-370ish)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\lead_gen_v3.py` (find_leads_v3, enrich_lead_4step, _state_registry_lookup)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\light_enrich.py` (enrich_lead_lite, Apollo/Hunter REST steps)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\lead_enrichment.py` (enrich_with_linkedin)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\lead_gen_v2.py` / `lead_finder.py` (unused alternates)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\smart_scraper.py` / `scrapling_scraper.py` / `apollo_free_scraper.py` / `apollo_scraper\scraper.py` / `crawl_skill.py` (browser-dependent, inert on Render)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\lead_validator.py` (score_lead)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\core\_lead_repo.py` (leads schema, save_lead)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\core\ai_client.py` (UnifiedAIClient 3-tier fallback, confirmed dead)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\app\skills\lead_scraper\SKILL.md`
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\requirements.txt` / `requirements-mega.txt` (confirms browser libs absent from Render deploy)
- `C:\Users\Mike\OneDrive\Desktop\Cosker\OROVA\vault\10-brain\active-context.md` (independent confirmation of dead LLM keys)

## Follow-ups

- [ ] Confirm whether `calicodev.sos.ca.gov`'s Business Entity Search product has a genuine $0 tier (portal pricing requires sign-in to view) before committing to it as the primary CA source.
- [ ] One-time browser inspection of `bizfileonline.sos.ca.gov/search` to find its internal JSON XHR endpoint, in case it's usable directly without CALICO signup friction.
- [ ] Register a free OpenCorporates API key and smoke-test `/companies/search` + officer fetch against 5 known CA/WA/OR businesses to sanity-check real-world officer-name coverage before building Stage 1.
- [ ] Decide whether to special-case LA County FBN/DBA search (has a free online portal) given it's the single county most aligned with the "luxury West Coast" ICP.
- [ ] When implementing, merge `enrich_lead_4step` and `enrich_lead_lite` into one call to kill the current double-enrichment redundancy (Job 1, finding 6) as part of the same change.
