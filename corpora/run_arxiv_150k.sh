#!/usr/bin/env bash
#
# Canonical arxiv-150k fixture build, for the RunPod CPU pod.
#
# One script, one command. Defaults are the canonical build; the env vars
# exist so the same logic can be exercised on the smoke fixture on a laptop
# before the pod is ever started:
#
#   SPEC=fixtures/arxiv-smoke.fixture.yaml \
#   SOURCE=tasks/scratch/001-synthetic-source.json \
#   TARBALL=/tmp/arxiv-smoke-small.tgz \
#   TARBALL_LARGE=/tmp/arxiv-smoke-large.tgz \
#   bash corpora/run_arxiv_150k.sh
#
# Leave SKIP_PROJECTION unset when testing: the ground-view export needs
# projection.npy, so a skipped projection fails the run at that step.
#
# When testing under Git Bash, keep TARBALL free of a drive-letter colon
# ("/tmp/x.tgz", not "C:/tmp/x.tgz"): GNU tar reads "host:path" as a remote
# location and fails with "Cannot connect to C". Does not arise on the pod.
#
# On the pod, run it with no env vars set. In particular leave SKIP_PROJECTION
# unset: the canonical build produces projection.npy.

set -euo pipefail

SPEC="${SPEC:-fixtures/arxiv-150k.fixture.yaml}"
SOURCE="${SOURCE:-/workspace/arxiv-metadata-oai-snapshot.json}"
TARBALL="${TARBALL:-/workspace/arxiv-150k-small.tgz}"
TARBALL_LARGE="${TARBALL_LARGE:-/workspace/arxiv-150k-large.tgz}"
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

# ------------------------------------------------------------- source receipt
# Printed before any work starts. The sha256 below is the value that goes into
# the spec's source.snapshot_sha256 field.
if [ ! -f "$SOURCE" ]; then
    echo "ERROR: source not found: $SOURCE" >&2
    exit 1
fi

SIZE="$(stat -c %s "$SOURCE" 2>/dev/null || wc -c < "$SOURCE" | tr -d ' ')"

echo "=============================================================="
echo "oneground canonical fixture build"
echo "  repo        : $REPO"
echo "  python      : $(python --version 2>&1)"
echo "  spec        : $SPEC"
echo "  source      : $SOURCE"
echo "  source bytes: $SIZE"
echo "  started     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--------------------------------------------------------------"
echo "hashing source (this is source.snapshot_sha256) ..."
SRC_SHA="$(sha256sum "$SOURCE" | cut -d' ' -f1)"
echo "  source.snapshot_sha256: $SRC_SHA"
echo "=============================================================="

# The fixture id comes from the spec, so the log name, the verify target and
# the artifact directory cannot drift apart.
FIXTURE_ID="$(python -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["fixture"]["id"])' "$SPEC")"
FIXDIR="fixtures/$FIXTURE_ID"
LOG="logs/build-${FIXTURE_ID}.log"

echo "fixture id  : $FIXTURE_ID"
echo "artifacts   : $FIXDIR"
echo "log         : $LOG"
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
python -m oneground.cli fixture verify "$FIXTURE_ID"

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
