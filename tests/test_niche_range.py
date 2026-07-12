"""Tests for TARGET_NICHE range parsing (worker._parse_niche_range).

Live hunt 2026-07-12: a broad TARGET_NICHE was being mashed into a single
SerpAPI query (returning generic repair shops) instead of being rotated
through as a list of niches. This pins the split so a comma/semicolon/newline
separated range yields individual niches to rotate one per run.
"""
from app.worker import _parse_niche_range


def test_comma_separated_range_splits():
    got = _parse_niche_range("exotic car dealer california, luxury remodel california, luxury real estate")
    assert got == ["exotic car dealer california", "luxury remodel california", "luxury real estate"]


def test_semicolons_and_newlines_also_split():
    assert _parse_niche_range("a; b\nc") == ["a", "b", "c"]


def test_single_niche_returns_one_item():
    assert _parse_niche_range("exotic car dealer california") == ["exotic car dealer california"]


def test_blank_or_empty_returns_empty_list():
    assert _parse_niche_range("") == []
    assert _parse_niche_range("  ") == []
    assert _parse_niche_range(",, ;\n") == []


def test_whitespace_trimmed_and_blanks_dropped():
    assert _parse_niche_range(" exotic cars ,, , luxury homes ") == ["exotic cars", "luxury homes"]
