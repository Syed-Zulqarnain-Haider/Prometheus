#!/usr/bin/env python3
"""Read-only: an exhaustive RBAC coverage matrix, derived from the code.

"Is RBAC solid?" cannot be answered by looking. It can be answered by enumerating
EVERY route, reading the guard each one actually carries, and listing which roles
are exercised against it by a test. What is left over is the answer.

This reports four things, and each is a finding on its own:

  1. UNGUARDED   - a route with no capability/role dependency at any level.
  2. UNSCOPED    - a route that reaches the fact table WITHOUT going through
                   QueryBuilder, which is what injects the caller's row scopes.
                   An endpoint like this returns every app to everyone.
  3. UNTESTED    - a guarded route no test calls. A guard nobody tests is a guard
                   that survives until someone deletes it by accident.
  4. ROLE GAPS   - roles that no test ever uses, per route group.

It also prints the router-level dependencies, because a route can look bare and
still be gated by its router - reporting it as unguarded would be a false alarm.

Writes nothing. Runs nothing. Pure static reading.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "backend" / "app" / "api"
SERVICES = ROOT / "backend" / "app" / "services"
TESTS = ROOT / "backend" / "tests"

ROLES = ("admin", "executive", "pod_owner", "marketing", "finance", "viewer")
GUARD = re.compile(r"require_capability|require_role|require_admin|enforce_admin|CurrentUser|get_current")

#: `Alias = Annotated[UserContext, Depends(require_capability("export"))]` is a guard, and
#: a route typed `context: ExportUser` is gated by it. Hardcoding the alias names reported
#: four gated routes as unguarded, so the table is DERIVED from the code instead.
ALIAS_DEF = re.compile(
    r"^(?P<name>\w+)\s*=\s*Annotated\[\s*(?P<type>\w+)\s*,\s*Depends\((?P<dep>[^\]]+)\)\s*\]",
    re.M,
)


def dependency_aliases() -> dict[str, str]:
    """alias -> what it enforces, read from every module that defines one."""
    table: dict[str, str] = {}
    for path in sorted((ROOT / "backend" / "app").rglob("*.py")):
        for match in ALIAS_DEF.finditer(path.read_text(encoding="utf-8", errors="ignore")):
            dep = match.group("dep")
            if "require_capability" in dep:
                capability = re.search(r'require_capability\(\s*"([^"]+)"', dep)
                table[match.group("name")] = f'capability:{capability.group(1) if capability else "?"}'
            elif "require_role" in dep:
                table[match.group("name")] = "role"
            elif match.group("type") in ("UserContext", "VerifiedIdentity"):
                table[match.group("name")] = "authenticated"
    return table


ALIASES = dependency_aliases()


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n== {title}\n{'=' * 78}")


def source_of(node: ast.AST, text: str) -> str:
    return (ast.get_source_segment(text, node) or "").replace("\n", " ")


class Route:
    def __init__(self, module: str, method: str, path: str, name: str,
                 decorator_deps: str, params: str, line: int) -> None:
        self.module = module
        self.method = method
        self.path = path
        self.name = name
        self.decorator_deps = decorator_deps
        self.params = params
        self.line = line

    @property
    def guard(self) -> str:
        blob = f"{self.decorator_deps} {self.params}"
        if "require_capability" in blob:
            match = re.search(r'require_capability\(\s*"([^"]+)"', blob)
            return f'capability:{match.group(1) if match else "?"}'
        if "require_role" in blob:
            return "role"
        if "enforce_admin" in blob:
            return "admin step-up"
        # A typed dependency alias carries its guard with it. Strongest wins, so a route
        # taking both CurrentUser and ExportUser reports the capability, not "authenticated".
        found = [
            enforced for alias, enforced in ALIASES.items()
            if re.search(rf"(?<![\w]){re.escape(alias)}(?![\w])", blob)
        ]
        for enforced in found:
            if enforced.startswith("capability:"):
                return enforced
        if "role" in found:
            return "role"
        if found or "get_current" in blob:
            return "authenticated"
        return "NONE"


def collect_routes() -> tuple[list[Route], dict[str, str]]:
    routes: list[Route] = []
    router_deps: dict[str, str] = {}
    for path in sorted(API.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        module = str(path.relative_to(ROOT))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        # Router-level dependencies gate every route in the file.
        for node in ast.walk(tree):
            if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name)
                    and node.value.func.id == "APIRouter"):
                router_deps[module] = source_of(node.value, text)

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not (isinstance(decorator, ast.Call)
                        and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr in ("get", "post", "put", "patch", "delete")):
                    continue
                route_path = ""
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    route_path = str(decorator.args[0].value)
                routes.append(Route(
                    module=module,
                    method=decorator.func.attr.upper(),
                    path=route_path,
                    name=node.name,
                    decorator_deps=source_of(decorator, text),
                    params=" ".join(source_of(a, text) for a in node.args.args)
                           + " " + " ".join(source_of(a, text) for a in node.args.kwonlyargs),
                    line=node.lineno,
                ))
    return routes, router_deps


ROUTES, ROUTER_DEPS = collect_routes()
TEST_TEXT = "\n".join(
    p.read_text(encoding="utf-8", errors="ignore") for p in sorted(TESTS.rglob("*.py"))
) if TESTS.exists() else ""

rule("0a. dependency aliases discovered, and what each enforces")
for alias, enforced in sorted(ALIASES.items()):
    print(f"  {alias:22} -> {enforced}")

rule("0b. router-level dependencies (these gate every route in the file)")
for module, deps in sorted(ROUTER_DEPS.items()):
    gated = "GATED" if GUARD.search(deps) else "not gated at router level"
    print(f"  {module:52} {gated}")
    if GUARD.search(deps):
        print(f"       {deps[:150]}")

rule(f"1. every route and the guard it actually carries  ({len(ROUTES)} routes)")
by_module: dict[str, list[Route]] = {}
for route in ROUTES:
    by_module.setdefault(route.module, []).append(route)

unguarded: list[Route] = []
for module in sorted(by_module):
    router_gated = GUARD.search(ROUTER_DEPS.get(module, "")) is not None
    print(f"\n-- {module}   (router-level: {'gated' if router_gated else 'open'})")
    for route in sorted(by_module[module], key=lambda r: r.line):
        guard = route.guard
        if guard == "NONE" and not router_gated:
            unguarded.append(route)
            guard = "*** NONE ***"
        elif guard == "NONE":
            guard = "via router"
        print(f"   {route.method:6} {route.path:44} {guard:22} {route.name}")

rule("2. UNGUARDED routes - no capability, no role, no router gate")
if unguarded:
    for route in unguarded:
        print(f"  {route.module}:{route.line}  {route.method} {route.path}  ({route.name})")
else:
    print("  none - every route is gated at the route or the router")

rule("3. UNSCOPED data access - reaching the fact table without a scope filter")
print("""  QueryBuilder is what injects the caller's row scopes into WHERE. Checked per
  FUNCTION, not per file: a module that scopes one query and not another looks
  clean at file level, which is exactly the shape this is meant to catch.

  A function that deletes or counts the whole table (data-clear, health checks) is
  legitimately unscoped - those are listed too, so the judgement is visible rather
  than hidden by a heuristic.
""")
SCOPE_TOKENS = ("QueryBuilder", "build_scope_filter", "fact_scope_filter",
                "_base_filters", "_windowed_filters", "qb.")
for path in sorted(SERVICES.rglob("*.py")) + sorted(API.rglob("*.py")):
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "FACT_TABLE" not in text and "fact_daily_performance" not in text:
        continue
    try:
        tree = ast.parse(text)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = ast.get_source_segment(text, node) or ""
        if "FACT_TABLE" not in body and "fact_daily_performance" not in body:
            continue
        scoped = any(token in body for token in SCOPE_TOKENS)
        signature = " ".join(a.arg for a in node.args.args)
        takes_builder = "qb" in signature or "builder" in signature
        verdict = ("scoped" if scoped or takes_builder
                   else "*** NO scope filter - confirm this is deliberate ***")
        print(f"  {str(path.relative_to(ROOT)):52}:{node.lineno:<5} {node.name:34} {verdict}")

rule("4. UNTESTED routes - a guard nobody exercises")
untested = [
    route for route in ROUTES
    if route.path and route.path not in TEST_TEXT and route.name not in TEST_TEXT
]
print(f"  {len(ROUTES) - len(untested)} of {len(ROUTES)} routes appear in the test suite\n")
for route in untested:
    print(f"  {route.method:6} {route.path:44} {route.module}:{route.line}")

rule("5. role coverage in the tests")
for role in ROLES:
    count = len(re.findall(rf'["\']{role}["\']', TEST_TEXT))
    verdict = "never used in any test" if count == 0 else f"{count} reference(s)"
    print(f"  {role:14} {verdict}")

rule("6. the scope resolver itself - the single point every row filter passes through")
scopes = ROOT / "backend" / "app" / "services" / "scopes.py"
if scopes.exists():
    for number, line in enumerate(scopes.read_text(encoding="utf-8").splitlines(), 1):
        print(f"{number:5}: {line}")

rule("7. capability and metric-group definitions")
for name in ("role_capabilities", "role_metric_permissions", "user_scopes"):
    print(f"\n-- {name}")
    for path in sorted((ROOT / "backend" / "app").rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for number, line in enumerate(text.splitlines(), 1):
            if name in line:
                print(f"  {path.relative_to(ROOT)}:{number}: {line.strip()[:130]}")

print("\nread-only: nothing was written.")
