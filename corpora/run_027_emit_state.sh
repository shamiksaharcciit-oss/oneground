#!/usr/bin/env bash
# Task 027 on a pod: emit a state that carries the declared projection.
#
# The one path task 027 could not prove. On the developer's laptop a fresh
# `simulate --emit-state` at 150,000 vectors dies in faiss with
# `MemoryError: std::bad_alloc` building 256 HNSW shards; 027's acceptance
# therefore ran against task 020's emitted state with the declared columns
# attached by the same function `simulate` calls. This runs the real command
# on a machine that can hold it, and checks the result against the same
# answer key.
#
# It writes only inside the repo on the volume. It fetches nothing from the
# network and it does not fit a projection -- it reads the declared one.
#
# Prints DONE on the last line only if every check passed; the session's
# `done_marker` is DONE, so a failure is a stall, not a false success.
set -euo pipefail

REPO="${ONEGROUND_REPO:-/workspace/oneground}"
REQ="${ONEGROUND_REQUIREMENTS:-requirements.arxiv-150k.projection.pod.yaml}"
WORKDIR="${ONEGROUND_WORKDIR:-runs/027-arxiv-projection}"
OUT="${ONEGROUND_OUT:-/workspace/027-emit-state.tgz}"

cd "$REPO"

echo "=============================================================="
echo "oneground 027: simulate --emit-state with a declared projection"
echo "  repo        : $REPO"
echo "  requirements: $REQ"
echo "  workdir     : $WORKDIR"
echo "  started     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--------------------------------------------------------------"

if [ ! -x .venv/bin/python ]; then
  echo "ERROR: no virtualenv at $REPO/.venv -- setup did not complete" >&2
  exit 1
fi
PY=.venv/bin/python
echo "  python      : $($PY --version 2>&1)"
$PY -c "import faiss, numpy; print('  faiss       :', faiss.__version__); print('  numpy       :', numpy.__version__)"

# ---- what must already be here, checked before anything expensive ----
# The corpus is on the volume because 460 MB does not go up an scp. If the
# volume has been recycled this fails in a second with the path, instead of
# after the pod has spent twenty minutes on k-means.
fail=0
for f in /workspace/arxiv-150k/vectors.npy /workspace/arxiv-150k/queries.npy; do
  if [ -f "$f" ]; then
    echo "  corpus      : $f  ($(stat -c %s "$f") bytes)"
  else
    echo "ERROR: missing from the volume: $f" >&2
    fail=1
  fi
done
# The projection and the characterization are uploaded by the session.
for f in fixtures/arxiv-150k/ground_view_base.parquet \
         "$WORKDIR/characterization.json" "$WORKDIR/ground_truth.npy"; do
  if [ -f "$f" ]; then
    echo "  uploaded    : $f  ($(stat -c %s "$f") bytes)"
  else
    echo "ERROR: the session did not upload: $f" >&2
    fail=1
  fi
done
[ "$fail" -eq 0 ] || { echo "ERROR: inputs missing; nothing was run" >&2; exit 1; }

echo "--------------------------------------------------------------"
echo "free memory before the build:"
free -g || true
echo "--------------------------------------------------------------"

# ---- the command this session exists to run ----
$PY -m oneground.cli simulate "$REQ" --emit-state

echo "--------------------------------------------------------------"
echo "what the state carries:"
$PY - <<'PYEOF'
import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.getcwd())
from oneground.models import state as S

wd = os.environ.get("ONEGROUND_WORKDIR", "runs/027-arxiv-projection")
paths = sorted(glob.glob(os.path.join(wd, "state", "*.state.npz")))
if not paths:
    raise SystemExit(f"no state emitted in {wd}/state")
for p in paths:
    head, cols = S.read_state(p)
    proj = sorted(c for c in cols if c.endswith(".projection"))
    print(f"  {os.path.basename(p)}")
    print(f"    config   {head['config_label']}")
    for c in proj:
        a = np.asarray(cols[c])
        finite = int(np.isfinite(a).all(axis=1).sum())
        print(f"    {c:<24} {a.shape} {a.dtype}  finite rows {finite}")
    if not proj:
        raise SystemExit(f"{p}: emitted no projection column")

info = json.load(open(os.path.join(wd, "state", "state_info.json"),
                      encoding="utf-8"))
pr = info.get("projection") or {}
print("  state_info.projection:")
for k in ("kind", "path", "sha256", "rows", "method", "seed",
          "query_placement_k", "illustrative"):
    if k in pr:
        print(f"    {k:<20} {str(pr[k])[:90]}")
if pr.get("kind") != "declared":
    raise SystemExit(f"projection kind is {pr.get('kind')!r}, not 'declared'")
PYEOF

# ---- package the outputs BEFORE any check that can fail ----
# This session's own first run got the order wrong. The acceptance ran first,
# failed on a real finding, and `set -euo pipefail` aborted the script before
# its tar -- so `pod fetch` had nothing to fetch and the evidence for the
# failure had to be pulled off the pod by hand over ssh before the stall
# watchdog terminated it. A failure's evidence is the evidence you most need.
#
# Receipts first, the same rule task 016 keeps. From here the bundle exists
# whatever the checks say, and the checks decide only whether DONE is printed.
echo "--------------------------------------------------------------"
echo "packaging outputs (before the checks: a failure's evidence must come home)"
tar -czf "$OUT" \
    "$WORKDIR/state" \
    "$WORKDIR/simulate.json" \
    "$WORKDIR/simulate_info.json"
echo "  $OUT  ($(stat -c %s "$OUT") bytes)"

# ---- the acceptance, against the same answer key task 027 used ----
# It is allowed to fail: `set +e` around it so the packaging below always runs.
echo "--------------------------------------------------------------"
echo "acceptance: the emitted state against site/teaser/data/base.bin"
set +e
$PY tasks/scratch/027_acceptance.py --state-dir "$WORKDIR/state"
acceptance=$?
set -e

# The acceptance's own JSON says which check failed and why; it belongs in the
# bundle, so repack with it.
if [ -f tasks/scratch/027-acceptance.json ]; then
  tar -czf "$OUT" \
      "$WORKDIR/state" \
      "$WORKDIR/simulate.json" \
      "$WORKDIR/simulate_info.json" \
      tasks/scratch/027-acceptance.json
  echo "  repacked with the acceptance result  ($(stat -c %s "$OUT") bytes)"
fi

if [ "$acceptance" -ne 0 ]; then
  echo "--------------------------------------------------------------"
  echo "ERROR: the acceptance did not pass. The lines above say which check"
  echo "failed and whether it is this task's or a build that does not"
  echo "reproduce. The outputs are packaged at $OUT and can be fetched."
  echo "  finished    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit "$acceptance"
fi

echo "  finished    : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "DONE"
