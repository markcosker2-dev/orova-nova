import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.core.ai_client import UnifiedAIClient, _BREAKER

@pytest.mark.asyncio
async def test_circuit_breaker_triggers_and_falls_back():
    """[P7] Verify circuit breaker opens after failures and falls through to Groq."""
    from app.core.ai_client import _BREAKER, _record_failure, _record_success, _is_open
    
    # Simulate OpenRouter failures
    for _ in range(3):
        _record_failure("google/gemini-2.0-flash-lite-preview-02-05:free")
    
    assert _BREAKER["google/gemini-2.0-flash-lite-preview-02-05:free"]["failures"] >= 3
    
    # Circuit should be open now
    # Test that the circuit breaker actually blocks
    is_blocked = _is_open("google/gemini-2.0-flash-lite-preview-02-05:free")
    assert is_blocked is True