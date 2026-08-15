"""Successive hunts must reach new contractors, not re-read page one.

The WA L&I query's WHERE clause is fixed (active construction contractors,
GENERAL/RESIDENTIAL, in the metro city list, licensed 3-25 years) and its ORDER
is deterministic — and it had no `$offset`. So every hunt fetched THE SAME first
`fetch` rows, forever.

Live 2026-08-14: five consecutive hunts across five different `location` values
returned the same five businesses and added zero leads. The lead count sat at 14
while 8,768 contractors passed the identical filter, unreachable. The one-off
10 -> 14 growth earlier that day came from CHANGING the filter, not from hunting
again — which is why it looked like discovery worked.

`location` and `niche` never appear in the WHERE clause at all, so varying them
changes nothing. Pagination is the only thing that moves the hunt forward.

A cursor in DB state advances one page per run and rewinds on a short page.
It resets on deploy (state is not restored from Sheets — "leads only"), which
just re-walks from the start; dedup absorbs the repeat and the backfill turns a
re-read into a repair.
"""
import asyncio

import pytest

from app.skills import lead_gen_v3 as v3


class _FakeState:
    """Stands in for DatabaseManager's state row."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.writes = []

    async def get_state(self, key, default=None):
        return self.store.get(key, default)

    async def set_state(self, key, value):
        self.store[key] = value
        self.writes.append((key, value))


@pytest.fixture
def state(monkeypatch):
    fake = _FakeState()
    import app.core.database as db
    monkeypatch.setattr(db, "DatabaseManager", fake)
    return fake


def test_the_first_hunt_starts_at_the_beginning(state):
    assert asyncio.run(v3._next_wa_offset(200)) == 0


def test_each_hunt_advances_a_page(state):
    first = asyncio.run(v3._next_wa_offset(200))
    second = asyncio.run(v3._next_wa_offset(200))
    third = asyncio.run(v3._next_wa_offset(200))
    assert [first, second, third] == [0, 200, 400], (
        "five hunts returned the same five businesses because the cursor never moved"
    )


def test_the_cursor_is_persisted_for_the_next_run(state):
    asyncio.run(v3._next_wa_offset(200))
    assert state.store[v3._WA_LNI_OFFSET_KEY] == 200


def test_a_walked_out_register_rewinds(state):
    asyncio.run(v3._next_wa_offset(200))
    asyncio.run(v3._reset_wa_offset())
    assert asyncio.run(v3._next_wa_offset(200)) == 0, (
        "paging off the end must not leave the hunt permanently silent"
    )


def test_a_runaway_cursor_is_clamped(state):
    state.store[v3._WA_LNI_OFFSET_KEY] = v3._WA_LNI_MAX_OFFSET + 1
    assert asyncio.run(v3._next_wa_offset(200)) == 0, (
        "Socrata refuses large offsets; wrap rather than hunt into an error"
    )


def test_a_negative_cursor_is_clamped(state):
    state.store[v3._WA_LNI_OFFSET_KEY] = -50
    assert asyncio.run(v3._next_wa_offset(200)) == 0


def test_an_unreadable_cursor_degrades_to_page_one_not_to_no_hunt(monkeypatch):
    """Fail-open. A broken cursor must never stop the hunt."""
    class _Broken:
        async def get_state(self, *a, **k):
            raise RuntimeError("state unavailable")

        async def set_state(self, *a, **k):
            raise RuntimeError("state unavailable")

    import app.core.database as db
    monkeypatch.setattr(db, "DatabaseManager", _Broken())
    assert asyncio.run(v3._next_wa_offset(200)) == 0
