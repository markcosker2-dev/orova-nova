import os
import pytest

# Keep tests deterministic and offline: firewall goal alignment falls back to
# the keyword heuristic instead of calling the embedding API.
os.environ.setdefault("FIREWALL_SEMANTIC_ALIGNMENT", "0")


@pytest.fixture(autouse=True)
def funded_workflow_test_mode(monkeypatch):
    # Historical tests exercise funded/automated paths with mocked providers.
    # Production defaults are $0 and no CEO auto-execution; the repair suite
    # explicitly tests those defaults as well as blocked network side effects.
    monkeypatch.setenv("ZERO_BUDGET_MODE", "0")
    monkeypatch.setenv("CEO_AUTO_EXECUTE", "1")
