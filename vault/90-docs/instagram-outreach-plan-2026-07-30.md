---
name: instagram-outreach-plan-2026-07-30
description: Why cold IG DMs can't be automated, the 10 ICP-qualified Seattle remodelers to DM by hand, the drafts to send, and the new Yelp capability found while checking
type: doc
created: 2026-07-30
status: active
---

# Instagram outreach — the plan, in plain terms

**Read this instead of the chat transcript.** Everything you need is here.

---

## 1. The short version

You asked me to set up automated cold DMs to ICP-fit businesses from OROVA's
Instagram.

**I can't automate the sending, and it's not a permissions problem I can fix.**
Instagram's API physically cannot start a new DM conversation. I verified this
directly from the tool definition, not from documentation:

> `INSTAGRAM_SEND_TEXT_MESSAGE` — "Send a text message to an Instagram user via
> DM **in an existing conversation. Cannot initiate new DM threads — a prior
> conversation must exist.**"

The recipient field makes it concrete: it needs a `recipient_id` (PSID) that can
only come from a conversation that **already exists**. Usernames don't work.
There is no parameter I can fill in to reach a stranger.

This is the same wall email hit, for the same underlying reason: platforms let
you *reply* to people who contacted you, not *initiate* at strangers. Meta closed
cold DM initiation deliberately.

**So: the DMs have to be sent by you, by hand, from the app.** That is also
exactly what your own playbook says — `traction-playbook.md` line 58: *"Instagram
DM → Loom link → email follow-up. **5-10 per day maximum.**"* It was designed as
a manual channel. Nothing was lost.

**What I did instead:** built you a researched, ICP-qualified list of 10 real
Seattle-area remodelers with a personalised draft for each. That's section 4.

---

## 2. Two problems with the account itself — fix before you send

**a) `orova.co` is set to PRIVATE.** Composio reports
`account_type: "PRIVATE"` (connected 2026-07-28). A private account is close to
fatal for cold outreach: when a contractor gets a DM from a stranger, the first
thing he does is tap the profile. On a private account he sees nothing —
no work, no posts, no proof. Many won't even accept the message request.

**Switch to a Business or Creator account and make it public before DM #1.**
This is free and takes two minutes in Instagram settings.

**b) There's nothing on the profile yet.** The vault records the OROVA Facebook
page at 2 followers, no website, unverified. Assume Instagram is similar. A
prospect who looks you up mid-conversation and finds an empty profile is a lost
prospect — and this is the moment they're *most* likely to look.

Minimum before sending: profile photo, one line of bio saying what you do for
remodelers, and 3–5 posts. They don't need to be portfolio work (**never
fabricate client work**) — they can be genuinely useful posts about lead-gen for
remodelers. The point is that the profile isn't blank.

---

## 3. A genuinely good surprise: Yelp is available, free, right now

While checking Instagram I found that **Yelp is live through Composio and needs
no API key, no approval, and no payment.**

This matters because ADR-0014 wrote Yelp off as a dead end ("free tier ambiguous,
needs 1–2 day approval"). That was wrong, or has changed. Verified live today:
one search returned **3,300 Seattle contractors** with rating, review count,
phone, address and category.

Why it's valuable — it fills the two holes the WA licence registry leaves:

| Field | WA licence registry | Yelp |
|---|---|---|
| Owner name | ✅ 100% | ❌ |
| Phone | ✅ 100% | ✅ |
| **Business size / credibility proxy** | ❌ none | ✅ **review count + rating** |
| **Category (remodel vs handyman vs tile)** | ❌ weak | ✅ **explicit** |
| Website | ❌ | partial |

ADR-0014 flagged "no employee count, so the 6–10-person ICP can't be filtered;
the data is full of one-person handymen" as an unsolved problem needing an
*unvalidated* proxy. **Yelp's review count and category labels are a better
proxy, and they're free.** A contractor with 50+ reviews and a "General
Contractor" primary category is not a one-man handyman.

I have not built this into Nova. It's a finding to act on, and I'd want your
go-ahead first.

---

## 4. The 10 targets — and why each one qualifies

Sourced from Yelp, then filtered against **ADR-0012** (custom home builders /
high-end remodelers lead the ICP) and **ADR-0013** (they must plausibly have a
crew on payroll and a backlog that can run dry).

**Qualification rules I applied:**
- Primary category must be **General Contractor** — not Handyman, Tiling,
  Flooring, Siding, Decks, or Damage Restoration.
- Name or category must signal **discretionary remodel / custom build**, not
  repair or insurance work.
- **Review count ≥ 20** — evidence of sustained volume, i.e. a crew, not a
  side job.
- Rating ≥ 4.5 — they can already deliver; the constraint is deal flow, which
  is what you sell.

| # | Business | City | Rating | Reviews | Why it qualifies |
|---|---|---|---|---|---|
| 1 | **Wise Choice Construction** | Renton | 4.7 | 113 | Highest volume on the list. 113 reviews = a real operation with payroll. |
| 2 | **Level Up Construction & Remodeling** | Seattle | 4.9 | 57 | "Remodeling" in the name, GC category, downtown office address. |
| 3 | **Eagle Remodel & Construction** | Everett | 5.0 | 52 | Remodel-first, perfect rating, 52 reviews. |
| 4 | **NW Quality Construction** | Bellevue | 4.7 | 45 | Bellevue = highest-value remodels in the metro. *(Caveat: damage-restoration secondary — insurance work is a different buyer. Diagnose on the call.)* |
| 5 | **Cruz Construction & Renovation** | Bothell | 4.9 | 38 | Renovation-first, strong rating. |
| 6 | **Dream Home Construction** | Issaquah | 5.0 | 34 | **Kitchen & Bath + GC — the single strongest ICP signal here.** Issaquah is affluent. |
| 7 | **Cobalt Construction** | Seattle | 4.8 | 33 | Real office address (Aurora Ave), GC only, no trade dilution. |
| 8 | **Cherry Design + Build** | Seattle | 4.7 | 32 | **"Design + Build"** — the exact model that sells $100K+ jobs. |
| 9 | **Your Home Builders** | Seattle | 4.7 | 27 | Custom home builder — ADR-0012's lead vertical by name. |
| 10 | **JD McDowell Construction** | Seattle | 5.0 | 24 | Perfect rating, physical address, GC only. |

**Deliberately excluded, so you can see the filter working:**
VF Handyman and Remodeling (4.9★, 98 reviews — *rejected: "Handyman" primary
category, the disqualified one-person segment*) · Seismic Northwest Retrofit
(*seismic/structural, not discretionary remodel*) · ANK Construction, Alpine
Tile, Prestige Stone (*tiling/flooring specialty trades*) · Advanced Home Repairs
(*repair, not remodel*) · LYD Construction, A.D.Master (*decks and siding*).

Note VF Handyman had better numbers than most of the list and was still cut.
That's the ICP doing its job — 98 reviews of handyman work is still a segment
where one extra job doesn't cover your retainer.

---

## 5. What to actually send

**Rules I followed** (from ADR-0013 and `business_context.json`):
- **Never sell "more leads."** That's a vitamin, and Angi undercuts it 16×.
- Sell the **deadline** — the gap after the current job wraps.
- **Diagnose before prescribing.** A first DM asks a question; it does not pitch.
- **Never** mention AI, never claim clients or case studies you don't have.
- Short. A long DM from a stranger reads as spam.

### Draft A — the default (use for most)

> Hey — saw your work in {city}. Quick question, not a pitch: when the job your
> crew is on right now wraps, do you know what's next, or does it go quiet for a
> few weeks?

Why it works: it's a real question about the thing that actually keeps him up —
payroll against an empty schedule. It's answerable in five words. It sells
nothing, so there's nothing to deflect.

### Draft B — for the design-build / kitchen-and-bath ones (#6, #8)

> Hey — {business} looks like you do proper design-build work, not just
> handyman jobs. Curious: where do the good projects come from at the moment,
> referrals mostly?

Why: acknowledges they're the premium end (true, and flattering without being
fake), and "referrals mostly?" gets a yes almost every time — which opens the
real conversation about what happens when referrals go quiet.

### Draft C — for the highest-volume one (#1, 113 reviews)

> Hey — 113 reviews is serious. Are you turning work away at the moment, or
> still filling the calendar?

Why: at that volume he may genuinely be full. If he says "turning work away"
he's not a prospect right now and you've saved yourself the pitch. If he
hesitates, you've found the pain.

### When he replies — then, and only then, the Loom

Per your playbook, the Loom goes on the **follow-up**, not the first message.
2–3 minutes screen-recording *their* Facebook page and what you'd change. That's
the credibility step, and it's the one thing on this list nobody else does.

**Do not send anything if he says stop.** Log it and never contact again.

---

## 6. Your next 30 minutes

1. **Switch `orova.co` to Business/Creator and make it public.** (2 min)
2. **Put something on the profile** — photo, bio line, 3 posts. (20 min)
3. **Send 5 DMs from the list above.** Draft A unless noted. (10 min)
4. **Write down who replied.** That's it — no CRM, no code.

Five DMs is the whole task. At your playbook's own cadence you're 10 days from
50 conversations.

---

## 7. What I did NOT do, and why

- **I sent nothing.** Sending a message on your behalf needs your explicit
  approval per message, and here it's moot — the API can't do it anyway.
- **I did not automate any part of this.** Automating cold IG DMs would need
  unofficial tooling that risks the account, and it's the same reasoning that
  killed LinkedIn automation in ADR-0006. Not worth an account you'll rely on.
- **I did not wire Yelp into Nova.** Real capability, but that's a build
  decision and a new dependency — your call first.
- **I did not touch the Retell phone lane.** Separate, serious issue: see below.

---

## 8. The other thing you need to know

Independent of Instagram, the compliance review found a **live legal problem
with the automated phone lane** — the channel I'd told you was the answer.

- **RCW 80.36.400** appears to ban automated commercial solicitation calls in
  Washington outright — no B2B exemption, no consent cure — and violation is a
  per-se Consumer Protection Act claim (treble damages).
- **TCPA §227(b)** attaches $500–$1,500 *per call* for artificial-voice calls to
  wireless numbers without consent, and **has no B2B exemption**. Licence records
  routinely list mobiles and don't say which are which.
- **`is_dnc_registered` in our code is a no-op that fails open** — I verified
  this by reading it. There is currently **zero** National DNC Registry
  protection in production.
- **No recording announcement exists.** WA is a two-party-consent state
  (RCW 9.73.030) and Retell records every call.

The honest caveat: the strongest claim — whether a *two-way conversational* AI
counts as an "automatic dialing and announcing device" — rests on a source that
couldn't be opened to confirm. So this is a **stop-and-check, not a proven wall**.

**Nothing has been dialled. `CALLS_AUTOPILOT` is off and I have not touched it.**
The one paid hour of a Washington consumer-protection lawyer on that single
question is, in my view, the highest-value dollar available to this project — it
either unlocks the phone channel or permanently shelves it.

**Instagram DMs, sent by hand, carry none of this risk.** That's a second reason
they're the right move today.

---

## Linked
- [[traction-playbook]] — the IG DM → Loom → email sequence this follows
- [[0012-icp-rerank-and-pilot-pricing]] — the ICP filter used in §4
- [[0013-painkiller-positioning-and-real-competition]] — why the drafts sell a deadline
- [[0014-licence-registries-as-the-discovery-source]] — needs updating: Yelp is NOT a dead end
- [[active-context]]
