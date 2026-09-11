#!/usr/bin/env bash
#
# Push appended calibration lines to the calibration branch, safely.
#
# Calibration run #3 failed here:
#
#     ! [rejected]  calibration -> calibration (non-fast-forward)
#
# The old step fetched the branch with `git fetch origin "$BRANCH" || true`
# and then `git checkout -B "$BRANCH" "origin/$BRANCH"`, falling back to
# `git checkout -B "$BRANCH"` when that failed. On a tag push the checkout
# action configures no `refs/remotes/origin/*` refspec, so `origin/$BRANCH`
# did not exist, the `|| true` swallowed it, and the fallback started the
# branch from the *tag commit* -- unrelated to what the remote already had.
# The push could only be rejected.
#
# Three things this does differently:
#
#   1. Asks the remote whether the branch exists (`git ls-remote`) rather than
#      inferring it from whether a local ref happens to be configured, and
#      fetches an explicit refspec so the remote-tracking ref is really there.
#   2. Merges rather than rebases. The history is append-only: a rebase
#      conflicts on the last line and resolving it either way discards one
#      run's measurement. merge_history.py appends this run's lines to
#      whatever the branch now holds, so a concurrent run cannot be lost.
#   3. Retries a bounded number of times, re-deriving from the *new* tip each
#      attempt. Never force-pushes: a force here would delete exactly the
#      concurrent lines the retry exists to preserve.
#
# Usage:
#   push-calibration.sh <branch> <history-path> <new-lines-path> <message>
#
# Environment:
#   REMOTE          default origin
#   BASE_BRANCH     branch to create from when calibration does not exist yet
#                   (default main)
#   PUSH_ATTEMPTS   default 3

set -euo pipefail

BRANCH="${1:?branch}"
HISTORY="${2:?history path}"
NEW="${3:?new lines path}"
MSG="${4:?commit message}"

REMOTE="${REMOTE:-origin}"
BASE_BRANCH="${BASE_BRANCH:-main}"
PUSH_ATTEMPTS="${PUSH_ATTEMPTS:-3}"

if [ ! -s "$NEW" ]; then
  echo "no new calibration lines; nothing to push"
  exit 0
fi

git config user.name  "oneground calibration bot"
git config user.email "noreply@users.noreply.github.com"

# Position the branch on the remote's current tip, or create it.
# Echoes `existing` or `created` so the caller and the tests can tell.
start_branch() {
  # The working copy of the history still carries this run's appended lines.
  # They are already captured in $NEW, so restore the file before switching
  # branches -- otherwise git refuses the checkout, or carries the local edit
  # across and the merge double-counts it.
  git checkout -- "$HISTORY" 2>/dev/null || true

  if git ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
    git fetch --no-tags "$REMOTE" \
      "+refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH" >/dev/null 2>&1
    git checkout -B "$BRANCH" "refs/remotes/$REMOTE/$BRANCH" >/dev/null 2>&1
    echo existing
  elif git ls-remote --exit-code --heads "$REMOTE" "$BASE_BRANCH" \
        >/dev/null 2>&1; then
    git fetch --no-tags "$REMOTE" \
      "+refs/heads/$BASE_BRANCH:refs/remotes/$REMOTE/$BASE_BRANCH" \
      >/dev/null 2>&1
    git checkout -B "$BRANCH" "refs/remotes/$REMOTE/$BASE_BRANCH" \
      >/dev/null 2>&1
    echo created
  else
    # Neither exists: a bare remote nobody has pushed to. Start from HEAD.
    git checkout -B "$BRANCH" >/dev/null 2>&1
    echo created
  fi
}

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for attempt in $(seq 1 "$PUSH_ATTEMPTS"); do
  origin_state="$(start_branch)"
  echo "attempt $attempt/$PUSH_ATTEMPTS: branch $origin_state on $REMOTE"

  python "$here/merge_history.py" \
    --base "$HISTORY" --append "$NEW" --out "$HISTORY"

  git add "$HISTORY"
  if git diff --cached --quiet; then
    echo "every appended line is already on $BRANCH; nothing to commit"
    exit 0
  fi
  git commit -q -m "$MSG"

  if git push "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
    echo "pushed $BRANCH on attempt $attempt"
    exit 0
  fi

  echo "push rejected -- the tip moved. Re-deriving from it."
  # Drop our commit; the next pass re-reads the remote and re-appends. Never
  # `push --force`: the lines that arrived while we were working are someone
  # else's measurements.
  git reset --hard "HEAD~1" >/dev/null 2>&1 || true
done

echo "::error::could not push $BRANCH after $PUSH_ATTEMPTS attempt(s)"
exit 1
