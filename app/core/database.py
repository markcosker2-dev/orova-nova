"""DatabaseManager — composed from domain-specific repository mixins (A-01).

All public methods remain identical; consuming code requires zero changes.
The class is now assembled from:
  - _DBBase:      connection pool, init, query primitives, shutdown
  - _LeadRepo:    lead CRUD, dedup, cold-lead queries
  - _MetricsRepo:  metrics CRUD, performance stats
  - _StateRepo:    key/value state store
"""
from app.core._db_base import _DBBase, DB_PATH, DATA_DIR, DEFAULT_DATA_DIR  # noqa: F401 — re-exported
from app.core._lead_repo import _LeadRepo
from app.core._metrics_repo import _MetricsRepo
from app.core._state_repo import _StateRepo


class DatabaseManager(_DBBase, _LeadRepo, _MetricsRepo, _StateRepo):
    """Unified database manager — backward-compatible facade over domain repos.

    Method resolution order:
      DatabaseManager → _DBBase, _LeadRepo, _MetricsRepo, _StateRepo

    Every existing call (DatabaseManager.save_lead, .get_metrics, .query, etc.)
    continues to work without modification.
    """
    pass