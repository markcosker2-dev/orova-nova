"""Status writes must not trust sheet IDs reused after Render restarts."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.skills import sheets_sync


def _row(lead_id, business, state="WA"):
    return [str(lead_id), business] + [""] * 11 + [state]


def test_status_update_uses_business_and_state_not_recycled_id():
    ws = MagicMock()
    ws.get_all_values.return_value = [
        _row("ID", "Business", "State"),
        _row(76, "Unrelated Builder"),
        _row(80, "Target Builder"),
    ]
    with patch.object(sheets_sync, "_get_worksheet", AsyncMock(return_value=ws)), \
         patch("app.core.database.DatabaseManager.fetchone", new_callable=AsyncMock,
               return_value={"business": "Target Builder", "url": "", "state": "WA"}):
        result = asyncio.run(sheets_sync.sync_lead_status_to_sheets(76, "Contacted"))
    assert result == {"ok": True, "row": 3, "status": "Contacted"}
    assert ws.update_cell.call_args.args[0] == 3


def test_ambiguous_business_does_not_change_any_row():
    ws = MagicMock()
    ws.get_all_values.return_value = [
        _row("ID", "Business", "State"),
        _row(76, "Target Builder"),
        _row(80, "Target Builder"),
    ]
    with patch.object(sheets_sync, "_get_worksheet", AsyncMock(return_value=ws)), \
         patch("app.core.database.DatabaseManager.fetchone", new_callable=AsyncMock,
               return_value={"business": "Target Builder", "url": "", "state": "WA"}):
        result = asyncio.run(sheets_sync.sync_lead_status_to_sheets(76, "Contacted"))
    assert result == {"ok": False, "reason": "lead_not_found_or_ambiguous"}
    ws.update_cell.assert_not_called()
