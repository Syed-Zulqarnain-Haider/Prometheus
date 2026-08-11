#!/usr/bin/env bash
#
# Set up the `production` / `dev` branch pair on the DEPLOYED host, committing the live
# working tree first so nothing that is currently serving traffic is lost.
#
#   Dry run (default - shows exactly what it would do, changes nothing):
#     bash scripts/setup-branches.sh
#
#   Do it:
#     bash scripts/setup-branches.sh --yes
#
# Why not `git add -A`: the deployed tree carries untracked junk (backups/, caches) and may
# carry real secrets (.env, keys). This stages tracked edits plus only the untracked files
# that survive a denylist, and ABORTS outright if anything secret-looking is about to be
# committed - a secret in git history is not something you can take back with a revert.

set -euo pipefail

CONFIRM="${1:-}"
COMMIT_MSG="chore: snapshot deployed state before branch split"

# Untracked paths never worth committing. Matched against the path as git reports it.
JUNK_RE='(^|/)(backups?|node_modules|__pycache__|\.next|\.venv|venv|\.mypy_cache|\.pytest_cache|\.ruff_cache)(/|$)|\.(log|bak|pyc|swp)$|\.bak\.[0-9]+$'

# Anything matching this must NEVER enter git history. `.env.example` is fine; `.env` is not.
SECRET_RE='(^|/)\.env($|\.[^/]*$)|(^|/)secrets?/|\.(pem|key|p12|pfx)$|credentials.*\.json$|service[-_]account.*\.json$'
SECRET_ALLOW_RE='\.example$|\.sample$|\.template$'

say() { printf '%s\n' "$*"; }
die() { printf 'ABORTED: %s\n' "$*" >&2; exit 1; }

git rev-parse --git-dir >/dev/null 2>&1 || die "not inside a git repository"
cd "$(git rev-parse --show-toplevel)"

CURRENT="$(git rev-parse --abbrev-ref HEAD)"
say "repository : $(pwd)"
say "on branch  : ${CURRENT}"
say ""

# ── What would be committed ──────────────────────────────────────────────────────
mapfile -t TRACKED < <(git diff --name-only)          # modified, tracked
mapfile -t STAGED  < <(git diff --cached --name-only) # already staged
mapfile -t UNTRACKED_ALL < <(git ls-files --others --exclude-standard)

UNTRACKED=()
SKIPPED=()
for path in "${UNTRACKED_ALL[@]:-}"; do
  [ -z "${path}" ] && continue
  if printf '%s' "${path}" | grep -Eq "${JUNK_RE}"; then
    SKIPPED+=("${path}")
  else
    UNTRACKED+=("${path}")
  fi
done

say "tracked files modified : ${#TRACKED[@]}"
say "already staged         : ${#STAGED[@]}"
say "untracked to include   : ${#UNTRACKED[@]}"
say "untracked skipped      : ${#SKIPPED[@]} (backups, caches, logs)"
say ""

if [ "${#UNTRACKED[@]}" -gt 0 ]; then
  say "New files that WILL be committed:"
  printf '  + %s\n' "${UNTRACKED[@]}"
  say ""
fi
if [ "${#SKIPPED[@]}" -gt 0 ]; then
  say "Skipped as junk (left untracked on disk, not deleted):"
  printf '  - %s\n' "${SKIPPED[@]:0:20}"
  [ "${#SKIPPED[@]}" -gt 20 ] && say "  ... and $(( ${#SKIPPED[@]} - 20 )) more"
  say ""
fi

# ── Secret guard: refuse rather than warn ────────────────────────────────────────
CANDIDATES=("${TRACKED[@]:-}" "${STAGED[@]:-}" "${UNTRACKED[@]:-}")
DANGER=()
for path in "${CANDIDATES[@]}"; do
  [ -z "${path}" ] && continue
  if printf '%s' "${path}" | grep -Eq "${SECRET_RE}" && ! printf '%s' "${path}" | grep -Eq "${SECRET_ALLOW_RE}"; then
    DANGER+=("${path}")
  fi
done
if [ "${#DANGER[@]}" -gt 0 ]; then
  printf 'Secret-looking files are in the commit set:\n' >&2
  printf '  ! %s\n' "${DANGER[@]}" >&2
  die "refusing to commit. Add them to .gitignore (and 'git rm --cached' if tracked), then re-run."
fi
say "secret scan            : clean"

# ── Branch collision check ───────────────────────────────────────────────────────
for branch in production dev; do
  if git show-ref --verify --quiet "refs/heads/${branch}"; then
    die "local branch '${branch}' already exists - delete it or run the remaining steps by hand."
  fi
done

if [ "${CONFIRM}" != "--yes" ]; then
  say ""
  say "DRY RUN - nothing changed. Re-run with --yes to:"
  say "  1. commit the above onto '${CURRENT}'"
  say "  2. create 'production' and 'dev' at that commit"
  say "  3. push both to origin, then check out 'dev'"
  exit 0
fi

# ── Act ──────────────────────────────────────────────────────────────────────────
git add -u
[ "${#UNTRACKED[@]}" -gt 0 ] && git add -- "${UNTRACKED[@]}"

if git diff --cached --quiet; then
  say "nothing to commit - the tree is already clean"
else
  git commit -m "${COMMIT_MSG}"
  say "committed onto ${CURRENT}"
fi

git branch production
git branch dev
git push -u origin production
git push -u origin dev
git checkout dev

say ""
say "Done. production and dev both point at $(git rev-parse --short HEAD); you are on dev."
say "Make changes on dev; merge dev into production when you want them live."
