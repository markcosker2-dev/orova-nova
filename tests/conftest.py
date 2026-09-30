import os
import pytest

# Installed before test collection imports main/worker. Verification must not
# inherit credentials from the operator's production-configured local file.
_prior_dotenv_disabled = os.environ.get("PYTHON_DOTENV_DISABLED")
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

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


def pytest_unconfigure(config):
    """Stop idle test workers left by legacy sync/async fixture combinations.

    The assertions finish, but orphaned asyncio and AnyIO worker threads keep
    the interpreter (and CI) open indefinitely. This only runs after tests;
    it does not change the application lifecycle.
    """
    if _prior_dotenv_disabled is None:
        os.environ.pop("PYTHON_DOTENV_DISABLED", None)
    else:
        os.environ["PYTHON_DOTENV_DISABLED"] = _prior_dotenv_disabled
    import concurrent.futures
    import gc
    from anyio._backends._asyncio import WorkerThread

    for obj in gc.get_objects():
        if isinstance(obj, concurrent.futures.ThreadPoolExecutor):
            obj.shutdown(wait=False, cancel_futures=True)
        elif isinstance(obj, WorkerThread) and obj.is_alive():
            obj.stop()
