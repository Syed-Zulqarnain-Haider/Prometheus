"""Unit tests for the aggregate cache: daily-boundary TTL and permission-aware keys."""

from datetime import UTC, datetime

from app.core.cache import (
    AGG_TTL_GRACE_SECONDS,
    AGG_TTL_MAX_SECONDS,
    AGG_TTL_MIN_SECONDS,
    REBUILD_HOUR_UTC,
    REBUILD_MINUTE_UTC,
    aggregate_cache_key,
    aggregate_ttl_seconds,
    perms_token,
    scope_token,
    seconds_until_next_rebuild,
)
from app.schemas.auth import ScopeOut

_BOUNDARY_SECS = REBUILD_HOUR_UTC * 3600 + REBUILD_MINUTE_UTC * 60  # 05:16 → 19_560s


# ── TTL aligns to the next daily rebuild boundary ────────────────────────────
def test_seconds_until_next_rebuild_before_boundary() -> None:
    now = datetime(2026, 6, 22, 1, 0, tzinfo=UTC)  # 01:00, before 05:16
    assert seconds_until_next_rebuild(now) == _BOUNDARY_SECS - 3600


def test_seconds_until_next_rebuild_rolls_to_next_day_after_boundary() -> None:
    now = datetime(2026, 6, 22, 6, 0, tzinfo=UTC)  # 06:00, after 05:16
    assert seconds_until_next_rebuild(now) == 24 * 3600 - (6 * 3600 - _BOUNDARY_SECS)


def test_ttl_lets_entry_survive_until_just_past_next_rebuild() -> None:
    # An entry created just after the rebuild should live ~a full day (capped) so it
    # reaches the next rebuild rather than expiring mid-day and forcing a cold recompute.
    now = datetime(2026, 6, 22, 6, 0, tzinfo=UTC)
    ttl = aggregate_ttl_seconds(now)
    assert ttl == min(seconds_until_next_rebuild(now) + AGG_TTL_GRACE_SECONDS, AGG_TTL_MAX_SECONDS)
    assert AGG_TTL_MIN_SECONDS <= ttl <= AGG_TTL_MAX_SECONDS


def test_ttl_just_before_boundary_is_grace_plus_remaining() -> None:
    now = datetime(2026, 6, 22, 5, 15, tzinfo=UTC)  # 1 min before 05:16
    assert aggregate_ttl_seconds(now) == 60 + AGG_TTL_GRACE_SECONDS


def test_ttl_is_much_longer_than_the_old_fixed_minutes() -> None:
    # Regression intent: cached aggregates must live hours, not minutes.
    now = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
    assert aggregate_ttl_seconds(now) >= 3 * 60 * 60


# ── Cache key isolates permission profiles (defence in depth) ────────────────
def test_cache_key_varies_by_permitted_groups() -> None:
    scope = scope_token([ScopeOut(scope_type="all", scope_value=None)])
    params = {"date_from": "2026-06-01", "date_to": "2026-06-30"}
    full = aggregate_cache_key(
        "metrics.summary", scope, perms_token(["store_installs", "ua_spend"]), params
    )
    limited = aggregate_cache_key("metrics.summary", scope, perms_token(["store_installs"]), params)
    assert full != limited  # same scope + params, different perms → different entries


def test_cache_key_same_for_same_inputs() -> None:
    scope = scope_token([ScopeOut(scope_type="all", scope_value=None)])
    perms = perms_token(["store_installs", "ua_spend"])
    params = {"date_from": "2026-06-01", "date_to": "2026-06-30"}
    assert aggregate_cache_key("metrics.summary", scope, perms, params) == aggregate_cache_key(
        "metrics.summary", scope, perms, params
    )


def test_perms_token_is_order_independent() -> None:
    assert perms_token(["ua_spend", "store_installs"]) == perms_token(
        ["store_installs", "ua_spend"]
    )
