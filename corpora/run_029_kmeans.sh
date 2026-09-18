#!/usr/bin/env bash
# Task 029 step 4: the same k-means on a second environment, under the knobs
# that were shown to move it here.
#
# WHAT THIS DECIDES. Task 027 measured 256 centroids differing by 0.00104
# between this laptop and a pod, same faiss-cpu 1.15.0, same numpy 2.5.3, same
# seed. Locally, SIMD dispatch was DISPROVED as the cause (all four
# FAISS_OPT_LEVEL settings give bitwise identical centroids) and the assignment
# step's reduction order was shown to move them by 0.00366 -- larger than the
# cross-machine difference. The leading explanation is the BLAS each wheel
# links.
#
# So this does not just re-run the k-means. It runs it on the pod under the
# same settings that were varied here, and brings the centroids back, so the
# two machines can be compared setting by setting:
#
#   * if the pod's DEFAULT reproduces task 027's emitted centroids, the pod is
#     self-consistent and 027's finding is confirmed from a second run.
#   * if any pod setting reproduces the LAPTOP's centroids, the reduction
#     order is the whole story and the difference is a knob, not a platform.
#   * if none does, the difference is in the BLAS implementation itself, and
#     the honest answer is to state that centroid assignment is per-platform
#     and bound the effect -- a finding, not a failure. That is the
#     developer's call to make, not this script's.
#
# It measures and brings home. It changes nothing and fixes nothing.
#
# Outputs are packaged BEFORE any check that can fail, which is task 027's
# lesson: its acceptance failed on a real finding and aborted the script
# before its own tar, and the evidence had to be pulled off by hand.
set -euo pipefail

REPO="${ONEGROUND_REPO:-/workspace/oneground}"
OUT="${ONEGROUND_OUT:-/workspace/029-kmeans.tgz}"
WORK="${ONEGROUND_WORK:-/workspace/oneground/runs/029-kmeans}"
VEC="${ONEGROUND_VECTORS:-/workspace/arxiv-150k/vectors.npy}"

cd "$REPO"
mkdir -p "$WORK"

echo "=============================================================="
echo "oneground 029: k-means reduction order on a second environment"
echo "  repo    : $REPO"
echo "  started : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--------------------------------------------------------------"

[ -x .venv/bin/python ] || { echo "ERROR: no venv at $REPO/.venv" >&2; exit 1; }
PY=.venv/bin/python
$PY --version
$PY -c "import faiss, numpy; print('faiss', faiss.__version__, '| numpy', numpy.__version__)"

[ -f "$VEC" ] || { echo "ERROR: corpus missing from the volume: $VEC" >&2; exit 1; }
echo "  corpus  : $VEC ($(stat -c %s "$VEC") bytes)"

echo "--------------------------------------------------------------"
echo "what this host is"
{
  echo "== lscpu =="; lscpu 2>/dev/null | head -25
  echo "== flags =="; grep -m1 '^flags' /proc/cpuinfo 2>/dev/null | tr ' ' '\n' | grep -iE '^(avx|sse4|fma)' | sort -u | tr '\n' ' '; echo
  echo "== nproc =="; nproc
} | tee "$WORK/host.txt"

echo "--------------------------------------------------------------"
echo "the k-means, under each setting"
$PY tasks/scratch/029_pod_kmeans.py --vectors "$VEC" --out "$WORK"

echo "--------------------------------------------------------------"
echo "packaging (before any check, so a failure's evidence comes home)"
tar -czf "$OUT" -C "$(dirname "$WORK")" "$(basename "$WORK")"
echo "  $OUT ($(stat -c %s "$OUT") bytes)"

echo "  finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "DONE"
