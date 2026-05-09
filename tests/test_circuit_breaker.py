import pytest
import asyncio
from unittest.mock import AsyncMock, patch
# Assuming this is where UnifiedAIClient lives
from app.core.ai_client import UnifiedAIClient

@pytest.mark.asyncio
async def test_circuit_breaker_triggers_and_falls_back():
    """
    [P7] Verify the state machine:
    3 failures -> Circuit OPEN -> 4th call immediately hits Fallback.
    """
    # Mocking the primary provider call
    with patch("app.core.ai_client.UnifiedAIClient._call_primary", new_callable=AsyncMock) as mock_primary, \
         patch("app.core.ai_client.UnifiedAIClient._call_fallback", new_callable=AsyncMock) as mock_fallback:
        
        mock_primary.side_effect = Exception("HTTP 500 Internal Server Error")
        mock_fallback.return_value = "Safe Fallback Response"
        
        client = UnifiedAIClient()
        
        # 1. Simulate 3 consecutive failures
        for _ in range(3):
            try:
                await client.chat([{"role": "user", "content": "test"}])
            except:
                pass
        
        # 2. Check if circuit is open (failures >= threshold)
        from app.core.ai_client import _BREAKER
        # OpenRouter is the default provider in ai_client.py
        assert _BREAKER["openrouter"]["failures"] >= 3
        
        # 3. Check if 4th call immediately routes to Fallback without hitting Primary
        mock_primary.reset_mock()
        res = await client.chat([{"role": "user", "content": "test"}])
        
        mock_primary.assert_not_called()
        mock_fallback.assert_called()
        assert res == "Safe Fallback Response"
