#!/usr/bin/env bash
# Places the two files `sessions/036-volume-inspect.yaml` found missing from
# the layout `run_036_models.sh` expects -- and nothing else. Read `tasks/
# 068-*.report.md` for the inspection this session is a direct consequence
# of: arxiv-150k's `sample.jsonl.zst` exists on the volume already, inside
# `arxiv-150k-large.tgz`, unextracted; stackexchange-150k is absent from the
# volume under every layout the inspection checked.
#
# Every digest below is copied from this repo's own tracked
# `fixtures/<corpus>/MANIFEST.sha256`, not recomputed from a fresh build --
# the question this session answers is "does the volume now hold the bytes
# this repo already declares are the right ones", not "what are the right
# bytes". Every extraction is verified against it before this script
# reports success; a mismatch refuses rather than leaving a wrong file
# behind with the right name, which is worse than a missing one.
set -euo pipefail

cd /workspace/oneground

ASSETS="${ONEGROUND_ASSETS:-/workspace}"
say() { echo "[$(date -u +%H:%M:%S)] $*"; }

verify() {
  # verify <path> <expected_sha256> <label>
  local path="$1" expected="$2" label="$3"
  if [ ! -f "$path" ]; then
    echo "REFUSED: $label expected at $path and is not there after extraction." >&2
    exit 2
  fi
  local got
  got="$(sha256sum "$path" | cut -d' ' -f1)"
  if [ "$got" != "$expected" ]; then
    echo "REFUSED: $label at $path does not match its declared digest." >&2
    echo "  expected $expected" >&2
    echo "  got      $got" >&2
    echo "A file with the right name and the wrong bytes is worse than a" >&2
    echo "missing one -- left in place for inspection, not deleted." >&2
    exit 2
  fi
  say "  ok  $label  $got"
}

# ------------------------------------------------------- 1. arxiv-150k
# Already on the volume, unextracted. No upload for this one.
say "arxiv-150k: extracting sample.jsonl.zst from the tarball already on the volume"
if [ ! -f "$ASSETS/arxiv-150k-large.tgz" ]; then
  echo "REFUSED: $ASSETS/arxiv-150k-large.tgz is not there -- the volume" >&2
  echo "inspection (task 068) found it; if this session runs later than" >&2
  echo "that inspection, something removed it in between and that is a" >&2
  echo "bigger problem than this script fixes." >&2
  exit 2
fi
mkdir -p "$ASSETS/arxiv-150k"
tar -xzf "$ASSETS/arxiv-150k-large.tgz" -C "$ASSETS/arxiv-150k" \
  --strip-components=2 fixtures/arxiv-150k/sample.jsonl.zst
verify "$ASSETS/arxiv-150k/sample.jsonl.zst" \
  404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655 \
  "arxiv-150k/sample.jsonl.zst"

# ------------------------------------------------- 2. stackexchange-150k
# Absent from the volume under every layout the inspection checked. The
# tarball travels up as this session's own declared `inputs:` -- scp from
# the laptop, not a download from anywhere the pod could reach faster,
# because nothing in this project publishes it at a URL.
say "stackexchange-150k: extracting from the uploaded tarball"
if [ ! -f "$ASSETS/stackexchange-150k-large.tgz" ]; then
  echo "REFUSED: $ASSETS/stackexchange-150k-large.tgz did not arrive." >&2
  echo "Check the session's inputs: block and input_size_cap_mb." >&2
  exit 2
fi
mkdir -p "$ASSETS/stackexchange-150k"
tar -xzf "$ASSETS/stackexchange-150k-large.tgz" -C "$ASSETS/stackexchange-150k" \
  --strip-components=2 \
  fixtures/stackexchange-150k/vectors.npy \
  fixtures/stackexchange-150k/queries.npy \
  fixtures/stackexchange-150k/sample.jsonl.zst
verify "$ASSETS/stackexchange-150k/vectors.npy" \
  067d8ffbdf16f08f0a43e3fa1fccb3ca4a62093cd8f00069038f7d88bee17f30 \
  "stackexchange-150k/vectors.npy"
verify "$ASSETS/stackexchange-150k/queries.npy" \
  465a37757bd7dd1daef7ac2bf9a62a9c32deb8d32e907493cc75c22e4ac76b54 \
  "stackexchange-150k/queries.npy"
verify "$ASSETS/stackexchange-150k/sample.jsonl.zst" \
  2ab675cc3c20a0ff97602c26d070c24d307a97a4f69529ea37d7fd145c74ef0e \
  "stackexchange-150k/sample.jsonl.zst"

# ---------------------------------------------------- 3. leave a receipt
say "both corpora placed and verified"
{
  echo "arxiv-150k/sample.jsonl.zst        verified 404cb92e...ae73655"
  echo "stackexchange-150k/vectors.npy     verified 067d8ffb...b71b0"
  echo "stackexchange-150k/queries.npy     verified 465a3775...c76b54"
  echo "stackexchange-150k/sample.jsonl.zst verified 2ab675cc...4ef0e"
} > /workspace/036-place-corpora-receipt.txt
say "DONE"
