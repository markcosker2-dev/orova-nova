---
name: session-2026-08-07-california-owner-names-are-free
description: The CSLB personnel file — 197,697 named principals, 100% fill — downloads free from the Public Data Portal. The $235 price recorded on 2026-08-05 is wrong, and California is the #1 geography.
type: session
created: 2026-08-07
status: done
tags: [discovery, registry, california, cslb, correction, adr-0014]
---

# California owner names are FREE — correcting the $235 finding

> [!danger] This overturns [[2026-08-05-registry-by-state-and-or-ccb]] §5 and ADR-0014
> That session concluded: *"The personnel file is real, but it is **not free**…
> CSLB sells fixed-block text files by mail order, **$235.00 each**."*
>
> **Measured live 2026-08-07: the personnel file downloads free, as CSV, from
> the CSLB Public Data Portal.** No mail order, no cheque, no $235.

## The evidence

`https://www.cslb.ca.gov/onlineservices/dataportal/ContractorList` states, verbatim
in the served HTML:

> *"A list of license information broken into three files: license master,
> workers' compensation, and **personnel file**."*
>
> **PERSONNEL:** *"license number, **personnel names, titles**, classification(s),
> and bond information. Disassociated personnel are not included."*
>
> **LICENSE MASTER:** *"license number, business name, address, **telephone
> number**, license status, issue/expiration dates, classification(s)…"*
>
> **Format:** *"available in Excel (.xls) or CSV format."*
> **Fee:** *"**There is no charge for this service.**"*
> NOTE: *"Email addresses are not provided (B&P Code §27)"*

Downloaded end to end, not merely read:

```
HTTP 200  bytes=46,575,901  content-type: text/csv
content-disposition: attachment; filename=PersonnelData.csv
```

| measure | value |
|---|---|
| rows | **206,657** |
| distinct licence numbers | **114,780** |
| `Name-TP = Principal` rows | **197,697** |
| of which carry a name | **197,696 — 100.0%** |
| `Sole Owner` title | **156,877** |

`Sole Owner` is the single most valuable title in the file: for a small
contractor the sole owner *is* the decision maker, which is the whole problem
the CALICO / owner-waterfall effort exists to solve.

Sample rows (`LIC-NO, Name-TP, Name, EMP-Titl-CDE`):

```
8, Principal, DAVIS  DANA  MICHAEL,     Officer
8, Principal, NILSEN MARK  ALAN,        Officer | Responsible Managing Officer
```

Note the name layout is `LAST FIRST MIDDLE`, space-padded — the same shape WA
L&I uses, so `_person_from_principal` already handles it (including the suffix
fix from #146).

## How to fetch it (it is not a plain URL)

The portal is ASP.NET WebForms and **session-stateful**. A direct GET of
`DownLoadFile.ashx?fName=PersonnelData&type=C` returns **0 bytes** unless the
matching postback happened first on the same cookie jar. The working sequence:

1. `GET /onlineservices/dataportal/ContractorList` with a cookie jar; scrape
   `__VIEWSTATE`, `__VIEWSTATEGENERATOR`, `__EVENTVALIDATION`.
2. POST `__EVENTTARGET=ctl00$MainContent$ddlStatus`, `ddlStatus=P`
   (`M` = License Master, `W` = Workers' Comp, `P` = Personnel).
3. Re-scrape the tokens, then POST `__EVENTTARGET=ctl00$MainContent$lbtnPersonnelcsv`.
   **The Master button is named differently — `lbMasterCSV`, not `lbtn…`.**
4. Follow the 302 to `DownLoadFile.ashx`.

> [!warning] Their WAF will block you
> After several automated requests in quick succession the site returned
> *"Request Rejected… Please consult with your administrator"* with a support
> ID. **The Master file was NOT downloaded for this reason** — the mechanism is
> proven by the Personnel download, but the join is not yet demonstrated
> end to end.
>
> These files are periodic extracts, not live data. Any implementation should
> fetch them **rarely** (weekly at most), cache the result, and back off hard on
> rejection. Getting the IP banned costs the whole California channel.

## Why this matters more than it looks

California is the **#1 ICP geography** ([[active-context]]): ~20,000 Los Angeles
contractors versus 3,600 Portland and 3,300 Seattle. It was the one West Coast
state the pipeline could not reach with a named decision maker, and the recorded
reason was a $235 spend the owner could not justify pre-revenue.

That reason was wrong. The blocker was never money — it was that nobody had
found the free route.

> [!note] The $235 file is still real, and still not needed
> CSLB does sell fixed-block mail-order files. The 2026-08-05 session found
> those and reasonably concluded they were the only source of personnel data.
> The Public Data Portal export is a *different product* that carries the same
> field, free. Both facts are true; only the conclusion was wrong.

## A second finding: the $235 may have been unnecessary anyway

The live outbound Retell prompt already contains a **NO-NAME path**, written
specifically for this case:

> *"CRITICAL: {{name}} IS OFTEN NOT A REAL NAME. Many lead sources (California
> licence records especially) carry no owner name at all… use the NO-NAME path."*

So even the free **Master file alone** — business, address, phone — was already
callable, via the twenty-seven-second opener. The owner name upgrades the
opener; it was never the thing gating the channel. Worth remembering the next
time a spend gets justified by a capability the system already has.

## Follow-ups

- [ ] Prove the join end to end: Master ⟕ Personnel on `LIC-NO` → business +
      phone + named principal. Blocked only by the WAF cool-off.
- [ ] Wire CSLB as the third licence registry (ADR-0014 seam), matching the
      WA/OR `register_licence_registry` pattern — **extension, not a new
      abstraction**.
- [ ] Filter hard: 114,780 licences is far wider than ICP. Reuse the
      business-name ICP filter that cut WA from 15,069 to ~4,280 (28.4%).
- [ ] Correct ADR-0014 and [[2026-08-05-registry-by-state-and-or-ccb]] §5.
- [ ] Emails are excluded by statute (B&P §27) — CSLB will never supply them.
      This is another independent reason the phone lane, not email, is the
      California path.
