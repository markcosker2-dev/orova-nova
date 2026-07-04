"""Regression tests for two latent bugs found in the skill health audit
(vault/20-ops/sessions/2026-07-04-skill-health-audit.md):

1. gmail_skill.process_incoming_email used `logger` without importing logging
   → NameError on every hard-bounce.
2. sheets_sync.sync_lead_outcome_to_sheets read `.value` off an un-awaited
   asyncio.to_thread(...) coroutine → AttributeError on the notes path.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock

from app.skills import gmail_skill, sheets_sync


def test_gmail_bounce_path_no_nameerror():
    """A bounce email must be handled (and logged) without NameError."""
    email = {
        "subject": "Delivery Status Notification (Failure)",
        "body": "Your message to dead@example.com could not be delivered.",
    }
    with patch.object(gmail_skill, "DatabaseManager") as mock_db:
        mock_db.blacklist_lead = AsyncMock()
        res = asyncio.run(gmail_skill.process_incoming_email(email, client_id=0))
    assert res == {"status": "ignored", "reason": "hard_bounce"}
    mock_db.blacklist_lead.assert_awaited_once_with("dead@example.com")


def test_gmail_non_bounce_passes_through():
    res = asyncio.run(gmail_skill.process_incoming_email({"subject": "Hello!"}, client_id=0))
    assert res == {"status": "ok"}


def test_sheets_outcome_notes_path_awaits_cell():
    """The notes branch must await the cell lookup before reading .value."""
    ws = MagicMock()
    ws.col_values.return_value = ["ID", "5"]           # header + our lead at row 2
    ws.cell.return_value = SimpleNamespace(value="prior note")
    ws.update_cell.return_value = None
    with patch.object(sheets_sync, "_get_worksheet", AsyncMock(return_value=ws)):
        res = asyncio.run(sheets_sync.sync_lead_outcome_to_sheets(
            lead_id=5, action="email_sent", result="sent", details="follow-up",
        ))
    assert res == {"ok": True, "row": 2}
    # The cell was fetched (awaited) and its value fed into the appended note.
    ws.cell.assert_called_once()
    appended = ws.update_cell.call_args_list[-1].args[-1]
    assert "prior note" in appended and "follow-up" in appended
