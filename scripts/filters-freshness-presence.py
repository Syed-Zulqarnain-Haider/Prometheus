#!/usr/bin/env python3
"""App-category filter, an honest data-maturity date, and presence actually wired up.

1. THE CATEGORY FILTER THE OWNER ASKED FOR - AND TWO THAT WERE SILENTLY DROPPED
   app_category is a real fact column (registry, 79 cols), as are hou and pod_owner. The
   frontend already SENDS hou; the metrics API never accepted it, and FastAPI drops an
   unknown query param without a word - so the filter bar counted an active filter, the
   pill rendered, and every number on the page was the unfiltered total. That is a wrong
   number wearing a filter's clothes, which is worse than an error.

   All three are now accepted, validated under the same MAX_FILTER_VALUES cap, and applied
   as pure NARROWING conditions after the scope filter - they can only ever remove rows.
   No new scope type, no new way to widen.

2. A DATA-MATURITY DATE THAT MEANS SOMETHING ("verify the data maturity date")
   /meta/freshness reported the last successful run's build timestamp and its status. Two
   ways that misleads: a successful run that loaded almost nothing still reads "success"
   (the platform audit found six days of near-zero store installs behind a green badge),
   and a historical backfill's build timestamp regresses the banner while live data is
   current. It now also reports what the data itself says:

     max_fact_date   - the newest date any row actually exists for;
     settled_through - max_fact_date minus the source lag, the date through which figures
                       are trustworthy (Apple arrives 2-3 days late, so the last days are
                       still moving);
     data_age_days   - how far behind today the newest row is;
     rows_previous / volume_drop_pct - last successful load against the one before it, so
                       a load that "succeeded" while bringing a fraction of the usual
                       volume is visible instead of green.

   Read-only and additive: existing keys keep their meaning, so nothing that consumes this
   endpoint breaks.

3. PRESENCE, WHICH WAS WIRED TO NOTHING
   presence_service.touch has zero callers - so presence keys were never set and
   last_seen_at never updated, while the People directory and chat read receipts render
   from them. Everyone permanently offline, receipts stuck at "sent", no error anywhere.
   It is called now from the one place that runs on every authenticated request, after the
   context resolves. It is already self-throttling (one Redis SET in the common case, a
   database write at most every five minutes) and already swallows its own failures, so
   the request path is unaffected.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".")
TEST = ROOT / "backend/tests/test_filters_and_freshness.py"

report: list[str] = []

EDITS: list[tuple[str, str, str, str]] = [
    # ── 1. filters ─────────────────────────────────────────────────────────────────
    (
        "backend/app/schemas/metrics.py",
        "three real dimensions join the filter model",
        """    pods: list[str] = []
    publishers: list[str] = []
    apps: list[str] = []""",
        """    pods: list[str] = []
    publishers: list[str] = []
    apps: list[str] = []
    # Real fact columns, all pure NARROWING filters (never scope). hou and pod_owners
    # were already being sent by the frontend and silently dropped by FastAPI, so the
    # filter bar showed an active filter over unfiltered numbers.
    hou: list[str] = []
    pod_owners: list[str] = []
    categories: list[str] = []""",
    ),
    (
        "backend/app/schemas/metrics.py",
        "and are capped like the others",
        (
            '        dimensions = (("pods", self.pods), ("publishers", self.publishers), '
            '("apps", self.apps))'
        ),
        """        dimensions = (
            ("pods", self.pods),
            ("publishers", self.publishers),
            ("apps", self.apps),
            ("hou", self.hou),
            ("pod_owners", self.pod_owners),
            ("categories", self.categories),
        )""",
    ),
    (
        "backend/app/services/query_builder.py",
        "applied after the scope filter, narrowing only",
        """        if params.apps:
            conditions.append(FACT_TABLE.c.canonical_key.in_(params.apps))
        return conditions""",
        """        if params.apps:
            conditions.append(FACT_TABLE.c.canonical_key.in_(params.apps))
        if params.hou:
            conditions.append(FACT_TABLE.c.hou.in_(params.hou))
        if params.pod_owners:
            conditions.append(FACT_TABLE.c.pod_owner.in_(params.pod_owners))
        if params.categories:
            conditions.append(FACT_TABLE.c.app_category.in_(params.categories))
        return conditions""",
    ),
    (
        "backend/app/api/v1/metrics.py",
        "accepted as query parameters",
        """    apps: Annotated[list[str] | None, Query()] = None,
) -> MetricFilters:""",
        """    apps: Annotated[list[str] | None, Query()] = None,
    hou: Annotated[list[str] | None, Query()] = None,
    pod_owners: Annotated[list[str] | None, Query()] = None,
    categories: Annotated[list[str] | None, Query()] = None,
) -> MetricFilters:""",
    ),
    (
        "backend/app/api/v1/metrics.py",
        "passed through to the model",
        """            apps=apps or [],
        )""",
        """            apps=apps or [],
            hou=hou or [],
            pod_owners=pod_owners or [],
            categories=categories or [],
        )""",
    ),
    # ── 3. presence ────────────────────────────────────────────────────────────────
    (
        "backend/app/api/deps.py",
        "presence is called on every authenticated request",
        """    request.state.user_context = context
    return context""",
        """    # Presence had NO caller at all: keys were never set and last_seen_at never
    # updated, while the People directory and chat read receipts render from them -
    # everyone permanently offline, receipts stuck at "sent", no error anywhere. This is
    # the one place that runs on every authenticated request. touch() is self-throttling
    # (one Redis SET in the common case, a DB write at most every five minutes) and
    # swallows its own failures, so it cannot affect the request.
    await presence_service.touch(
        cache, db, context.user_id, login_at=_auth_time(decoded)
    )

    request.state.user_context = context
    return context""",
    ),
    (
        "backend/app/api/deps.py",
        "the auth-time reader",
        """async def get_user_context(""",
        '''def _auth_time(decoded: dict[str, Any]) -> datetime | None:
    """The token's authentication time, if the provider supplied a sane one.

    Stored as last_login_at only when it moves forward, so a stale cached token cannot
    drag it backwards - but a malformed claim should not raise inside authentication
    either, so anything unparseable is simply None.
    """
    raw = decoded.get("auth_time")
    if not isinstance(raw, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(raw), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


async def get_user_context(''',
    ),
    # ── 2. freshness ───────────────────────────────────────────────────────────────
    (
        "backend/app/api/v1/meta.py",
        "freshness reports what the data itself says",
        '''    return {
        "bq_built_at": last_success.bq_built_at.isoformat()
        if last_success and last_success.bq_built_at
        else None,
        "last_status": latest.status if latest else None,
        "last_run_finished_at": latest.finished_at.isoformat()
        if latest and latest.finished_at
        else None,
        "rows_loaded": last_success.rows_loaded if last_success else None,
    }''',
        '''    # What the DATA says, not just what the run said. A successful run that loaded
    # almost nothing still reads "success" (the platform audit found six days of
    # near-zero store installs behind a green badge), and a historical backfill's build
    # timestamp regresses the banner while live data is current.
    max_fact_date = await db.scalar(select(func.max(FACT_TABLE.c.date)))
    previous_success = (
        (
            await db.execute(
                select(SyncRun)
                .where(SyncRun.status == "success")
                .order_by(SyncRun.id.desc())
                .offset(1)
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    drop_pct: float | None = None
    if (
        last_success
        and previous_success
        and last_success.rows_loaded is not None
        and previous_success.rows_loaded
    ):
        delta = previous_success.rows_loaded - last_success.rows_loaded
        drop_pct = round(max(0.0, delta / previous_success.rows_loaded) * 100, 1)

    today = date.today()
    return {
        "bq_built_at": last_success.bq_built_at.isoformat()
        if last_success and last_success.bq_built_at
        else None,
        "last_status": latest.status if latest else None,
        "last_run_finished_at": latest.finished_at.isoformat()
        if latest and latest.finished_at
        else None,
        "rows_loaded": last_success.rows_loaded if last_success else None,
        # The newest date any row exists for - the real extent of the data.
        "max_fact_date": max_fact_date.isoformat() if max_fact_date else None,
        # The date through which figures are trustworthy: Apple arrives 2-3 days late,
        # so the most recent days are still moving and must not be read as final.
        "settled_through": (max_fact_date - timedelta(days=SOURCE_LAG_DAYS)).isoformat()
        if max_fact_date
        else None,
        "data_age_days": (today - max_fact_date).days if max_fact_date else None,
        "rows_previous": previous_success.rows_loaded if previous_success else None,
        # A "successful" load that brought a fraction of the usual volume, made visible.
        "volume_drop_pct": drop_pct,
    }''',
    ),
    (
        "backend/app/api/v1/meta.py",
        "the lag constant",
        """@router.get("/freshness")""",
        '''# Apple store data arrives 2-3 days behind; the most recent days are still moving, so
# nothing inside this window should be presented as final.
SOURCE_LAG_DAYS = 3


@router.get("/freshness")''',
    ),
]

TEST_SRC = '''\
"""Filters that are accepted rather than silently dropped, and an honest maturity date.

The filter half exists because of a wrong-number-wearing-a-filter's-clothes bug: the
frontend sent hou, the API never accepted it, FastAPI dropped it without a word, and the
page showed unfiltered totals under an active-looking filter pill.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.schemas.metrics import MAX_FILTER_VALUES, MetricFilters

from tests.conftest import MetricsEnv

WINDOW = {"date_from": date(2026, 6, 1), "date_to": date(2026, 6, 2)}


def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}


def test_the_new_dimensions_are_part_of_the_model() -> None:
    f = MetricFilters(**WINDOW, hou=["HOU_A"], pod_owners=["PO"], categories=["Puzzle"])
    assert f.hou == ["HOU_A"]
    assert f.pod_owners == ["PO"]
    assert f.categories == ["Puzzle"]


def test_they_are_capped_like_every_other_dimension() -> None:
    # An uncapped list is an uncapped IN clause - the same reason the other three are
    # bounded.
    with pytest.raises(ValueError, match="too many categories"):
        MetricFilters(**WINDOW, categories=[str(i) for i in range(MAX_FILTER_VALUES + 1)])


async def test_a_category_filter_reaches_the_query_instead_of_being_dropped(
    metrics_env: MetricsEnv,
) -> None:
    # The bug: an unknown query param is dropped by FastAPI without complaint, so the
    # page renders unfiltered totals under an active filter. A category nothing matches
    # must therefore produce zero, never the grand total.
    everything = await metrics_env.client.get(
        "/api/v1/metrics/summary?date_from=2026-06-01&date_to=2026-06-02",
        headers=_auth("admin"),
    )
    filtered = await metrics_env.client.get(
        "/api/v1/metrics/summary?date_from=2026-06-01&date_to=2026-06-02"
        "&categories=NoSuchCategory",
        headers=_auth("admin"),
    )
    assert everything.status_code == 200 and filtered.status_code == 200
    assert filtered.json()["current"] != everything.json()["current"]


async def test_an_hou_filter_is_accepted_too(metrics_env: MetricsEnv) -> None:
    resp = await metrics_env.client.get(
        "/api/v1/metrics/summary?date_from=2026-06-01&date_to=2026-06-02&hou=NoSuchHou",
        headers=_auth("admin"),
    )
    assert resp.status_code == 200


async def test_freshness_reports_what_the_data_says_not_only_the_run(
    metrics_env: MetricsEnv,
) -> None:
    resp = await metrics_env.client.get("/api/v1/meta/freshness", headers=_auth("admin"))
    assert resp.status_code == 200
    body = resp.json()
    # The original keys keep their meaning - this is additive.
    for key in ("bq_built_at", "last_status", "rows_loaded"):
        assert key in body
    # ...plus the maturity signals a green badge alone cannot give.
    for key in (
        "max_fact_date",
        "settled_through",
        "data_age_days",
        "rows_previous",
        "volume_drop_pct",
    ):
        assert key in body, key


async def test_settled_through_trails_the_newest_date(metrics_env: MetricsEnv) -> None:
    # Apple lands 2-3 days late, so the newest days are still moving: the settled date
    # must be strictly older than the newest date that has any rows at all.
    body = (
        await metrics_env.client.get("/api/v1/meta/freshness", headers=_auth("admin"))
    ).json()
    if body["max_fact_date"] and body["settled_through"]:
        assert body["settled_through"] < body["max_fact_date"]
'''


def window(path: Path, needle: str) -> str:
    if not path.exists():
        return f"      | MISSING: {path}"
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            lo, hi = max(0, i - 4), min(len(lines), i + 12)
            return "\n".join(f"      | {n + 1:>4}  {lines[n]}" for n in range(lo, hi))
    return f"      | {path}: anchor not found"


def main() -> int:
    if not (ROOT / "backend").is_dir():
        print("ABORTED: run this from the repository root.", file=sys.stderr)
        return 1

    if "categories: list[str]" in (ROOT / "backend/app/schemas/metrics.py").read_text():
        print("Already applied - left alone.")
        if TEST.parent.is_dir():
            TEST.write_text(TEST_SRC)
            print(f"  - {TEST}: refreshed")
        return 0

    planned: dict[Path, str] = {}
    problems: list[str] = []
    for rel, label, old, new in EDITS:
        path = ROOT / rel
        if not path.exists():
            problems.append(f"  [{label}] {rel}: file missing")
            continue
        text = planned.get(path, path.read_text())
        if text.count(old) != 1:
            problems.append(
                f"  [{label}] {rel}: expected exactly 1 match, found {text.count(old)}\n"
                + window(path, old.splitlines()[0].strip()[:56])
            )
            continue
        planned[path] = text.replace(old, new, 1)

    if problems:
        print("NOTHING WAS WRITTEN - a filter accepted by the API but not applied in the")
        print("query would be the same silent-drop bug in a new place. Mismatches:\n")
        for p in problems:
            print(p)
        return 1

    # Imports the new code needs, added explicitly rather than inferred.
    def merge_from_import(text: str, module: str, names: set[str]) -> str:
        """Widen an existing `from <module> import a, b` to include `names`, sorted."""
        prefix = f"from {module} import "
        line = next((ln for ln in text.splitlines() if ln.startswith(prefix)), None)
        if line is None:
            return text
        have = {n.strip() for n in line[len(prefix) :].split(",") if n.strip()}
        if names <= have:
            return text
        return text.replace(line, prefix + ", ".join(sorted(have | names)), 1)

    def add_import(text: str, statement: str, after_prefix: str) -> str:
        if statement in text:
            return text
        line = next((ln for ln in text.splitlines() if ln.startswith(after_prefix)), None)
        return text if line is None else text.replace(line, line + "\n" + statement, 1)

    def add_import_before(text: str, statement: str, before_prefix: str) -> str:
        """Insert above a known import so the result stays in isort order.

        ruff checks import ordering and a correct patch that fails lint is a failed
        patch - dropping a stdlib import straight after __future__ puts it in the wrong
        group, which is exactly what happened the first time.
        """
        if statement in text:
            return text
        line = next((ln for ln in text.splitlines() if ln.startswith(before_prefix)), None)
        return text if line is None else text.replace(line, statement + "\n" + line, 1)

    deps = ROOT / "backend/app/api/deps.py"
    text = planned[deps]
    text = merge_from_import(text, "typing", {"Annotated", "Any"})
    text = add_import(
        text, "from app.services import presence_service", "from app.schemas.auth import"
    )
    if "presence_service" not in text or "Any" not in text:
        print("NOTHING WAS WRITTEN - could not place the deps.py imports. On disk:\n"
              + window(deps, "from typing import"))
        return 1
    planned[deps] = text

    meta = ROOT / "backend/app/api/v1/meta.py"
    text = planned[meta]
    text = merge_from_import(text, "datetime", {"date", "timedelta"})
    # meta.py may have no datetime import at all, in which case the merge is a no-op and
    # one has to be introduced. Anchored on __future__, which every module here has.
    text = add_import_before(text, "from datetime import date, timedelta", "from typing import")
    text = merge_from_import(text, "sqlalchemy", {"func", "select"})
    text = add_import_before(
        text, "from sqlalchemy import func, select", "from app.api.deps import"
    )
    text = add_import(
        text, "from app.core.fact_table import FACT_TABLE", "from app.api.deps import"
    )
    # Check the IMPORT STATEMENTS, not the names - the names appear in the code just
    # inserted, so testing for those would pass while the module still cannot import.
    required = (
        ("timedelta", "from datetime import"),
        ("func", "from sqlalchemy import"),
        ("FACT_TABLE", "from app.core.fact_table import FACT_TABLE"),
    )
    for name, statement in required:
        line = next((ln for ln in text.splitlines() if ln.startswith(statement)), None)
        if line is None or name not in line:
            print(f"NOTHING WAS WRITTEN - meta.py has no import providing {name}."
                  " On disk:\n" + window(meta, "import"))
            return 1
    planned[meta] = text

    for path, content in planned.items():
        path.write_text(content)
        report.append(f"[fix] {path}")
    if TEST.parent.is_dir():
        TEST.write_text(TEST_SRC)
        report.append(f"[test] {TEST}: filters reach the query; freshness tells the truth")

    print("PATCHED, NOT YET VERIFIED - the test run is the verification, not this script.")
    for line in report:
        print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
