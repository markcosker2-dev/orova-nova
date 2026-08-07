"""Build the Instagram-research input file from CSLB's free bulk export.

## What this is for

Mark's Instagram handle-research scheduled task reads a CSLB export from
Downloads and, for each business, spends web-search quota finding TWO things:
an Instagram handle and the owner's name. Its own prompt says:

    "FINDING THE OWNER NAME — CSLB does not publish owner names, so this is
     genuinely unknown at the start."

**That is false.** Measured 2026-08-07: CSLB's Public Data Portal serves a free
PERSONNEL file carrying 197,696 named principals at 100% fill, 156,877 of them
`Sole Owner`. See [[2026-08-07-california-owner-names-are-free]].

So the task has been paying search quota for data that is free in a CSV. The
quota is the binding constraint on the whole channel — ~243 searches/month,
1-2 per business, which is why the task caps at 30 businesses per run while
Mark sends 5-10 DMs a day by hand.

This script pre-fills `owner_name`, so the task only has to find the handle.
Same quota, roughly double the businesses per run.

It changes nothing about the task itself and sends nothing to anyone.

## Input — both files are FREE, no key, no account

https://www.cslb.ca.gov/onlineservices/dataportal/ContractorList
  · dropdown "License Master" -> Download CSV  -> MasterData.csv
  · dropdown "Personnel"      -> Download CSV  -> PersonnelData.csv

Download them in a BROWSER. Their WAF rejects scripted POSTs after a few
requests ("Request Rejected ... support ID"), and getting the IP banned costs
the entire California channel. This script therefore reads local files and
never touches the network.

## Usage

    python scripts/cslb_ig_research_file.py \
        --master ~/Downloads/MasterData.csv \
        --personnel ~/Downloads/PersonnelData.csv \
        --counties "LOS ANGELES,ORANGE,SAN DIEGO" \
        --limit 200 \
        --out ~/Downloads/CSLBSearchData_prefilled.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# EXTENSION, NOT A SECOND FILTER. `off_icp_trade_reason` is the single ADR-0012
# entry point the storage gate, the boot hygiene sweep and the pre-send gate all
# share — its own docstring says it exists so they "cannot drift apart". A
# private copy of the ICP rules here would be exactly that drift.
from app.skills.lead_validator import off_icp_trade_reason  # noqa: E402

# ── names ───────────────────────────────────────────────────────────────────
# CSLB's Name field is FIXED-WIDTH: "LAST<pad>FIRST<pad>MIDDLE". Verified on a
# 4,000-row sample — 100% split cleanly on a run of 2+ spaces, and multi-word
# surnames ("MC CURDY") survive because their internal gap is a single space.
#
# Do NOT feed these to `owner_finder._person_from_principal`. That helper reads
# a comma-less string as "FIRST ... LAST", so "DAVIS  DANA  MICHAEL" comes back
# as "Davis Michael" — surname as the given name, and a wrong first name in a
# DM is worse than no first name at all.
_FIELD_SPLIT = re.compile(r"\s{2,}")


def parse_cslb_name(raw: str) -> tuple:
    """'DAVIS   DANA   MICHAEL' -> ('Dana', 'Davis', 'Dana Davis')."""
    parts = [p.strip() for p in _FIELD_SPLIT.split((raw or "").strip()) if p.strip()]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return "", _title(parts[0]), _title(parts[0])
    last, first = _title(parts[0]), _title(parts[1])
    return first, last, f"{first} {last}".strip()


def _title(s: str) -> str:
    """Title-case each token so 'MC CURDY' -> 'Mc Curdy', not 'Mc curdy'."""
    return " ".join(w.capitalize() for w in (s or "").split())


# ── which principal speaks for the business ─────────────────────────────────
# Lower rank wins. `Deceased` is a real CSLB title (2,352 rows) and must never
# be selected — the whole point of this file is that a human then DMs them.
_TITLE_RANK = [
    ("sole owner", 0),
    ("responsible managing officer/chief executive officer/president", 1),
    ("chief executive officer/president", 2),
    ("responsible managing officer", 3),
    ("general partner", 4),
    ("qualifying partner", 4),
    ("responsible managing member", 4),
    ("responsible managing manager", 4),
    ("officer", 5),
    ("responsible managing employee", 6),   # an employee, not an owner
]
_EXCLUDED_TITLES = ("deceased",)


def title_rank(titles: str) -> int:
    t = (titles or "").lower()
    if any(x in t for x in _EXCLUDED_TITLES):
        return 99
    for needle, rank in _TITLE_RANK:
        if needle in t:
            return rank
    return 50


# ── ICP ─────────────────────────────────────────────────────────────────────
# ADR-0012 leads with custom home builders / high-end remodelers. CSLB
# classification B = General Building, B-2 = Residential Remodeling — the two
# the research task's own priority rule names first.
_WANTED_CLASSES = {"B", "B-2"}
# A positive signal that this is design-build/custom work rather than a single
# trade. Used only to RANK, never to exclude — excluding on it would quietly
# drop plenty of on-ICP builders whose name says nothing.
_DESIGN_BUILD_HINTS = re.compile(
    r"\b(custom|design[\s-]?build|remodel|renovat|luxur|estate|fine\s+home|"
    r"craftsman|artisan|bespoke|builder)\b", re.I)


def classes_of(raw: str) -> set:
    return {c.strip().upper() for c in re.split(r"[|,/;]", raw or "") if c.strip()}


# ── flexible column lookup ──────────────────────────────────────────────────
# The Master file's exact header is not pinned here on purpose: it is a
# government export whose column names have changed before, and a hard-coded
# header that silently matches nothing produces an empty file that looks like
# "no leads matched" rather than "the parser broke".
def pick(fieldnames, *patterns) -> str:
    for pat in patterns:
        rx = re.compile(pat, re.I)
        for f in fieldnames or []:
            if rx.fullmatch(f.strip()) or rx.search(f.strip()):
                return f
    return ""


def load_personnel(path: str) -> dict:
    """LIC-NO -> best principal {first,last,display,title}."""
    best = {}
    with open(path, encoding="utf-8", errors="replace", newline="") as fh:
        rd = csv.DictReader(fh)
        f_lic = pick(rd.fieldnames, r"LIC[-_ ]?NO", r"licen[cs]e\s*[-_#]?\s*(no|num|number)?", r"^lic$")
        f_typ = pick(rd.fieldnames, r"Name[-_ ]?TP", r"name.*type")
        f_nam = pick(rd.fieldnames, r"^Name$", r"name")
        f_ttl = pick(rd.fieldnames, r"EMP[-_ ]?Titl[-_ ]?CDE", r"title")
        if not (f_lic and f_nam):
            raise SystemExit(f"personnel file: could not find licence/name columns in {rd.fieldnames}")
        for row in rd:
            if f_typ and (row.get(f_typ) or "").strip().lower() != "principal":
                continue
            lic = (row.get(f_lic) or "").strip()
            titles = (row.get(f_ttl) or "") if f_ttl else ""
            rank = title_rank(titles)
            if rank == 99 or not lic:
                continue
            first, last, disp = parse_cslb_name(row.get(f_nam) or "")
            if not disp:
                continue
            cur = best.get(lic)
            if cur is None or rank < cur["rank"]:
                best[lic] = {"rank": rank, "first": first, "last": last,
                             "display": disp,
                             "title": (titles.split("|")[0] or "").strip()}
    return best


def build(master_path, personnel_path, counties, limit, out_path, per_city_cap):
    principals = load_personnel(personnel_path)
    print(f"[personnel] {len(principals):,} licences with a usable named principal")

    counties = {c.strip().upper() for c in (counties or "").split(",") if c.strip()}
    rows, skipped_icp, no_owner, no_phone = [], 0, 0, 0

    with open(master_path, encoding="utf-8", errors="replace", newline="") as fh:
        rd = csv.DictReader(fh)
        fn = rd.fieldnames
        f_lic = pick(fn, r"LIC[-_ ]?NO", r"licen[cs]e\s*[-_#]?\s*(no|num|number)?", r"^lic$")
        f_biz = pick(fn, r"business.*name", r"^BusinessName$", r"^name$")
        f_adr = pick(fn, r"address.*1", r"^address$", r"mail.*address", r"street")
        f_cty = pick(fn, r"^city$", r"business.*city", r"mail.*city")
        f_cnt = pick(fn, r"^county$")
        f_tel = pick(fn, r"phone", r"telephone", r"business.*phone")
        f_cls = pick(fn, r"classification", r"CL[-_ ]?CDE", r"class")
        f_typ = pick(fn, r"business.*type", r"entity")
        f_sta = pick(fn, r"primary.*status", r"^status$", r"licen[cs]e.*status")
        f_zip = pick(fn, r"^zip", r"postal")
        missing = [n for n, v in [("licence", f_lic), ("business", f_biz), ("phone", f_tel)] if not v]
        if missing:
            raise SystemExit(f"master file: missing {missing}. Headers seen: {fn}")

        for row in rd:
            lic = (row.get(f_lic) or "").strip()
            biz = (row.get(f_biz) or "").strip()
            if not lic or not biz:
                continue
            if f_sta:
                st = (row.get(f_sta) or "").strip().upper()
                if st and not st.startswith(("ACTIVE", "CLEAR")):
                    continue
            county = (row.get(f_cnt) or "").strip().upper() if f_cnt else ""
            if counties and county and county not in counties:
                continue
            cls = classes_of(row.get(f_cls) or "") if f_cls else set()
            if _WANTED_CLASSES and cls and not (cls & _WANTED_CLASSES):
                continue
            phone = re.sub(r"\D", "", row.get(f_tel) or "")
            if len(phone) != 10:
                no_phone += 1
                continue
            p = principals.get(lic)
            if not p:
                no_owner += 1
                continue
            # The SAME gate the storage path uses. `vertical` is set so the
            # ADR-0012 trade rules (auto repair, dealers, ...) actually apply —
            # the research task's own prompt lists the identical exclusions.
            reason = off_icp_trade_reason({"business": biz, "vertical": "custom home builder"})
            if reason:
                skipped_icp += 1
                continue
            rows.append({
                "BusinessName": biz,
                "Address": (row.get(f_adr) or "").strip() if f_adr else "",
                "City": (row.get(f_cty) or "").strip() if f_cty else "",
                "County": county,
                "Zip": (row.get(f_zip) or "").strip() if f_zip else "",
                "PhoneNumber": f"+1{phone}",
                "Classifications": "|".join(sorted(cls)),
                "BusinessType": (row.get(f_typ) or "").strip() if f_typ else "",
                "LicenseNumber": lic,
                # ── the whole point: pre-filled, so the task stops paying for it
                "owner_name": p["display"],
                "owner_first": p["first"],
                "owner_title": p["title"],
                "owner_source": "cslb_personnel",
                "instagram_handle": "",   # the task fills this in
            })

    # Rank: B-2 first (residential remodel is the sharpest ICP match), then a
    # design-build name signal, then bigger cities. BusinessType is deliberately
    # NOT used — the task prompt is explicit that it is a tax filing status, not
    # a size or affordability signal.
    def sort_key(r):
        cls = set(r["Classifications"].split("|"))
        return (0 if "B-2" in cls else 1,
                0 if _DESIGN_BUILD_HINTS.search(r["BusinessName"]) else 1,
                r["City"])
    rows.sort(key=sort_key)

    # Spread across cities — the task asks for this explicitly ("rather than 30
    # from one suburb"), and 30 DMs into one town reads like a spam run.
    if per_city_cap:
        seen = defaultdict(int)
        spread = []
        for r in rows:
            key = r["City"].upper()
            if seen[key] >= per_city_cap:
                continue
            seen[key] += 1
            spread.append(r)
        rows = spread

    if limit:
        rows = rows[:limit]

    cols = ["BusinessName", "Address", "City", "County", "Zip", "PhoneNumber",
            "Classifications", "BusinessType", "LicenseNumber",
            "owner_name", "owner_first", "owner_title", "owner_source",
            "instagram_handle"]
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    print(f"[master]    skipped: off-ICP {skipped_icp:,} · no principal {no_owner:,} · bad phone {no_phone:,}")
    print(f"[out]       {len(rows):,} rows -> {out_path}")
    if rows:
        print("\nfirst 5:")
        for r in rows[:5]:
            print(f"  {r['BusinessName'][:40]:42} {r['City'][:16]:18} "
                  f"{r['PhoneNumber']}  {r['owner_name']} ({r['owner_title'][:26]})")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--master", required=True, help="MasterData.csv from the CSLB portal")
    ap.add_argument("--personnel", required=True, help="PersonnelData.csv from the CSLB portal")
    ap.add_argument("--counties", default="", help="comma-separated, e.g. 'LOS ANGELES,ORANGE'")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--per-city-cap", type=int, default=8)
    ap.add_argument("--out", default="CSLBSearchData_prefilled.csv")
    a = ap.parse_args()
    build(a.master, a.personnel, a.counties, a.limit, a.out, a.per_city_cap)


if __name__ == "__main__":
    main()
