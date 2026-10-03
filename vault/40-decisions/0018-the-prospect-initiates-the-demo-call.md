---
name: 0018-the-prospect-initiates-the-demo-call
description: Manual permission-first DMs invite a prospect to call OROVA's disclosed inbound AI demo; automated outbound AI calling remains disabled.
type: decision
created: 2026-09-22
status: active
tags: [decision, outreach, instagram, linkedin, retell, consent]
---

# ADR-0018 — The prospect initiates the demo call

## Status

Accepted — owner direction, 2026-09-22.

## Context

OROVA has no customer results or testimonials it may truthfully use. It does
have a working AI lead-qualification artefact, but automated outbound
artificial-voice calls carry legal and platform risk. OROVA also has no
approved cold-email provider lane: AgentMail's terms prohibit unsolicited
messaging, and there is no domain-email system ready for compliant operation.

The existing Instagram queue has 61 unsent rows and no outcome history. That
is inventory, not evidence. The immediate constraint is a first genuine
conversation, not more lead discovery or another automation layer.

## Decision

Use a permission-first **inbound demo-call CTA**:

1. Mark reviews one business and sends one short, truthful Instagram or
   LinkedIn DM manually. No bot, scraper or bulk sender.
2. The message says OROVA built an AI lead qualifier and invites the recipient
   to call OROVA's number if they want to experience it. It does not claim
   clients, results, scarcity or a free offer.
3. The prospect decides whether to call. OROVA does not auto-dial them.
4. Nova immediately identifies itself as AI and, when recording is enabled,
   asks permission before continuing.
5. Nova labels the experience as a simulation, asks a few natural
   qualification questions, summarises what the prospect's team would receive,
   then explicitly exits the simulation.
6. Nova diagnoses whether the real constraint is insufficient lead volume or
   wasted time chasing and screening leads. It names only the relevant OROVA
   component and asks for a 15-minute conversation with Mark. Nova does not
   quote price or invent a booked slot; it captures two preferred times.

Internal shorthand such as “drug dealer method” is not prospect-facing copy.
The durable name is **inbound demo-call CTA**.

## Boundaries

- This decision does not certify legal compliance and is not legal advice.
- Washington automated outbound solicitation stays disabled under RCW
  80.36.400. The inbound path is deliberately not an automated outbound call.
- The FCC treats AI-generated/artificial voice in outbound calls as an
  artificial or prerecorded voice under the TCPA. No outbound workaround is
  inferred from a public phone number or a social profile.
- LinkedIn prohibits third-party automation that scrapes or automatically
  sends messages. Instagram's official Send API is for eligible conversations
  after the user has messaged the professional account. Cold first touches are
  manual.
- Stop on refusal or opt-out. Do not repeatedly message nonresponders.
- Before sending traffic, back up and verify the live Retell inbound prompt.
  The local canonical source is not the deployed agent.
- Any Instagram or LinkedIn send and any public post still requires a human
  review of the exact copy and destination.

## First message pattern

> Hey [first name] — I built a small AI lead-qualifier demo for businesses like
> [company]. If you want to hear exactly what a new lead would experience, call
> [OROVA demo number]. It identifies itself as AI and takes about a minute. If
> it is not relevant, no worries — I will leave it there.

Personalise the first sentence from a public business fact. Do not claim the
demo was custom-built for that company unless it actually was.

## Evidence to record

For every send, record only the minimum operational event: channel, public
profile URL, date, exact approved copy and outcome. A call, reply and meeting
are separate events. Silence is not a reply; a preferred time is not a booked
meeting.

## Sources checked 2026-09-22

- [FCC declaratory ruling on AI/artificial voice calls](https://docs.fcc.gov/public/attachments/FCC-24-17A1_Rcd.pdf)
- [Washington RCW 80.36.400](https://app.leg.wa.gov/rcw/default.aspx?cite=80.36.400)
- [California CPUC automatic dialing announcement devices](https://www.cpuc.ca.gov/regulatory-services/enforcement-and-citations/utility-enforcement-branch/automatic-dial-around-devices---robocalls)
- [LinkedIn prohibited software and extensions](https://www.linkedin.com/help/linkedin/answer/a1341387)
- [Meta Instagram Send API](https://www.postman.com/meta/instagram/folder/uxudqu0/send-api)
- [FTC CAN-SPAM compliance guide](https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business)

## Linked

[[0017-the-sample-is-the-proof|ADR-0017]] ·
[[zero-budget-operations-2026-09-21]] · [[active-context]]
