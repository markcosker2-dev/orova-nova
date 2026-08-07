---
name: email-infrastructure-setup-2026-08-06
description: PARKED 2026-08-07 — orova.io is NOT in Mark's Cloudflare account, so there is no domain to build on. The recipe below is correct and kept for whenever a domain exists.
type: doc
created: 2026-08-06
status: archived
tags: [email, dns, cloudflare, brevo, gmail, security, handoff, parked]
---

# Free custom-domain email — setup sheet

> [!caution] PARKED 2026-08-07 — owner instruction, do not resume unprompted
> **`orova.io` is NOT in Mark's Cloudflare account.** He checked the dashboard
> and it is not listed. Being on Cloudflare *nameservers* (`gabe`/`meg`) never
> proved ownership — millions of domains are, and inferring ownership from DNS
> is the same mistake that produced the wrong `orova.co` call the day before.
>
> RDAP: registered **2025-09-28** via **Cloudflare Registrar**, expires
> **2026-09-28**, `client transfer prohibited`. Cloudflare Registrar sells only
> to its own account holders, so it is plausibly under a second login of Mark's
> — but that is unconfirmed, and it cannot simply be bought.
>
> **Nothing below was executed.** No DNS record was created, no Brevo account
> exists, no domain was purchased, no Gmail setting was changed.
>
> Parking this costs nothing. The email channel was already measured at **~1%
> viable** end-to-end ([[email-channel-viability-2026-08-06]]) and cold sending
> stays blocked on `BUSINESS_POSTAL_ADDRESS` regardless. This infrastructure
> only ever unlocked *reply and booking correspondence* — which is worth
> nothing until a conversation exists, and there have been none.
>
> The recipe below is correct and was verified as far as it could be without a
> domain. Resume it only when Mark says there is a domain to build on.

> [!danger] Two corrections that change the plan
> **`orova.co` is NOT ours.** Authoritative DNS (Cloudflare + Google) puts it on
> `ns1/ns2.lander.d.parity.domains` — a domain **parking / for-sale lander**.
> An earlier session claimed we owned it; that was inferred from a vault note
> and was wrong.
>
> **`orova.io` IS ours** (pending Mark's confirmation): on **Cloudflare
> nameservers** (`gabe`/`meg.ns.cloudflare.com`), matching our stated DNS
> provider, and completely blank — no MX, no TXT, no A, no `_dmarc`.
>
> **So the address is `mark@orova.io`.** Everything below is written for it.
> `orova.agency` is genuinely unregistered if a different name is preferred.

---

## 0. What this is for — and what it is NOT for

This unlocks **reply and booking correspondence**: confirmations, reschedules,
follow-up questions from someone who already said yes. That is
transactional/relationship content and is not gated the way cold outbound is.

**It does not unlock cold email.** Two independent blockers, unchanged:

1. **CAN-SPAM §7704 requires a physical postal address.** `BUSINESS_POSTAL_ADDRESS`
   is unset, and `agentmail_skill.send_outreach` **fails closed** on it by
   design. Do not route around that gate.
2. **Brevo's ToS prohibits cold / purchased-list emailing.** Same wall
   AgentMail hit, different vendor.

Measured separately: only **~1%** of registry leads have a real personal
mailbox at all. See [[email-channel-viability-2026-08-06]].

---

## 1. Cloudflare Email Routing — inbound (free)

Cloudflare **generates these records itself** when you enable Email Routing.
Do not hand-type them; the wizard adds them and verifies them for you.

**Dashboard → `orova.io` → Email → Email Routing → Get started.**

It will create:

| Type | Name | Content | Priority |
|---|---|---|---|
| MX | `orova.io` | `route1.mx.cloudflare.net` | 10 |
| MX | `orova.io` | `route2.mx.cloudflare.net` | 20 |
| MX | `orova.io` | `route3.mx.cloudflare.net` | 30 |
| TXT | `orova.io` | `v=spf1 include:_spf.mx.cloudflare.net ~all` | — |

> [!warning] The SPF record above is INCOMPLETE for our setup
> Cloudflare's default SPF authorises Cloudflare only. We also send **through
> Brevo**, so it must be merged — see §2. **One SPF record per domain, ever.**
> Two SPF records is a permanent `permerror` and everything lands in spam.

Then: **Routing rules → Create address** → `mark@orova.io` →
destination `markcosker2@gmail.com` → Cloudflare emails a verification link to
that Gmail; click it.

Optionally add a **catch-all** → same destination, so nothing sent to the
domain is silently lost.

---

## 2. DNS records for Brevo — outbound

Get the real values from **Brevo → Senders, Domains & Dedicated IPs → Domains →
Add a domain → `orova.io` → Authenticate**. Brevo shows a DKIM record unique to
the account; the placeholder below cannot be guessed.

### 2a. SPF — merged, ONE record only

Replace the Cloudflare-generated SPF with this single record:

| Field | Value |
|---|---|
| Type | `TXT` |
| Name | `@` |
| Content | `v=spf1 include:_spf.mx.cloudflare.net include:spf.brevo.com ~all` |

### 2b. DKIM — copy from Brevo, do not invent

| Field | Value |
|---|---|
| Type | `TXT` |
| Name | `brevo._domainkey` |
| Content | *(the `k=rsa; p=MIGfMA0…` string Brevo displays)* |

Brevo also asks for a `brevo-code` TXT record for ownership:

| Field | Value |
|---|---|
| Type | `TXT` |
| Name | `@` |
| Content | `brevo-code:<the code Brevo shows>` |

### 2c. DMARC — start in monitor mode

| Field | Value |
|---|---|
| Type | `TXT` |
| Name | `_dmarc` |
| Content | `v=DMARC1; p=none; rua=mailto:markcosker2@gmail.com; fo=1; adkim=r; aspf=r` |

`p=none` **monitors without rejecting**. Leave it there for ~2 weeks, confirm
the reports show SPF+DKIM passing, then tighten to `p=quarantine` and later
`p=reject`. Starting at `p=reject` on a fresh domain silently bins your own
mail.

> [!important] Cloudflare proxy must be OFF for mail records
> MX and TXT records cannot be proxied. If any row shows an orange cloud, click
> it to grey ("DNS only"). Proxying mail records breaks delivery.

---

## 3. Gmail "Send mail as" — exact inputs

**Gmail → ⚙ See all settings → Accounts and Import → "Send mail as" → Add
another email address.**

**Step 1**
| Field | Value |
|---|---|
| Name | `Mark Cosker` |
| Email address | `mark@orova.io` |
| Treat as an alias | **UNTICK** |

**Step 2 — SMTP**
| Field | Value |
|---|---|
| SMTP Server | `smtp-relay.brevo.com` |
| Port | `587` |
| Username | *(Brevo → SMTP & API → SMTP tab → the login, usually your Brevo account email)* |
| Password | *(the Brevo **SMTP key** — NOT your Brevo account password, NOT the v3 API key)* |
| Secured connection | **TLS** |

Gmail sends a confirmation code to `mark@orova.io`. Because §1 forwards that
address to `markcosker2@gmail.com`, **the code arrives in your normal inbox** —
that is the whole trick, and it only works if §1 is finished first.

**Then set it as default** if you want replies to come from it by default.

> [!note] Why "on behalf of" disappears
> Gmail adds `via gmail.com` when it sends your mail through its own servers
> with a foreign From. Relaying through Brevo with SPF+DKIM aligned to
> `orova.io` removes the mismatch, so the header is not added. Untick "treat as
> alias" so replies thread back correctly.

---

## 4. Order of operations

1. Confirm `orova.io` is ours in Cloudflare.
2. §1 Email Routing → verify `markcosker2@gmail.com` → **test: send from a
   phone to `mark@orova.io`, confirm it lands in Gmail.**
3. Create the Brevo account, add + authenticate `orova.io`, copy DKIM +
   brevo-code into Cloudflare, **merge SPF into one record**, add DMARC.
4. Wait for Brevo to show the domain **Authenticated** (minutes to a few hours).
5. §3 Gmail send-as. Confirmation code arrives via the §1 forward.
6. **Test: send from Gmail as `mark@orova.io` to a different address, then view
   the raw headers and confirm `spf=pass`, `dkim=pass`, `dmarc=pass`, and no
   "on behalf of".**

Step 6 is the only thing that proves it works. A green tick in a dashboard does
not.

---

## 5. HermesClaw — MCP wiring

`~/.hermes/config.yaml` already has a top-level `mcp_servers:` block (line
~442) in this shape:

```yaml
mcp_servers:
  agentmail:
    command: npx
    args:
    - -y
    - agentmail-mcp
    env:
      AGENTMAIL_API_KEY: <secret>
```

Add Composio's Gmail server as a sibling. Composio's Tool Router is an HTTP
endpoint, so it is bridged with `mcp-remote`:

```yaml
mcp_servers:
  composio_gmail:
    command: npx
    args:
    - -y
    - mcp-remote
    - https://connect.composio.dev/mcp?agent=hermesclaw
    env:
      COMPOSIO_API_KEY: <paste-your-own-key-here>
```

**Authenticate via the Tool Router, not by pasting Google credentials.** Run
the connection flow once; Composio holds the OAuth grant and hands the agent a
scoped tool, so no Google password or refresh token ever enters this repo or
the config file. Never commit `COMPOSIO_API_KEY` — `.env` and `~/.hermes/` are
outside git, keep it that way.

---

## 6. The reply-thread lock — `app/core/thread_registry.py`

**Shipped and tested (19 tests).** This is the guardrail that makes an
inbox-reading agent safe.

**The threat.** An agent that reads an inbox and acts on it is a prompt-injection
target. Filtering by sender does not help — `From` is trivially spoofed.

**The control is provenance, not content.** Process a message only if it replies
to a `Message-ID` this system actually transmitted. Everything else is dropped
**before its body is ever shown to the model** — a filter that reads the message
to decide whether to trust it has already lost.

```python
from app.core.thread_registry import record_outbound, should_process_inbound

# On EVERY send — recording is part of sending, not an audit afterthought.
await record_outbound(sent_message_id, to=lead_email, lead_id=lead["id"])

# On EVERY inbound, BEFORE reading the body:
ok, why, entry = await should_process_inbound(msg["headers"])
if not ok:
    logger.info(f"[INBOX] ignored — {why}")
    continue            # body never enters the context window
```

Verified live:

| case | verdict |
|---|---|
| genuine reply (`In-Reply-To` matches) | PROCESS |
| deep in thread (`References` only) | PROCESS |
| stranger emails the address directly | **IGNORE** |
| forged thread, well-formed headers | **IGNORE** |
| spoofed `From`, thread not ours | **IGNORE** |

Fails closed on an empty registry, malformed headers, or a storage error.

---

## 7. Outbound From header

Composio's `sendEmail`/`createDraft` must set `From: Mark Cosker
<mark@orova.io>`. That only produces aligned SPF/DKIM once §2 and §3 are done —
until then it will send but fail authentication and land in spam.

**And it remains subject to the existing gates.** Cold outbound still requires
`BUSINESS_POSTAL_ADDRESS`, and `send_outreach` fails closed without it. This
infrastructure does not change that and must not be used to bypass it.

## Linked

[[email-channel-viability-2026-08-06]] ·
[[session-2026-08-06-security-offer-and-the-open-channel]]
