#!/usr/bin/env bash
#
# Make `git push` on the deployed host do the safe thing by default:
#
#   * push.default = simple  -> a bare `git push` pushes the CURRENT branch to the branch
#     of the same name on origin. On `dev` (where the server lives) that is `origin/dev`.
#     It can never fan out to other branches.
#
#   * a pre-push hook that REFUSES a push to `production` unless it is deliberate.
#     Production is what goes live; reaching it should be a decision, not a reflex.
#     To promote on purpose:  ALLOW_PROD_PUSH=1 git push origin production
#
# Run on the server, from the repo root:
#     bash scripts/install-git-guards.sh
#
# Re-runnable. Only touches this repository's config and its .git/hooks/pre-push.

set -euo pipefail

git rev-parse --git-dir >/dev/null 2>&1 || { echo "ABORTED: not inside a git repository" >&2; exit 1; }
cd "$(git rev-parse --show-toplevel)"
HOOK_DIR="$(git rev-parse --git-path hooks)"
HOOK="${HOOK_DIR}/pre-push"

git config push.default simple
git config push.autoSetupRemote true   # a new branch pushes to a same-named branch on origin

mkdir -p "${HOOK_DIR}"

# An existing hook that is not ours is left alone - overwriting someone else's hook silently
# is how automation eats work.
if [ -f "${HOOK}" ] && ! grep -q 'prometheus-prod-guard' "${HOOK}"; then
  echo "ABORTED: ${HOOK} already exists and was not written by this script." >&2
  echo "Move it aside and re-run, or add the guard to it by hand." >&2
  exit 1
fi

cat > "${HOOK}" <<'HOOK_EOF'
#!/usr/bin/env bash
# prometheus-prod-guard - refuse accidental pushes to production.
# Promote deliberately with:  ALLOW_PROD_PUSH=1 git push origin production
set -euo pipefail

while read -r _local_ref _local_sha remote_ref _remote_sha; do
  [ -z "${remote_ref:-}" ] && continue
  case "${remote_ref}" in
    refs/heads/production)
      if [ "${ALLOW_PROD_PUSH:-}" != "1" ]; then
        printf '\n'                                                              >&2
        printf 'Push to PRODUCTION blocked.\n'                                   >&2
        printf 'production is what goes live, so pushing to it is deliberate.\n' >&2
        printf '\n'                                                              >&2
        printf 'To promote what is on dev:\n'                                    >&2
        printf '    git checkout production\n'                                   >&2
        printf '    git merge dev\n'                                             >&2
        printf '    ALLOW_PROD_PUSH=1 git push origin production\n'              >&2
        printf '    git checkout dev\n'                                          >&2
        printf '\n'                                                              >&2
        exit 1
      fi
      printf 'Pushing to production deliberately (ALLOW_PROD_PUSH=1).\n' >&2
      ;;
  esac
done

exit 0
HOOK_EOF

chmod +x "${HOOK}"

echo "push.default        : $(git config push.default)"
echo "push.autoSetupRemote: $(git config push.autoSetupRemote)"
echo "pre-push hook       : ${HOOK}"
echo ""
echo "On branch '$(git rev-parse --abbrev-ref HEAD)', a bare 'git push' now goes to origin/$(git rev-parse --abbrev-ref HEAD)."
echo "Pushes to production are blocked unless ALLOW_PROD_PUSH=1 is set."
