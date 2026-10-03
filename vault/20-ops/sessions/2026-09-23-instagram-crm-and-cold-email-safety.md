---
name: 2026-09-23-instagram-crm-and-cold-email-safety
type: session
date: 2026-09-23
status: active
tags: [instagram, make, crm, email, zero-budget]
---

# Instagram, CRM, and cold-email safety — 2026-09-23

## Verified live facts

- OROVA is Meta ads lead generation plus lead qualification/follow-up; AI calling is an optional, consent-gated part of the latter, not the whole offer.
- The prior OROVA NOVA task had 310 stored production leads, zero verified replies/meetings, and 61 Instagram outreach drafts not yet sent. It did not establish a first client.
- On 2026-09-23, production `/api/leads?limit=2000` returned 310 business records. `OROVA CRM` Google Sheet `Leads` contained 312 nonempty rows representing the same 310 distinct businesses. Four rows are duplicates, and sheet numeric IDs 76/77 are absent/reused; use verified business/URL/state identity for status updates, not sheet ID alone. The CRM Sheet is distinct from the Instagram outreach Sheet and Make's Instagram post queue.
- Make scenario `OROVA | IG Publisher` (`9546332`) was active, with all prior queue records marked `posted` and no pending post. `OROVA IG Post Queue` is data store `106186`.
- A new claim-safe six-slide carousel, `carousel_13_two_jobs` (`post_30`, order 33), was added to Make and run once. The queue is `posted`, media ID `18586404292069022`, and Instagram independently returned the matching `CAROUSEL_ALBUM` and caption at https://www.instagram.com/p/DdnzTIqCXzt/ (2026-09-23 07:43 UTC). This is the first newly published post from this repair session, not a first-ever OROVA post.
- After posting, the Instagram Business account reported 184 followers, 69 following, and 30 media. Its latest 10 feed items had one like and zero comments in total at the 2026-09-23 read; the newest post had not had time to accumulate engagement. One active story was returned. This baseline argues for learning from actual saves/replies/reach, not claiming posting alone is growth.
- A recurring Codex task named `OROVA Instagram social media manager` is active for Monday/Wednesday/Friday 21:00 local. It reviews Instagram and Make, plans truthful $0 content, handles routine engagement, verifies publication, and updates this vault. It does not promise follower growth or clients.
- Instagram Composio and GitHub connections are active. Mark connected Make to Composio, and the connection reports `ACTIVE`, but the Make API test fails with HTTP 401: the connector calls `us2.make.com` while OROVA's workspace is on `eu2.make.com`. A ping alone succeeded and does not prove account authorization. The signed-in EU2 Make browser itself works and published the post. Do not treat the Composio Make path as operational until a real scenario read succeeds against the correct region.
- Mark flagged AI-looking captions and hashtags glued to the text. The local `CAPTION.txt` had blank lines, but the live Instagram caption was flattened by the Make browser-entry path. `social/CAPTION_STYLE.md` and the recurring manager task now require real short paragraphs, a blank line before 3–5 spaced hashtags, and verification of the actual queued and live caption before another publication. The already-live post was not edited.
- Production remains on build `bd33ab8ffbab`. Local safety/CRM changes are not yet deployed. The last documented Drive OAuth backup failed `invalid_grant`. A Google Sheet lead copy is not a full DB backup and cannot preserve all consent, approval, event, learning, and conversation state. Do not merge/deploy before a complete independently downloaded and integrity-checked production DB snapshot and release verification.
- Live `nova.py config` showed AgentMail configured and email lanes active, but the required postal address unset, so the production-era email sink currently fails closed. This is not proof of zero past sends. Keep the address unset and do not approve cold-email sends; the new hard policy block remains local until a backup-gated deployment.
- Render's Free service shell displayed an upgrade requirement, so it is not a $0 route to copy out the SQLite database. No upgrade or live environment change was made.

## Work prepared in the feature branch

- Make carousel assets: `social/carousel_13_two_jobs/slide_1.jpg` through `slide_6.jpg`, caption and render spec. Image URLs were verified before queueing.
- Lead hunt reporting now verifies durable Sheet sync of exactly the newly inserted leads before saying they were saved. Status updates resolve a live lead's business identity against the Sheet rather than trusting reused row IDs. CLI status/deploy snapshots request all 2000 available leads instead of the API's default first 100.
- AgentMail unsolicited prospect sending is hard-disabled at the provider sink and removed from Nova's planner toolset and hunt workflow; inbound replies remain in scope. The hunt no longer composes, requests approval, sends, or enrolls cold email even if the budget flag changes. See [[0021-agentmail-is-inbound-reply-only]]. No claim that this local code is live until a verified deployment.

## Next gates

1. Finish and test the local changes; run full tests, knowledge compile check, and secret scan. Mark reviews/merges the feature branch.
2. Resolve the Composio Make region mismatch and require a successful authenticated scenario read (not just `ACTIVE` or ping) before using its tools. Browser access already posted the first carousel.
3. Repair/verify full production backup independently before Render deployment. Preserve the prior image and rollback/restore plan. No deployment on an unverified Sheet-only fallback.
4. Keep Retell demo traffic and demo-number outreach on hold until the separate inbound launch gates pass. Keep cold AgentMail, automated cold DM, SMS, and outbound AI calling off. Manually review researched outreach and record actual sends, replies, demo calls, and meetings separately.
