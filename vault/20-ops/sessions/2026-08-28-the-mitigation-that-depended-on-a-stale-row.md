---
name: the-mitigation-that-depended-on-a-stale-row
description: A closed PII finding was closed only because the repo was private; it isn't. Plus an ungated LLM-callable send path and the unfixed twin of a bug already fixed one function above it.
type: session
created: 2026-08-28
status: active
---

# The mitigation that depended on a stale row

Ran the business rather than the codebase: system, GTM, compliance, docs,
strategy. Four things worth keeping.

## 1. A closed finding that isn't closed

`active-context.md` recorded prospect PII as handled:

> *"Private gates all three at once... old blobs and PR file views 404.
> No Support ticket needed."*

True when written. **The repo is public** — GitHub API, `"private": false`.
The gate that entry reasons from does not exist, so the PII in older commits
and merged PR diffs is world-readable. Confirmed by walking history: `cf7e7a1^`
still carries a real name and mobile across four fixtures.

The status table two sections above said **PRIVATE**. One stale row, and a
security conclusion resting on it. That is the lesson worth more than the fix:
**a wrong fact in a document is not inert — other entries reason from it.**

## 2. The same PII was still in the current tree

`cf7e7a1` — *"redact prospect PII from fixtures on a public repo"* — fixed four
files. The same data was in twenty-two more, because nothing checked.

Verified rather than assumed: a number in `test_yelp_discovery.py`, paired
with a real Seattle general contractor's business name. Houzz lists that
contractor at the identical number.

The number is deliberately not written here — see the postscript.

The fix hit a guard rail worth recording. `is_placeholder_phone()` deliberately
**rejects** the 555 range as dummy data — correctly. So *"never store a fake
number"* and *"never commit a real one"* are in genuine tension, and the six
fixtures that must model a dialable number now carry **OROVA's own line**. The
only number satisfying both constraints is one you own.

`check_secrets.py` rule 3 now fails the build on any routable number. Verified
both ways: re-planting the Cherry number fails the scan; removing it passes.

## 3. The booking reply could mail someone who opted out

`send_outreach` checks opt-out, CAN-SPAM address, ICP and approval.
`reply_to_email` checked **nothing** — and it is not a lesser path:
`worker.py:910` uses it for the HOT-reply booking funnel, and `planner.py:281`
registers it as an **LLM-callable tool**.

Reachable unattended, not theoretical: `ceo_brain._execute_tasks` instantiates
`TaskPlanner` on a scheduled lane, and the planner holds that tool.

Third instance of one pattern. The dialler already says it:

> *"Gating at each call site is how that hole opened, and an LLM-invokable
> path cannot be gated by convention at all."*

## 4. The gate would not have worked anyway

`_normalize_email` was `(email or "").strip().lower()` — the exact defect
`_normalize` (phones) was rewritten to fix on 2026-08-03, **left standing in
the email half of the same file**:

    stored 'dave@x.com' -> is_email_suppressed('Dave <dave@x.com>') = False  BYPASS

Not an exotic form: it is what an inbox hands you. `check_replies` stores the
raw `from_` header, so the one path that knows a prospect replied is the one
most likely to carry a display name.

> **When you fix a normalisation bug, check whether the same function has a
> twin one field over.** This one sat forty lines below its own fix for
> twenty-five days.

## What I did NOT do, and why

**The approval gate on `reply_to_email` is still missing** for the LLM path.
Adding it looked like a two-line change and would have silently broken every
approved booking reply: approvals are **single-use** (`approval_workflow.py:173`
sets `status = "consumed"`), and `worker.py:896` already consumes one before
calling. A second check inside would find nothing approved and block the send.
The correct fix moves the gate out of the worker and into the chokepoint, and
adjusts the requeue path — its own reviewed change, not a late addition.

**~40 licence-registry company names and ~12 owner personal names** remain in
fixtures. Public record, and the actionable half (the phone) is gone, so the
risk is much lower — but renaming touches the name-parsing tests, whose whole
point is the exact string.

**git history** needs Mark: a Support purge, knowing acceptance, or contacting
the individual. A history rewrite alone does not clear merged PR diffs.

## Strategy — the honest read

Nothing this session touched moves the number that matters. It still reads
**zero**: 0 calls, 0 meetings, 0 prospect conversations, ever.

Today found real defects in a machine that has never carried a single prospect.
That is worth doing — the opt-out hole was live — but it is also the pathology:
**twenty-plus PRs of auditing a pipeline nothing has ever flowed through.**

One asset is reachable by a stranger *today*, with no configuration Mark has
not already done: **+1 716 670 3920**. An agent is bound to it. In its whole
life it has taken one call, on 2026-08-07, which hung up at 22 seconds against
an opener ending in *"How can I help?"*

The cheapest real evidence available is Mark dialling his own number and
listening. That is the first end-to-end validation this system would ever have,
it costs two minutes, and it needs no lawyer, no key and no PR.

## Linked

[[active-context]] · [[0016-the-repo-stays-public]] · [[0017-the-sample-is-the-proof]]


## Postscript — the note was itself a leak

The first version of this file quoted the real number as evidence.
`check_secrets.py` rule 3, added in the same session, failed CI on it.

That is the corollary the file's own header states for the rotated API key:

> *"The corollary rule 1 cannot enforce: do not DESCRIBE a live key either.
> The same handoff that withheld the literal explained how to derive it from
> the previous one, which leaks it just as well."*

Writing up a PII leak is a way to leak it. The finding survives intact without
the digits.

**And it exposed a hole in how I verified.** `check_secrets.py` scans
**tracked** files (`tracked_files()` shells out to git), so a brand-new file
passes locally right up until it is committed. I ran the gate, saw green, and
the green was measuring a file git had never heard of.

> **Run the secret scan after `git add`, not before.** A clean gate on an
> untracked file is not a clean gate.
