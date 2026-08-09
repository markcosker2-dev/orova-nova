"""The CRM workbook must be identified by ID, and never silently replaced.

## The incident (production, 2026-08-09)

Three irreconcilable row counts for one supposed document:

    11:21:21  boot restore read the Leads tab          -> 4 rows
    11:23:48  after 5 appends all returning ok         -> 4 rows
    (owner looking at their own sheet)                 -> 1 row

`sheets_sync` identified the workbook ONLY by title:

    SHEET_NAME = os.getenv("GOOGLE_SHEETS_WORKBOOK", "OROVA CRM")
    return client.open(SHEET_NAME)

`client.open()` asks Drive for a file with that title and takes the first hit.
Google permits duplicate titles, so with two visible to the service account the
target is non-deterministic and can change between restarts.

Worse, the fallback was:

    except Exception:
        return client.create(cache_key)

which minted a NEW spreadsheet of the same title on any transient failure —
owned by the service account, invisible in the owner's Drive. Each blip added
another candidate for the next lookup, so the ambiguity ratcheted. Writes could
land in a document nobody was looking at while reporting success.

`CRM_SHEET_ID` was already declared in .env for exactly this purpose, was empty,
and was referenced by no code at all.
"""
import importlib

import pytest


def _reload_with(monkeypatch, **env):
    """Reimport sheets_sync with the given environment (module-level config)."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import app.skills.sheets_sync as ss
    return importlib.reload(ss)


class _FakeClient:
    """Records how the workbook was requested."""

    def __init__(self, open_ok=True, key_ok=True):
        self.opened_by_key = None
        self.opened_by_title = None
        self.created = []
        self._open_ok = open_ok
        self._key_ok = key_ok

    def open_by_key(self, key):
        self.opened_by_key = key
        if not self._key_ok:
            raise RuntimeError("no such spreadsheet")
        return _FakeWorkbook(id_=key, title="OROVA CRM")

    def open(self, title):
        self.opened_by_title = title
        if not self._open_ok:
            raise RuntimeError("SpreadsheetNotFound")
        return _FakeWorkbook(id_="resolved-by-title", title=title)

    def create(self, title):
        self.created.append(title)
        return _FakeWorkbook(id_="NEWLY-CREATED", title=title)


class _FakeWorkbook:
    def __init__(self, id_, title):
        self.id = id_
        self.title = title

    def worksheet(self, title):
        return _FakeWorksheet()

    def add_worksheet(self, title, rows, cols):
        return _FakeWorksheet()


class _FakeWorksheet:
    def row_values(self, n):
        # Return matching headers so _open_workbook does no header rewrite.
        from app.skills.sheets_sync import WORKSHEET_HEADERS
        return WORKSHEET_HEADERS["Leads"]

    def update(self, *a, **k):
        return None


def _run(ss, client):
    import asyncio
    from unittest.mock import AsyncMock, patch
    ss._workbook_cache = {"wb": None, "ts": 0.0, "key": None}
    with patch.object(ss, "get_sheets_client", AsyncMock(return_value=client)):
        return asyncio.run(ss._open_workbook())


SHEET_ID = "1udNrtV09Y7Eg2bWkU8-5cNbat-8TxZt9ZNoD5j3x-BM"


def test_workbook_is_opened_by_id_when_pinned(monkeypatch):
    """The whole point: a pinned ID removes the duplicate-title ambiguity."""
    ss = _reload_with(monkeypatch, CRM_SHEET_ID=SHEET_ID)
    client = _FakeClient()
    wb = _run(ss, client)
    assert client.opened_by_key == SHEET_ID, "must open by ID, not by title"
    assert client.opened_by_title is None, "must not fall back to a title lookup"
    assert wb.id == SHEET_ID


def test_a_missing_workbook_is_never_silently_recreated(monkeypatch):
    """The ratchet that made backups vanish.

    A transient failure used to mint a second 'OROVA CRM' owned by the service
    account. Failing loudly is correct: a backup written somewhere nobody can
    find is worse than a backup that errors.
    """
    ss = _reload_with(monkeypatch, CRM_SHEET_ID=SHEET_ID)
    client = _FakeClient(key_ok=False)
    wb = _run(ss, client)
    assert wb is None, "a failed open must return None, not a new spreadsheet"
    assert client.created == [], "must NEVER create a replacement workbook"


def test_title_lookup_failure_also_never_creates(monkeypatch):
    """Same guarantee on the unpinned back-compat path."""
    ss = _reload_with(monkeypatch, CRM_SHEET_ID="")
    client = _FakeClient(open_ok=False)
    wb = _run(ss, client)
    assert wb is None
    assert client.created == [], "must NEVER create a replacement workbook"


def test_unpinned_still_works_but_warns(monkeypatch, caplog):
    """Back-compat: no ID configured still resolves, but says it is ambiguous."""
    ss = _reload_with(monkeypatch, CRM_SHEET_ID="")
    client = _FakeClient()
    with caplog.at_level("WARNING"):
        wb = _run(ss, client)
    assert wb is not None
    assert client.opened_by_title == ss.SHEET_NAME
    assert "CRM_SHEET_ID is unset" in caplog.text
    assert "resolved title" in caplog.text, "must name the id it actually resolved to"


def test_the_resolved_spreadsheet_id_is_logged(monkeypatch, caplog):
    """'The write is lying' must be checkable, not inferred.

    Logging the id the process actually used lets the owner compare it against
    the id in their browser URL — which is the single observation that
    distinguishes a broken write from a write landing in another document.
    """
    ss = _reload_with(monkeypatch, CRM_SHEET_ID=SHEET_ID)
    client = _FakeClient()
    with caplog.at_level("INFO"):
        _run(ss, client)
    assert SHEET_ID in caplog.text
