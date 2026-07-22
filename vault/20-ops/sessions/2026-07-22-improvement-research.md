---
name: session-2026-07-22-improvement-research
description: Deep-research pass — memory-efficiency audit (512MB reclaim) + a three-things improvement roadmap, after reading the whole vault
type: session
created: 2026-07-22
status: active
---

# Improvement research — memory audit + "work even better" roadmap (2026-07-22)

Continues [[session-2026-07-22-handoff]]. Owner ask: read the whole Obsidian
vault to understand what OROVA is, then find improvements **that don't blow the
512MB Render free tier**. This note is the research output.

## What I read
The full brain (`10-brain/*`), all recent ADRs (`0006`–`0010`), the reliability
sessions (`0720`, `0721`), and the `hermesclaw-orova` playbook. Grounding for
everything below is code, not the (partly stale — `active-context`/`progress`
are ~07-10/13) prose.

## The core insight
**Most of the 512MB is spent running code the live SDR lanes never execute.**
`worker.py`'s lanes import a lean set (`lead_gen_v3`, `light_enrich`,
`contact_waterfall`, `agentmail_skill`, `outbound_dialer`, `lead_validator`,
`email_sequence_skill`, `ceo_brain`). The memory-heavy passengers ride in
through **dead dependencies** and the **bypassed AI-OS planner**. So the biggest
"space" wins *reduce* RAM with ~zero behavior change — and they buy the headroom
the OOM-blocked work (batch reenrich, enrichment consolidation) needs.

---

## Part A — Memory-efficiency audit

### A1. Dead/heavy dependency reclaim — SHIPPING as PR #99
Removed 5 deps the live path never uses (all grep-verified, no test imports):

| Dep | Cost | Verdict |
|---|---|---|
| `spacy` + `en_core_web_sm` | code's own comment: **~100-150MB RAM** + thinc/blis/numpy | 6th-fallback owner NER, superseded by the ADR-0009 waterfall; low-precision PERSON extraction is the anti-pattern [[0008-lead-intelligence-provenance]]/[[0009-persistent-decision-maker-waterfall]] moved away from. `light_enrich` already degrades via `except ImportError`. |
| `python-jobspy` | pulls **pandas+numpy** | job-postings scanner reachable only via the bypassed planner; import now guarded. |
| `timezonefinder` | ~40-50MB polygons | used only by the never-called coords path; state lookup (US-only ICP) replaces it. |
| `sqlmodel` | drags SQLAlchemy | zero imports (`models/core.py` deleted). |
| `yagmail` | dead weight | zero imports (AgentMail is the mailer). |

Estimated **~150-250MB RAM** + a large image/cold-start cut. Dockerfile
`spacy download` step removed too.

### A2. Deferred memory items (ranked)
1. **`firecrawl-py`** — key-gated ($0, never keyed); removable once `lead_finder`'s
   `except` breadth is confirmed. Small follow-up PR.
2. **Enrichment consolidation** ([[0010-consolidation-before-features]] §3): merge
   `light_enrich` (1,517 LOC) + `lead_gen_v3` (1,236) → one pass. Kills the
   double-crawl → **halves crawl RAM/latency/quota**. *This is the real fix for the
   batch-reenrich OOM* (handoff §4). A1 buys the headroom to do it safely.
3. **AI-OS excision** (handoff §6): the planner/soul/personas/self_* tree (~5,000
   LOC) is imported but bypassed by `nova_chat`, and it's what drags
   `job_signal_hunter`/`browser_ops`/`seo_audit`/`lead_finder` (Playwright — not
   even installed → dead on Render) into the process. **Staged** removal only
   (rewire `ceo_brain` auto-execute → direct hunt; drop agentic endpoints; remove
   dashboard observability routes; then delete). Big-bang breaks the pipeline+deploy.
4. **Container RAM hygiene**: set `MALLOC_ARENA_MAX=2` (+ modest `gc` tuning) — a
   cheap glibc-arena win for Python web apps on small tiers; measure with the
   existing `psutil` health metric before/after.

---

## Part B — "Work even better" roadmap (the three-things rule)

Filtered to **data quality / conversion / operational reliability**, driven by
production evidence not design discussion. Most of this is already sanctioned in
the ADRs — the value here is sequencing it behind the memory headroom above.

### The honest headline
The single highest-leverage improvement is **not code** — it's the **first real
send** (owner emails West Coast Exotic Cars: Eric Curran, verified phone + direct
email, score 100; handoff §3.1). Zero campaign outcomes exist, so the learning
loop, funnel math, and per-source confidence recalibration are all optimizing
against nothing. **Outcome data > any further optimization** (three-things rule).
Everything below prepares for volume that doesn't exist yet — real, but secondary.

### B1. Data quality (code-actionable now)
- **Evidence ledger for email/phone/title** ([[0010-consolidation-before-features]] §4)
  — extend the ADR-0009 owner ledger to every contact field (per-field arrays,
  upgrade-only, confidence from max+agreement). *Extension-first: extend the ledger,
  don't add a "trust layer."*
- **Waterfall stages** ([[0009-persistent-decision-maker-waterfall]] next-steps):
  append public-LinkedIn (`site:linkedin.com/in` via DDG) + FB/IG-bio sources; the
  chain is built to append. More decision-maker coverage, $0.
- **Low-confidence re-entry loop** (Clay's re-waterfall): owner_conf < 60 loops
  back through remaining strategies before scoring.

### B2. Conversion (mostly owner/env-gated — confirm before building)
- **Booking link**: if `CALENDLY_LINK`/`CAL_COM_EVENT_SLUG` is unset, a HOT reply
  queues a booking-link reply with **no link** — the funnel's single most important
  message silently degrades. Confirm it's set; if not, that's the top conversion fix.
- **Deliverability**: no sending domain + SPF/DKIM → cold email lands in spam
  (biggest deliverability lever). Owner needs the domain; code can add SPF/DKIM +
  mail-tester checks on first send.
- **CAN-SPAM**: set `BUSINESS_POSTAL_ADDRESS` (compliance + deliverability).

### B3. Operational reliability (code-actionable now)
- **Event-log KPI ladder** ([[0007-prospect-event-log]] + [[0010-consolidation-before-features]] §5):
  emit `reply_received`/`meeting_booked` events; a funnel-metrics endpoint over
  evidence→deliverability→replies→meetings. Makes the SDR **measurable** and is the
  precondition for the learning loop to ever be real.
- **Stage-tagged observability** (§6): `[STAGE:hunt|enrich|score|gate|send|reply]`
  log lines + `/api/pipeline/health` last-N failures per stage.
- **AI capacity**: Groq+Gemini free tiers 429 together; OpenRouter tier-3 restored
  (PR #97). Backoff/queue tuning helps, but this is fundamentally a capacity choice.

---

## Part C — Web-sourced improvements (2026 best practice)
Fresh external research this session. Grouped by NEW technique vs VALIDATES the
existing direction.

### Memory (NEW — highest-value, directly fixes the OOM)
- **jemalloc** instead of glibc malloc. A 2026 async-FastAPI case study measured RSS
  creep drop **1.25 → 0.12 MB/hr (~10×)** from the allocator swap alone — freed
  crawl/BeautifulSoup memory returns to the OS instead of sitting in glibc arenas.
  This is the direct fix for the batch-reenrich OOM (handoff §4).
  - Cheap first step (no new dep): `ENV MALLOC_ARENA_MAX=2` in the Dockerfile.
  - Full fix: `apt-get install -y libjemalloc2` +
    `ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2` +
    `ENV MALLOC_CONF=background_thread:true,dirty_decay_ms:1000,muzzy_decay_ms:1000`.
  - Measure with the existing `psutil` health metric before/after.

### Deliverability / conversion (NEW, mostly code-actionable)
2026 priority order: (1) warmed inbox → (2) clean DNS → (3) IPs → (4) list hygiene
→ (5) content → (6) word avoidance. "Don't start at 6 before 1-4." Maps to OROVA:
- **SPF + DKIM + DMARC, all three, aligned to the From domain** (2-of-3 no longer
  passes; DMARC ≥ p=none). Non-compliant senders: 22-34% to spam vs 89% inbox.
  Owner: set up on the sending domain (getorova.com).
- **RFC 8058 one-click List-Unsubscribe header** — now required by Gmail/Yahoo/Apple.
  Code: add `List-Unsubscribe` + `List-Unsubscribe-Post` headers in the AgentMail
  send path (the vault has a CAN-SPAM footer, not the one-click header).
- **Warmup ramp, not a flat cap** — new domains need 3-4 wks (6 if <90 days): 5-10/day
  ramping +3-5/day to 30-50/day. Code: make Nova's daily send cap follow a warmup
  schedule for the first month on a new domain.
- **Deliverability linter** in the composer/approval gate: plain text, 0 attachments,
  0-1 links, subject <50 chars, no all-caps, one CTA, plain-text opt-out — validate
  outgoing mail before send. Keep complaints <0.3%, bounces <2%.

### Outreach quality (NEW)
- **Signal-based outreach replies at 5-18% vs 1-3% generic.** Signals = leadership
  change, hiring, expansion, tech adoption. Extend the evidence ledger with a
  `signals` field (a newly-hired GM the registry waterfall already surfaces IS a
  leadership-change signal) and lead the email with it. Biggest reply-rate lever.
- **AI-template detection**: token-swap templates get spam-flagged even when legit.
  OROVA's bab/pas/aida + `{first_name}` swap is exactly the pattern filters catch —
  use the dossier/decision-maker evidence for a genuine first line.

### Validates the existing direction (keep going)
- Waterfall enrichment 85-95% coverage vs 40-70% single-source → ADR-0008/0009 is the
  2026-correct architecture.
- Re-verify every 90 days / before any 60+ day-cold segment → the `last_checked` +
  scheduled-reenrich design (ADR-0010 §4) is exactly right.
- Human-review-before-send → the approval gate is 2026 best practice, not a limitation.

Sources: PowerDMARC/RedSift (sender rules), Instantly (deliverability + enrichment),
Autobound/Apollo/Mailforge (AI cold email + spam filters), BetterUp eng (jemalloc).

---

## Recommended sequence
1. ✅ **PR #99** (5 heavy deps) — merged + deployed (build 362627c, memory ok).
2. Owner: **first send** + booking link + SPF/DKIM/DMARC + rotate leaked secrets (handoff §3).
3. ✅ **PR #100** jemalloc + `firecrawl-py` removal — merged + deployed (build 6ab469f, memory ok).
4. **Enrichment consolidation** (A2.2 / ADR-0010 §3) — durable memory + data-quality win. **← next code session** (traced in the Appendix).
5. **Event-log KPI ladder** (B3) — measurability before more optimization.
6. Once the first send + domain exist: List-Unsubscribe header, warmup-ramp send cap, composer linter, signal-based personalization (Part C).

Deferred (owner-gated, staged, not now): AI-OS excision (A2.3).

## Appendix — Enrichment consolidation (ADR-0010 §3): traced 2026-07-22, ready for a focused session
Confirmed the double-crawl (up to **3 crawls/lead**):
1. `find_leads` → `find_leads_v3` (`lead_gen_v3.py:1147`) calls `enrich_lead_4step`
   → crawls the site.
2. worker hunt lane (`worker.py:327` find_leads → `:367` `enrich_lead_lite`) crawls
   the SAME site again (`light_enrich`, 1,517 LOC — the MX-gate/Verifalia/
   `email_status`/confidence pass).
3. `resolve_decision_maker` (`worker.py:376`, contact_waterfall) crawls team/about
   pages again.

**Safe approach = MERGE, not skip.** A naive "skip `enrich_lead_lite` if fields
present" guard would REGRESS data quality — it owns the MX gate, Verifalia,
`email_status` (verified/found/guessed) and `contact_confidence` that ADR-0008 built;
`enrich_lead_4step` does not. Fold both into a single crawl-once pass that preserves
every ADR-0008/0009 signal, then have the hunt lane call the one pass. Reuse the
shared httpx client (`lead_gen_v3.py:19`) and share the fetched page across
owner/email/phone/waterfall extraction so each site is fetched once.

**Why it's a dedicated session, not a tail-of-session hack:** revenue-pipeline core
(~2,750 LOC, two modules); a mistake reintroduces the fabrication/guessed-email
regressions ADR-0008 fixed. Do it with full context and the suite green at each seam.

## Linked
- [[session-2026-07-22-handoff]] · [[0010-consolidation-before-features]] · [[0009-persistent-decision-maker-waterfall]] · [[0008-lead-intelligence-provenance]] · [[0007-prospect-event-log]] · [[profitability-plan]] · [[active-context]]
