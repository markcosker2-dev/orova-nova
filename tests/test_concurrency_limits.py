"""Concurrency limits have exactly one owner (audit B1, 2026-07-26).

app/core/semaphore.py declared itself "the single source of truth for all
RAM-heavy skill concurrency control. Ensures Render (512MB RAM) is protected
from OOM kills" — and was imported by NOTHING, while three call sites each
hard-coded their own magic number. There is live history of an OOM kill wiping
the disk mid-run, so the guard that was meant to prevent a repeat was inert.

It was removed rather than adopted: a process-wide limit of 1 would serialise
lanes past Render's 30s request kill, and would deadlock wherever one guarded
coroutine awaits another (enrich_lead_lite -> _fetch_page). memory_monitor in
hardening.py is the canonical resource guard — it measures real RSS and is what
the re-enrich lane checks — so the fan-out caps now live beside it.
"""
import ast
import pathlib
import re

import pytest

from app.core.hardening import CONCURRENCY_LIMITS, concurrency_limit

REPO = pathlib.Path(__file__).resolve().parent.parent


# ─── The removed module stays removed ────────────────────────────

def test_the_unused_global_semaphore_module_is_gone():
    assert not (REPO / "app" / "core" / "semaphore.py").exists(), (
        "app/core/semaphore.py was removed as a redundant second owner of "
        "concurrency control; reintroducing it recreates the divergence"
    )


def test_nothing_imports_the_removed_module():
    for path in (REPO / "app").rglob("*.py"):
        src = path.read_text(encoding="utf-8", errors="replace")
        assert "core.semaphore" not in src and "core import semaphore" not in src, \
            f"{path} references the removed semaphore module"


# ─── One owner for the numbers ───────────────────────────────────

@pytest.mark.parametrize("name", ["page_crawl", "lead_enrich", "lead_enrich_batch"])
def test_every_named_limit_resolves(name):
    assert concurrency_limit(name) >= 1


def test_unknown_limit_fails_safe_to_one():
    # On a 512MB tier the safe direction is fewer, never unbounded.
    assert concurrency_limit("no-such-operation") == 1


def test_no_call_site_hard_codes_its_own_semaphore_number():
    """The actual drift this fixes: three modules each carrying a magic number.
    Any asyncio.Semaphore(<literal>) in app/skills is a regression."""
    offenders = []
    for path in (REPO / "app" / "skills").rglob("*.py"):
        src = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"Semaphore\(\s*(\d+)\s*\)", src):
            line = src[:m.start()].count("\n") + 1
            offenders.append(f"{path.name}:{line} -> Semaphore({m.group(1)})")
    assert not offenders, (
        "hard-coded concurrency limits found; use "
        "hardening.concurrency_limit(name) instead: " + "; ".join(offenders))


# ─── The crawl cap must actually bind ────────────────────────────

def test_crawl_limit_binds_against_the_real_page_list():
    """It was 10 while light_enrich builds [homepage] + prioritized[:4] — at most
    5 pages, or 7 on the hard-coded fallback path. A cap above the list size
    never blocks, so the 'guard' guarded nothing."""
    src = (REPO / "app" / "skills" / "light_enrich.py").read_text(
        encoding="utf-8", errors="replace")
    fallback_paths = re.search(
        r'for path in \[([^\]]*)\]:\s*\n\s*pages_to_crawl\.append', src)
    assert fallback_paths, "fallback page list not found — update this test"
    max_pages = 1 + fallback_paths.group(1).count('"') // 2   # homepage + fallbacks
    assert CONCURRENCY_LIMITS["page_crawl"] < max_pages, (
        f"page_crawl={CONCURRENCY_LIMITS['page_crawl']} does not bind a list of "
        f"up to {max_pages} pages — it would never block")


def test_limits_are_sane_for_a_512mb_tier():
    for name, value in CONCURRENCY_LIMITS.items():
        assert 1 <= value <= 8, f"{name}={value} is implausible for 512MB"


# ─── Collection config (audit B4) ────────────────────────────────

def test_pytest_only_collects_the_tests_directory():
    """Root-level test_*.py files are manual smoke scripts: test_auth.py fires
    httpx calls at localhost as an import side effect. Bare `pytest` must not
    collect them, so local runs match CI."""
    cfg = (REPO / "pytest.ini").read_text(encoding="utf-8")
    assert re.search(r"^testpaths\s*=\s*tests\s*$", cfg, re.M), \
        "pytest.ini must restrict collection to tests/"
