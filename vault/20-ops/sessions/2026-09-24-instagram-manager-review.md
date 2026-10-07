---
name: 2026-09-24-instagram-manager-review
type: session
date: 2026-09-24
status: active
tags: [instagram, make, zero-budget, operations]
---

# Instagram manager review — 2026-09-24

## Verified live facts

- The canonical checkout is `C:\\Users\\Mike\\Documents\\Codex\\2026-09-21\\github-plugin-github-openai-curated-remote\\work\\orova-nova`; its `origin` is `https://github.com/markcosker2-dev/orova-nova`.
- Instagram `@orova.co` reported 184 followers, 69 following, and 30 media. The newest post remains `carousel_13_two_jobs` / media `18586404292069022`, published September 23: https://www.instagram.com/p/DdnzTIqCXzt/.
- At this review it had reached 12 accounts and had 0 likes, comments, saves, shares, and total interactions. Its comment list was empty.
- The Instagram inbox had no new prospect conversation. The most recently updated thread was Mark's own account on September 20; no reply was sent.
- The signed-in EU2 Make browser verified `OROVA IG Post Queue` (data store `106186`) contains 31 records and all are `posted`; no pending post exists. `post_30` / order 33 is the latest record, has media ID `18586404292069022`, and is marked `posted` at September 23 15:43 local.
- The latest queue caption is flattened to one paragraph, and the same flattening is visible in the live Instagram caption. The earlier browser-entry defect therefore remains unresolved.
- The Composio Make connection still reports active but every authenticated scenario/list/log read returned HTTP 401 (`Not authorized`), consistent with the known US2-versus-EU2 region mismatch. The direct scenario detail page did not finish loading during this read-only check, so this run verifies the prior publication through the posted queue record plus the live media rather than a new scenario-run detail.

## Decision

No new asset was rendered or queued. Although the queue is empty, adding a post before preserving `\n\n` as visible paragraph separation would repeat the documented formatting failure. The latest actual response also gives no evidence that another AI-caller-focused post is warranted: the new, accurately positioned ads-plus-qualification carousel has 0 interactions so far.

## Next action

Use a non-publishing Make entry test that saves a caption with explicit `Shift+Enter` paragraph breaks, inspect the persisted queue value for `<br><br>`/visible breaks, and only then prepare the next founder-education carousel. Keep the new caption claim-safe and do not expose the held demo number.

## Follow-up completed later September 24

- Mark supplied the actual black OROVA wordmark. Current feed/installed OROVA social skill use near-black `#111111`, off-white `#FAFAF8`, restrained green `#12BE60`, Space Grotesk/Inter; older `app/core/brand_guidelines.json` conflicts. The next Reel follows the live feed and does not use a generated logo.
- The stale `app/core/brand_guidelines.json` was aligned to the live feed and the exact supplied wordmark was saved in the repo in commit `63c7e7a` (feature branch only; not production deployment).
- A 24.9-second informational faceless Reel with narration, subtitles and three free Google Flow shots was produced at `social/reel_04_builder_lead_path/reel_04_builder_lead_path.mp4`. The corrected export at GitHub commit `a778208` is H.264 720x1280/30 fps with AAC **48 kHz/128 kbps** audio, matching Meta's Reel specification. The public video URL returns HTTP 200 but `application/octet-stream`; publisher/Instagram ingestion must still be verified.
- Make queue record `reel_4` / order 34 is now `pending` with `post_type=reel`, the video URL and a caption with actual `<br><br>` paragraph breaks. The saved record survived a reload and was checked on page 2 of the data store. The first scheduled publishing attempt is September 25 at 00:00 Singapore time (09:00 September 24 Los Angeles), not a guaranteed publication.
- The existing Codex social-manager automation was updated in place to use this exact brand, rotate formats/topics, require voice-led informational Reels, check caption spacing and avoid invented results. The broad unsolicited demo-number cold-DM approach is unproven; use manual, researched permission-first outreach and hold the AI demo until it is verified. See the live Obsidian note `2026-09-24-voiced-reel-and-outreach.md` for details.

## Reel preflight follow-up

- A zero-cost `scripts/ig_reel_preflight.py` guardrail checks exported Reel media, `CAPTION.txt`, and optional public video URL before future queueing. The existing `reel_4` asset passes; the GitHub URL emits a non-blocking `application/octet-stream` warning. This is **not** proof of live Instagram publication or audible narration.
- The active social-manager automation now requires that preflight and a listening check. The saved Make queue record and publisher schedule were not changed.
- Four focused tests, knowledge consistency check, and secret scan passed. Full pytest printed 1,554 passed / 26 warnings but lingered after summary and was interrupted, so it did not exit cleanly.
- Next: verify the next Make run and actual Instagram Reel; keep Render gated on a recoverable full production database backup.
