#!/usr/bin/env bash
#
# The stackexchange-150k canonical build, end to end, as one pod run.
#
# Two steps, in order, and the first must pass before the second starts:
#
#   1. fetch the 59 pinned source shards and verify every sha256 against
#      sessions/stackexchange-shards.sha256,
#   2. build, verify and tar the fixture with the generic runner.
#
# The download is its own step rather than part of the builder because it is
# the one step that can fail for a reason that is not ours -- a moved revision,
# a truncated transfer -- and a build that started on unverified bytes would
# produce a digest nobody could reproduce. `oneground pod`'s `setup:` is a
# fixed venv-on-local-disk script and not a hook, so the fetch lives here, at
# the top of the run, rather than in the session's setup field.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    . .venv/bin/activate
elif [ -f .venv/Scripts/activate ]; then
    # shellcheck disable=SC1091
    . .venv/Scripts/activate
else
    echo "ERROR: no virtualenv at $REPO/.venv" >&2
    exit 1
fi

export FIXTURE="${FIXTURE:-stackexchange-150k}"
export SOURCE="${SOURCE:-/workspace/stackexchange-posts}"
SPEC="fixtures/${FIXTURE}.fixture.yaml"

echo "=============================================================="
echo "step 1/2  fetching source shards (digests verified)"
echo "  spec  : $SPEC"
echo "  dest  : $SOURCE"
echo "=============================================================="
python corpora/fetch_stackexchange.py --spec "$SPEC" --dest "$SOURCE"

echo
echo "=============================================================="
echo "step 2/2  building $FIXTURE"
echo "=============================================================="
exec bash corpora/run_fixture_build.sh
