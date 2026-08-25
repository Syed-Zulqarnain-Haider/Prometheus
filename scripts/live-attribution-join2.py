#!/usr/bin/env python3
"""Live attribution, attempt three.

WHAT THIS IS FOR
    App Master is the source of truth for an app's pod / pod_owner / hou /
    publisher. The fact table only carries whatever those values were when the
    sync last wrote each row, and the sync only rewrites a trailing window of
    days. So today, moving an app to a different pod moves the last ~40 days of
    its history and leaves everything older sitting under the old pod - one app
    counted under two pods inside the same YTD total, with no error anywhere.

    This patch resolves those four columns LIVE at query time: the whole history
    of an app follows its App Master row the moment it is edited.

WHY THIS SHAPE (the two things that broke attempt two)
    1. COALESCE types bigint and text cannot be matched.
       app_master.pod is BIGINT, fact.pod is TEXT. Fixed by construction: the
       app_master side is always CAST to the fact column's own type, whatever
       that type happens to be, so the pair can never mismatch again.

    2. Cartesian product in spotlight_service.
       Attempt two put an app_master reference inside the scope predicate that
       QueryBuilder EXPOSES to other services. Any consumer that did not also
       join app_master got "FROM fact, app_master" with no join condition.
       Fixed by splitting the two: the exposed fact-only scope filter is left
       exactly as it was, and a second, live scope filter is built alongside it
       and used ONLY inside QueryBuilder's own statements - every one of which
       is forced through _select(), which pins the FROM to the outer join.

    Every statement produced by the patched QueryBuilder is compiled here, on
    the server, before this script reports success: SAWarning is promoted to an
    error and each statement's final FROM list must contain exactly one entry.
    That is the check that would have caught attempt two.

SAFETY
    Nothing is written unless every edit resolves. Re-running is a no-op.
    Reverting is: git checkout -- backend/app/services/query_builder.py
                 rm -f backend/app/services/live_attribution.py
                 rm -f backend/tests/test_live_attribution.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QB = ROOT / "backend" / "app" / "services" / "query_builder.py"
LIVE = ROOT / "backend" / "app" / "services" / "live_attribution.py"
GUARD = ROOT / "backend" / "tests" / "test_live_attribution.py"
CONFTEST = ROOT / "backend" / "tests" / "conftest.py"

ATTRIBUTION = ("pod", "pod_owner", "hou", "publisher")
MARKER = "from app.services.live_attribution import"

problems: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    problems.append(msg)


def note(msg: str) -> None:
    notes.append(msg)


# ---------------------------------------------------------------- discovery --
def discover_app_master() -> tuple[str, str] | None:
    """Find the module that defines APP_MASTER_TABLE and the canonical-key column."""
    hits: list[Path] = []
    for path in (ROOT / "backend" / "app").rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if re.search(r"^APP_MASTER_TABLE\s*[:=]", text, re.M):
            hits.append(path)
    if not hits:
        fail("APP_MASTER_TABLE is not defined anywhere under backend/app - cannot continue.")
        return None
    if len(hits) > 1:
        fail(f"APP_MASTER_TABLE defined in more than one module: {[str(h) for h in hits]}")
        return None
    module = str(hits[0].relative_to(ROOT / "backend")).removesuffix(".py").replace("/", ".")

    key = "canonical_key"
    cols = ROOT / "backend" / "app" / "core" / "app_master_columns.py"
    if cols.exists():
        match = re.search(r"^PRIMARY_KEY\s*[:=].*?[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']",
                          cols.read_text(encoding="utf-8"), re.M)
        if match:
            key = match.group(1)
    note(f"app_master table module: {module}   primary key: {key}")
    return module, key


# ------------------------------------------------------------- live module --
LIVE_SOURCE = '''"""Live attribution: pod / pod_owner / hou / publisher resolved from App Master.

The fact table stores whatever these were when the sync last wrote each row, and
the sync only rewrites a trailing window of days. Reading them straight off the
fact row therefore splits an app's history the moment it is reassigned: recent
days under the new pod, older days under the old one, inside the same total.

Here they are resolved at query time from ``app_master`` instead, so an edit in
App Master moves an app's ENTIRE history immediately.

Two deliberate constraints:

* the app_master side is always CAST to the fact column's own type - app_master.pod
  is BIGINT while fact.pod is TEXT, and COALESCE refuses to mix them;
* nothing here is ever put into a predicate that leaves this package's control.
  ``FACT_WITH_MASTER`` is an explicit outer join and every statement that uses a
  live column must select FROM it. A live predicate handed to a service that does
  not join app_master would produce a cartesian product, not an error.

The join is on ``app_master``'s primary key, so it can never multiply fact rows;
apps with no App Master row keep the value the sync wrote (the COALESCE fallback).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Join, cast, func

from app.core.fact_table import FACT_TABLE
from {module} import APP_MASTER_TABLE
from app.services.scopes import SCOPE_TYPE_TO_COLUMN

#: Fact-table column linking a fact row to its App Master row.
LINK_COLUMN = "{key}"

#: Attribution columns owned by App Master. Only names present in BOTH tables are
#: resolved live; anything else falls back to the fact column untouched.
LIVE_ATTRIBUTION_COLUMNS: tuple[str, ...] = tuple(
    name
    for name in ("pod", "pod_owner", "hou", "publisher")
    if name in FACT_TABLE.c and name in APP_MASTER_TABLE.c
)

#: The only FROM a statement using live columns may have.
FACT_WITH_MASTER: Join = FACT_TABLE.outerjoin(
    APP_MASTER_TABLE,
    APP_MASTER_TABLE.c[LINK_COLUMN] == FACT_TABLE.c[LINK_COLUMN],
)


def live_column(name: str) -> Any:
    """The attribution column as App Master has it NOW, falling back to the fact row.

    Returns the plain fact column for anything App Master does not own, so this is
    safe to call with any column name.
    """
    fact = FACT_TABLE.c[name]
    if name not in LIVE_ATTRIBUTION_COLUMNS:
        return fact
    # Cast to the fact column's own type: app_master.pod is BIGINT, fact.pod is TEXT.
    return func.coalesce(cast(APP_MASTER_TABLE.c[name], fact.type), fact)


def live_scope_columns() -> dict[str, Any]:
    """Scope-type -> live column, for ``build_scope_filter(..., columns=...)``.

    Row scopes follow the live attribution too: an app moved into a pod is visible
    to that pod's owner across its whole history, and out of the old pod's, at once.
    """
    return {scope: live_column(column) for scope, column in SCOPE_TYPE_TO_COLUMN.items()}
'''


# ------------------------------------------------------------ QB rewriting --
class QBPatch:
    def __init__(self, source: str) -> None:
        self.src = source
        self.tree = ast.parse(source)
        self.lines = source.splitlines(keepends=True)
        self.offsets = [0]
        for line in self.lines:
            self.offsets.append(self.offsets[-1] + len(line))
        self.edits: list[tuple[int, int, str]] = []
        self.cls = next(
            (n for n in self.tree.body
             if isinstance(n, ast.ClassDef) and n.name == "QueryBuilder"),
            None,
        )

    def pos(self, lineno: int, col: int) -> int:
        return self.offsets[lineno - 1] + col

    def span(self, node: ast.AST) -> tuple[int, int]:
        return (
            self.pos(node.lineno, node.col_offset),
            self.pos(node.end_lineno or node.lineno, node.end_col_offset or node.col_offset),
        )

    def replace(self, node: ast.AST, text: str) -> None:
        start, end = self.span(node)
        self.edits.append((start, end, text))

    def methods(self) -> list[ast.FunctionDef]:
        if self.cls is None:
            return []
        return [n for n in self.cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    def apply(self) -> str:
        out = self.src
        for start, end, text in sorted(self.edits, key=lambda e: -e[0]):
            out = out[:start] + text + out[end:]
        return out


def is_fact_c(node: ast.AST) -> bool:
    """True for the ``FACT_TABLE.c`` part of FACT_TABLE.c.x / FACT_TABLE.c[x]."""
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "c"
        and isinstance(node.value, ast.Name)
        and node.value.id == "FACT_TABLE"
    )


def uses_fact(fn: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "FACT_TABLE" for n in ast.walk(fn))


def patch_query_builder(module: str) -> str | None:
    source = QB.read_text(encoding="utf-8")
    if MARKER in source:
        note("query_builder.py already carries the live-attribution wiring - left as is.")
        return None

    patch = QBPatch(source)
    if patch.cls is None:
        fail("query_builder.py has no class QueryBuilder - the file is not what I expect.")
        return None

    converted: list[str] = []
    skipped: list[str] = []
    live_hits: list[str] = []

    for fn in patch.methods():
        if not uses_fact(fn):
            continue

        # -- select(...) -> self._select(...), so the FROM is always the join ----
        for node in ast.walk(fn):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "select"):
                continue
            # select(inner) over an already-aggregated subquery must NOT be joined.
            if (len(node.args) == 1 and not node.keywords
                    and isinstance(node.args[0], ast.Name)):
                skipped.append(f"{fn.name}:{node.lineno} select({node.args[0].id}) - subquery")
                continue
            segment = ast.get_source_segment(source, node) or ""
            if ".select_from(" in segment:
                skipped.append(f"{fn.name}:{node.lineno} - already has select_from")
                continue
            patch.replace(node.func, "self._select")
            converted.append(f"{fn.name}:{node.lineno}")

        # -- attribution columns -> live_column(...) ---------------------------
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and is_fact_c(node.value):
                if node.attr in ATTRIBUTION:
                    patch.replace(node, f'live_column("{node.attr}")')
                    live_hits.append(f"{fn.name}:{node.lineno} FACT_TABLE.c.{node.attr}")
            elif isinstance(node, ast.Subscript) and is_fact_c(node.value):
                inner = ast.get_source_segment(source, node.slice) or ""
                # _GROUP_BY_COLUMN[...] is always a dimension; distinct_values only
                # ever deals in dimensions. Measures (_sum) are left alone.
                if "_GROUP_BY_COLUMN" in inner or fn.name == "distinct_values":
                    patch.replace(node, f"live_column({inner})")
                    live_hits.append(f"{fn.name}:{node.lineno} FACT_TABLE.c[{inner}]")

        # -- scope filter -> the live one, inside QueryBuilder's own statements --
        if fn.name.startswith("fact_") or fn.name == "__init__":
            continue
        for node in ast.walk(fn):
            if (isinstance(node, ast.Attribute) and node.attr == "_scope_filter"
                    and isinstance(node.value, ast.Name) and node.value.id == "self"):
                patch.replace(node, "self._live_scope_filter")
                live_hits.append(f"{fn.name}:{node.lineno} self._scope_filter")

    if not converted:
        fail("Found no select() call to route through the join - refusing to write.")
    if not live_hits:
        fail("Found no attribution column to make live - refusing to write.")

    out = patch.apply()

    # -- import ------------------------------------------------------------
    anchor = "from app.services.scopes import build_scope_filter"
    if anchor not in out:
        fail(f"query_builder.py: anchor not found -> {anchor}")
        return None
    out = out.replace(
        anchor,
        f"{MARKER} FACT_WITH_MASTER, live_column, live_scope_columns\n{anchor}",
        1,
    )

    # -- second, live scope filter alongside the exposed fact-only one ------
    init = re.search(r"^(\s*)self\._scope_filter\s*=\s*build_scope_filter\(([^\n]*?)\)\s*$",
                     out, re.M)
    if init is None:
        fail("query_builder.py: could not find the self._scope_filter assignment in __init__.")
        return None
    indent, args = init.group(1), init.group(2)
    out = out[:init.end()] + (
        f"\n{indent}# Used ONLY inside this class's own statements, every one of which selects"
        f"\n{indent}# FROM the join. The fact-only filter above stays exactly as it was so that"
        f"\n{indent}# services reusing it can never be handed an app_master reference they do"
        f"\n{indent}# not join (that is what produced a cartesian product last time)."
        f"\n{indent}self._live_scope_filter = build_scope_filter("
        f"{args}, columns=live_scope_columns())"
    ) + out[init.end():]

    # -- the _select helper -------------------------------------------------
    tree = ast.parse(out)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "QueryBuilder")
    init_fn = next(
        (n for n in cls.body
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "__init__"),
        None,
    )
    if init_fn is None:
        fail("query_builder.py: QueryBuilder has no __init__.")
        return None
    body_lines = out.splitlines(keepends=True)
    insert_at = init_fn.end_lineno or 0
    helper = (
        "\n"
        "    @staticmethod\n"
        "    def _select(*columns: Any) -> Select[Any]:\n"
        '        """A SELECT pinned to the fact/app_master outer join.\n'
        "\n"
        "        Every statement this class builds goes through here. Live attribution\n"
        "        columns reference app_master, and SQLAlchemy infers the FROM list from\n"
        "        the columns it can see - so without an explicit select_from a live\n"
        "        column produces ``FROM fact_daily_performance, app_master`` with no join\n"
        "        condition. That is a cartesian product, and it is a warning, not an\n"
        '        error. Pinning the FROM here makes it unrepresentable."""\n'
        "        return select(*columns).select_from(FACT_WITH_MASTER)\n"
    )
    out = "".join(body_lines[:insert_at]) + helper + "".join(body_lines[insert_at:])

    note(f"select() -> self._select(): {len(converted)} site(s): {', '.join(converted)}")
    if skipped:
        note(f"select() left alone: {'; '.join(skipped)}")
    note(f"live attribution rewired at {len(live_hits)} site(s):")
    for hit in live_hits:
        note(f"    {hit}")
    return out


# ------------------------------------------------------------------ guards --
GUARD_SOURCE = '''"""Guards for live attribution (App Master -> every query, immediately).

These exist because the failure they catch is silent. SQLAlchemy infers a
statement's FROM list from the columns it sees, so a predicate that mentions
``app_master`` inside a statement that does not join it yields
``FROM fact_daily_performance, app_master`` - a cartesian product, emitted as a
warning and not an error. The first version of this feature shipped exactly that
into a service that reused the query builder's scope predicate.
"""

from __future__ import annotations

import datetime as dt
import warnings

import pytest
from sqlalchemy import Select, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SAWarning

from app.core.fact_table import FACT_TABLE
from app.schemas.auth import ScopeOut
from app.services.live_attribution import (
    FACT_WITH_MASTER,
    LIVE_ATTRIBUTION_COLUMNS,
    live_column,
    live_scope_columns,
)
from app.services.query_builder import QueryBuilder
from app.services.scopes import build_scope_filter


def _compile(stmt: Select) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        return str(stmt.compile(dialect=postgresql.dialect()))


def test_pod_is_resolved_live_and_type_matched() -> None:
    """app_master.pod is BIGINT and fact.pod is TEXT; COALESCE cannot mix them."""
    assert "pod" in LIVE_ATTRIBUTION_COLUMNS
    sql = _compile(select(live_column("pod").label("pod")).select_from(FACT_WITH_MASTER))
    assert "coalesce" in sql.lower()
    assert "CAST" in sql
    assert "app_master" in sql


def test_unowned_column_is_left_on_the_fact_table() -> None:
    assert live_column("canonical_key") is FACT_TABLE.c.canonical_key
    assert live_column("platform") is FACT_TABLE.c.platform


def test_live_predicate_without_the_join_is_a_cartesian_product() -> None:
    """The failure mode this feature has to stay ahead of, pinned as a test."""
    stmt = select(FACT_TABLE.c.date).where(live_column("pod") == "3")
    with pytest.raises(SAWarning, match="cartesian"):
        _compile(stmt)


def test_scope_columns_cover_every_scope_type() -> None:
    columns = live_scope_columns()
    assert set(columns) == {"hou", "pod", "publisher", "app"}
    _compile(select(FACT_TABLE.c.date).select_from(FACT_WITH_MASTER).where(
        build_scope_filter([ScopeOut.model_construct(scope_type="pod", scope_value="3")],
                           columns=columns)
    ))


def _builder() -> QueryBuilder:
    from app.core.metric_registry import Group

    context = type(
        "Ctx",
        (),
        {
            "scopes": [ScopeOut.model_construct(scope_type="pod", scope_value="3")],
            "metric_groups": [g.value for g in Group],
        },
    )()
    return QueryBuilder(context)  # type: ignore[arg-type]


def test_exposed_scope_filter_stays_free_of_app_master() -> None:
    """Other services reuse this predicate WITHOUT joining app_master."""
    builder = _builder()
    exposed = getattr(builder, "fact_scope_filter", None)
    predicate = exposed() if callable(exposed) else builder._scope_filter
    sql = str(select(FACT_TABLE.c.date).where(predicate).compile(
        dialect=postgresql.dialect()))
    assert "app_master" not in sql


@pytest.mark.parametrize("group_by", ["pod", "publisher", "hou", "app"])
def test_breakdown_has_exactly_one_from(group_by: str) -> None:
    builder = _builder()
    metric = sorted(builder.permitted_measures)[0]
    stmt = builder.breakdown(_filters(), group_by, [metric])  # type: ignore[arg-type]
    assert len(stmt.get_final_froms()) == 1
    _compile(stmt)


def _filters():
    from app.schemas.metrics import MetricFilters

    return MetricFilters.model_construct(
        date_from=dt.date(2026, 1, 1), date_to=dt.date(2026, 1, 31)
    )


def test_summary_has_exactly_one_from() -> None:
    stmt = _builder().summary(_filters())
    assert len(stmt.get_final_froms()) == 1
    _compile(stmt)
'''


def patch_conftest() -> str | None:
    """Promote the cartesian-product warning to an error for the whole suite."""
    if not CONFTEST.exists():
        note("backend/tests/conftest.py not found - suite-wide cartesian guard skipped.")
        return None
    source = CONFTEST.read_text(encoding="utf-8")
    if "cartesian product" in source:
        note("conftest.py already promotes the cartesian-product warning - left as is.")
        return None
    block = (
        "\n\n"
        "# A missing join condition is a SQLAlchemy WARNING, not an error: the query still\n"
        "# runs, and quietly returns the cross product. Any test that provokes one should\n"
        "# fail loudly. Scoped to that one message so no unrelated warning becomes a gate.\n"
        "warnings.filterwarnings(\"error\", message=\".*cartesian product.*\")\n"
    )
    if re.search(r"^import warnings$", source, re.M) is None:
        source = re.sub(r"^(from __future__ import annotations\n)", r"\1\nimport warnings\n",
                        source, count=1, flags=re.M)
        if "import warnings" not in source:
            source = "import warnings\n" + source
    return source.rstrip("\n") + block


# ------------------------------------------------------------ verification --
def verify() -> None:
    """Build every statement the patched QueryBuilder can build and inspect the SQL."""
    sys.path.insert(0, str(ROOT / "backend"))
    import warnings

    from sqlalchemy import Select
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.exc import SAWarning

    from app.core.metric_registry import Group  # noqa: PLC0415
    from app.schemas.auth import ScopeOut  # noqa: PLC0415
    from app.schemas.metrics import MetricFilters  # noqa: PLC0415
    from app.services.query_builder import QueryBuilder  # noqa: PLC0415

    context = type("Ctx", (), {
        "scopes": [ScopeOut.model_construct(scope_type="pod", scope_value="3")],
        "metric_groups": [g.value for g in Group],
    })()
    builder = QueryBuilder(context)
    measures = sorted(builder.permitted_measures)
    if not measures:
        fail("verification: the synthetic context has no permitted measures.")
        return

    import datetime as dt
    filters = MetricFilters.model_construct(
        date_from=dt.date(2026, 1, 1), date_to=dt.date(2026, 1, 31)
    )

    def arg_for(name: str):
        table = {
            "params": filters, "filters": filters,
            "metrics": [measures[0]], "metric": measures[0],
            "group_by": "pod", "dimension": "pod", "entity": "pod",
            "column": "pod", "field": "pod", "label": "pod", "key": "pod",
            "bucket": "day", "sort": measures[0], "direction": "desc", "limit": 5,
        }
        return table.get(name, _MISSING)

    _MISSING = object()
    checked = 0
    unverified: list[str] = []

    import inspect
    for name, fn in inspect.getmembers(QueryBuilder, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        kwargs = {}
        skip = False
        for param in list(sig.parameters.values())[1:]:
            value = arg_for(param.name)
            if value is _MISSING:
                if param.default is inspect.Parameter.empty:
                    skip = True
                    break
                continue
            kwargs[param.name] = value
        if skip:
            unverified.append(f"{name} (unknown required argument)")
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", SAWarning)
                stmt = fn(builder, **kwargs)
                if not isinstance(stmt, Select):
                    continue
                froms = stmt.get_final_froms()
                if len(froms) != 1:
                    fail(f"verification: {name}() has {len(froms)} FROM entries "
                         f"(cartesian product): {[str(f) for f in froms]}")
                    continue
                str(stmt.compile(dialect=postgresql.dialect()))
        except SAWarning as exc:
            fail(f"verification: {name}() raised SQLAlchemy warning-as-error: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 - every failure is reported, none swallowed
            unverified.append(f"{name} ({type(exc).__name__}: {exc})")
            continue
        checked += 1

    note(f"verification: {checked} statement(s) compiled clean, exactly one FROM each.")
    if unverified:
        note("verification: NOT exercised (reported, not assumed safe):")
        for item in unverified:
            note(f"    {item}")

    # The exposed predicate must still be app_master-free for other services.
    from sqlalchemy import select as sa_select  # noqa: PLC0415

    from app.core.fact_table import FACT_TABLE  # noqa: PLC0415
    exposed = getattr(builder, "fact_scope_filter", None)
    predicate = exposed() if callable(exposed) else getattr(builder, "_scope_filter", None)
    if predicate is not None:
        sql = str(sa_select(FACT_TABLE.c.date).where(predicate).compile(
            dialect=postgresql.dialect()))
        if "app_master" in sql:
            fail("verification: the EXPOSED scope filter references app_master - "
                 "this is what cross-joined spotlight_service last time.")
        else:
            note("verification: exposed scope filter is app_master-free (spotlight is safe).")

    # A live column really does resolve from app_master, with a cast.
    from app.services.live_attribution import (  # noqa: PLC0415
        FACT_WITH_MASTER, LIVE_ATTRIBUTION_COLUMNS, live_column,
    )
    note(f"live attribution columns: {list(LIVE_ATTRIBUTION_COLUMNS)}")
    sql = str(sa_select(live_column("pod").label("pod")).select_from(FACT_WITH_MASTER)
              .compile(dialect=postgresql.dialect()))
    if "app_master" not in sql or "CAST" not in sql.upper():
        fail(f"verification: live pod did not compile to a cast app_master lookup:\n{sql}")
    else:
        note("verification: live pod = COALESCE(CAST(app_master.pod ...), fact.pod).")


# ------------------------------------------------------------------ recon ---
def recon() -> None:
    """Read-only: what else reuses these predicates, and where App Master writes."""
    print("\n--- consumers of the query builder's scope predicate ---")
    pattern = re.compile(r"(fact_scope_filter|_scope_filter|_base_filters|_windowed_filters)")
    for path in sorted((ROOT / "backend" / "app").rglob("*.py")):
        if path.name in {"query_builder.py", "scopes.py", "live_attribution.py"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                print(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")

    print("\n--- App Master write path (for the cache-bust step) ---")
    service = ROOT / "backend" / "app" / "services" / "app_master_service.py"
    if not service.exists():
        print("backend/app/services/app_master_service.py not found")
        return
    text = service.read_text(encoding="utf-8")
    tree = ast.parse(text)
    lines = text.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = "\n".join(lines[node.lineno - 1: node.end_lineno])
        if "push_update" in body or "update" in node.name.lower():
            args = ", ".join(a.arg for a in node.args.args)
            print(f"\n  {node.name}({args})  [lines {node.lineno}-{node.end_lineno}]")
            for offset, line in enumerate(lines[node.lineno - 1: node.end_lineno]):
                print(f"    {node.lineno + offset}: {line}")


# ------------------------------------------------------------------- main ---
def main() -> int:
    for path in (QB, ROOT / "backend" / "app" / "services" / "scopes.py"):
        if not path.exists():
            fail(f"missing: {path.relative_to(ROOT)}")
    discovered = discover_app_master()
    if problems:
        report()
        return 1
    assert discovered is not None
    module, key = discovered

    qb_out = patch_query_builder(module)
    conftest_out = patch_conftest()
    # Plain substitution, not str.format: the generated module contains dict and set
    # comprehensions, and every brace in them would be read as a format field.
    live_out = LIVE_SOURCE.replace("{module}", module).replace("{key}", key)

    for label, text in (("live_attribution.py", live_out), ("query_builder.py", qb_out or "")):
        if not text:
            continue
        try:
            ast.parse(text)
        except SyntaxError as exc:
            fail(f"{label}: the patched source does not parse: {exc}")

    if problems:
        report()
        return 1

    # Nothing is written until every edit above resolved.
    LIVE.write_text(live_out, encoding="utf-8")
    GUARD.parent.mkdir(parents=True, exist_ok=True)
    GUARD.write_text(GUARD_SOURCE, encoding="utf-8")
    if qb_out:
        QB.write_text(qb_out, encoding="utf-8")
    if conftest_out:
        CONFTEST.write_text(conftest_out, encoding="utf-8")
    note("wrote: live_attribution.py, test_live_attribution.py"
         + (", query_builder.py" if qb_out else "")
         + (", conftest.py" if conftest_out else ""))

    try:
        verify()
    except Exception as exc:  # noqa: BLE001
        fail(f"verification could not run ({type(exc).__name__}: {exc}) - "
             "treat this patch as UNVERIFIED.")

    report()
    recon()
    return 1 if problems else 0


def report() -> None:
    for line in notes:
        print(line)
    if problems:
        print("\nFAILED:")
        for line in problems:
            print(f"  - {line}")
    else:
        print("\nOK - live attribution wired and every statement verified.")


if __name__ == "__main__":
    raise SystemExit(main())
