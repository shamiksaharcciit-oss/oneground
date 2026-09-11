#!/usr/bin/env bash
#
# Push appended calibration lines to the calibration branch, safely.
#
# Two failures shaped this script.
#
# Run #3: `! [rejected]  calibration -> calibration (non-fast-forward)`.
# The step fetched with `git fetch origin "$BRANCH" || true` and then checked
# out `origin/$BRANCH`, falling back to a bare `checkout -B "$BRANCH"`. On a
# tag push the checkout action configures no `refs/remotes/origin/*` refspec,
# so `origin/$BRANCH` did not exist, the `|| true` swallowed it, and the
# fallback started the branch from the *tag commit* -- unrelated to what the
# remote already had. The push could only be rejected, on every retry.
#
# Run #5: `.github/scripts/merge_history.py: No such file or directory`.
# 014c's fix kept checking the branch out into the job's working tree. The
# `calibration` branch is rooted at 0.1.0-preview, three commits before the
# scripts existed, so `git checkout` *deleted them from disk* -- and the very
# next line invoked one of them by path. The same checkout removes
# `count_contradictions.py`, which the action runs one step later, so the job
# had two ways to fail on a file that is present in the commit it started from.
#
# The lesson of #5 is not "resolve that path differently". It is that the
# working tree is the wrong vehicle for this update: the branch being written
# to has a different tree from the branch the job is running from, and a
# checkout makes those two facts collide. So this builds the commit out of the
# object database with plumbing and never moves HEAD, the index, or a single
# file in the checkout. A run that fails here leaves the workspace byte for
# byte as it found it.
#
# Three further properties, unchanged from 014c:
#
#   1. Asks the remote whether the branch exists (`git ls-remote`) rather than
#      inferring it from whether a local ref happens to be configured, and
#      fetches an explicit refspec so the ref is really there.
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

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# `$HISTORY` is relative to the caller's cwd; git plumbing wants it relative to
# the repo root. They are the same thing when the action runs from the
# workspace, but not when a test or a developer runs from a subdirectory.
HISTORY_PATH="$(git rev-parse --show-prefix)$HISTORY"

# Resolve the commit the new one must be built on, without touching the
# checkout. Echoes "<state> <rev>", where state is `existing` or `created`.
resolve_tip() {
  if git ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
    git fetch --no-tags "$REMOTE" \
      "+refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH" >/dev/null 2>&1
    echo "existing refs/remotes/$REMOTE/$BRANCH"
  elif git ls-remote --exit-code --heads "$REMOTE" "$BASE_BRANCH" \
        >/dev/null 2>&1; then
    git fetch --no-tags "$REMOTE" \
      "+refs/heads/$BASE_BRANCH:refs/remotes/$REMOTE/$BASE_BRANCH" \
      >/dev/null 2>&1
    echo "created refs/remotes/$REMOTE/$BASE_BRANCH"
  else
    # Neither exists: a bare remote nobody has pushed to. Start from HEAD.
    echo "created HEAD"
  fi
}

for attempt in $(seq 1 "$PUSH_ATTEMPTS"); do
  read -r state tip_ref <<EOF
$(resolve_tip)
EOF
  echo "attempt $attempt/$PUSH_ATTEMPTS: branch $state on $REMOTE"

  # The branch's history as the remote currently has it, read from the object
  # database. Absent on a brand-new branch, which merge_history.py allows.
  base="$tmp/base.jsonl"
  : > "$base"
  tip="$(git rev-parse --verify --quiet "${tip_ref}^{commit}" || true)"
  if [ -n "$tip" ] && git cat-file -e "$tip:$HISTORY_PATH" 2>/dev/null; then
    git cat-file -p "$tip:$HISTORY_PATH" > "$base"
  fi

  python "$here/merge_history.py" \
    --base "$base" --append "$NEW" --out "$tmp/merged.jsonl"

  # Build the tree beside the checkout's index, never in it: GIT_INDEX_FILE
  # points at a scratch index that is thrown away with $tmp.
  # --path so the blob is byte-identical to what `git add` of the real
  # history file would have produced under the repo's attributes.
  blob="$(git hash-object -w --path "$HISTORY_PATH" -- "$tmp/merged.jsonl")"
  export GIT_INDEX_FILE="$tmp/index"
  rm -rf "$GIT_INDEX_FILE"
  if [ -n "$tip" ]; then
    git read-tree "$tip"
  else
    git read-tree --empty
  fi
  git update-index --add --cacheinfo "100644,$blob,$HISTORY_PATH"
  tree="$(git write-tree)"
  unset GIT_INDEX_FILE

  if [ -n "$tip" ] && [ "$tree" = "$(git rev-parse "$tip^{tree}")" ]; then
    echo "every appended line is already on $BRANCH; nothing to commit"
    exit 0
  fi

  if [ -n "$tip" ]; then
    commit="$(git commit-tree "$tree" -p "$tip" -m "$MSG")"
  else
    commit="$(git commit-tree "$tree" -m "$MSG")"
  fi

  # No leading `+` and no force: the lines that arrived while we were working
  # are someone else's measurements, and the retry exists to keep them.
  if git push "$REMOTE" "$commit:refs/heads/$BRANCH" >/dev/null 2>&1; then
    echo "pushed $BRANCH on attempt $attempt"
    exit 0
  fi

  echo "push rejected -- the tip moved. Re-deriving from it."
  # Nothing to undo: the commit is a dangling object in this clone, no ref
  # points at it, and the next pass re-reads the remote and re-appends.
done

echo "::error::could not push $BRANCH after $PUSH_ATTEMPTS attempt(s)"
exit 1
