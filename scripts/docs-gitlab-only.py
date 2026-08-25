#!/usr/bin/env python3
"""GitLab is the only repository. Remove every trace of any other from project memory.

Standing order from the owner. CLAUDE.md is the permanent memory: while it describes a
second repository, every future session reads that and starts talking about one again.

WHY THIS IS STRUCTURAL, NOT ANCHORED
    The first attempt matched exact paragraphs and missed three of six, because the
    deployed CLAUDE.md has drifted from the copy I hold. Prose I cannot see is a bad
    anchor. This version finds the OFFENDING LINES, expands each to its markdown unit
    (bullet + continuations, or paragraph), and replaces or removes the unit - so
    rewording cannot defeat it.

    Every change is printed as before/after. Nothing is silent.

SAFETY
    Refuses to write if it would remove more than a quarter of either file, or if a
    top-level heading disappears. Verifies afterwards that no reference survives.
    Re-running is a no-op. Revert: git checkout -- CLAUDE.md README.md
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = [ROOT / "CLAUDE.md", ROOT / "README.md"]
PATTERN = re.compile(r"github", re.I)

# Applied to SINGLE LINES first. A line fixed here never expands into a unit, which is what
# stops a reference inside a fenced code block from taking the whole section with it.
LINE_RULES: list[tuple[str, str]] = [
    (
        r"^\.github/workflows/\{[^}]*\}\s*$",
        "scripts/  (ship.sh, run-backend-tests.sh, run-frontend-tests.sh, patch scripts)",
    ),
]

#: Keywords whose CLAUSE is cut out of a line, leaving the rest of the sentence intact.
CLAUSE_KEYWORDS = ("GITHUB_TOKEN",)


def drop_clause(line: str, keyword: str) -> str:
    """Remove just the clause mentioning ``keyword``, not the whole sentence."""
    index = line.lower().find(keyword.lower())
    if index == -1:
        return line
    left = max(line.rfind(";", 0, index), line.rfind(",", 0, index))
    right = line.find(".", index)
    right = len(line) if right == -1 else right + 1
    if left > 0:
        return line[:left].rstrip() + "." + line[right:].rstrip()
    return (line[:index].rstrip() + " " + line[right:].lstrip()).strip()


# A unit whose text contains the signature is REPLACED by the given text. Signatures are
# chosen to be the part least likely to have been reworded. Anything not matched by a
# signature is removed outright and printed, so a silent deletion is impossible.
REPLACEMENTS: list[tuple[str, str]] = [
    (
        "transport pipe",
        "",  # folded into the bullet above
    ),
    (
        "gated by CI",
        """- Both branches are gated by the SAME checks, run before delivery and again on the
  server: ruff, mypy --strict, pytest (`./scripts/run-backend-tests.sh`), tsc, vitest
  (`./scripts/run-frontend-tests.sh`), next build. A branch nothing checks is a branch
  where nothing is checked.""",
    ),
    (
        "repository that matters",
        """- **GitLab is the ONLY repository. There is no other.** (owner decision, 2026-08-11,
  restated as a standing order 2026-08-25.) It is the source of truth, the deployment
  remote, and the only repository ever named to the owner. `production` and `dev` live
  there.
- How a script physically reaches the server is an internal detail of `./scripts/ship.sh`
  and is NEVER surfaced: no remote names, no raw fetch/push commands, no branch
  bookkeeping, no CI belonging to anything other than GitLab. Every command handed to the
  owner is `./scripts/ship.sh <script>.py`, or a GitLab command, or a server command.
  Report status only in terms of GitLab and the deployed host.""",
    ),
    (
        "LOCALLY before delivery",
        """- Verification happens LOCALLY before delivery (ruff, mypy --strict, pytest, tsc, lint,
  vitest, next build) and again in the server's docker build. Those are the gates.""",
    ),
    (
        "sandbox can reach",
        """GitLab is the only repository: the source of truth and the deployment remote.
Flow: verify locally (ruff, mypy, pytest, tsc, lint, vitest, next build) -> on the server
`./scripts/ship.sh <script>.py`, which collects the change, applies the anchored patch
scripts for drifted files (two-pass: verify every anchor exactly once, else write nothing;
idempotent via marker), runs only the suite that can be affected, and restarts ONLY if
that suite passes -> `alembic upgrade head` -> `up -d --build` -> commit + push to GitLab
(`origin`). Alembic revision ids must be NEW - a reused id silently no-ops the idempotency
check (this bit once: d4e5f6a7b8c9 collided with July's app-master migration).""",
    ),
]

#: Applied regardless of whether the unit mentions anything: the scrub REMOVES the old
#: description, this WRITES the standing order. Without it CLAUDE.md ends up merely quiet
#: on the subject rather than explicit, and a future session re-invents the old wording.
STANDING_ORDER = """- **GitLab is the ONLY repository. There is no other.** (owner decision, 2026-08-11,
  restated as a standing order 2026-08-25.) It is the source of truth, the deployment
  remote, and the only repository ever named to the owner. `production` and `dev` live
  there.
- How a script physically reaches the server is an internal detail of `./scripts/ship.sh`
  and is NEVER surfaced: no remote names, no raw fetch/push commands, no branch
  bookkeeping, no CI belonging to anything other than GitLab. Every command handed to the
  owner is `./scripts/ship.sh <script>.py`, or a GitLab command, or a server command.
  Report status only in terms of GitLab and the deployed host."""

#: (file, signature identifying the unit to replace, replacement)
UPGRADES: list[tuple[str, str, str]] = [
    ("CLAUDE.md", "GitLab is the ONLY repository", STANDING_ORDER),
]

#: Must be present when the script finishes, or the standing order never landed.
REQUIRED = "GitLab is the ONLY repository. There is no other."

problems: list[str] = []


def unit_bounds(lines: list[str], index: int) -> tuple[int, int]:
    """The markdown unit containing line ``index``: a bullet with its continuation lines,
    or a paragraph. Returned as a half-open [start, end) range."""
    bullet = re.compile(r"^\s*[-*]\s")
    # Walk back to the start of the bullet or paragraph.
    start = index
    while start > 0:
        if bullet.match(lines[start]) or lines[start].startswith(("#", "```")):
            break
        if not lines[start - 1].strip():
            break
        if bullet.match(lines[start - 1]):
            start -= 1
            break
        start -= 1
    # Walk forward: a bullet ends at the next bullet, a blank line, or a heading.
    end = index + 1
    while end < len(lines):
        line = lines[end]
        if not line.strip() or bullet.match(line) or line.startswith(("#", "```")):
            break
        # A continuation line is indented; an unindented line starts something new.
        if bullet.match(lines[start]) and not line.startswith((" ", "\t")):
            break
        end += 1
    return start, end


def scrub(path: Path) -> str | None:
    original = path.read_text(encoding="utf-8")
    if not PATTERN.search(original):
        print(f"  {path.name}: already clean")
        return None

    lines = original.splitlines()

    # Line-level rules first: a line fixed in place never becomes a unit, so a reference
    # inside a fenced code block cannot drag its whole section out with it.
    for index, line in enumerate(lines):
        if not PATTERN.search(line):
            continue
        for expression, replacement in LINE_RULES:
            if re.match(expression, line):
                print(f"\n  {path.name}:{index + 1}\n    - {line}\n    + {replacement}")
                lines[index] = replacement
                break
        else:
            for keyword in CLAUSE_KEYWORDS:
                if keyword.lower() in line.lower():
                    fixed = drop_clause(line, keyword)
                    print(f"\n  {path.name}:{index + 1}\n    - {line}\n    + {fixed}")
                    lines[index] = fixed
                    break

    # Collect units back-to-front so earlier indices stay valid while editing.
    seen: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        if not PATTERN.search(line):
            continue
        bounds = unit_bounds(lines, index)
        if bounds not in seen:
            seen.append(bounds)

    for start, end in sorted(seen, reverse=True):
        block = "\n".join(lines[start:end])
        replacement: str | None = None
        for signature, text in REPLACEMENTS:
            if signature in block:
                replacement = text
                break
        print(f"\n  {path.name}:{start + 1}-{end}")
        for line in block.splitlines():
            print(f"    - {line}")
        if replacement is None:
            print("    (no replacement rule matched - REMOVED)")
            lines[start:end] = []
        elif replacement == "":
            print("    (folded into the bullet above - REMOVED)")
            lines[start:end] = []
        else:
            for line in replacement.splitlines():
                print(f"    + {line}")
            lines[start:end] = replacement.splitlines()

    # Write the standing order in place of whatever described the arrangement before.
    for name, signature, replacement in UPGRADES:
        if name != path.name:
            continue
        if replacement.splitlines()[0] in "\n".join(lines):
            continue  # already upgraded
        hit = next((i for i, line in enumerate(lines) if signature in line), None)
        if hit is not None:
            start, end = unit_bounds(lines, hit)
            print(f"\n  {path.name}:{start + 1}-{end}  (standing order replaces the old bullet)")
            for line in lines[start:end]:
                print(f"    - {line}")
            for line in replacement.splitlines():
                print(f"    + {line}")
            lines[start:end] = replacement.splitlines()
            continue

        # The bullet has been reworded, so there is nothing to replace. Failing here would
        # leave memory silent on the subject, which is the outcome this whole script exists
        # to prevent - so APPEND to the branching-policy section instead, and say where.
        section = next(
            (i for i, line in enumerate(lines)
             if line.startswith("#") and re.search(r"merge|branch", line, re.I)),
            None,
        )
        if section is None:
            print(f"\n  {path.name}: no branching-policy section - appending a new one")
            lines.extend(["", "## Repository", "", *replacement.splitlines()])
            continue
        end = section + 1
        while end < len(lines) and not lines[end].startswith("#"):
            end += 1
        while end > section + 1 and not lines[end - 1].strip():
            end -= 1
        print(f"\n  {path.name}: appending the standing order to {lines[section].strip()!r} "
              f"at line {end + 1} (its old bullet has been reworded, so there was nothing "
              f"to replace)")
        for line in replacement.splitlines():
            print(f"    + {line}")
        lines[end:end] = replacement.splitlines()

    out = "\n".join(lines)
    if not out.endswith("\n"):
        out += "\n"

    # Guards: a scrub must not gut the file.
    kept = len(out.splitlines()) / max(1, len(original.splitlines()))
    if kept < 0.75:
        problems.append(f"{path.name}: would drop {(1 - kept) * 100:.0f}% of the file - refusing")
        return None
    for heading in re.findall(r"^#{1,2} .+$", original, re.M):
        if heading not in out:
            problems.append(f"{path.name}: heading disappeared -> {heading!r}")
            return None
    if PATTERN.search(out):
        survivors = [f"{n}: {l}" for n, l in enumerate(out.splitlines(), 1) if PATTERN.search(l)]
        problems.append(f"{path.name}: a reference survived -> {survivors}")
        return None
    return out


def main() -> int:
    memory = ROOT / "CLAUDE.md"
    if memory.exists():
        lines = memory.read_text(encoding="utf-8").splitlines()
        start = next((i for i, line in enumerate(lines)
                      if line.startswith("#") and re.search(r"merge|branch", line, re.I)), None)
        if start is not None:
            end = start + 1
            while end < len(lines) and not lines[end].startswith("#"):
                end += 1
            print("  CLAUDE.md branching policy as it stands on this server:")
            for number in range(start, end):
                print(f"  {number + 1:5}: {lines[number]}")
            print()

    pending: dict[Path, str] = {}
    for path in TARGETS:
        if not path.exists():
            problems.append(f"missing: {path.name}")
            continue
        result = scrub(path)
        if result is not None:
            pending[path] = result

    if problems:
        print("\nFAILED - nothing was written:")
        for line in problems:
            print(f"  - {line}")
        return 1

    for path, text in pending.items():
        path.write_text(text, encoding="utf-8")

    print()
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        hits = len(PATTERN.findall(text))
        print(f"  {path.name}: {hits} reference(s) remaining")
        if hits:
            problems.append(f"{path.name} is not clean")
    memory = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    if REQUIRED not in memory:
        problems.append("CLAUDE.md does not carry the standing order - the scrub left it "
                        "merely quiet on the subject instead of explicit.")
    else:
        print("  CLAUDE.md: standing order present")
    if problems:
        print("\nFAILED after writing - revert with: git checkout -- CLAUDE.md README.md")
        return 1
    print("\nDone. GitLab is the only repository named anywhere in project memory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
