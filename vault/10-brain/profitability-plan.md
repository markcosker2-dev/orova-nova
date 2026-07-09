---
name: profitability-plan
description: improved go-to-first-client and scale plan
type: brain
created: 2026-07-05
status: active
---

# OROVA Profitability Plan

A numbers-driven path from **zero clients** to a repeatable, profitable agency.
Builds on [[orova-playbook]], [[business-model]], [[active-context]], and
`app/core/business_context.json`. Where this plan disagrees with those files,
**this is the proposed correction** — nothing here is applied to code or to
`business_context.json` automatically; see §6 for the diff Mark reviews.

---

## 1. Honest gap analysis of the current plan

The existing plan (playbook + business_context.json) is directionally sound —
premium ICP, real automation, disciplined approval gates — but has five holes
that would sink it on contact with reality:

1. **No funnel math exists anywhere.** The playbook describes the *steps*
   (email → call → meet → close) but never states how many leads it takes to
   produce one meeting, or how many meetings to produce one client. Without
   this, "hunt more leads" and "improve the pitch" are indistinguishable
   priorities. §2 fixes this.

2. **The ICP is too broad and includes verticals that don't fit the
   motion.** `business_context.json`'s `icp.primary_verticals` lists "private
   aviation and yacht charter" alongside exotic auto and home builders. Web
   research (below) shows private aviation and crewed yacht charter are
   overwhelmingly **not** solo-owner-checks-their-own-inbox businesses —
   decision-makers are family offices, fleet operators, brokerages, and
   executive assistants, a fundamentally different (and much longer, referral-
   driven) sales motion than cold email/cold call to an owner. Cold-outreach-
   to-owner works for **exotic/luxury auto (dealers, detailing, wraps,
   restoration), custom home builders/remodelers, and luxury real estate
   agents** — all classically owner-operated SMBs that already buy Meta ads.
   §2 narrows the ICP; §6 proposes the JSON diff.

3. **Lead quality is still broken in production, not just historically.**
   `vault/30-leads/` (auto-synced from the live DB) currently contains
   `fairmont.com` (a hotel in Hanoi), `oxfordlearnersdictionaries.com`,
   `vocabulary.com`, `customcursor.com` — none of these are West-Coast luxury
   SMBs. This is dated 2026-07-03, before the 2026-07-05 SerpAPI-Maps fix
   described in [[active-context]], so it may already be improving — but it
   means the "9 worker lanes are live" status line is optimistic about output
   quality, not just uptime. The funnel math in §2 is *only* valid once
   discovery is reliably on-ICP; until then, effective lead volume is lower
   than the raw count in the dashboard.

4. **The compliance gap on the call lane is real and currently unpriced
   risk, not just a checklist item.** [[owner-contact-research]] (2026-07-05)
   confirms `app/core/dnc.py` implements an opt-out suppression list but
   **not** a National DNC Registry scrub, and there is no cell-vs-business-line
   classification gate before `trigger_retell_call()`. The B2B exemption that
   makes cold-calling legal here depends entirely on calling the **published
   business line**, not a personal cell — and Nova's phone source (Yelp/
   Google Maps/website) is already, correctly, the business line. That's good
   — but it should be stated as policy, not left implicit, because the day
   someone plugs in a "get the owner's cell" enrichment source, the exemption
   silently stops applying. §5 and §6 make this explicit.

5. **The margin story is real but was never load-tested against an actual
   1/3/10-client cost stack.** "$60-500/mo per client, 75-80% margin" is
   asserted three times across the vault (business-model, playbook, business_
   context.json) but never itemized against live 2026 vendor pricing. §3
   rebuilds it bottom-up and it holds — but two costs the current plan treats
   as free (Make.com, Higgsfield) aren't wired into `.env.example` at all yet,
   meaning they're real future line items, not currently-paid costs. Also:
   **SerpAPI's free 250 searches/month is a hard ceiling shared by lead
   discovery *and* owner-name lookup** — at even modest volume this caps out
   before month-end, which is a volume constraint the funnel math must respect
   (see §2 sizing) and a real near-term paid upgrade (§3).

None of this means the plan is wrong — it means it's **untested against
numbers**, and two of the five gaps (ICP breadth, lead quality) actively waste
the scarce resource (SerpAPI quota, Mark's approval attention) on the wrong
targets.

---

## 2. Go-to-first-client plan

### 2.1 Refined ICP

**Keep:** Luxury/premium, West Coast (CA/OR/WA/NV/AZ), can afford $4-5K/mo +
$2-2.5K ad spend, budget minimum $4K/mo.

**Sharpen to three verticals, ranked by fit for *this specific motion*
(cold email/call reaching an owner who checks their own inbox and already
runs or is ready to run Meta ads):**

| Priority | Vertical | Why it fits this motion | Why it's #1/2/3 |
|---|---|---|---|
| **1** | Exotic/luxury auto — **dealers, detailing/PPF/wrap/tint shops, restoration, storage** | Classic owner-operator SMB; case studies confirm Meta lead ads already work here (tint/ceramic-coating shop targeting Tesla owners; Lexus dealer at $1.17 CPC); decision-maker is one person, reachable by cold email | **Best fit.** Small enough to need a $4-5K agency, big enough to afford it, and the closest thing OROVA has to proof (Meta lead ads for auto is a well-trodden path). |
| **2** | Custom home builders / high-end remodeling | Owner-operator or small partnership; already spends on marketing to fill a project pipeline that's naturally lumpy (perfect fit for "AI qualifies so you only talk to real buyers"); high average project value makes $4-5K/mo trivial | **Strong #2.** Longer sales cycle for the *end client* (a remodel), but the agency sale to the builder is still an owner-to-owner conversation. |
| **3** | Luxury real estate agents (individual top producers, not brokerages) | Solo-operator by definition; personally profits from every extra qualified lead; Meta lead-gen for real estate is an extremely well-understood ad format | **Solid #3.** Narrower budget for some agents ($4K/mo is a bigger bite of a solo agent's P&L than a business with staff), so score for production volume/team size before hunting. |

**Deprioritize (move to "later, different motion" — not "never"):**
Private aviation and yacht charter. Decision-makers here are frequently family
offices, brokerages, fleet operators, or executive assistants — not a single
owner reading a cold email. If OROVA wants these later, the right channel is
referral/network or a long-cycle relationship play, not the fast cold-outreach
funnel this plan is built to optimize. Keep them in `secondary_verticals` for
opportunistic hits, not as hunt targets.

### 2.2 The single sharpest offer/angle

**Lead with Package 1 as the wedge, not Package 2.** The current playbook
pitches P2 ($5K, includes Retell qualification) as if it's the obvious
upsell-from-nothing choice. For a **first client with zero case studies**,
$4K/mo P1 is the lower-friction yes — it's a smaller ask, and Mark can
personally handle the first few leads' worth of "does this even work"
validation before asking a stranger to trust an AI to also field their calls.
**Position P2 as the natural second conversation** once P1 is delivering (or
as a same-call upsell if the prospect asks "can you also handle the leads?").

**The angle stays the demo-sells-itself move** ("you're talking to Nova right
now — that's the product"), but sharpen the hook for the top-priority vertical:

> *"I noticed {dealership/shop} doesn't have decision-maker ads running on
> Meta right now — most of the {luxury auto} shops we look at are leaving
> qualified buyers on the table because Instagram/Facebook lead ads convert
> at half the cost of a walk-in. We build the ads, the AI creatives, and the
> follow-up system — you just show up to booked appointments."*

Specific, falsifiable, and about *their* gap — not a generic luxury pitch.

### 2.3 Funnel math

**Benchmarks used (July 2026 web research, sourced below):**

- Cold email reply rate: **agency-managed campaigns average 5.8%**; 5-15% is
  the realistic band for a well-targeted B2B list; below 3% signals a
  targeting/copy problem.
- Cold email → meeting-booked conversion: **0.4%+ is "good"**; most B2B
  campaigns convert roughly **1 meeting per 100 sends**; well-targeted
  campaigns with strong follow-up reach **1 per 50-70**.
- Cold call dial → meeting-booked: **average 2.5%**, top performers 5-8%.
  Connect rate (someone answers) is **3-10%** of dials; **4.6% of live
  conversations** book a meeting.
- Cold email deal-close rate (email → paying client, no calling layer):
  average is a brutal **0.2%** (~1 per 500 sends); 3.5-4.5% is called "good"
  in 2026 sourcing but that figure is for lead-to-opportunity in well-run
  campaigns, not stranger-to-signed-retainer — treat 0.2-1% as the realistic
  band for **cold-outbound-to-signed-$4K/mo-retainer** specifically, since
  this is a much higher-commitment ask than a typical B2B software trial.
- Meeting → closed-client rate for a **high-touch, human-closed** sale (Mark
  runs the Google Meet personally, per the existing playbook) is not directly
  benchmarked in cold-outreach studies (those measure lead-gen SaaS, not
  service agencies closed by a founder) — using a conservative **20-30%**
  meeting-to-close rate, which matches typical high-ticket-service-agency
  founder-led sales performance where the founder can handle objections live
  (vs. the ~10-15% often cited for junior-rep-run demos).
- Sales cycle for a $4-5K/mo retainer: **2-4 weeks for smaller companies**,
  possibly extending to 4-6 weeks — i.e., expect the gap between first email
  and signed invoice to span **2-6 weeks**, not days.

**The funnel, stacked (per 100 on-ICP leads found):**

```
100 leads found (on-ICP: exotic auto / home builders / luxury RE agent)
  → ~85 have a usable email (rest route straight to call lane per existing
     "guessed emails bounce ~40%" logic in worker.py)
  → 85 cold emails sent
  → ~5 replies (5.8% agency benchmark)
  → of non-repliers, ~40 have a usable phone → cold-call escalation
  → ~2-4 calls connect (3-10% connect rate on 40 dials)
  → ~1-2 meetings booked from calls (2.5% of 40 dials, consistent w/ connect
     math) + ~1 meeting booked directly from an email reply
  → 2-3 meetings booked per 100 leads (combining both channels)
  → Mark runs the Google Meet, closes at ~20-30%
  → 0.5-1 new clients per 100 on-ICP leads processed through the full funnel
```

**Translating that into "how long to client #1":**

| Assumption | Leads needed | At current hunt rate | Time to client #1 |
|---|---|---|---|
| Conservative (0.5 clients / 100 leads) | ~200 leads | `LEADS_TO_FIND_PER_RUN=5` × up to `MAX_RUNS_PER_DAY=10` = up to 50/day **cap**, but real output is throttled by SerpAPI's 250/mo quota shared with owner-lookup → realistic **~30-50 on-ICP leads/week** once discovery is clean | **~4-7 weeks** of steady hunting + the 2-6 week sales cycle stacked on top of the *last* batch that produces a meeting → **realistic first-client target: 8-12 weeks from a clean, on-ICP hunting pipeline**, not 8-12 weeks from today (today's pipeline still needs the lead-quality fix in Gap 3 to actually deliver 30-50/week *on-ICP*). |
| Optimistic (1 client / 100 leads, tight ICP + strong personalization) | 100 leads | Same constraint | **~4-6 weeks** once the pipeline is clean and on-ICP |

**The binding constraint is not lead volume — it's SerpAPI's 250/mo free
quota**, shared between `lead_gen_v3`'s discovery and `owner_finder.py`'s
name lookup. At ~15 businesses/search (per [[active-context]]'s live test),
250 searches/month caps raw discovery around **3,750 businesses/month
before scoring/filtering** — comfortably enough for the lead *volume* this
funnel needs, but owner-name lookups compete for the same budget, so the
practical ceiling is lower. **This is the one paid upgrade worth making before
client #1**, not after (§3 has the cost: $25/mo for 1,000 searches removes the
constraint entirely and is trivially affordable pre-revenue).

**Path to clients #2-5 (post client #1):**

Once P1 is proven, three things change the math favorably:
1. **A real case study replaces the placeholder** in
   `business_context.json`'s `case_studies` block — this alone typically
   lifts reply rate (social proof is one of the highest-leverage cold-email
   levers in every benchmark source reviewed).
2. **Referral becomes available** — the existing client is in the exact ICP
   and knows peers in the same vertical; referral/warm-intro conversion is
   **3-4x faster and dramatically higher-converting** than cold (per
   research: warm intro/referral rates run 15-25% vs. 1.5-2% for cold
   lists) — ask every closed client for 2-3 names within 30 days of signing.
3. **The champion/challenger learning loop has real data to work with** —
   `strategy-snapshot.md` currently shows baseline/0-sample win rates for all
   three email frameworks (bab/pas/aida); after client #1's outreach volume,
   this becomes a real ranking, not a placeholder.

**Realistic pace once the pipeline is validated:** at ~30-50 on-ICP leads/week
sustained, and a 0.5-1% cold close rate improving toward referral-boosted
rates, **clients #2-5 should come faster than #1** (no more pipeline-quality
debugging, a case study to quote, and referral flow layering on top) —
plausibly one every **3-5 weeks** rather than one every 8-12.

---

## 3. Pricing/margin sanity check

### 3.1 Itemized monthly cost per client (2026 vendor pricing, researched)

| Cost | Rate | Assumed monthly volume (per active client) | Monthly cost |
|---|---|---|---|
| **Retell.ai voice engine** | $0.07/min base + LLM ($0.006-0.06/min) + telephony (~$0.015/min) → realistic all-in **$0.13-0.31/min** | ~40 cold-call dials/mo × ~2 min avg (many are voicemail/no-answer, few connects run longer) ≈ 80-120 min/mo | **$10-37/mo** |
| **Twilio number + usage** | $1.15/mo number + $0.014/min outbound | Same ~100 min/mo | **~$2.50/mo** |
| **SerpAPI** | Free tier 250/mo (shared across discovery + owner lookup) OR $25/mo for 1,000 | At 1 client: free tier likely sufficient if hunting is throttled to this client only. At 3+ clients sharing one account: **paid tier needed** | **$0-25/mo** |
| **Make.com** (CRM sync — not yet wired, per roadmap item) | Core plan ~$9-16/mo for a few thousand ops | Only needed once a client's CRM sync (HubSpot/GoHighLevel) is active | **$0-16/mo** (currently $0 — not yet integrated) |
| **Higgsfield** (AI ad creatives — not yet wired) | Vendor pricing not independently re-verified this session; treat as a real forthcoming line item, plan for **~$20-50/mo** at low creative volume | Ongoing creative refresh | **~$20-50/mo (est., unconfirmed)** |
| **Hosting** | Render free tier today ($0); paid tier (~$7-25/mo) only needed once free-tier limits (512MB RAM, cold starts, 750 hrs/mo) bind | Shared across all clients, not per-client | **$0/mo today, amortized $7-25/mo across all clients once upgraded** |
| **LLM (Groq)** | Free tier today; paid Anthropic/OpenAI only after revenue per roadmap | Shared, not per-client | **$0/mo today** |
| **Email (AgentMail)** | Not independently re-priced this session — treat as a small existing line item | Shared infra | **Assume ~$0-20/mo, unconfirmed** |

**Total realistic per-client cost once fully built out: ~$35-150/mo** at
typical single-client call/creative volume — actually **better** than the
$60-500/mo range currently stated in the playbook, because Retell's realistic
cost-per-minute is lower than a worst-case estimate once call volume is
capped at `MAX_CALLS_PER_DAY=5` system-wide (not per-client). The $500/mo
upper bound in the existing docs likely anticipated much higher call volume
than the current worker.py caps actually allow — worth noting as the current
code is *more* margin-safe than the docs claim, not less.

### 3.2 Margin at 1 / 3 / 10 clients

Using **Package 1 ($4,000/mo)** as the conservative floor (since §2.2
recommends leading with P1) and **Package 2 ($5,000/mo)** where relevant:

| # Clients | MRR (all P1) | MRR (all P2) | Shared infra (amortized) | Per-client variable cost | Total cost | Margin (P1 floor) | Margin (P2) |
|---|---|---|---|---|---|---|---|
| 1 | $4,000 | $5,000 | ~$0-25 (Render free, SerpAPI free) | ~$35-75/mo | ~$60-100/mo | **97-98.5%** | **98-99%** |
| 3 | $12,000 | $15,000 | ~$25-50 (SerpAPI paid tier, Render likely still free) | ~$35-75/mo × 3 = $105-225 | ~$130-275/mo | **97.7-98.9%** | **98.2-99.1%** |
| 10 | $40,000 | $50,000 | ~$50-100 (Render paid tier, SerpAPI mid-tier $75/mo for 5,000 searches, Make.com scaled) | ~$35-100/mo × 10 = $350-1,000 (call volume per client likely grows past `MAX_CALLS_PER_DAY=5` global cap — this cap needs to become per-client, see §5) | ~$400-1,100/mo | **97.25-99%** | **97.8-99.2%** |

**Verdict: the 75-80% margin target in `business_context.json` is not just
real — it's conservative.** Even at 10 clients with generous cost padding,
realistic margins run **97%+**. The stated 75-80% target appears to have
assumed either much higher per-client Retell/creative costs than current
vendor pricing supports, or was set as a deliberately safe floor. **Recommend
correcting the target upward to 90%+ as the realistic operating margin**,
while keeping 75-80% as the conservative *worst-case* floor for board/investor
conversations (i.e., "even if costs triple unexpectedly, margin holds at
75-80%"). This is a genuine strength to lead with in the pitch if a prospect
ever asks about OROVA's own unit economics as a proof point of AI-operated
efficiency.

**One real constraint at 10 clients:** `MAX_CALLS_PER_DAY=5` in `worker.py` is
currently a **global** cap (not per-client) — at 10 active clients all
needing cold-call escalation, this becomes a genuine bottleneck long before
cost does. This is a code change to flag for later (not in scope for this
read-only plan — see §5's lane-by-lane notes), not a margin problem.

---

## 4. Weekly operating cadence (solo owner + autonomous agent)

Mark's time is the scarcest resource, not compute. The cadence below assumes
Nova runs the 9 lanes unattended and Mark's job is **approval, judgment calls,
and closing** — the things `business_context.json`'s `automation_policy`
already correctly reserves for him.

| Day | Mark's time | What Nova does automatically |
|---|---|---|
| **Monday** | 30 min: review weekend's CEO brief (Lane 6, `ceo_brain_job`) + approve/reject queued cold emails and calls from the fast lane (Lane 1) queue that piled up over the weekend. Check `strategy-snapshot.md` for any new champion/challenger flips. | Hunting (Lane 2), reply monitoring (Lane 3), drip sends (Lane 9) continue all weekend regardless. |
| **Tuesday-Thursday** | 15-20 min/day: clear the approval queue (should be near-zero latency once `OUTREACH_AUTOPILOT`/`CALLS_AUTOPILOT` flip on after the trust-building period) + **any booked Google Meets** (this is the real time sink — treat every booked meeting as the top priority of the day, per the 2-6 week sales cycle math in §2.3, since a delayed response costs a live deal). | All 9 lanes running on schedule; HOT replies auto-queue booking links (Lane 3 + `process_pending_booking_replies`) pending Mark's approval or `REPLIES_AUTOPILOT`. |
| **Friday** | 30-45 min: read the week's health-check summaries (Lane 7, every 2h) for anything degraded; skim `skill-health.md`/`improvement-log.md` once Track A/B of ADR-0004 ship; decide whether to widen `TARGET_NICHE`/adjust the vertical mix based on which is producing replies. | Self-improvement loop (Lane 8, every 6h) keeps ranking email frameworks/send times; backup (Lane 5, every 3h) protects the week's learning data. |
| **Weekly (any day), 1x**: | 15 min: check `MAX_DAILY_COST`/`MAX_CALLS_PER_DAY` actuals vs. caps — are the safety limits binding (losing leads) or slack (room to raise them)? Check SerpAPI quota usage — is the 250/mo (or paid tier) on pace to run out mid-month? | — |

**Cadence changes as trust builds** (mirrors the existing
`automation_policy.fully_autonomous` / `requires_approval_now` split): the
first 2-4 weeks, expect the daily 15-20 min to be closer to 30-45 min while
every email/call needs a manual look. Once `strategy-snapshot.md` shows real
win-rate separation between frameworks (not baseline 0-sample rows) and the
first 20-30 sends have gone out clean, flip `OUTREACH_AUTOPILOT=1` — this is
the single biggest cadence unlock available, and it's gated on Mark's
judgment call, not a code change.

**What this cadence deliberately does NOT include:** manually reviewing every
lead the hunt lane finds. That defeats the point of the autonomous system. The
CEO brief (Lane 6) exists specifically to summarize "what happened" so Mark
reviews *outcomes*, not *inputs*.

---

## 5. What each of the 9 worker lanes must do differently

Tied to the real lane implementations in `app/worker.py`:

1. **Lane 1 — Fast lane (approvals + calls, every 2 min, `run_ceo_fast_lane`)**
   No functional change needed — this already correctly gates on Mark's
   approval and enforces PST business hours (9am-5pm) before dialing. **Do**
   confirm the 9am-5pm window matches the *lead's* timezone, not just Mark's
   PST — a Nevada or Arizona lead could be called at an odd local hour if the
   business is in a different zone than assumed. Not urgent, but worth a
   note for whoever picks up the DNC-scrub follow-up (§6).

2. **Lane 2 — Slow lane (hunting, every 60 min, `run_lead_hunt_slow_lane`)**
   **This is the lane the ICP refinement (§2.1) actually changes.** The
   hardcoded `niches` list (lines 279-296) still includes `'private jet
   charter california'` and `'yacht charter california'` — per §2.1's
   research, these should be **removed from the default rotation** (kept
   reachable via explicit `TARGET_NICHE` override only, for opportunistic
   manual hunts) and replaced with more granular exotic-auto and home-builder
   queries (e.g. split "exotic car dealer" into dealer/detailing/wrap/
   restoration sub-niches so the champion/challenger loop can learn which
   *sub-vertical* converts best, not just which top-level niche). This is a
   config-list change, not an architecture change — flagged here for a future
   code session, not applied by this plan.

3. **Lane 3 — Reply + drip monitor (every 5 min, `reply_and_drip_check_job`)**
   No structural change. The HOT/WARM/COLD classification and booking-queue
   design are sound. **Do** prioritize wiring `CALENDLY_LINK`/`CAL_COM_EVENT_
   SLUG` (roadmap item #8, still open per [[roadmap]]) before client #1's
   first HOT reply arrives — right now a HOT reply queues a booking-link
   reply with **no link configured**, which silently degrades to "asked them
   for times" (per the code's own fallback), losing the automation's whole
   value-add on the single most important message in the funnel.

4. **Lane 4 — Cold lead escalation (every 30 min, `run_cold_lead_escalation`)**
   This lane is where the DNC/TCPA gap (Gap 4, §1) lives. **Policy to state
   explicitly** (not a code change, a documented constraint): this lane must
   only ever dial the **business's published line** (Yelp/Google Maps/
   website — already its only phone source today) and must never be pointed
   at a personal-cell enrichment source. The existing `app/core/dnc.py`
   suppression list should be treated as a *manual opt-out log*, not a
   substitute for a National DNC Registry scrub — flagging the registry-scrub
   gap as a real follow-up (already logged in
   [[owner-contact-research]]'s follow-ups) rather than something this
   revenue-focused plan should quietly ignore.

5. **Lane 5 — Cloud backup (every 3h)** No change — this is pure
   infrastructure hygiene, already correctly tuned to Render's ephemeral disk
   risk.

6. **Lane 6 — CEO brief (daily, 17:00 UTC)** **Add the funnel math from §2.3
   as a standing section of the daily brief**: leads found → emails sent →
   replies → calls → meetings booked → this week vs. last week. Right now the
   brief format isn't traced in this read-only pass, but the cadence in §4
   depends on Mark being able to see funnel *conversion*, not just activity
   counts, at a glance every morning.

7. **Lane 7 — Health check (every 2h)** No change to cadence. **Do** make
   sure a health-check alert fires if SerpAPI's quota is within, say, 10% of
   the monthly cap — per §2.3, this is the actual binding constraint on lead
   volume and Mark should hear about it before hunting silently goes to zero
   mid-month, not after.

8. **Lane 8 — Self-improvement (every 6h)** No change needed for this plan —
   ADR-0004 already scopes activating the dormant `SelfLearningLoop`/
   `PatternReinforcer` cycles here. Once real outreach volume exists (post
   client #1), this lane starts producing genuine signal instead of the
   current 0-sample baseline rows in `strategy-snapshot.md`.

9. **Lane 9 — Drip sender (every 1h, `send_pending_drip_emails`)** No
   structural change. Worth confirming the drip sequence's send cadence
   (day-2, day-X follow-ups per [[active-context]]'s note about the fixed
   double-send bug) matches the 2-6 week sales-cycle window from §2.3 — a
   drip that exhausts itself in the first week undersells a buyer who takes
   a month to decide.

**Cross-cutting, not one lane:** the `MAX_CALLS_PER_DAY=5` and
`MAX_RUNS_PER_DAY=10` caps in `worker.py` are global across all clients
today. This is fine at 1 client, becomes a real constraint at 3+ (§3.2's
10-client note) — flagged for a future code session, not urgent pre-client-1.

---

## 6. Proposed edits to `app/core/business_context.json` — FOR OWNER REVIEW

**Not applied.** These are recommended changes only; Mark should review and
either approve, adjust, or reject each one.

### 6.1 `icp.primary_verticals` — narrow to the three that fit the motion

```diff
   "primary_verticals": [
     "Luxury / premium brands (the core focus)",
     "Exotic and luxury automotive (dealers, rentals, tuning, detailing, storage, restoration)",
     "Custom home builders / high-end remodeling",
-    "Private aviation and yacht charter"
+    "Luxury real estate agents (individual top producers)"
   ],
   "secondary_verticals": [
     "High-ticket service providers",
-    "Luxury real estate",
+    "Private aviation and yacht charter (opportunistic only — decision-makers here are typically family offices/brokerages/fleet operators, not a single owner reachable by cold email; do not hunt these as a default rotation target)",
     "Premium professional services"
   ],
```

**Why:** §2.1's research — these verticals don't match "single owner reads
their own cold email," which is the load-bearing assumption of the entire
outreach funnel.

### 6.2 `sales_funnel` — add the funnel math as a standing reference

```diff
   "sales_funnel": {
     "steps": [ ... ],
     "booking_target": "Book the appointment with Mark (human closes the deal).",
+    "funnel_benchmarks_2026": {
+      "cold_email_reply_rate_target": "5-8% (agency-managed benchmark: 5.8%)",
+      "cold_email_to_meeting_rate_target": "1-2%",
+      "cold_call_dial_to_meeting_rate_target": "2.5-5%",
+      "meeting_to_close_rate_target": "20-30% (founder-led close)",
+      "leads_per_client_estimate": "100-200 on-ICP leads processed through the full funnel per new client, pre-referral",
+      "note": "See vault/10-brain/profitability-plan.md for full derivation and sources."
+    },
     "signature_objection": { ... },
     "qualified_lead_definition": "..."
   },
```

**Why:** gives Nova's CEO-brain and self-improvement loops an explicit target
to compare actuals against, instead of only tracking raw counts.

### 6.3 `commercial_terms.margin_target` — correct upward, keep old value as floor

```diff
-    "margin_target": "75-80% profit after OROVA's monthly costs (Twilio number + usage, Retell pay-as-you-go, Make.com, Higgsfield, hosting/LLM/email). Ad spend is not an OROVA cost.",
+    "margin_target": "90%+ realistic operating margin at current vendor pricing (see vault/10-brain/profitability-plan.md §3); 75-80% retained as the conservative worst-case floor for external/investor conversations. Ad spend is not an OROVA cost.",
```

**Why:** §3.2's bottom-up cost model shows realistic margins of 97%+ at 1, 3,
and 10 clients given current Retell/Twilio/SerpAPI pricing — the existing
75-80% figure undersells OROVA's own unit economics, which is itself a
credible differentiator to cite when pitching an "AI-operated agency."

### 6.4 `outreach` framework examples — lead with Package 1, not implied Package 2

```diff
     "initial_email_framework": {
       "hook": "Mention something specific about their business — show you actually looked",
-      "value": "One sentence about what OROVA does that's relevant to them",
+      "value": "One sentence about what OROVA does that's relevant to them — for a first-touch email to a prospect with no case study yet, lead with Package 1 (Meta lead-gen + creatives); mention Package 2's AI qualification only if they ask 'what do you do with the leads.'",
       "ask": "Low-pressure invitation for a 10-15 minute chat",
```

**Why:** §2.2 — P1 is the lower-friction first yes for a stranger with zero
social proof; P2 is the natural second conversation once trust exists.

### 6.5 New field: `compliance.calling_policy` (net-new section)

```diff
+  "compliance": {
+    "calling_policy": {
+      "rule": "Retell/cold-call lane may ONLY dial a business's published line (source: Yelp/Google Maps/website — Nova's existing phone source). NEVER wire in a personal-cell enrichment source for the automated dialer — the B2B TCPA exemption this lane relies on protects business-line calls soliciting a B2B service; it does NOT extend to a personal cell even for the same B2B pitch.",
+      "known_gap": "app/core/dnc.py implements an opt-out suppression list, not a National DNC Registry scrub. A registry-scrub gate ahead of trigger_retell_call() is an open follow-up, not yet built.",
+      "source": "vault/20-ops/sessions/2026-07-05-owner-contact-research.md"
+    }
+  },
```

**Why:** makes an implicit-but-correct current behavior into an explicit
policy so it survives future code changes (e.g., someone adding a
"find the owner's cell" enrichment step without realizing it breaks the
exemption the calling lane depends on).

---

## Sources (web research, July 2026)

- [B2B Cold Email Statistics 2026: Benchmarks & What Works Now](https://martal.ca/b2b-cold-email-statistics-lb/)
- [What are B2B Cold Email Response Rates? (2026 Study)](https://belkins.io/blog/cold-email-response-rates)
- [Cold Email Conversion Rate: Average Benchmarks by Industry (2026)](https://reachoutly.com/cold-email/conversion-rate/)
- [Cold Email Benchmarks by Industry — Cleverly](https://www.cleverly.co/blog/cold-email-benchmarks-by-industry)
- [B2B Cold Calling Statistics 2026 — Konabayev](https://konabayev.com/blog/b2b-cold-calling-statistics-2026/)
- [B2B Cold Calling Benchmarks 2026 — Belkins](https://belkins.io/blog/cold-calling-benchmarks)
- [Cold Call to Meeting Conversion — Optifai (939 companies)](https://optif.ai/learn/questions/cold-call-to-meeting-conversion-rate/)
- [25+ Cold Calling Statistics 2026 — Cleverly](https://www.cleverly.co/blog/cold-calling-statistics)
- [Cold Email for Marketing Agencies — RevenueFlow](https://www.revenueflow.com/blog/cold-email-for-agencies)
- [AI Phone Agent Pricing — Retell AI](https://www.retellai.com/pricing)
- [Retell AI Pricing per Minute — Cekura](https://www.cekura.ai/blogs/retell-ai-pricing-per-minute)
- [Twilio Pricing — Programmable Voice, US](https://www.twilio.com/en-us/voice/pricing/us)
- [SerpApi: Plans and Pricing](https://serpapi.com/pricing)
- [B2B Sales Cycle Length: How Long to Close a Deal — Databox](https://databox.com/b2b-sales-cycle-length)
- [The Industry Average B2B Sales Cycle Length](https://blog.hellostepchange.com/blog/the-industry-average-b2b-sales-cycle-length)
- [7 Cars, 30 Days, 1 Facebook Ad — 9 Clouds case study](https://9clouds.com/blog/case-study-7-cars-30-days-1-facebook-ad/)
- [How to Set Up a High-Converting Meta Ads Campaign for Detailing Businesses](https://www.detailersmovement.com/how-to-set-up-a-high-converting-meta-ads-campaign-for-your-detailing-business-auto-detailers-ppf-installers-tint-shops-wrap-businesses/)
- [Luxury Yacht Marketing: Reaching UHNW Clients](https://yachtcharterrevenue.com/blog/luxury-yacht-marketing-strategy-uhnw-clients)

## Linked

- [[orova-playbook]] · [[business-model]] · [[active-context]] · [[roadmap]]
- [[owner-contact-research]] — TCPA/DNC compliance detail this plan builds on
- [[0003-owner-name-first-lead-engine]] — lead engine architecture referenced in §1/§5
