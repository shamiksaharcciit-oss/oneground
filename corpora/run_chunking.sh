#!/usr/bin/env bash
#
# The chunking comparison on a pod (task 031 step 7).
#
# The corpus is sec-filings-10k's `documents.jsonl.zst`, 692 MB, which ships
# as a release asset and is NOT in the repository -- a git bundle carries
# commits, so it cannot arrive that way, and 692 MB does not go up an scp
# inside `input_size_cap_mb`. It comes off the network volume, where task
# 030's session left it.
#
# That is checked FIRST, before the model is loaded or anything is tokenised,
# so a missing corpus costs four minutes and names the path rather than
# failing twenty minutes in.
#
# Receipts are packaged the moment they exist, and again after each strategy:
# a run terminated before its last step must leave behind whatever it had
# finished. Task 030 learned that twice.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

REQ="${REQ:-requirements.chunking-sec-filings.yaml}"
CORPUS_DIR="${CORPUS_DIR:-/workspace/sec-filings-10k}"
CORPUS="$CORPUS_DIR/documents.jsonl.zst"
ASSET="${ASSET:-/workspace/sec-filings-10k-large.tgz}"
TARBALL="${TARBALL:-/workspace/chunking-sec-filings.tgz}"
DEVICE="${DEVICE:-cuda}"
BATCH="${BATCH:-128}"
DOCUMENTS="${DOCUMENTS:-}"
ANCHORS="${ANCHORS:-}"

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

mkdir -p logs
LOG="logs/chunking.log"
WORKDIR="$(python -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["run"]["workdir"])' "$REQ")"

echo "=============================================================="
echo "oneground chunking stage"
echo "  repo       : $REPO"
echo "  python     : $(python --version 2>&1)"
echo "  reqs       : $REQ"
echo "  corpus     : $CORPUS"
echo "  device     : $DEVICE"
echo "  workdir    : $WORKDIR"
echo "  started    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--------------------------------------------------------------"

# ------------------------------------------------- the corpus, checked first
if [ ! -f "$CORPUS" ]; then
    echo "corpus not at $CORPUS; looking for the release asset ..."
    if [ ! -f "$ASSET" ]; then
        echo "ERROR: neither $CORPUS nor $ASSET exists." >&2
        echo "       This run needs sec-filings-10k's documents.jsonl.zst," >&2
        echo "       which task 030's session left on the network volume." >&2
        echo "       Nothing has been loaded and nothing has been spent past" >&2
        echo "       setup; put the file at one of those paths and re-run." >&2
        ls -la /workspace/ 2>&1 | head -20 >&2
        exit 2
    fi
    echo "extracting $ASSET ..."
    mkdir -p "$CORPUS_DIR"
    tar -xzf "$ASSET" -C /tmp fixtures/sec-filings-10k/documents.jsonl.zst
    mv /tmp/fixtures/sec-filings-10k/documents.jsonl.zst "$CORPUS"
fi
echo "corpus present: $(stat -c %s "$CORPUS") bytes"

# The requirements file names the developer's local path; on the pod the
# corpus is on the volume. Overridden rather than edited, so the committed
# requirements file stays the one a reader checks against.
ARGS=(--corpus "$CORPUS" --device "$DEVICE" --batch "$BATCH")
[ -n "$DOCUMENTS" ] && ARGS+=(--documents "$DOCUMENTS")
[ -n "$ANCHORS" ] && ARGS+=(--anchors "$ANCHORS")

pack() {
    local stage="$1"
    local members=()
    local f
    for f in "$WORKDIR"/*.json "$LOG"; do
        [ -f "$f" ] && members+=("$f")
    done
    if [ ${#members[@]} -eq 0 ]; then
        echo "nothing to package after ${stage}"
        return 0
    fi
    tar -czf "$TARBALL.tmp" -C "$REPO" "${members[@]}"
    mv -f "$TARBALL.tmp" "$TARBALL"
    echo "packaged after ${stage}: ${#members[@]} file(s), $(stat -c %s "$TARBALL") bytes"
}

# pipefail is set, so a failure fails the pipeline despite tee.
python corpora/run_chunking.py "$REQ" "${ARGS[@]}" 2>&1 | tee "$LOG"
pack "the run"

echo
echo "tarball contents:"
tar -tzf "$TARBALL" | sed 's/^/  /'
echo "  finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
echo "DONE"
echo "$TARBALL"
