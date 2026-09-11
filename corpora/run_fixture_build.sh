#!/usr/bin/env bash
#
# Canonical fixture build, for any fixture, on the pod.
#
# Generalised from corpora/run_arxiv_150k.sh in task 016. That script stays
# where it is: sessions/arxiv-build.yaml names it, three task reports invoke it
# by path, and a build that has already produced published values should not
# have its entry point moved out from under it.
#
# The only thing this needs to know is which fixture. Everything else is
# derived from the spec, so the log name, the verify target, the artifact
# directory and the tarball names cannot drift apart:
#
#   FIXTURE=stackexchange-150k SOURCE=/workspace/stackexchange-posts \
#   bash corpora/run_fixture_build.sh
#
# On a laptop, against the smoke fixture, before the pod is ever started:
#
#   FIXTURE=arxiv-smoke \
#   SOURCE=tasks/scratch/001-synthetic-source.json \
#   TARBALL=/tmp/arxiv-smoke-small.tgz \
#   TARBALL_LARGE=/tmp/arxiv-smoke-large.tgz \
#   bash corpora/run_fixture_build.sh
#
# Leave SKIP_PROJECTION unset when testing: the ground-view export needs
# projection.npy, so a skipped projection fails the run at that step.
#
# When testing under Git Bash, keep TARBALL free of a drive-letter colon
# ("/tmp/x.tgz", not "C:/tmp/x.tgz"): GNU tar reads "host:path" as a remote
# location and fails with "Cannot connect to C". Does not arise on the pod.

set -euo pipefail

FIXTURE="${FIXTURE:-arxiv-150k}"
SPEC="${SPEC:-fixtures/${FIXTURE}.fixture.yaml}"
SOURCE="${SOURCE:?SOURCE must name the source file or shard directory}"
TARBALL="${TARBALL:-/workspace/${FIXTURE}-small.tgz}"
TARBALL_LARGE="${TARBALL_LARGE:-/workspace/${FIXTURE}-large.tgz}"
SKIP_PROJECTION="${SKIP_PROJECTION:-}"

# ---------------------------------------------------------------- repo + venv
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    . .venv/bin/activate                      # Linux pod
elif [ -f .venv/Scripts/activate ]; then
    # shellcheck disable=SC1091
    . .venv/Scripts/activate                  # Git Bash on Windows
else
    echo "ERROR: no virtualenv at $REPO/.venv" >&2
    exit 1
fi

mkdir -p logs

if [ ! -e "$SOURCE" ]; then
    echo "ERROR: source not found: $SOURCE" >&2
    exit 1
fi

# The fixture id comes from the spec, not from $FIXTURE, so a mismatch between
# the two is caught here rather than by writing artifacts into the wrong
# directory.
SPEC_ID="$(python -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["fixture"]["id"])' "$SPEC")"
if [ "$SPEC_ID" != "$FIXTURE" ]; then
    echo "ERROR: FIXTURE=$FIXTURE but $SPEC declares id $SPEC_ID" >&2
    exit 1
fi

FIXDIR="fixtures/$SPEC_ID"
LOG="logs/build-${SPEC_ID}.log"

# ------------------------------------------------------------- source receipt
# Printed before any work starts. This is the value that goes into the spec's
# source.snapshot_sha256. `source_digest` hashes a file directly and a sharded
# directory by its sorted `<sha256>  <name>` manifest, so a multi-file source
# has one digest that moves if any shard does.
if [ -d "$SOURCE" ]; then
    SIZE="$(du -sb "$SOURCE" 2>/dev/null | cut -f1 || echo '?')"
    NSHARDS="$(find "$SOURCE" -type f -name '*.parquet' | wc -l | tr -d ' ')"
else
    SIZE="$(stat -c %s "$SOURCE" 2>/dev/null || wc -c < "$SOURCE" | tr -d ' ')"
    NSHARDS=1
fi

echo "=============================================================="
echo "oneground canonical fixture build"
echo "  repo        : $REPO"
echo "  python      : $(python --version 2>&1)"
echo "  fixture     : $SPEC_ID"
echo "  spec        : $SPEC"
echo "  source      : $SOURCE"
echo "  source parts: $NSHARDS"
echo "  source bytes: $SIZE"
echo "  artifacts   : $FIXDIR"
echo "  log         : $LOG"
echo "  started     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--------------------------------------------------------------"
echo "hashing source (this is source.snapshot_sha256) ..."
SRC_SHA="$(python -c 'import sys; from oneground.fixture.build import source_digest; print(source_digest(sys.argv[1]))' "$SOURCE")"
echo "  source.snapshot_sha256: $SRC_SHA"
echo "=============================================================="
echo

# -------------------------------------------------------------------- build
BUILD_ARGS=(--spec "$SPEC" --source "$SOURCE" --out fixtures/)
if [ -n "$SKIP_PROJECTION" ]; then
    echo "NOTE: SKIP_PROJECTION set - no projection.npy will be produced."
    BUILD_ARGS+=(--skip-projection)
fi

# pipefail is set, so a builder failure fails the pipeline despite tee.
python corpora/build_fixture.py "${BUILD_ARGS[@]}" 2>&1 | tee "$LOG"

echo
echo "build finished, verifying ..."

# ------------------------------------------------------------------- verify
python -m oneground.cli fixture verify "$SPEC_ID"

# ------------------------------------------------------------ ground view
# Recomputes the per-point table the hero image is drawn from, from the
# artifacts just built. It asserts its own geometry against the spec's
# published values and exits non-zero if they disagree, so a bad export fails
# the run rather than shipping a picture that contradicts the numbers.
echo
echo "exporting ground view ..."
python corpora/export_ground_view.py --spec "$SPEC" --dir "$FIXDIR" 2>&1 | tee -a "$LOG"

# ---------------------------------------------------------------- small tar
# Everything a laptop needs to review the build. The big artifacts
# (vectors.npy, queries.npy, sample.jsonl.zst) stay on the network volume.
MEMBERS=(
    "$FIXDIR/MANIFEST.sha256"
    "$FIXDIR/characterization.json"
    "$FIXDIR/build_info.json"
    "$FIXDIR/query_ids.json"
    "$FIXDIR/ground_truth.npy"
    "$FIXDIR/ground_view_base.parquet"
    "$FIXDIR/ground_view_queries.parquet"
    "$FIXDIR/ground_view_centroids.parquet"
    "$LOG"
)

if [ -f "$FIXDIR/projection.npy" ]; then
    MEMBERS+=("$FIXDIR/projection.npy")
else
    # Not fatal: the tarball is still worth having. But the canonical build is
    # expected to produce a projection, so say so loudly.
    echo "WARNING: $FIXDIR/projection.npy not found - not in the tarball." >&2
    echo "WARNING: expected for the canonical build unless --skip-projection was used." >&2
fi

mkdir -p "$(dirname "$TARBALL")"
tar -czf "$TARBALL" -C "$REPO" "${MEMBERS[@]}"

echo
echo "tarball contents:"
tar -tzf "$TARBALL" | sed 's/^/  /'
echo
echo "  bytes: $(stat -c %s "$TARBALL" 2>/dev/null || wc -c < "$TARBALL" | tr -d ' ')"

# ---------------------------------------------------------------- large tar
# The release asset: the artifacts too big to carry in the small tarball, and
# the reason a clone reports them couldnt_check. Built second so that a failure
# here still leaves the reviewable tarball on disk.
LARGE=(
    "$FIXDIR/vectors.npy"
    "$FIXDIR/queries.npy"
    "$FIXDIR/sample.jsonl.zst"
)
mkdir -p "$(dirname "$TARBALL_LARGE")"
tar -czf "$TARBALL_LARGE" -C "$REPO" "${LARGE[@]}"

echo
echo "release asset contents:"
tar -tzf "$TARBALL_LARGE" | sed 's/^/  /'
echo
echo "  bytes: $(stat -c %s "$TARBALL_LARGE" 2>/dev/null || wc -c < "$TARBALL_LARGE" | tr -d ' ')"
echo "  finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo "Paste to the orchestrator: the TO_BE_FILLED block above, the last 40"
echo "lines of $LOG, and this source.snapshot_sha256:"
echo "  $SRC_SHA"
echo
echo "DONE"
echo "$TARBALL"
echo "$TARBALL_LARGE"
