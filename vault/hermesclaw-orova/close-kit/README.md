---
name: close-kit
description: The documents a first deal dies without — agreement, invoice, onboarding
type: doc
created: 2026-07-12
status: active
---

# Close-Kit — From "yes" to signed & paid

> Council verdict (2026-07-11): the first deal is lost to missing paperwork,
> not missing code. This folder is that paperwork. Terms pulled from
> `app/core/business_context.json` — keep in sync if pricing changes.

## The close sequence (what happens after a HOT reply)

1. Google Meet with Mark → verbal yes.
2. Mark sends **[[service-agreement]]** (fill the bracketed fields) + the
   **[[invoice-template]]** for the chosen term.
3. Client signs + pays (Wise / ACH). Ad spend is set up **client-side,
   direct to Meta** — never through OROVA.
4. Run **[[onboarding-checklist]]** — access, assets, first campaign, go-live.

## ⚠️ Before the FIRST real send — owner to-dos (not code)

- [ ] **Sign the agreement yourself once** end-to-end to sanity-check it, or
      get a one-time lawyer pass (this kit is a strong draft, not legal advice).
- [ ] **Pick an e-sign tool** (Docusign/PandaDoc free tier, or PDF + typed
      signature) and an **invoicing tool** (Wise supports invoices natively).
- [ ] **Meta Business Manager**: verify the business + confirm you can be
      added as a partner/admin to a client ad account (never run ads until this
      works — it's the #1 silent onboarding blocker).
- [ ] **Sending domain + SPF/DKIM** before volume outreach (deliverability).
