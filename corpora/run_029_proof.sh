#!/usr/bin/env bash
# Task 029 step 4, end to end: `simulate` on a second environment with the
# determinism fix in place.
#
# The first session measured the k-means directly and answered the question.
# This runs the real command, because the claim now being made -- byte-identity
# across environments -- is about what a user runs and what the fixture's
# receipt is about, not about a probe script.
#
# It brings back simulate.json, simulate_info.json and the centroids. The
# comparison happens on the laptop, against the same command's output there.
# This script judges nothing.
#
# Outputs are packaged BEFORE any check that can fail (task 027's lesson).
set -euo pipefail

REPO="${ONEGROUND_REPO:-/workspace/oneground}"
REQ="${ONEGROUND_REQUIREMENTS:-requirements.arxiv-150k.determinism.pod.yaml}"
WORKDIR="${ONEGROUND_WORKDIR:-runs/029-proof}"
OUT="${ONEGROUND_OUT:-/workspace/029-proof.tgz}"
VEC="${ONEGROUND_VECTORS:-/workspace/arxiv-150k/vectors.npy}"

cd "$REPO"

echo "=============================================================="
echo "oneground 029: simulate, deterministic, on a second environment"
echo "  requirements: $REQ"
echo "  workdir     : $WORKDIR"
echo "  started     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--------------------------------------------------------------"

[ -x .venv/bin/python ] || { echo "ERROR: no venv at $REPO/.venv" >&2; exit 1; }
PY=.venv/bin/python
$PY --version
$PY -c "import faiss, numpy; print('faiss', faiss.__version__, '| numpy', numpy.__version__)"
[ -f "$VEC" ] || { echo "ERROR: corpus missing from the volume: $VEC" >&2; exit 1; }
echo "  corpus  : $VEC ($(stat -c %s "$VEC") bytes)"

# What this host is, and -- the gap the first session left -- what the wheel
# actually links. One line of ldd settles what was inferred last time.
echo "--------------------------------------------------------------"
echo "host and wheel"
{
  echo "== cpu =="
  lscpu 2>/dev/null | grep -E "Model name|Socket|Core|Thread|^CPU\(s\)" || true
  grep -m1 '^flags' /proc/cpuinfo 2>/dev/null | tr ' ' '\n' \
    | grep -iE '^(avx|sse4|fma)' | sort -u | tr '\n' ' '; echo
  echo "== what faiss links =="
  SO="$($PY -c "import faiss, glob, os; print(glob.glob(os.path.join(os.path.dirname(faiss.__file__), '_swigfaiss*.so'))[0])")"
  echo "  $SO"
  ldd "$SO" 2>/dev/null || true
  echo "== bundled libs =="
  $PY - <<'PYEOF'
import glob, os, faiss
root = os.path.dirname(os.path.dirname(faiss.__file__))
hits = glob.glob(os.path.join(root, "faiss*.libs", "*"))
print("\n".join("  " + os.path.basename(h) for h in sorted(hits)) or "  (none)")
PYEOF
} 2>&1 | tee "/workspace/029-host.txt"

echo "--------------------------------------------------------------"
$PY -m oneground.cli simulate "$REQ"

echo "--------------------------------------------------------------"
echo "the centroids this run used, saved for comparison"
$PY - <<PYEOF
import hashlib, json, os, sys
import numpy as np
sys.path.insert(0, os.getcwd())
from oneground.measures.crispness import kmeans
from oneground.models.base import deterministic_faiss
x = np.ascontiguousarray(np.load("$VEC", mmap_mode="r"), dtype=np.float32)
with deterministic_faiss(True):
    c = kmeans(x, 256, 20260908)
np.save(os.path.join("$WORKDIR", "centroids-deterministic.npy"), c)
print("  centroids sha256:", hashlib.sha256(c.tobytes()).hexdigest()[:16])
PYEOF

echo "--------------------------------------------------------------"
echo "packaging (before any check, so a failure's evidence comes home)"
cp /workspace/029-host.txt "$WORKDIR/host.txt" || true
tar -czf "$OUT" "$WORKDIR"
echo "  $OUT ($(stat -c %s "$OUT") bytes)"

echo "  finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "DONE"
