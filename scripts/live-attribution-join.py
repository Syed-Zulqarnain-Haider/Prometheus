#!/usr/bin/env python3
"""Resolve pod / pod_owner / hou / publisher from App Master, live, for all history.

THE PROBLEM. The fact table carries its OWN copy of those four columns, baked in by
whichever sync run loaded each row. Every metric, filter option and row-scope predicate
read that copy. Two consequences the owner hit:

  * an App Master edit did not appear until the next daily sync, with nothing saying so;
  * it only ever reached the last SYNC_WINDOW_DAYS (40) of history, so rows older than the
    window kept the previous assignment forever - one app under two different pods inside
    the same year-to-date total, every number looking perfectly healthy.

THE FIX. Stop reading the copy. A LEFT JOIN to app_master on canonical_key, and
COALESCE(app_master.x, fact.x) wherever attribution is grouped, filtered or scoped. An
edit is then visible on the next query and applies to ALL history, because there is no
stale copy left to be stale. The owner chose this explicitly: attribution is retroactive,
a report re-run after a reassignment reads differently, and that is the intent.

WHY LEFT JOIN AND COALESCE, not an inner join. An app can be in the feed before it is in
app_master - that is exactly what the -1 bucket is for - and an inner join would drop its
rows out of every total in silence. The fallback keeps it counted with the attribution
BigQuery gave it. It also keeps the existing suite honest: app_master is empty in tests,
so COALESCE falls through to the fact column and every current assertion still means what
it meant.

THE DANGER, and why every select goes through one helper. SQLAlchemy infers FROM from the
columns it sees. A bare ``select(...)`` that mentions an app_master column produces a
CARTESIAN PRODUCT - not an error - so every number is multiplied by however many app rows
match. Silently. In production. There are nine such selects in this module, and patching
eight would be worse than patching none, so they all route through ``_select()`` and a new
test parses the module and fails if any bare ``select(`` reappears.

ROW SCOPE MOVES TOO. build_scope_filter already accepts a ``columns`` mapping (it was
written for the apps endpoints). Scope predicates resolve through the same COALESCE, so a
pod owner moved between pods immediately sees the new pod and loses the old. If scope
matched the fact copy while data grouped by app_master, you would get current data behind
a stale permission - the worst of both.

    python3 scripts/live-attribution-join.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

QB = Path("backend/app/services/query_builder.py")
GUARD_TEST = Path("backend/tests/test_query_builder_join.py")

HEADER = '''# ── attribution: current, never as-of-sync ───────────────────────────────────
#
# The fact table carries its own copy of these four columns, written by whichever sync run
# loaded the row. Reading that copy is why an App Master edit took until the next sync to
# appear, and why it only reached the last SYNC_WINDOW_DAYS of history: older rows kept the
# previous assignment forever, so one app could sit under two pods inside the same
# year-to-date total while every number looked healthy.
#
# Resolving through app_master makes attribution one current fact - an edit shows on the
# next query and applies to ALL history, because no stale copy is left to be stale.
ATTRIBUTION_COLUMNS: frozenset[str] = frozenset({"pod", "pod_owner", "hou", "publisher"})

# LEFT, not inner: an app can be in the feed before it is in app_master - that is what the
# -1 bucket is - and an inner join would drop its rows out of every total in silence.
FACT_WITH_ATTRIBUTION = FACT_TABLE.join(
    APP_MASTER_TABLE,
    FACT_TABLE.c.canonical_key == APP_MASTER_TABLE.c[APP_MASTER_KEY],
    isouter=True,
)


def attribution_column(name: str) -> Any:
    """The CURRENT value, falling back to the fact row's copy when the app is not in
    app_master yet. Anything that is not attribution comes from the fact table untouched:
    canonical_key is an identity, not an assignment, and never moves."""
    if name not in ATTRIBUTION_COLUMNS:
        return FACT_TABLE.c[name]
    return func.coalesce(APP_MASTER_TABLE.c[name], FACT_TABLE.c[name])


def scope_columns() -> dict[str, Any]:
    """Row-scope columns, resolved the same way.

    If scope matched the fact copy while the data grouped by app_master, a pod owner moved
    between pods would keep seeing their OLD pod's rows and lose their new one - current
    data behind a stale permission, which is worse than either alone.
    """
    return {
        "hou": attribution_column("hou"),
        "pod": attribution_column("pod"),
        "publisher": attribution_column("publisher"),
        "app": FACT_TABLE.c.canonical_key,
    }


def _select(*columns: Any) -> Select[Any]:
    """EVERY query in this module starts here.

    Attribution lives in a joined table now, so a bare ``select(...)`` mentioning an
    app_master column yields a CARTESIAN PRODUCT rather than an error: every number
    multiplied by however many app rows match, silently, in production. One helper makes
    that impossible by accident, and tests/test_query_builder_join.py fails the build if a
    bare ``select(`` ever comes back.
    """
    return select(*columns).select_from(FACT_WITH_ATTRIBUTION)


'''

GUARD = '''"""Every metrics query must carry the app_master join.

Attribution is resolved through a LEFT JOIN to app_master. SQLAlchemy infers a query's
FROM clause from the columns it sees, so a bare ``select(...)`` that mentions an
app_master column does not fail - it emits ``FROM fact, app_master`` with no join
condition, a cartesian product that multiplies every number by however many app rows
match. There is no exception, no warning and no wrong-looking output; the totals are just
larger.

This reads the module's own source rather than executing a query, because the failure is a
property of how the SQL is CONSTRUCTED, and catching it needs no database, no fixtures and
no user context. A test that needed all three would be the test nobody runs.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.services import query_builder

SOURCE = Path(query_builder.__file__).read_text()
TREE = ast.parse(SOURCE)


def _bare_select_calls() -> list[int]:
    """Line numbers of every ``select(...)`` call that is not inside the _select helper."""
    helper_lines: set[int] = set()
    for node in ast.walk(TREE):
        if isinstance(node, ast.FunctionDef) and node.name == "_select":
            end = node.end_lineno or node.lineno
            helper_lines = set(range(node.lineno, end + 1))
    offenders: list[int] = []
    for node in ast.walk(TREE):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "select"):
            continue
        if node.lineno in helper_lines:
            continue
        # select(subquery) is reading from an already-aggregated subquery, not the fact
        # table, and must NOT carry the join - joining again there would re-multiply rows
        # that have already been grouped.
        if len(node.args) == 1 and isinstance(node.args[0], ast.Name):
            continue
        offenders.append(node.lineno)
    return offenders


def test_no_query_bypasses_the_join_helper() -> None:
    offenders = _bare_select_calls()
    assert offenders == [], (
        "these lines call select() directly instead of _select(), which drops the "
        f"app_master join and cross-joins the fact table: {offenders}"
    )


def test_the_helper_and_the_join_still_exist() -> None:
    # Guards against the test above passing vacuously because the helper was renamed or
    # deleted: with no _select at all, "no bare selects" would still be trivially true if
    # someone also removed the queries.
    assert "def _select(" in SOURCE
    assert "isouter=True" in SOURCE, "the join must stay LEFT - an inner join silently drops apps"
    assert "select_from(FACT_WITH_ATTRIBUTION)" in SOURCE


def test_scope_columns_cover_every_scope_type() -> None:
    # A scope type missing from this mapping falls back to the fact column, which is how a
    # reassigned pod owner ends up with current data behind a stale permission.
    from app.services.scopes import SCOPE_TYPE_TO_COLUMN

    assert set(query_builder.scope_columns()) == set(SCOPE_TYPE_TO_COLUMN)


def test_attribution_falls_back_rather_than_dropping_rows() -> None:
    # COALESCE, not a bare app_master column: an app in the feed but not yet in app_master
    # must keep the attribution BigQuery gave it instead of going NULL and falling out of
    # every split.
    rendered = str(query_builder.attribution_column("pod"))
    assert "coalesce" in rendered.lower()
    # ...and an identity column is NOT coalesced - it does not live in app_master.
    assert "coalesce" not in str(query_builder.attribution_column("canonical_key")).lower()
'''

EDITS = [
    {
        "why": "import the app_master table and its key",
        "anchor": """from app.core.fact_table import FACT_TABLE
from app.core.metric_registry import Col, Group, effective_registry
from app.schemas.auth import UserContext""",
        "replacement": """from app.core.app_master_columns import PRIMARY_KEY as APP_MASTER_KEY
from app.core.fact_table import FACT_TABLE
from app.core.metric_registry import Col, Group, effective_registry
from app.models.app_master import APP_MASTER_TABLE
from app.schemas.auth import UserContext""",
        "marker": "APP_MASTER_KEY",
    },
    {
        "why": "the join, the resolvers and the one select helper",
        "anchor": '''class QueryBuilder:
    """Builds scoped, parameterized SELECTs for one caller."""''',
        "replacement": HEADER + '''class QueryBuilder:
    """Builds scoped, parameterized SELECTs for one caller."""''',
        "marker": "def attribution_column(",
    },
    {
        "why": "row scope resolves through app_master too",
        "anchor": """        self._scope_filter = build_scope_filter(context.scopes)""",
        "replacement": """        # Scope predicates resolve through app_master as well. build_scope_filter already
        # takes this mapping - it was written for the apps endpoints - and passing it here
        # is what stops a reassigned pod owner keeping their old pod and losing their new.
        self._scope_filter = build_scope_filter(context.scopes, columns=scope_columns())""",
        "marker": "columns=scope_columns()",
    },
    {
        "why": "client filters narrow on current attribution",
        "anchor": """        if params.pods:
            conditions.append(FACT_TABLE.c.pod.in_(params.pods))
        if params.publishers:
            conditions.append(FACT_TABLE.c.publisher.in_(params.publishers))
        if params.apps:
            conditions.append(FACT_TABLE.c.canonical_key.in_(params.apps))
        if params.hou:
            conditions.append(FACT_TABLE.c.hou.in_(params.hou))
        if params.pod_owners:
            conditions.append(FACT_TABLE.c.pod_owner.in_(params.pod_owners))""",
        "replacement": """        if params.pods:
            conditions.append(attribution_column("pod").in_(params.pods))
        if params.publishers:
            conditions.append(attribution_column("publisher").in_(params.publishers))
        if params.apps:
            conditions.append(FACT_TABLE.c.canonical_key.in_(params.apps))
        if params.hou:
            conditions.append(attribution_column("hou").in_(params.hou))
        if params.pod_owners:
            conditions.append(attribution_column("pod_owner").in_(params.pod_owners))""",
        "marker": 'attribution_column("pod").in_',
    },
    {
        "why": "filter dropdown options come from current attribution",
        "anchor": """        col = FACT_TABLE.c[column]
        where = self._windowed_filters(narrowed, narrowed.date_from, narrowed.date_to)
        if label is not None:
            label_col = FACT_TABLE.c[label]""",
        "replacement": """        # Options follow the CURRENT assignment: a pod created in App Master is selectable
        # at once, and one that no longer exists stops being offered - instead of the
        # dropdown and App Master disagreeing until a sync, or forever for old rows.
        col = attribution_column(column)
        where = self._windowed_filters(narrowed, narrowed.date_from, narrowed.date_to)
        if label is not None:
            label_col = attribution_column(label)""",
        "marker": "col = attribution_column(column)",
    },
    {
        "why": "pod owner grouping",
        "anchor": """        group_col = FACT_TABLE.c.pod_owner
        columns: list[Any] = [group_col.label("pod_owner")]""",
        "replacement": """        group_col = attribution_column("pod_owner")
        columns: list[Any] = [group_col.label("pod_owner")]""",
        "marker": 'group_col = attribution_column("pod_owner")',
    },
    {
        "why": "every group_by token resolves through attribution",
        "anchor": """        group_col = FACT_TABLE.c[_GROUP_BY_COLUMN[group_by]]
        columns: list[Any] = [group_col.label(group_by)]
        if group_by == "app":
            columns.append(func.max(FACT_TABLE.c.app_name).label("app_name"))
        columns.extend(self._sum(m).label(m) for m in metrics)""",
        "replacement": """        group_col = attribution_column(_GROUP_BY_COLUMN[group_by])
        columns: list[Any] = [group_col.label(group_by)]
        if group_by == "app":
            columns.append(func.max(FACT_TABLE.c.app_name).label("app_name"))
        columns.extend(self._sum(m).label(m) for m in metrics)""",
        "marker": "group_col = attribution_column(_GROUP_BY_COLUMN[group_by])\n        columns: list[Any] = [group_col.label(group_by)]\n        if group_by == \"app\":\n            columns.append(func.max(FACT_TABLE.c.app_name).label(\"app_name\"))\n        columns.extend(self._sum(m)",
    },
    {
        "why": "contribution grouping",
        "anchor": """        group_col = FACT_TABLE.c[_GROUP_BY_COLUMN[group_by]]
        column = FACT_TABLE.c[metric]""",
        "replacement": """        group_col = attribution_column(_GROUP_BY_COLUMN[group_by])
        column = FACT_TABLE.c[metric]""",
        "marker": "group_col = attribution_column(_GROUP_BY_COLUMN[group_by])\n        column = FACT_TABLE.c[metric]",
    },
    {
        "why": "per-entity daily series grouping",
        "anchor": """        group_col = FACT_TABLE.c[_GROUP_BY_COLUMN[group_by]]
        columns: list[Any] = [group_col.label(group_by), FACT_TABLE.c.date.label("date")]""",
        "replacement": """        group_col = attribution_column(_GROUP_BY_COLUMN[group_by])
        columns: list[Any] = [group_col.label(group_by), FACT_TABLE.c.date.label("date")]""",
        "marker": "group_col = attribution_column(_GROUP_BY_COLUMN[group_by])\n        columns: list[Any] = [group_col.label(group_by), FACT_TABLE.c.date",
    },
    {
        "why": "the apps table must not contradict the overview",
        "anchor": """                func.max(FACT_TABLE.c.publisher).label("publisher"),
                func.max(FACT_TABLE.c.pod).label("pod"),
                func.max(FACT_TABLE.c.hou).label("hou"),""",
        "replacement": """                # Same resolution as everywhere else: if this read the fact copy, the
                # Apps table would show a different pod from the Overview for the same app.
                func.max(attribution_column("publisher")).label("publisher"),
                func.max(attribution_column("pod")).label("pod"),
                func.max(attribution_column("hou")).label("hou"),""",
        "marker": 'func.max(attribution_column("publisher"))',
    },
]

# Each select site, anchored on text unique to it.
SELECT_SITES = [
    'select(col.label("value"), func.max(label_col).label("label"))',
    'select(col.label("value"))\n            .where(and_(*where, col.isnot(None)))\n            .distinct()',
    "return select(*columns).where(and_(*where))\n",
    "return select(*columns).where(and_(*where)).group_by(bucket_expr).order_by(bucket_expr)",
    "return (\n            select(*columns)\n            .where(and_(*where))\n            .group_by(group_col)\n            .order_by(self._sum(metrics[0]).desc())\n        )",
    "stmt = (\n            select(*columns)",
    "select(*columns)\n            .where(and_(*where))\n            .group_by(group_col)\n            # ABSOLUTE delta",
    "select(*columns)\n            .where(and_(*where))\n            .group_by(group_col, FACT_TABLE.c.date)",
    "inner = (\n            select(",
]


def main() -> int:
    if not QB.exists():
        print(f"ABORTED: {QB} not found - run from the repository root")
        return 1
    text = QB.read_text()

    if "FACT_WITH_ATTRIBUTION" in text:
        print("nothing to do - already applied")
        return 0

    problems: list[str] = []
    for index, edit in enumerate(EDITS, start=1):
        found = text.count(edit["anchor"])
        if found != 1:
            problems.append(
                f"  [{index}] expected exactly 1 match, found {found}  ({edit['why']})\n"
                f"        anchor starts: {edit['anchor'].splitlines()[0].strip()[:76]!r}"
            )
            continue
        text = text.replace(edit["anchor"], edit["replacement"], 1)

    for index, site in enumerate(SELECT_SITES, start=1):
        found = text.count(site)
        if found != 1:
            problems.append(
                f"  [select {index}] expected exactly 1 match, found {found}\n"
                f"        starts: {site.splitlines()[0].strip()[:76]!r}"
            )
            continue
        text = text.replace(site, site.replace("select(", "_select(", 1), 1)

    if problems:
        print("ABORTED - NOTHING was written. Every problem at once:")
        print()
        for problem in problems:
            print(problem)
        print()
        print("Nine selects must ALL carry the join; patching eight cross-joins the rest.")
        return 1

    # Verify the OUTPUT. The failure this guards is silent, so trusting the anchors is not
    # enough: parse the result and confirm no bare select survived.
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        print(f"ABORTED - NOTHING was written: the patched module does not parse: {exc}")
        return 1

    helper_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_select":
            helper_lines = set(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    bare: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "select":
            if node.lineno in helper_lines:
                continue
            if len(node.args) == 1 and isinstance(node.args[0], ast.Name):
                continue  # select(subquery) - correct, must not join again
            bare.append(node.lineno)
    if bare:
        print("ABORTED - NOTHING was written. These selects still bypass the join and")
        print(f"would cross-join the fact table: lines {bare}")
        return 1
    if not helper_lines:
        print("ABORTED - NOTHING was written: the _select helper is not in the output")
        return 1

    QB.write_text(text)
    print(f"wrote {QB}")
    if not GUARD_TEST.exists() or GUARD_TEST.read_text() != GUARD:
        GUARD_TEST.parent.mkdir(parents=True, exist_ok=True)
        GUARD_TEST.write_text(GUARD)
        print(f"wrote {GUARD_TEST}")
    print()
    print("Attribution is now live for ALL history. Spot-check a pod total against what")
    print("you saw before this landed - the numbers SHOULD move if apps were ever moved.")
    print()
    print("Rebuild the backend, then run its suite.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
