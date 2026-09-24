# OROVA Instagram captions — future posts

Write for a custom home builder or remodeler reading on a phone, not for a content calendar. Make one specific observation, explain the implication in plain language, and ask one useful question or offer one clear next step. Rotate the actual offer: Meta ads that bring enquiries, qualification/follow-up that handles opted-in leads, or both. Never imply an AI caller creates demand by itself.

Format:

1. Two to four short paragraphs, separated by a real blank line (`\n\n`). Keep the opening direct; avoid formulaic hype, all-caps urgency, emoji piles, invented statistics, invented client stories, and “game-changing” AI language.
2. Put the CTA in its own short paragraph. Do not offer the Retell demo number while the inbound launch gate is on HOLD.
3. After the CTA, insert a blank line, then three to five relevant hashtags separated by ordinary spaces. Do not glue a hashtag to the CTA or dump a long hashtag wall.
4. Save the exact caption in each post's `CAPTION.txt`. Inspect the Make data-store record before the scenario runs: it must actually retain the paragraph breaks. The 2026-09-23 browser-entry path flattened the source caption even though `CAPTION.txt` had blank lines. On 2026-09-24, entering paragraphs with explicit `Shift+Enter` twice retained `<br><br>` in the saved `reel_4` Make record after reload. Use and verify this method (or a correctly regionalized API), then check the saved record and live Instagram caption. A well-formatted source file alone is not proof. If the queued value is flattened, repair it before publishing.
5. For each Reel, run `python scripts/ig_reel_preflight.py PATH_TO_REEL.mp4 PATH_TO_CAPTION.txt --url PUBLIC_VIDEO_URL` before queueing. It checks the local MP4, narration audio stream, caption formatting and public URL. It cannot prove that narration is audible, that Make kept the caption, or that Instagram accepted the upload; listen to the Reel and verify the saved Make record and live post separately. An `application/octet-stream` URL warning requires extra live verification, not a false claim of success.

Example shape (illustrative, not a ready-to-publish claim):

```
Your ads can be doing their job while follow-up quietly loses the enquiry.

Check where the delay starts: form submission, first reply, qualification, or booking. The fix depends on which handoff is broken.

DM “MAP” if you want to walk through your current path.

#CustomHomeBuilder #HomeRemodeling #MetaAds #LeadQualification
```

Review every claim against the current vault and live system. Do not post a hypothetical as an OROVA result.
