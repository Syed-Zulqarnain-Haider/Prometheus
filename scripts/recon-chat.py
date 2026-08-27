#!/usr/bin/env python3
"""Read-only: everything needed to make the Gemini assistant answer.

The widget renders only when /api/v1/chat/status says `available`. That flag has
several possible causes - no key, no provider registered, an admin toggle off, a
model name the SDK rejects - and they look identical from the browser. This finds
which one it is instead of guessing.

Prints NO key material: any value that looks like a credential is masked to its
length and last four characters.

Writes nothing.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BE = ROOT / "backend"
FE = ROOT / "frontend"
SKIP = ("node_modules", ".next", "__pycache__")
SECRET = re.compile(r"(key|token|secret|password|dsn|credential)", re.I)


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n== {title}\n{'=' * 78}")


def mask(value: str) -> str:
    value = value.strip()
    if len(value) <= 8:
        return f"<set, {len(value)} chars>"
    return f"<set, {len(value)} chars, ends {value[-4:]}>"


def files(root: Path, *patterns: str) -> list[Path]:
    out: list[Path] = []
    for pattern in patterns:
        out += [p for p in root.rglob(pattern) if not any(s in p.parts for s in SKIP)]
    return sorted(set(out))


def dump(path: Path, cap: int = 200) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    print(f"\n--- {path.relative_to(ROOT)}  [1-{min(cap, len(lines))} of {len(lines)}]")
    for number, line in enumerate(lines[:cap], 1):
        print(f"{number:5}: {line}")


def scan(paths: list[Path], pattern: str, context: int = 0, limit: int = 120) -> None:
    regex = re.compile(pattern, re.I)
    shown = 0
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for index, line in enumerate(lines):
            if not regex.search(line) or shown >= limit:
                continue
            shown += 1
            print(f"\n{path.relative_to(ROOT)}:{index + 1}")
            for number in range(max(0, index - context), min(len(lines), index + context + 1)):
                mark = ">" if number == index else " "
                print(f"  {mark} {number + 1:5}: {lines[number].rstrip()[:150]}")
    if shown == 0:
        print("  (no matches)")


PY = files(BE / "app", "*.py")
TS = files(FE, "*.ts", "*.tsx")

rule("1. the assistant's backend - every file that mentions it")
for path in PY:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"gemini|anthropic|openai|\bllm\b|assistant|ask.?your.?data|/chat", text, re.I):
        print(f"  {path.relative_to(ROOT)}")

rule("2. the chat routes and what gates `available`")
scan(files(BE / "app" / "api", "*.py"), r"chat|assistant|provider|available", context=4)

rule("3. the provider registry - which models are wired, and how the key is read")
scan(PY, r"gemini|generativeai|google\.genai|anthropic|openai|api_key|model\s*=|MODEL", context=3)

rule("4. where the key is expected to come from")
print("-- Settings fields --")
scan(files(BE / "app" / "core", "config.py"), r".*", limit=200)

rule("5. what is actually set in the running backend (values MASKED)")
probe = (
    "import os,json;"
    "print(json.dumps({k: v for k, v in os.environ.items() "
    "if any(w in k.upper() for w in ('GEMINI','GOOGLE','ANTHROPIC','OPENAI','CHAT','LLM','AI_'))}))"
)
result = subprocess.run(
    f'docker compose -f docker-compose.prod.yml exec -T backend python -c "{probe}"',
    shell=True, capture_output=True, text=True, cwd=ROOT,
)
raw = (result.stdout or result.stderr or "").strip()
if raw.startswith("{"):
    import json

    for name, value in sorted(json.loads(raw).items()):
        print(f"  {name} = {mask(value) if SECRET.search(name) else value}")
    if raw == "{}":
        print("  (nothing set - no provider credential reaches the backend)")
else:
    print(f"  could not read the backend environment: {raw[:300]}")

rule("6. operational settings rows (an admin toggle can also hold the key)")
probe2 = r'''
import os, re, psycopg
dsn = re.sub(r"^postgresql\+\w+://", "postgresql://",
             os.environ.get("PG_DSN") or os.environ.get("DATABASE_URL") or "")
if not dsn:
    raise SystemExit("no DSN")
with psycopg.connect(dsn) as pg, pg.cursor() as cur:
    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema='public' AND table_name LIKE '%setting%'""")
    for (table,) in cur.fetchall():
        print("--", table)
        cur.execute(f"SELECT * FROM {table} LIMIT 40")
        cols = [d.name for d in cur.description]
        print("   " + " | ".join(cols))
        for row in cur.fetchall():
            cells = []
            for name, value in zip(cols, row):
                text = "" if value is None else str(value)
                if re.search("key|token|secret|password", name, re.I) and text:
                    text = f"<set, {len(text)} chars>"
                cells.append(text[:60])
            print("   " + " | ".join(cells))
'''
result2 = subprocess.run(
    f"docker compose -f docker-compose.prod.yml exec -T backend python -c {probe2!r}",
    shell=True, capture_output=True, text=True, cwd=ROOT,
)
print((result2.stdout or result2.stderr or "").strip()[:4000])

rule("7. the admin UI that is supposed to configure it")
scan(TS, r"chat.?status|useSendChat|provider|assistant|api.?key", context=2, limit=60)

rule("7b. RBAC - can the assistant answer about apps the asker cannot see?")
print("""  The widget tells every user "I only ever see the data you're allowed to see".
  These are the four ways that sentence is either true or a lie:

    a) does the chat path build its queries through QueryBuilder(context) - the same
       object the REST API uses, which injects the caller's row scopes into WHERE -
       or does it query the fact table directly?
    b) does the MODEL write SQL? Text-to-SQL cannot be scope-safe: the scope has to be
       injected by code the model cannot edit, not asked for in a prompt.
    c) are metric-group permissions applied, or can a viewer ask for profit?
    d) is any answer CACHED on a key that omits the caller's scope? That leaks across
       users even when every query was correctly scoped.
""")

CHAT_FILES = [
    path for path in PY
    if re.search(r"gemini|anthropic|openai|\bllm\b|assistant|/chat|chat_", 
                 path.read_text(encoding="utf-8", errors="ignore"), re.I)
]
print(f"  chat-related backend modules: {[str(p.relative_to(ROOT)) for p in CHAT_FILES]}\n")

print("-- (a) does it go through the scoped query builder? --")
scan(CHAT_FILES, r"QueryBuilder|build_scope_filter|fact_scope_filter|UserContext|context\.scopes",
     context=3)

print("\n-- (b) does the MODEL produce SQL, or call fixed tools? --")
scan(CHAT_FILES, r"SELECT |FROM fact|text\(|execute\(|tool|function_call|schema|prompt",
     context=3, limit=80)

print("\n-- (c) metric permissions --")
scan(CHAT_FILES, r"metric_groups|permitted_measures|Group\.|require_capability", context=2)

print("\n-- (d) cache keys - do they carry the caller's scope? --")
scan(CHAT_FILES, r"cache|redis|scope_token|perms_token|aggregate_cache_key", context=3)

print("\n-- what the model is actually told (system prompt) --")
scan(CHAT_FILES, r"system|SYSTEM_PROMPT|role\s*[:=]\s*[\"']system", context=6, limit=40)

rule("8. is a Gemini SDK even installed?")
for name in ("backend/pyproject.toml", "backend/requirements.txt"):
    path = ROOT / name
    if path.exists():
        print(f"\n-- {name}")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"gemini|google|genai|anthropic|openai|httpx", line, re.I):
                print(f"  {number:5}: {line.strip()}")

print("\nread-only: nothing was written. No key material printed.")
