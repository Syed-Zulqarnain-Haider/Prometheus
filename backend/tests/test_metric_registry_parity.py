"""Drift guard: the backend metric registry MUST match the sync job's copy.

CLAUDE.md names backend/app/core/metric_registry.py the single source of truth,
while the sync job ships its own sync/metric_registry.py. This test fails if the
two ever diverge in columns, types, groups, or ordering — so they cannot silently
drift apart.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

from app.core.metric_registry import COLUMN_NAMES as BACKEND_COLUMN_NAMES
from app.core.metric_registry import REGISTRY as BACKEND_REGISTRY
from app.core.metric_registry import Group as BackendGroup


def _load_sync_registry() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "sync" / "metric_registry.py"
    spec = importlib.util.spec_from_file_location("sync_metric_registry", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _as_tuples(registry: list) -> list[tuple[str, str, str, str]]:
    return [(c.name, c.bq_type, c.pg_type, c.group.value) for c in registry]


def test_registry_columns_match_sync() -> None:
    sync = _load_sync_registry()
    assert _as_tuples(BACKEND_REGISTRY) == _as_tuples(sync.REGISTRY)


def test_column_names_match_sync() -> None:
    sync = _load_sync_registry()
    assert BACKEND_COLUMN_NAMES == sync.COLUMN_NAMES


def test_group_enum_matches_sync() -> None:
    sync = _load_sync_registry()
    backend_groups = {g.name: g.value for g in BackendGroup}
    sync_groups = {g.name: g.value for g in sync.Group}
    assert backend_groups == sync_groups


def test_registry_has_78_columns() -> None:
    # 77 view columns + _built_at system column.
    assert len(BACKEND_REGISTRY) == 78
