---
name: email-channel-viability-2026-08-06
description: Why every lead is emailable=False — measured, not assumed. The data does not exist, and no configuration change fixes it.
type: doc
created: 2026-08-06
status: active
tags: [email, can-spam, channel, measured]
---

# Why `emailable=False` — the measured answer

> [!important] One-line version
> **It is not a configuration problem.** `outreach_ready` never consults
> `BUSINESS_POSTAL_ADDRESS`, a sending domain, or consent. `emailable` is False
> because **the lead has no email address**, and for licence-registry leads a
> real one essentially does not exist to be found.

---

## 1. The two gates people conflate

They are in different modules and answer different questions.

| | `emailable` | send blocked |
|---|---|---|
| where | `lead_validator.outreach_ready` | `agentmail_skill.send_outreach:251` |
| asks | *do we have a direct address for a named person?* | *is it lawful to send?* |
| consults `BUSINESS_POSTAL_ADDRESS` | **no — never** | **yes, fail-closed** |

`emailable = has_name AND has_direct_email`, where
`has_direct_email = bool(email) AND not generic AND email_conf >= 65`.

For a registry lead `email == ""`, so it fails on the first clause. Nothing
about postal addresses, domains or consent is involved.

## 2. The funnel, measured live 2026-08-06

Three conditions stack, and each one is lossy:

| condition | measured | source |
|---|---|---|
| **A.** registry lead has a phone-verified website | **2/20 = 10%** | `website_resolver` over real OR CCB leads |
| **B.** a business *with* a site publishes any email | **4/9 = 44%** | production `_extract_emails` over 9 real contractor sites |
| **C.** that email is DIRECT, not a role inbox | **1/9 = 11%** | `_GENERIC_EMAIL_PREFIXES` |

**End to end: ≈10% × 11% ≈ 1% of registry leads could ever be `emailable`.**

And the single "direct" hit was `restore@arciform.com` — a *departmental* alias,
not a person. The true personal-mailbox rate on this sample is **zero**.

What the sites actually publish:

```
VITAN CONSTRUCTION      info@vitanconstruction.com     GENERIC
LAMONT BROS             contact@lamontbros.com         GENERIC
TIK CONSTRUCTION        contact@tikconstruction.com    GENERIC
ARCIFORM                restore@arciform.com           "direct" (dept alias)
MURRAYHILL / NEIL KELLY / HAMMER & HAND /
CRAFTSMAN / POWELL      (none published at all)
```

## 3. The gate behaves correctly at every step

Fed synthetic leads through the real `outreach_ready`:

| lead | `email_conf` | `emailable` |
|---|---|---|
| no email (registry lead) | 0 | False |
| generic, scraped (`info@`) | 50 | False — *"needs a direct mailbox"* |
| direct, scraped | 65 | **True** |
| direct, verified | 90 | **True** |
| direct, **guessed** | 35 | False — *"unverified / low confidence"* |

Guessed addresses score 35 against a threshold of 65, so they can never pass.
That ban is correct and was paid for: pattern-guessing caused the 48-bounce
incident (PR #124).

> [!note] The one real lever, and it is the owner's call
> `_GENERIC_EMAIL_PREFIXES` excludes `info@`/`contact@`. Accepting them would
> move the rate from ~1% to ~4.4% (10% × 44%). For a **6-10 person residential
> remodeler**, `info@` very often rings the owner's own phone — so the "direct
> mailbox" rule may be miscalibrated for *this* ICP specifically.
> **Not changed unilaterally.** It is an outreach-strategy decision, and 4.4%
> is still not a channel.

## 4. What this means

**Email is not a viable channel for licence-registry leads, at any
configuration.** This is a fact about small residential contractors — they do
not publish personal email addresses — not a bug to fix.

Registry leads remain `ready=True` via `callable=True`. The phone is the field
the registries fill at ~100%, and it is the field the outreach lane cannot
currently use.

## 5. Legal position (researched 2026-08-06, FTC guidance)

**CAN-SPAM does NOT require prior consent.** Cold B2B email to a work address is
lawful in the US. Seven rules apply, penalty up to **$53,088 per message** (FTC
2026 inflation adjustment):

1. accurate headers · 2. non-deceptive subject · 3. **advertisement
disclosure** · 4. physical postal address · 5. working opt-out · 6. honoured
within 10 business days · 7. monitoring affiliates

Element 3 was **missing entirely** and is fixed in
[#142](https://github.com/markcosker2-dev/orova-nova/pull/142). Element 4 is
unset and fail-closed — **a PO box unblocks it**.

So the legal blocker is small and owner-solvable. The *data* blocker is not.

## 6. Verified non-bug

The reply lane records an opt-out only when `intent == "COLD"`, which looks like
a legal obligation gated behind an LLM classifier. It is not:
`_keyword_classify_reply` reads the **same** `_OPTOUT_REPLY_SIGNALS` list and
short-circuits before the LLM. Tested on 10 replies including adversarial
mixed-intent ones — **0 dropped**. Both halves are now pinned by one test,
because the gate is only safe while the two lists agree.

## Linked

[[session-2026-08-06-security-offer-and-the-open-channel]] ·
[[0014-licence-registries-as-the-discovery-source]] ·
[[instagram-outreach-plan-2026-07-30]]
