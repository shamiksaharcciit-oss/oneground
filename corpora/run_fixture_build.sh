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
#   FIXTURE=stackexchange-150k bash corpora/run_fixture_build.sh
#
# SOURCE is optional. Give it for a spec whose source is a local file or
# directory; omit it for one that names its own source (a pinned dataset
# revision), which is streamed through the sampler and never stored.
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
# Optional. A spec that names its own source (a pinned dataset revision)
# streams it and stores nothing, so there is no local path to give.
SOURCE="${SOURCE:-}"
# Where artifacts are written. Only a test has reason to move this; the
# canonical build writes into the repo's own fixtures/ directory, which is
# where `fixture verify` and the ground-view export look for it.
OUT="${OUT:-fixtures/}"
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

if [ -n "$SOURCE" ] && [ ! -e "$SOURCE" ]; then
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

FIXDIR="${OUT%/}/$SPEC_ID"
LOG="logs/build-${SPEC_ID}.log"

# ------------------------------------------------------------- source receipt
# Reported before any work starts. A local source is described from disk; a
# streamed one has nothing on disk to describe, and its snapshot_sha256 is
# printed by the builder once it has verified the pinned revision.
if [ -z "$SOURCE" ]; then
    SIZE="streamed, not stored"
    NSHARDS="$(python -c 'import sys,yaml; s=yaml.safe_load(open(sys.argv[1]))["source"]; print(s.get("shards","?"))' "$SPEC")"
elif [ -d "$SOURCE" ]; then
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
echo "  source      : ${SOURCE:-<streamed from the revision the spec pins>}"
echo "  source parts: $NSHARDS"
echo "  source bytes: $SIZE"
echo "  artifacts   : $FIXDIR"
echo "  log         : $LOG"
echo "  started     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--------------------------------------------------------------"
if [ -n "$SOURCE" ]; then
    echo "hashing source (this is source.snapshot_sha256) ..."
    SRC_SHA="$(python -c 'import sys; from oneground.fixture.build import source_digest; print(source_digest(sys.argv[1]))' "$SOURCE")"
    echo "  source.snapshot_sha256: $SRC_SHA"
else
    SRC_SHA="(streamed -- printed by the builder after it verifies the pinned revision)"
    echo "source is streamed from the pinned revision; nothing is stored."
fi
echo "=============================================================="
echo

# -------------------------------------------------------------------- build
# --skip-projection is now ALWAYS passed: the projection runs as its own step
# below, after the receipts have been packaged. Same work, same order, same
# seed -- the only difference is that a kill during UMAP no longer takes the
# receipts with it. SKIP_PROJECTION=1 still means "do not project at all".
BUILD_ARGS=(--spec "$SPEC" --out "$OUT" --skip-projection)
if [ -n "$SOURCE" ]; then
    BUILD_ARGS+=(--source "$SOURCE")
fi
if [ -n "$SKIP_PROJECTION" ]; then
    echo "NOTE: SKIP_PROJECTION set - no projection.npy will be produced."
fi

# pipefail is set, so a builder failure fails the pipeline despite tee.
python corpora/build_fixture.py "${BUILD_ARGS[@]}" 2>&1 | tee "$LOG"

# ---------------------------------------------------------------- packaging
# Receipts first, and repackaged after every stage that adds a file.
#
# Session 20260911-220320 was killed at its cap 24m 38s after its MANIFEST was
# complete, and lost everything: the only tarball was built at the very end,
# so `watch` had nothing to fetch. The artifacts were on a container disk with
# no volume behind it, and they went with the pod.
#
# So packaging is no longer a final step. `pack` runs as soon as the receipts
# exist and again after each later stage, overwriting the same two paths, so
# whatever the run reached is always on disk ready to be fetched. Writing to a
# temp file and moving it into place means a `watch` that fetches mid-repack
# gets the previous complete tarball rather than a truncated one.
#
# This is the 011 runner's principle: the artifact of a run that was
# interrupted is whatever it had finished, not nothing.

pack() {
    local stage="$1"

    local members=(
        "$FIXDIR/MANIFEST.sha256"
        "$FIXDIR/characterization.json"
        "$FIXDIR/build_info.json"
        "$FIXDIR/query_ids.json"
        "$FIXDIR/ground_truth.npy"
        "$LOG"
    )
    # Optional members: present from the stage that produces them onward.
    local optional=(
        "$FIXDIR/projection.npy"
        "$FIXDIR/ground_view_base.parquet"
        "$FIXDIR/ground_view_queries.parquet"
        "$FIXDIR/ground_view_centroids.parquet"
    )
    local f
    for f in "${optional[@]}"; do
        [ -f "$f" ] && members+=("$f")
    done

    mkdir -p "$(dirname "$TARBALL")"
    tar -czf "$TARBALL.tmp" -C "$REPO" "${members[@]}"
    mv -f "$TARBALL.tmp" "$TARBALL"

    local large=()
    for f in "$FIXDIR/vectors.npy" "$FIXDIR/queries.npy" \
             "$FIXDIR/sample.jsonl.zst"; do
        [ -f "$f" ] && large+=("$f")
    done
    if [ ${#large[@]} -gt 0 ]; then
        mkdir -p "$(dirname "$TARBALL_LARGE")"
        tar -czf "$TARBALL_LARGE.tmp" -C "$REPO" "${large[@]}"
        mv -f "$TARBALL_LARGE.tmp" "$TARBALL_LARGE"
    fi

    echo "packaged after ${stage}: $(echo "${members[@]}" | wc -w) file(s) in"\
         "$(basename "$TARBALL")" \
         "($(stat -c %s "$TARBALL" 2>/dev/null || echo '?') bytes)"
}

# The receipts are complete the moment the builder returns -- it writes the
# MANIFEST before anything optional, and --skip-projection above stops it
# there. Everything from here is an addition, not a prerequisite.
pack "the manifest (receipts complete)"

# ------------------------------------------------------------- projection
# Its own step now, so the receipts are already packaged before UMAP starts.
# It is declared, not a receipt: a failure here leaves the fixture standing,
# so the run continues either way.
if [ -n "$SKIP_PROJECTION" ]; then
    echo
    echo "projection skipped (SKIP_PROJECTION set)."
else
    echo
    echo "projecting ..."
    if python -m oneground.cli fixture project --spec "$SPEC" --out "$OUT" 2>&1 | tee -a "$LOG"; then
        pack "the projection"
    else
        echo "WARNING: projection step failed - the fixture stands without it." >&2
        pack "the projection (failed)"
    fi
fi

# ------------------------------------------------------------------- verify
# Skips the value recomputation when every published value is still
# TO_BE_FILLED, which is the case on a first canonical build.
echo
echo "verifying ..."
python -m oneground.cli fixture verify "$SPEC_ID" --fixtures-dir "${OUT%/}" 2>&1 | tee -a "$LOG"
pack "verify"

# ------------------------------------------------------------ ground view
# Recomputes the per-point table the hero image is drawn from, from the
# artifacts just built. It asserts its own geometry against the spec's
# published values and exits non-zero if they disagree, so a bad export fails
# the run rather than shipping a picture that contradicts the numbers.
echo
echo "exporting ground view ..."
if python corpora/export_ground_view.py --spec "$SPEC" --dir "$FIXDIR" 2>&1 | tee -a "$LOG"; then
    pack "the ground view"
else
    echo "WARNING: ground-view export failed - earlier artifacts are packaged." >&2
    pack "the ground view (failed)"
fi

if [ ! -f "$FIXDIR/projection.npy" ]; then
    # Not fatal: the tarball is still worth having. But the canonical build is
    # expected to produce a projection, so say so loudly.
    echo "WARNING: $FIXDIR/projection.npy not found - not in the tarball." >&2
    echo "WARNING: expected for the canonical build unless SKIP_PROJECTION was set." >&2
fi

echo
echo "tarball contents:"
tar -tzf "$TARBALL" | sed 's/^/  /'
echo
echo "  bytes: $(stat -c %s "$TARBALL" 2>/dev/null || wc -c < "$TARBALL" | tr -d ' ')"

echo
echo "release asset contents:"
tar -tzf "$TARBALL_LARGE" | sed 's/^/  /'

echo "  finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo "Paste to the orchestrator: the TO_BE_FILLED block above, the last 40"
echo "lines of $LOG, and this source.snapshot_sha256:"
echo "  $SRC_SHA"
echo
echo "DONE"
echo "$TARBALL"
echo "$TARBALL_LARGE"
