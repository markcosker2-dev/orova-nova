---
name: 2026-08-09-a-bare-domain-is-not-a-business-name
description: Eight of thirteen distinct leads were bare domains that passed the storage gate; the fix is a name-shape rule, not a wider domain denylist
type: session
created: 2026-08-09
status: active
tags: [data-quality, storage-gate, icp]
---

# A bare domain is not a business name

## What was wrong

Eight of the **thirteen** distinct businesses in the entire production pipeline
were bare domains: `amazon.com`, `nytimes.com`, `cambridge.org`,
`definitions.net`, `vocabulary.com`, `custom-cursor.com`, `customink.com`,
`luxe.tv`. SerpAPI returns high-authority sites that merely rank for a query
like `custom home builder california`; with no scrapable business name, the
domain was stored as the business name.

They were not inert. The contact waterfall spent **five enrichment sources on
amazon.com** and extracted "Andy Jassy" as the owner — visible in the
production logs pulled at the start of this session.

## The hypothesis I started with was wrong

The task brief (which I wrote) said the likely hole was field plumbing: these
rows have empty `url`/`website`, so a domain check reading those fields could
never fire. **That was incorrect.** Measured against the live rows,
`_lead_domains()` resolves the domain fine — it also reads the *email* host,
and most of these rows carry one.

The real reason `off_icp_domain_reason` passed them is that its rules do not
cover this class, **by design**:

```python
# Deliberately narrow: only classes that can NEVER be a home-remodeling
# prospect. Anything merely *unlikely* is left alone — a false quarantine of a
# real contractor costs more than a junk row.
```

It covers gov/edu/mil, foreign ccTLDs, and a short empirical trade-press list.
`.tv` is *explicitly* excluded as one US businesses genuinely use. Nothing
there is broken.

## The fix, and why not a bigger denylist

Adding amazon/nytimes/cambridge to a domain list is unbounded whack-a-mole and
would corrupt the meaning of a list whose own comment says "never widen it to
guesswork."

The general rule is about the **shape of the name**, and it already has three
siblings in `validate_lead_for_storage`:

| existing | new |
|---|---|
| business name is a phone number | |
| business name is an email address | **business name is a bare domain** |
| fixture/sample business name | |

All four are the same defect: *a scraper put a non-name in the name field.*
That is the extension-first answer — no new abstraction, one more member of a
family that already exists.

Measured against the live rows: **8 of 8 junk rejected, 0 of 5 real contractors
touched.** The regex is anchored and whitespace-free, so `J.P. Morgan
Construction`, `Smith & Co.`, `St. John Builders` and `Build.co Remodeling` are
all safe — a real name has whitespace or no TLD.

> [!warning] The accepted cost
> A genuine contractor whose name we failed to scrape and stored as
> `summitremodel.com` is rejected too. Accepted because such a row cannot be
> personalised anyway ("Hi, I saw amazon.com…"), and because the hygiene sweep
> **quarantines** (`status='Invalid'` plus a note) rather than deletes — the
> call is reversible.

## What Mark will see after deploy — read this before panicking

The boot hygiene sweep re-runs this gate over existing rows, so on the next
deploy:

```
24 lead rows -> 16 rows, 8 quarantined
16 rows = 5 distinct businesses (the WA contractors)
```

**The lead count will visibly drop, and nothing is broken.** Given this
project's history of reading count drops as data loss
([[2026-08-09-the-durability-mystery-was-a-duplicate-problem]]), that is worth
saying plainly: the 8 are marked `Invalid` with a `[HYGIENE]` note, still in
the table, and recoverable with one UPDATE.

The remaining 16 rows are still only 5 businesses, because the business+state
dedup key added this session prevents *new* duplicates but does not merge
existing ones. Retroactive de-duplication was **not** built — merging rows is
destructive in a way quarantining is not, and it should be a deliberate,
separately reviewed pass.

Also unaddressed: the Leads sheet still holds the junk rows. Quarantine
excludes them from future syncs but does not remove what is already there.

## Linked

[[2026-08-09-the-durability-mystery-was-a-duplicate-problem]] ·
[[2026-08-09-the-scorer-measures-the-search-query]] ·
[[0015-med-spas-are-not-and-never-were-the-icp]] · [[handoff-2026-08-09]]
