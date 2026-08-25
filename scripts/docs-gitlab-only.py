#!/usr/bin/env python3
"""GitLab is the only repository. Strip every trace of any other from project memory.

Standing order from the owner. CLAUDE.md is the permanent memory, so this is not a
cosmetic edit: while that file described a second repository, every future session would
read it and start talking about one again.

Also removes the merge policy's dependence on CI belonging to anything other than GitLab -
the gates are the local suites and the server's docker build, which is what actually
gates a deploy here.

Nothing is written unless every anchor resolves exactly once. Re-running is a no-op.
Revert: git checkout -- CLAUDE.md README.md
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

EDITS: list[tuple[str, str, str, str]] = [
    (
        "CLAUDE.md",
        "merge policy no longer points at foreign CI",
        """- Both branches are gated by CI (`.github/workflows/ci.yml` watches `production`, `dev` and
  `main`) - a branch CI does not watch is a branch where nothing is checked.""",
        """- Both branches are gated by the SAME checks, run before delivery and again on the server:
  ruff, mypy --strict, pytest (`./scripts/run-backend-tests.sh`), tsc, vitest
  (`./scripts/run-frontend-tests.sh`), next build. A branch nothing checks is a branch
  where nothing is checked.""",
    ),
    (
        "CLAUDE.md",
        "one repository, and the delivery plumbing is never surfaced",
        """- **GitLab is the ONLY repository that matters** (owner decision, 2026-08-11). It is the
  source of truth and the deployment remote; `production` and `dev` live there.
- GitHub is a transport pipe ONLY, because the assistant's sandbox cannot reach GitLab:
  work is pushed to GitHub, the server fetches it from there, and the server pushes to
  GitLab. Never raise GitHub PRs, CI results, branch cleanup or mirror bookkeeping with the
  owner - it is plumbing, not their concern. Report status in terms of GitLab and the
  deployed host.
- Verification therefore happens LOCALLY before delivery (ruff, mypy --strict, pytest,
  tsc, lint, vitest, next build) and again in the server's docker build. GitHub Actions is
  not a gate the owner should ever hear about.""",
        """- **GitLab is the ONLY repository. There is no other.** (owner decision, 2026-08-11,
  restated as a standing order 2026-08-25.) It is the source of truth, the deployment
  remote, and the only repository ever to be named to the owner. `production` and `dev`
  live there.
- How a script physically reaches the server is an internal detail of
  `./scripts/ship.sh` and is NEVER surfaced: no remote names, no raw fetch/push commands,
  no branch bookkeeping, no CI belonging to anything other than GitLab. Every command
  handed to the owner is `./scripts/ship.sh <script>.py` or a GitLab/server command.
  Report status only in terms of GitLab and the deployed host.
- Verification happens LOCALLY before delivery (ruff, mypy --strict, pytest, tsc, lint,
  vitest, next build) and again in the server's docker build. Those are the gates.""",
    ),
    (
        "CLAUDE.md",
        "repository layout",
        ".github/workflows/{ci.yml, deploy-backend.yml, deploy-frontend.yml}",
        "scripts/  (ship.sh, run-backend-tests.sh, run-frontend-tests.sh, patch scripts)",
    ),
    (
        "README.md",
        "delivery pipeline described without naming a second repository",
        """The assistant's sandbox can reach GitHub but NOT GitLab; the server can reach both.
Flow: verify locally (ruff, mypy, pytest, tsc, lint, vitest, next build) -> push to the
GitHub transport branch -> on the server: `git fetch <github-url> dev` +
`git checkout FETCH_HEAD -- <explicit file paths>` (NEVER whole directories - the sandbox
tree is stale for server-drifted files) -> anchored patch scripts for drifted files""",
        """GitLab is the only repository: the source of truth and the deployment remote.
Flow: verify locally (ruff, mypy, pytest, tsc, lint, vitest, next build) -> on the server
`./scripts/ship.sh <script>.py`, which collects the change, applies it, runs only the
suite that can be affected, and restarts only if that suite passes -> anchored patch
scripts for drifted files""",
    ),
    (
        "README.md",
        "GitLab named as the only repository",
        "commit + push to GitLab (`origin`)",
        "commit + push to GitLab (`origin`) - the only repository",
    ),
    (
        "README.md",
        "no foreign CI token in the security notes",
        "  Firebase `*adminsdk*.json` key filenames; CI `GITHUB_TOKEN` is reduced to `contents: read`.",
        "  Firebase `*adminsdk*.json` key filenames.",
    ),
]

problems: list[str] = []
notes: list[str] = []


def main() -> int:
    pending: dict[Path, str] = {}
    for name, what, old, new in EDITS:
        path = ROOT / name
        if not path.exists():
            problems.append(f"missing: {name}")
            continue
        source = pending.get(path, path.read_text(encoding="utf-8"))
        if new in source and old not in source:
            notes.append(f"  {name}: already done - {what}")
            pending[path] = source
            continue
        count = source.count(old)
        if count != 1:
            problems.append(f"{name}: '{what}' matched {count} times, expected 1")
            continue
        pending[path] = source.replace(old, new, 1)
        notes.append(f"  {name}: {what}")

    if problems:
        return report()

    for path, text in pending.items():
        path.write_text(text, encoding="utf-8")

    # The point of the exercise: the word must be gone from project memory.
    for name in ("CLAUDE.md", "README.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        stragglers = [
            f"{name}:{number}: {line.strip()}"
            for number, line in enumerate(text.splitlines(), 1)
            if re.search(r"github", line, re.I)
        ]
        if stragglers:
            problems.append(f"{name} still names it:\n      " + "\n      ".join(stragglers))
        else:
            notes.append(f"  {name}: clean - no reference remains")
    return report()


def report() -> int:
    for line in notes:
        print(line)
    if problems:
        print("\nFAILED - review before committing:")
        for line in problems:
            print(f"  - {line}")
        return 1
    print("\nDone. GitLab is the only repository named anywhere in project memory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
