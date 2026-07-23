"""Persistent decision-maker + contact waterfall (ADR-0009, 2026-07-20).

The mandate: stop giving up after the first source. A human SDR with 20
minutes checks the site, the team page, the email itself, a search engine
and LinkedIn, then cross-references before believing anything. This module
replicates that: an ORDERED source chain that ACCUMULATES evidence into a
per-field ledger and only stops when a candidate clears the confidence bar
or every source is exhausted.

Design contracts:
- Never fabricate. A source that isn't sure contributes nothing.
- Every value carries Evidence{value, confidence, source, method,
  last_checked} — the "why we believe this" trail Mission Control shows.
- Cross-referencing is the point: two independent sources naming the same
  person is stronger than either alone; a personal email whose local-part
  matches a scraped/registry name VERIFIES that the email belongs to that
  person.
- Sources are module-level async callables so the orchestrator stays
  testable offline (patch the network sources; the pure logic is exercised
  directly).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Decision-maker role priority (who is most likely to buy OROVA) ───────────
# Lower rank = more valuable. Used to detect titles in scraped text and to
# break ties between equally-confident candidates.
_ROLE_PATTERNS: List[tuple] = [
    (1, "Owner", re.compile(r"\b(owner|proprietor)\b", re.I)),
    (2, "Founder", re.compile(r"\b(founder|co-?founder)\b", re.I)),
    (3, "CEO", re.compile(r"\b(chief executive officer|ceo)\b", re.I)),
    (4, "President", re.compile(r"\bpresident\b", re.I)),
    (5, "Managing Partner", re.compile(r"\bmanaging (partner|member|director)\b", re.I)),
    (6, "General Manager", re.compile(r"\b(general manager|gm)\b", re.I)),
    (7, "Sales Manager", re.compile(r"\b(sales manager|director of sales|head of sales|vp of sales)\b", re.I)),
    (8, "Marketing Director", re.compile(r"\b(marketing director|director of marketing|chief marketing officer|cmo)\b", re.I)),
    (9, "Operations Manager", re.compile(r"\b(operations manager|director of operations|chief operating officer|coo)\b", re.I)),
]
_ROLE_RANK_UNKNOWN = 99

# Generic inbox local-parts that name a function, not a person.
_GENERIC_LOCALPARTS = frozenset({
    "info", "sales", "contact", "support", "admin", "office", "hello",
    "team", "service", "services", "enquiries", "inquiries", "help", "hi",
    "marketing", "careers", "jobs", "hr", "billing", "accounts", "accounting",
    "noreply", "no-reply", "donotreply", "mail", "email", "general", "main",
    "reception", "frontdesk", "shop", "store", "orders", "parts", "finance",
    "leasing", "web", "webmaster", "postmaster", "privacy", "legal",
})

CONFIDENCE_STOP = 82   # a candidate this strong ends the waterfall early
CONFIDENCE_MIN = 30    # below this, a candidate is not worth storing as owner

# Recognized given names. A single-token email local-part is only inferred as
# a first name when it is in this set — this is what separates "blake@" (real
# first name) from "jsmith@" (initial+surname, ambiguous) and "exotics@"
# (business word). Precision over recall: never guess a name we can't
# recognize. Covers the common US SMB-owner demographic; extend as needed.
_COMMON_FIRST_NAMES = frozenset("""
aaron adam adrian alan albert alex alexander alexis alfredo ali alicia allison
amanda amber amy andre andrea andrew angela angelo anita anna anthony antonio
april arthur ashley austin barbara barry becky ben benjamin bernard beth betty
bill billy blake bob bobby bradley brandon brenda brendan brent brett brian
brittany brooke bruce bryan caleb calvin cameron carl carlos carmen carol
carolyn carrie casey catherine cathy cesar chad charles charlie chase chelsea
cheryl chris christian christina christine christopher cindy claire clarence
clark claudia clay clifford clint cody cole colin connor corey cory courtney
craig cristina crystal curtis cynthia dale dan dana daniel danielle danny
darren darryl dave david dawn dean deborah debra denis denise dennis derek
derrick devin diana diane diego dominic don donald donna doreen doris dorothy
doug douglas drew duane dustin dwayne dylan earl ed eddie edgar eduardo edward
edwin eileen elaine eleanor elena eli elizabeth ellen emily emma eric erica
erik erin ernest esteban ethan eugene eva evan evelyn fabian felix fernando
frances francis frank fred freddie gabriel gail gary gavin gene george gerald
gilbert gina glen glenn gloria gordon grace grant greg gregory guadalupe
gustavo guy hannah harold harry hayden heather hector heidi henry herbert
holly howard hunter ian isaac isabel ivan jack jackie jacob jacqueline jaime
jake james jamie jane janet janice jared jason javier jay jean jeff jeffrey
jenna jennifer jenny jeremy jerome jerry jesse jessica jesus jill jim jimmy
joan joann joanna joaquin joe joel john johnny jon jonathan jordan jorge jose
joseph josh joshua joy joyce juan judith judy julia julian julie justin
kara karen karl kate katherine kathleen kathryn kathy katie keith kelly ken
kenneth kevin kim kimberly kirk kristen kristin kurt kyle lance larry laura
lauren laurie lawrence lee leah leo leon leonard leslie lester lewis liam
linda lindsay lindsey lisa logan lois lori lorraine louis lucas luis luke
lydia lynn mack madison manuel marc marcia marco marcus margaret maria marie
marilyn mario marion mark marlene marsha martha martin marvin mary mason
matt matthew maureen maurice max maxwell megan mel melanie melissa melvin
mercedes meredith mia micah michael michele michelle miguel mike mildred
miranda mitchell molly monica morgan moses nancy natalie nathan nathaniel neil
nelson nicholas nick nicole noah norma norman oliver olivia omar oscar owen
pablo pam pamela patricia patrick paul paula pedro peggy perry pete peter
philip phillip phyllis rachel ralph ramon randall randy raul ray raymond
rebecca regina reginald renee rex ricardo richard rick ricky rita rob robert
roberta roberto robin rod rodney roger roland ron ronald ronnie rosa rose
ross roy ruben ruth ryan sally sam samantha samuel sandra sandy santiago sara
sarah scott sean sergio seth shane shannon shari sharon shaun shawn sheila
shelby sheldon sherry shirley sidney simon sonia sophia spencer stacey stacy
stan stanley stella stephanie stephen steve steven stuart sue susan suzanne
sydney sylvia tammy tanya tara ted terence teresa terrance terri terry thelma
theodore theresa thomas tiffany tim timothy tina toby todd tom tommy tony tonya
tracy travis trevor tristan troy tyler tyrone valerie vanessa vera veronica
vicki victor victoria vincent virginia wade wallace walter wanda warren wayne
wendy wesley wilbur willard william willie wilson yolanda yvonne zachary
""".split())


@dataclass
class Evidence:
    value: str
    confidence: int
    source: str        # ca_sos, website_team, email_localpart, search_snippet, linkedin_public
    method: str        # registry_api, page_scrape, inference, search, profile_match
    last_checked: str  # ISO date
    title: str = ""    # role title when the source also found one

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class DecisionMakerResult:
    name: str = ""
    title: str = ""
    role_rank: int = _ROLE_RANK_UNKNOWN
    confidence: int = 0
    source: str = ""
    evidence: List[Evidence] = field(default_factory=list)
    email_verified_personal: bool = False  # email local-part matched the name

    def ledger(self) -> List[dict]:
        return [e.as_dict() for e in self.evidence]


# ── Pure helpers (fully unit-tested, no network) ─────────────────────────────

def _norm_name(name: str) -> str:
    """Normalize for cross-source comparison: lowercase, collapse spaces,
    strip punctuation so 'Blake Johnson' == 'blake  johnson'."""
    return re.sub(r"[^a-z ]", "", (name or "").lower()).strip()


def detect_title(text: str) -> tuple:
    """Return (role_rank, canonical_title) for the highest-priority role
    mentioned in `text`, or (UNKNOWN, '') if none. Scans in priority order."""
    if not text:
        return _ROLE_RANK_UNKNOWN, ""
    for rank, canonical, pat in _ROLE_PATTERNS:
        if pat.search(text):
            return rank, canonical
    return _ROLE_RANK_UNKNOWN, ""


def infer_name_from_email(email: str) -> Optional[Evidence]:
    """Infer a person's name from a PERSONAL email's local-part.

    blake@…            -> "Blake"       (first name, conf 35)
    john.smith@…       -> "John Smith"  (full name, conf 50)
    Generic inboxes (info@, sales@) and unparseable locals (jsmith, b.j)
    return None — we never guess a name we can't defend.
    """
    from app.skills.lead_validator import is_plausible_person_name

    email = (email or "").strip().lower()
    if "@" not in email:
        return None
    local = email.split("@", 1)[0]
    # strip a trailing +tag
    local = local.split("+", 1)[0]
    if not local or local in _GENERIC_LOCALPARTS:
        return None

    today = date.today().isoformat()

    # first.last / first_last / first-last  ->  full name
    parts = [p for p in re.split(r"[._\-]", local) if p]
    if len(parts) == 2 and all(p.isalpha() and len(p) >= 2 for p in parts):
        name = f"{parts[0].capitalize()} {parts[1].capitalize()}"
        if is_plausible_person_name(name):
            return Evidence(name, 50, "email_localpart", "inference", today)
        return None

    # single token -> only inferred when it is a RECOGNIZED first name; this
    # keeps "blake@" and drops "jsmith@" (initial+surname) and "exotics@"
    # (business word) without guessing.
    if len(parts) == 1 and parts[0].isalpha() and parts[0] in _COMMON_FIRST_NAMES:
        return Evidence(parts[0].capitalize(), 35, "email_localpart", "inference", today)

    return None


def merge_candidates(evidence: List[Evidence]) -> DecisionMakerResult:
    """Cross-reference accumulated evidence into a single best decision maker.

    Groups candidates by normalized name; a name attested by N independent
    sources gets the max single-source confidence + (N-1)*agreement bonus.
    Picks the winner by final confidence, breaking ties toward the
    higher-priority role. Fabrication-safe: empty in -> empty result.
    """
    result = DecisionMakerResult(evidence=list(evidence))
    groups: Dict[str, List[Evidence]] = {}
    for ev in evidence:
        if not ev.value:
            continue
        groups.setdefault(_norm_name(ev.value), []).append(ev)
    if not groups:
        return result

    AGREEMENT_BONUS = 15
    best = None  # (final_conf, -role_rank_penalty, name, title, source, rank)
    for _, evs in groups.items():
        distinct_sources = {e.source for e in evs}
        base = max(e.confidence for e in evs)
        final = min(97, base + AGREEMENT_BONUS * (len(distinct_sources) - 1))
        # best title/role seen for this person across sources
        rank, title = _ROLE_RANK_UNKNOWN, ""
        for e in evs:
            if e.title:
                r, t = detect_title(e.title)
                if t and r < rank:
                    rank, title = r, e.title if e.title else t
        # display name: prefer the longest form (full name over first-only)
        display = max((e.value for e in evs), key=len)
        winning_source = max(evs, key=lambda e: e.confidence).source
        key = (final, -rank, display)
        if best is None or key > best[0]:
            best = (key, display, title, winning_source, final, rank)

    _, name, title, source, final, rank = best
    result.name = name
    result.title = title
    result.role_rank = rank
    result.confidence = final
    result.source = source

    # Email verification: if an email_localpart evidence shares its name with
    # an independent source, the email is confirmed to belong to that person.
    norm_best = _norm_name(name)
    localpart_ev = [e for e in evidence if e.source == "email_localpart"
                    and _norm_name(e.value) == norm_best]
    other_ev = [e for e in evidence if e.source != "email_localpart"
                and _norm_name(e.value) == norm_best]
    if localpart_ev and other_ev:
        result.email_verified_personal = True
        result.confidence = min(97, result.confidence + 10)
    return result


# ── Network sources (thin wrappers over existing primitives) ─────────────────
# Each returns a list[Evidence]; each is individually patchable in tests.

async def _source_registry(lead: dict) -> List[Evidence]:
    try:
        from app.skills.owner_finder import resolve_owner
        state = lead.get("state") or ""
        domain = lead.get("_domain") or ""
        hit = await resolve_owner(lead.get("business", ""), state=state,
                                  domain=domain, score=float(lead.get("score") or 0))
        if hit.get("owner"):
            src = hit.get("source", "registry")
            conf = int(round(float(hit.get("confidence", 0.7)) * 100))
            return [Evidence(hit["owner"], conf, src, "registry_api",
                             date.today().isoformat(), title=hit.get("title", ""))]
    except Exception as e:
        logger.debug(f"[WATERFALL] registry source failed: {e}")
    return []


async def _source_email_inference(lead: dict) -> List[Evidence]:
    ev = infer_name_from_email(lead.get("email", ""))
    return [ev] if ev else []


async def _source_website(lead: dict) -> List[Evidence]:
    """Scrape team/about/contact pages for a person + title. Reuses
    light_enrich's page fetch + owner extractor; fail-open."""
    website = lead.get("website") or lead.get("url") or ""
    if not website.startswith("http"):
        return []
    import urllib.parse as _up
    _host = _up.urlparse(website).netloc.lower().split(":")[0]
    if _host == "yelp.com" or _host.endswith(".yelp.com"):
        return []  # a Yelp directory page is not the business's own site
    try:
        from app.skills.light_enrich import _fetch_page, _extract_owner_name, _get_domain
        found: List[Evidence] = []
        home = await _fetch_page(website)
        pages = [website]
        if home and home.get("html"):
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(home["html"], "html.parser")
            dom = _get_domain(website)
            for a in soup.find_all("a", href=True):
                u = _up.urljoin(website, a["href"].strip())
                if _get_domain(u) == dom and any(
                        k in u.lower() for k in ("team", "about", "staff", "leader", "people", "meet", "management")):
                    pages.append(u)
            soup.decompose()  # release the parse graph immediately (512MB tier)
        seen = set()
        today = date.today().isoformat()
        # Cap at 3 pages (was 5): each page is a full HTML parse; on the
        # 512MB free tier a wider crawl per lead × a batch of leads is what
        # tripped the OOM killer (live 2026-07-21).
        for page in list(dict.fromkeys(pages))[:3]:
            data = home if page == website else await _fetch_page(page)
            html = (data or {}).get("html") or ""
            if not html:
                continue
            name = _extract_owner_name(html)
            if name and name not in seen:
                seen.add(name)
                # look for a title in the page text (markdown is the clean form)
                text = (data or {}).get("markdown") or ""
                rank, title = detect_title(text)
                is_team = any(k in page.lower() for k in ("team", "leader", "staff", "people"))
                conf = 70 if (is_team and title) else (60 if title else 55)
                found.append(Evidence(name, conf,
                                      "website_team" if is_team else "website_about",
                                      "page_scrape", today, title=title))
        return found
    except Exception as e:
        logger.debug(f"[WATERFALL] website source failed: {e}")
        return []


async def _source_search(lead: dict) -> List[Evidence]:
    """Search-snippet mining for owner/founder mentions via the existing
    Tavily/DDG contact search. Fail-open."""
    try:
        from app.skills.light_enrich import _ddg_enrich_contact
        domain = lead.get("_domain") or ""
        owner, _email = await _ddg_enrich_contact(lead.get("business", ""), domain)
        if owner:
            from app.skills.lead_validator import is_plausible_person_name
            if is_plausible_person_name(owner):
                return [Evidence(owner, 40, "search_snippet", "search",
                                 date.today().isoformat())]
    except Exception as e:
        logger.debug(f"[WATERFALL] search source failed: {e}")
    return []


# ── LinkedIn (public search-snippet) source ──────────────────────────────────
# We never scrape LinkedIn itself (it blocks bots) — we read the TITLES of public
# DuckDuckGo results for linkedin.com/in profiles, reliably formatted
# "First Last - Title - Company | LinkedIn". The company-match guard is the
# anti-fabrication protection: only accept a name whose result actually names
# THIS business, so a random person is never attached to the lead.
_BIZ_STOPWORDS = frozenset({
    "the", "and", "inc", "llc", "co", "company", "corp", "corporation", "group",
    "of", "ltd", "services", "service", "auto", "cars", "car", "motors", "shop",
})


def _company_matches(business: str, text: str) -> bool:
    """True when enough of the business's distinctive tokens appear in `text`.
    Guards against attaching a real LinkedIn person to the wrong company."""
    toks = [t for t in re.findall(r"[a-z0-9]+", (business or "").lower())
            if len(t) > 2 and t not in _BIZ_STOPWORDS]
    if not toks:
        return False
    tl = (text or "").lower()
    hits = sum(1 for t in toks if t in tl)
    return hits >= (1 if len(toks) == 1 else 2)


def _parse_linkedin_title(title: str) -> tuple:
    """Parse a public LinkedIn result title into (name, job_title); ('', '')
    when it isn't a parseable person profile. Handles
    'Jane Doe - GM - West Coast Exotics | LinkedIn',
    'Jane Doe - West Coast Exotics - LinkedIn',
    'Jane Doe - GM at West Coast Exotics | LinkedIn'."""
    if not title:
        return "", ""
    t = re.sub(r"\s*[|\-–—]\s*LinkedIn\s*$", "", title.strip(), flags=re.I).strip()
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", t) if p.strip()]
    if not parts:
        return "", ""
    name = parts[0]
    _, role = detect_title(" ".join(parts[1:])) if len(parts) > 1 else (0, "")
    return name, (role or "")


def _linkedin_dork(business: str) -> str:
    """Google dork for a business's public LinkedIn profiles.

    Double quotes are stripped from the business name first: 'Foo "Bar" Inc' would
    otherwise produce an unbalanced dork (site:linkedin.com/in "Foo "Bar" Inc")
    and SerpAPI returns nothing useful.
    """
    safe = (business or "").replace('"', " ").strip()
    return f'site:linkedin.com/in "{safe}"'


async def _serp_linkedin_search(business: str) -> list:
    """SerpAPI Google search for linkedin.com/in profiles of `business`.

    Uses SerpAPI, not raw DuckDuckGo — DDG throttles datacenter IPs (Render), so a
    server-side DDG query returns nothing (find_leads_v3 already flags DDG as
    "unreliable server-side"). Shares owner_finder's rationed 250/mo SerpAPI budget
    so LinkedIn lookups can never starve discovery. Returns organic_results
    ({title, link, snippet}) or []. Fail-open.
    """
    import os
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return []
    from app.skills.owner_finder import _ration_check_and_increment, SERPAPI_MONTHLY_CAP
    if not await _ration_check_and_increment("owner_finder:serp_monthly", SERPAPI_MONTHLY_CAP, "month"):
        logger.info("[WATERFALL] SerpAPI monthly cap reached — skipping LinkedIn")
        return []
    try:
        import httpx
        params = {"q": _linkedin_dork(business), "api_key": api_key,
                  "engine": "google", "num": 6}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get("https://serpapi.com/search", params=params)
        return resp.json().get("organic_results", []) if resp.status_code == 200 else []
    except Exception as e:
        logger.debug(f"[WATERFALL] linkedin(serpapi) search failed: {e}")
        return []


async def _source_linkedin(lead: dict) -> List[Evidence]:
    """Public-LinkedIn decision-maker source. Reads SerpAPI Google results for
    linkedin.com/in profiles (never scrapes LinkedIn; DDG is blocked from Render).
    The company-match guard is the anti-fabrication protection — a name is only
    accepted when its result actually names THIS business. Fail-open."""
    business = (lead.get("business") or "").strip()
    if not business:
        return []
    from app.skills.lead_validator import is_plausible_person_name
    results = await _serp_linkedin_search(business)
    today = date.today().isoformat()
    found: List[Evidence] = []
    seen = set()
    for r in results or []:
        if "linkedin.com/in/" not in (r.get("link") or "").lower():
            continue
        blob = f"{r.get('title', '')} {r.get('snippet', '')}"
        if not _company_matches(business, blob):
            continue  # result must name THIS business — anti-fabrication guard
        name, title = _parse_linkedin_title(r.get("title", ""))
        norm = _norm_name(name)
        if not name or norm in seen or not is_plausible_person_name(name):
            continue
        seen.add(norm)
        found.append(Evidence(name, 68 if title else 60, "linkedin_public",
                              "search", today, title=title))
    return found


# Ordered chain. Cheapest/strongest-signal first so the stop-early gate fires
# before we spend network budget: the email we already hold and the legal
# registry cost little; page scrapes and search cost more.
DEFAULT_SOURCES: List[Callable] = [
    _source_email_inference,
    _source_registry,
    _source_website,
    _source_linkedin,
    _source_search,
]


async def resolve_decision_maker(lead: dict,
                                 sources: Optional[List[Callable]] = None) -> DecisionMakerResult:
    """Run the persistent waterfall until a candidate clears CONFIDENCE_STOP
    or all sources are exhausted, then cross-reference. Never fabricates."""
    from app.skills.lead_gen_v3 import extract_domain
    lead = dict(lead)
    lead["_domain"] = lead.get("_domain") or extract_domain(lead.get("website") or lead.get("url") or "")
    chain = sources if sources is not None else DEFAULT_SOURCES

    accumulated: List[Evidence] = []
    for source in chain:
        try:
            evs = await source(lead)
        except Exception as e:
            logger.debug(f"[WATERFALL] source {getattr(source,'__name__','?')} raised: {e}")
            evs = []
        accumulated.extend(evs or [])
        # Cross-reference after every source so agreement can end it early.
        interim = merge_candidates(accumulated)
        if interim.confidence >= CONFIDENCE_STOP:
            logger.info(f"[WATERFALL] {lead.get('business','?')}: stop-early at "
                        f"{interim.confidence} via {interim.source} "
                        f"({getattr(source,'__name__','?')})")
            return interim

    final = merge_candidates(accumulated)
    logger.info(f"[WATERFALL] {lead.get('business','?')}: exhausted "
                f"{len(chain)} sources -> {final.name or '(none)'} "
                f"conf={final.confidence} src={final.source or '-'}")
    return final


def apply_decision_maker(lead: dict, dm: DecisionMakerResult) -> dict:
    """Fold a waterfall result into a lead dict IN PLACE, only when it beats
    what's already there. Returns the lead. Never downgrades a stronger
    existing owner (e.g. a registry hit); never writes an unconfident guess."""
    import json as _json
    existing = int(lead.get("owner_confidence") or 0)
    if dm.name and dm.confidence >= CONFIDENCE_MIN and dm.confidence > existing:
        lead["owner"] = dm.name
        lead["owner_title"] = dm.title or lead.get("owner_title", "")
        lead["owner_source"] = dm.source
        lead["owner_confidence"] = dm.confidence
        lead["evidence_json"] = _json.dumps(dm.ledger())
        # A personal email whose local-part matched the resolved name is now
        # verified as that person's address.
        if dm.email_verified_personal and lead.get("email_status") != "verified":
            lead["email_status"] = "verified"
            lead["email_source"] = (lead.get("email_source") or "enrichment") + "+dm_match"
    return lead


async def reenrich_stored_leads(limit: int = 25, max_confidence: int = 69) -> dict:
    """Persistence lane: re-run the waterfall on stored leads whose decision
    maker is missing or weak, upgrading them in place. Idempotent — a lead
    already at high confidence is skipped; a run that finds nothing new
    changes nothing. Fail-open per lead.

    Memory- and crash-safe on the 512MB free tier (live 2026-07-21: a
    limit-10 run OOM-restarted the instance, wiping the disk mid-run):
    - checks memory before EACH lead and stops gracefully above the cap,
      so the run can never trip Render's OOM killer;
    - persists each upgrade to the durable ladder IMMEDIATELY (not once at
      the end), so an interruption can't lose a completed decision maker;
    - gc.collect() after each lead to release the BeautifulSoup/page graph
      the website source builds."""
    import json as _json
    import gc as _gc
    from app.core.database import DatabaseManager
    from app.core.hardening import memory_monitor
    from app.core.durability import persist_leads_durably

    rows = await DatabaseManager.query(
        "SELECT * FROM leads WHERE COALESCE(status,'') != 'Invalid' "
        "AND COALESCE(owner_confidence,0) <= ? ORDER BY score DESC LIMIT ?",
        (max_confidence, limit), fetchall=True)
    summary = {"checked": 0, "upgraded": 0, "found_names": [], "stopped": None}
    for row in rows or []:
        # Memory gate: never start a lead if we're already near the cap.
        try:
            mem = await memory_monitor.check_memory()
            if mem.get("critical"):
                summary["stopped"] = f"memory {mem.get('memory_mb', 0):.0f}MB >= cap"
                logger.warning(f"[WATERFALL] reenrich stopped early — {summary['stopped']}; "
                               f"remaining leads deferred to next run")
                break
        except Exception:
            pass

        lead = dict(row)
        summary["checked"] += 1
        try:
            dm = await resolve_decision_maker(lead)
        except Exception as e:
            logger.debug(f"[WATERFALL] reenrich lead {lead.get('id')} failed: {e}")
            _gc.collect()
            continue
        existing = int(lead.get("owner_confidence") or 0)
        if dm.name and dm.confidence >= CONFIDENCE_MIN and dm.confidence > existing:
            try:
                await DatabaseManager.query(
                    "UPDATE leads SET owner=?, owner_title=?, owner_source=?, "
                    "owner_confidence=?, evidence_json=?, updated_at=CURRENT_TIMESTAMP "
                    "WHERE id=?",
                    (dm.name, dm.title, dm.source, dm.confidence,
                     _json.dumps(dm.ledger()), lead.get("id")))
                summary["upgraded"] += 1
                summary["found_names"].append(
                    {"id": lead.get("id"), "business": lead.get("business"),
                     "owner": dm.name, "title": dm.title,
                     "confidence": dm.confidence, "source": dm.source})
                # Crash-safe: persist THIS upgrade now. Drive is dead, so this
                # is a single Sheets append per upgrade — cheap, and an OOM on
                # the next lead can't erase what we just found.
                try:
                    await persist_leads_durably(recent_count=1, source="reenrich")
                except Exception as pe:
                    logger.warning(f"[WATERFALL] per-lead persist failed (non-fatal): {pe}")
            except Exception as e:
                logger.warning(f"[WATERFALL] reenrich update lead {lead.get('id')} failed: {e}")
        # Release the page/soup graph before the next lead.
        dm = None
        _gc.collect()

    logger.info(f"[WATERFALL] reenrich: {summary['upgraded']}/{summary['checked']} upgraded"
                + (f" (stopped: {summary['stopped']})" if summary["stopped"] else ""))
    return summary
