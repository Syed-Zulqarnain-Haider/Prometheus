#!/usr/bin/env python3
"""App Master change approval: propose -> admin approves/rejects.

Strict anchors. Every anchor is validated against every file BEFORE a single byte is
written, so a mismatch aborts having changed nothing. Safe to run twice: each region
carries its own marker.

Nine files are written whole (all new, except frontend/tests/nav.test.ts which is replaced
because its old body re-implemented the gating rule instead of calling it). Everything else
is an anchored edit into a file that already exists.
"""

import base64
import io
import re
import sys
import tarfile
from pathlib import Path

PAYLOAD = "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"


def die(message: str) -> None:
    print(f"ABORTED: {message}", file=sys.stderr)
    print("Nothing was written.", file=sys.stderr)
    raise SystemExit(1)


def read(path: Path) -> str:
    if not path.exists():
        die(f"{path} not found - run from the repository root")
    return path.read_text()


def once(text: str, anchor: str, path: Path) -> None:
    n = text.count(anchor)
    if n != 1:
        die(f"{path}: anchor appears {n} times, expected exactly 1: {anchor.strip()[:70]!r}")


# ── services import rewriter ─────────────────────────────────────────────────────
# `from app.services import ...` is written single-line in some files and parenthesised in
# others, and which one a file uses changes the moment a name pushes it past 100 columns.
# Parse whichever form is there, add the name, re-emit in the form ruff would.
SERVICES_PAREN = re.compile(r"^from app\.services import \(([^)]*)\)\n", re.M)
SERVICES_FLAT = re.compile(r"^from app\.services import ([^\n(]+)\n", re.M)


def add_service_imports(text: str, path: Path, names: list[str]) -> str:
    match = SERVICES_PAREN.search(text)
    if match:
        existing = [n.strip().rstrip(",") for n in match.group(1).split("\n") if n.strip()]
    else:
        match = SERVICES_FLAT.search(text)
        if not match:
            die(f"{path}: no 'from app.services import ...' statement to extend")
        existing = [n.strip() for n in match.group(1).split(",") if n.strip()]
    merged = sorted(set(existing) | set(names))
    flat = "from app.services import " + ", ".join(merged) + "\n"
    block = (
        flat
        if len(flat) <= 101
        else "from app.services import (\n" + "".join(f"    {n},\n" for n in merged) + ")\n"
    )
    return text[: match.start()] + block + text[match.end() :]


def insert_after_line_in_function(
    text: str, path: Path, func: str, line: str, new_line: str
) -> str:
    """Insert after the first occurrence of `line` INSIDE `func`.

    Scoped, because a line like `await _seed(metrics_env)` opens a dozen tests in the same
    file - a whole-file replace would hit whichever came first.
    """
    start = text.find(func)
    if start == -1:
        die(f"{path}: {func.strip()!r} not found")
    end = text.find("\nasync def ", start + len(func))
    end = len(text) if end == -1 else end
    body = text[start:end]
    if body.count(line) < 1:
        die(f"{path}: {line.strip()!r} not found inside {func.strip()[:50]!r}")
    return text[:start] + body.replace(line, line + new_line, 1) + text[end:]


ROOT = Path(".")
if not (ROOT / "backend" / "app" / "main.py").exists():
    die("run this from the repository root (backend/app/main.py is missing)")

edits: list[tuple[Path, str]] = []   # (path, new text)
skipped: list[str] = []


def plan(path: Path, marker: str, build) -> None:
    """Compute a file's new text now; write it only once every file has planned cleanly."""
    text = read(path)
    if marker in text:
        skipped.append(f"{path}: already applied")
        return
    edits.append((path, build(text)))


# ── 1. the apply-delay setting ───────────────────────────────────────────────────
SETTING = '''    "app_master_apply_delay_minutes": SettingSpec(
        key="app_master_apply_delay_minutes",
        type="int",
        default=10,
        label="App Master apply delay (minutes)",
        description="How long an ADMIN's own App Master edit waits before it applies by "
        "itself. It can be cancelled during that window - an undo that does not need a "
        "second person. Proposals from pod owners are unaffected: those wait for an "
        "approval, however long that takes. Set 0 to apply admin edits immediately.",
        minimum=0,
        maximum=1440,
    ),
'''


def build_settings(text: str) -> str:
    path = Path("backend/app/core/settings_registry.py")
    anchor = '    "digest_enabled": SettingSpec(\n'
    once(text, anchor, path)
    return text.replace(anchor, SETTING + anchor)


plan(
    Path("backend/app/core/settings_registry.py"),
    "app_master_apply_delay_minutes",
    build_settings,
)


# ── 2. register the model ────────────────────────────────────────────────────────
def build_models_init(text: str) -> str:
    path = Path("backend/app/models/__init__.py")
    imp = "from app.models.app_master_edit import AppMasterConfig, AppMasterEdit\n"
    once(text, imp, path)
    text = text.replace(
        imp,
        imp
        + "from app.models.app_master_requests import (\n"
        + "    OPEN_STATUSES,\n"
        + "    REQUEST_STATUSES,\n"
        + "    AppMasterChangeRequest,\n"
        + ")\n",
    )
    exported = '    "AppMasterEdit",\n'
    once(text, exported, path)
    return text.replace(
        exported,
        exported + '    "AppMasterChangeRequest",\n    "REQUEST_STATUSES",\n    "OPEN_STATUSES",\n',
    )


plan(Path("backend/app/models/__init__.py"), "AppMasterChangeRequest", build_models_init)


# ── 3. register the router ───────────────────────────────────────────────────────
def build_main(text: str) -> str:
    path = Path("backend/app/main.py")
    imp = "from app.api.v1 import app_master as app_master_routes\n"
    once(text, imp, path)
    text = text.replace(
        imp,
        imp + "from app.api.v1 import app_master_requests as app_master_request_routes\n",
    )
    inc = "app.include_router(app_master_routes.router, prefix=settings.api_v1_prefix)\n"
    once(text, inc, path)
    return text.replace(
        inc,
        inc + "app.include_router(app_master_request_routes.router, prefix=settings.api_v1_prefix)\n",
    )


plan(Path("backend/app/main.py"), "app_master_request_routes", build_main)


# ── 4. the admin PATCH now schedules instead of applying instantly ───────────────
SCHEDULE_BLOCK = '''
    # An admin's own edit no longer lands instantly: it is SCHEDULED, and applies by
    # itself once the configured delay has passed unless somebody cancels it first. That
    # is an undo window which needs nobody else to be awake. A delay of 0 keeps the old
    # behaviour for deployments that do not want it.
    if int(await settings_service.get_value(db, "app_master_apply_delay_minutes")) > 0:
        try:
            queued = await app_master_request_service.propose(db, context, key, changes)
        except app_master_request_service.RequestError as exc:
            await db.rollback()
            if str(exc) == "App not found":
                raise HTTPException(status.HTTP_404_NOT_FOUND, "App not found") from exc
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
        await audit.log_admin_action(
            user_id=context.user_id,
            action="app_master_change_scheduled",
            resource=key,
            detail={"changes": queued.changes},
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
        return {
            "scheduled": True,
            "request_id": str(queued.id),
            "apply_after": queued.apply_after.isoformat() if queued.apply_after else None,
        }
'''


def build_app_master_route(text: str) -> str:
    path = Path("backend/app/api/v1/app_master.py")
    text = add_service_imports(text, path, ["app_master_request_service", "settings_service"])
    anchor = "    changes = body.model_dump(exclude_unset=True)\n"
    once(text, anchor, path)
    return text.replace(anchor, anchor + SCHEDULE_BLOCK)


plan(
    Path("backend/app/api/v1/app_master.py"),
    "app_master_change_scheduled",
    build_app_master_route,
)


# ── 5. the scheduler lands due requests every tick ───────────────────────────────
APPLY_DUE_FN = '''async def _apply_due_app_master_changes(
    sessionmaker: async_sessionmaker[Any], settings: Settings
) -> None:
    """Land any admin App Master edit whose delay has elapsed.

    Runs on the ordinary minute tick, not the once-a-day pass: a ten-minute undo window is
    only meaningful if something is watching it that often. Its own session, so a failure
    here cannot reach the sync.
    """
    async with sessionmaker() as db:
        try:
            applied = await app_master_request_service.apply_due(db, settings)
        except Exception:  # noqa: BLE001 - must never kill the scheduler loop
            log.exception("scheduled App Master changes failed to apply")
            return
    if applied:
        log.info("applied %d scheduled App Master change(s)", applied)


'''

APPLY_DUE_CALL = '''        try:
            # Admin App Master edits whose undo window has closed. Every tick, because a
            # ten-minute window is only meaningful if something checks it that often.
            await _apply_due_app_master_changes(sessionmaker, settings)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - must never kill the loop
            log.exception("applying scheduled App Master changes failed")
'''


def build_scheduler(text: str) -> str:
    path = Path("backend/app/services/sync_scheduler.py")
    text = add_service_imports(text, path, ["app_master_request_service"])

    tick = "async def _tick("
    once(text, tick, path)
    text = text.replace(tick, APPLY_DUE_FN + tick)

    # Insert the call immediately before the try: that guards report delivery. Located by
    # walking back from the call itself, because the comment above it is prose and prose
    # drifts (an em-dash pass would break a comment anchor, never this one).
    marker = "await report_delivery_service.evaluate_due("
    at = text.find(marker)
    if at == -1:
        die(f"{path}: the scheduler loop's report-delivery step was not found")
    guard = text.rfind("\n        try:\n", 0, at)
    if guard == -1:
        die(f"{path}: no try: block guarding report delivery")
    cut = guard + 1
    return text[:cut] + APPLY_DUE_CALL + text[cut:]


plan(
    Path("backend/app/services/sync_scheduler.py"),
    "_apply_due_app_master_changes",
    build_scheduler,
)


# ── 6. existing App Master tests state their own timing assumption ───────────────
APPLY_NOW_HELPER = '''

async def _apply_immediately(env: MetricsEnv) -> None:
    """Turn the admin edit delay off for tests that assert the edit lands NOW.

    An admin PATCH is normally SCHEDULED (see test_app_master_requests.py) and applies by
    itself after a delay. These tests are about the write path itself, so they state their
    own assumption rather than depending on whatever the default happens to be.
    """
    async with env.sessionmaker() as s:
        await settings_service.set_value(
            s, "app_master_apply_delay_minutes", 0, uuid.UUID(_metrics_uid("admin"))
        )
'''


def build_app_master_tests(text: str) -> str:
    path = Path("backend/tests/test_app_master.py")
    text = add_service_imports(text, path, ["settings_service"])

    conftest = "from tests.conftest import MetricsEnv\n"
    once(text, conftest, path)
    text = text.replace(conftest, "from tests.conftest import MetricsEnv, _metrics_uid\n")

    typing_import = "from typing import Any\n"
    once(text, typing_import, path)
    text = text.replace(typing_import, "import uuid\nfrom typing import Any\n")

    auth = '''def _auth(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer valid-{role}"}
'''
    once(text, auth, path)
    text = text.replace(auth, auth + APPLY_NOW_HELPER)

    seed = "    await _seed(metrics_env)\n"
    add = "    await _apply_immediately(metrics_env)\n"
    for func in (
        "async def test_edit_writes_bigquery_then_postgres_and_audits(",
        "async def test_edit_leaves_postgres_untouched_when_bigquery_write_fails(",
        "async def test_edit_records_history_and_undo_restores(",
    ):
        text = insert_after_line_in_function(text, path, func, seed, add)
    return text


plan(Path("backend/tests/test_app_master.py"), "_apply_immediately", build_app_master_tests)


# ── 7. the new table + the new migration head ────────────────────────────────────
def build_metadata_test(text: str) -> str:
    path = Path("backend/tests/test_models_metadata.py")
    match = re.search(r"\n(\s*)\"[a-z_]+\",\n\}\n", text)
    if match is None:
        die(f"{path}: could not find the end of EXPECTED_TABLES")
    cut = match.end() - 2
    return text[:cut] + '    "app_master_change_requests",\n' + text[cut:]


plan(
    Path("backend/tests/test_models_metadata.py"),
    "app_master_change_requests",
    build_metadata_test,
)


def build_migration_test(text: str) -> str:
    path = Path("backend/tests/test_migrations.py")
    new, n = re.subn(
        r'_HEAD = "[0-9a-f]+".*',
        '_HEAD = "e51b8c46f2d7"  # app_master_change_requests (current head)',
        text,
        count=1,
    )
    if n != 1:
        die(f"{path}: no _HEAD pin found - the file has changed shape")
    return new


plan(Path("backend/tests/test_migrations.py"), "e51b8c46f2d7", build_migration_test)


# ── 8. nav: one gating rule, read by all three navigators ────────────────────────
NAV_HELPER = '''

/** The items one caller may see. Hiding is COSMETIC - every route behind these is enforced
 *  server-side - but the sidebar, mobile drawer and command palette must agree, so they all
 *  read this rather than each re-deriving the rule. */
export function visibleNavItems(
  capabilities: string[] | undefined,
  roles: string[] | undefined,
): NavItem[] {
  const isAdmin = capabilities?.includes("admin_panel") ?? false;
  return NAV_ITEMS.filter((item) => {
    if (item.requiresAdmin && !isAdmin) return false;
    if (item.requiresRole && !isAdmin && !item.requiresRole.some((r) => roles?.includes(r)))
      return false;
    return true;
  });
}
'''

NAV_ENTRY = '''  {
    href: "/app-changes",
    label: "App Changes",
    icon: ClipboardCheck,
    requiresRole: ["pod_owner"],
  },
'''


def build_nav(text: str) -> str:
    path = Path("frontend/lib/nav.ts")
    close = '} from "lucide-react";\n'
    once(text, close, path)
    text = text.replace(close, "  ClipboardCheck,\n" + close)

    field = "  requiresAdmin?: boolean;\n"
    once(text, field, path)
    text = text.replace(
        field,
        field
        + "  /** Only shown to callers holding one of these roles. Admins always see it - they\n"
        + "   *  are the other half of every workflow gated this way. */\n"
        + "  requiresRole?: string[];\n",
    )

    entry = '  { href: "/app-master", label: "App Master", icon: Database, requiresAdmin: true },\n'
    once(text, entry, path)
    text = text.replace(entry, NAV_ENTRY + entry)
    return text.rstrip("\n") + "\n" + NAV_HELPER


plan(Path("frontend/lib/nav.ts"), "visibleNavItems", build_nav)


def build_sidebar(text: str) -> str:
    path = Path("frontend/components/layout/sidebar.tsx")
    imp = 'import { NAV_ITEMS } from "@/lib/nav";'
    once(text, imp, path)
    text = text.replace(imp, 'import { visibleNavItems } from "@/lib/nav";')
    old = """  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;

  const visible = useMemo(
    () => NAV_ITEMS.filter((item) => !item.requiresAdmin || isAdmin),
    [isAdmin],
  );"""
    once(text, old, path)
    return text.replace(
        old,
        """  const visible = useMemo(
    () => visibleNavItems(me?.capabilities, me?.roles),
    [me?.capabilities, me?.roles],
  );""",
    )


plan(Path("frontend/components/layout/sidebar.tsx"), "visibleNavItems", build_sidebar)


def build_mobile_nav(text: str) -> str:
    path = Path("frontend/components/layout/mobile-nav.tsx")
    imp = 'import { NAV_ITEMS } from "@/lib/nav";'
    once(text, imp, path)
    text = text.replace(imp, 'import { visibleNavItems } from "@/lib/nav";')
    old = """  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;
  const items = NAV_ITEMS.filter((item) => !item.requiresAdmin || isAdmin);"""
    once(text, old, path)
    return text.replace(old, "  const items = visibleNavItems(me?.capabilities, me?.roles);")


plan(Path("frontend/components/layout/mobile-nav.tsx"), "visibleNavItems", build_mobile_nav)


def build_palette(text: str) -> str:
    path = Path("frontend/components/layout/command-palette.tsx")
    imp = 'import { NAV_ITEMS } from "@/lib/nav";'
    once(text, imp, path)
    text = text.replace(imp, 'import { visibleNavItems } from "@/lib/nav";')
    old = '  const isAdmin = me?.capabilities.includes("admin_panel") ?? false;\n'
    once(text, old, path)
    text = text.replace(
        old, "  const capabilities = me?.capabilities;\n  const roles = me?.roles;\n"
    )
    pages = (
        "    const pages: Command[] = NAV_ITEMS.filter((n) => !n.requiresAdmin || isAdmin)"
        ".map((n) => ({\n"
    )
    once(text, pages, path)
    text = text.replace(
        pages, "    const pages: Command[] = visibleNavItems(capabilities, roles).map((n) => ({\n"
    )
    deps = "  }, [isAdmin, router]);"
    once(text, deps, path)
    return text.replace(deps, "  }, [capabilities, roles, router]);")


plan(Path("frontend/components/layout/command-palette.tsx"), "visibleNavItems", build_palette)


# ── 9. the hooks (appended - the file's tail is the one part that never drifts) ──
HOOKS = '''

// -- App Master change requests (propose -> admin approves) -------------------
/** One queued edit to the app master. `stale` names the columns whose value moved
 *  underneath the request while it waited; empty means nothing changed. */
export interface AppMasterChangeRequest {
  id: string;
  canonical_key: string;
  changes: Record<string, unknown>;
  before_snapshot: Record<string, unknown>;
  status: "pending" | "scheduled" | "approved" | "rejected" | "cancelled" | "failed";
  requested_by_name: string | null;
  requested_at: string;
  /** Set only while scheduled: when it applies by itself unless cancelled. */
  apply_after: string | null;
  decided_at: string | null;
  decision_note: string | null;
  stale: Record<string, { when_proposed: unknown; now: unknown }>;
}

/** The editable columns of one app, for building a proposal form. */
export interface AppMasterEditableRow {
  canonical_key: string;
  app_name: string | null;
  values: Record<string, unknown>;
}

export function useChangeRequests(openOnly = true) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["app-master-requests", openOnly],
    queryFn: () =>
      apiFetch<AppMasterChangeRequest[]>(
        `/api/v1/app-master-requests${buildQuery({ open_only: openOnly })}`,
      ),
    enabled: Boolean(user),
    refetchInterval: 60000,
  });
}

/** Current values for one app - 404s (and so stays undefined) outside the caller's scopes. */
export function useEditableRow(canonicalKey: string | null) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["app-master-editable", canonicalKey],
    queryFn: () =>
      apiFetch<AppMasterEditableRow>(
        `/api/v1/app-master-requests/editable/${encodeURIComponent(canonicalKey ?? "")}`,
      ),
    enabled: Boolean(user) && Boolean(canonicalKey),
    retry: false,
  });
}

function invalidateRequests(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["app-master-requests"] });
  queryClient.invalidateQueries({ queryKey: ["app-master"] });
  queryClient.invalidateQueries({ queryKey: ["app-master-editable"] });
}

export function useProposeChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { canonical_key: string; changes: Record<string, unknown> }) =>
      apiFetch<AppMasterChangeRequest>("/api/v1/app-master-requests", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidateRequests(queryClient),
  });
}

export function useApproveChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<Record<string, unknown>>(`/api/v1/app-master-requests/${id}/approve`, {
        method: "POST",
      }),
    onSuccess: () => invalidateRequests(queryClient),
  });
}

export function useRejectChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string }) =>
      apiFetch<AppMasterChangeRequest>(`/api/v1/app-master-requests/${id}/reject`, {
        method: "POST",
        body: JSON.stringify({ note: note?.trim() || null }),
      }),
    onSuccess: () => invalidateRequests(queryClient),
  });
}

export function useCancelChange() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<AppMasterChangeRequest>(`/api/v1/app-master-requests/${id}/cancel`, {
        method: "POST",
      }),
    onSuccess: () => invalidateRequests(queryClient),
  });
}
'''


def build_hooks(text: str) -> str:
    for needed in ("buildQuery", "useQueryClient", "useAuth", "apiFetch"):
        if needed not in text:
            die(f"frontend/lib/api-hooks.ts: {needed} is not imported - the file has changed shape")
    return text.rstrip("\n") + "\n" + HOOKS


plan(Path("frontend/lib/api-hooks.ts"), "useChangeRequests", build_hooks)


# ── 10. README (documentation - never fatal) ─────────────────────────────────────
README_SECTION = '''
### App Master change approval
Editing the app master is no longer a thing one person does alone.

**Pod owners** get an **App Changes** page. They pick one of *their* apps (an app outside
their row scopes answers 404, exactly like an app that does not exist), change any of the six
editable columns, and send it. Nothing is written anywhere - not BigQuery, not the serving
copy - until an admin approves it. Values are validated on the way IN through the same
`AppMasterUpdate` model the admin edit uses, so a bad `pod` is refused when it is proposed
rather than when it is approved.

**Admins** see every waiting request on the same page and either approve (which applies it
through the ordinary edit path - BigQuery first, then Postgres, change history, undo) or
reject it with a reason. The proposer is notified either way.

An **admin's own edit is scheduled, not instant**: it lands by itself after
`app_master_apply_delay_minutes` (Admin -> Settings, default **10**) unless somebody cancels
it first. That is an undo window that needs nobody else to be awake; setting the delay to
`0` restores the old immediate behaviour. The scheduler applies due requests every tick, each
one isolated - a request that cannot be written is parked as `failed` and the admins are told,
so one bad row never stops the rest.

If somebody else changes the same column while a request waits, the request is flagged
**stale** and the approval screen shows the admin both values. It is flagged, never refused:
the newer value is sometimes the wrong one, and the admin is the one who can tell.

The change history credits the **proposer** as the editor and the audit log records the
**approver** - "whose edit is this" and "who let it through" are different questions.

'''


def try_readme() -> None:
    path = ROOT / "README.md"
    if not path.exists():
        return
    text = path.read_text()
    if "App Master change approval" in text:
        skipped.append("README.md: already documented")
        return
    match = re.search(r"\n### Explore [^\n]*\n", text)
    if match is None:
        skipped.append("README.md: no place to put the section (skipped, docs only)")
        return
    path.write_text(text[: match.start()] + "\n" + README_SECTION.strip("\n") + text[match.start() :])
    print("wrote README.md")


# ── write ────────────────────────────────────────────────────────────────────────
buffer = io.BytesIO(base64.b64decode(PAYLOAD))
with tarfile.open(fileobj=buffer, mode="r:gz") as tar:
    members = tar.getnames()
    tar.extractall(ROOT)
for name in members:
    print(f"wrote {name}")

for path, text in edits:
    path.write_text(text)
    print(f"patched {path}")
for note in skipped:
    print(note)

try_readme()

if not edits and not members:
    print("nothing to do")
print("done")
