#!/usr/bin/env bash
# Task 032b: `simulate --emit-state` on a second environment.
#
# Task 029 step 4 proved cross-environment identity for simulate.json and the
# centroids through the product path. It could not prove it for the emitted
# state: that run predates `--emit-state` on its branch and its tarball has no
# `state/` at all. This runs the same command with the flag, and brings the
# state home.
#
# It judges nothing. The comparison happens on the laptop, against the same
# command's output there at the same commit.
#
# Outputs are packaged BEFORE any check that can fail (task 027's lesson).
set -euo pipefail

REPO="${ONEGROUND_REPO:-/workspace/oneground}"
REQ="${ONEGROUND_REQUIREMENTS:-requirements.arxiv-150k.determinism.pod.yaml}"
WORKDIR="${ONEGROUND_WORKDIR:-runs/032b-state}"
OUT="${ONEGROUND_OUT:-/workspace/032b-state.tgz}"
VEC="${ONEGROUND_VECTORS:-/workspace/arxiv-150k/vectors.npy}"

cd "$REPO"

echo "=============================================================="
echo "oneground 032b: simulate --emit-state on a second environment"
echo "  requirements: $REQ"
echo "  workdir     : $WORKDIR"
echo "  commit      : $(git rev-parse HEAD 2>/dev/null || echo unknown)"
echo "  started     : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "--------------------------------------------------------------"

[ -x .venv/bin/python ] || { echo "ERROR: no venv at $REPO/.venv" >&2; exit 1; }
PY=.venv/bin/python
$PY --version
$PY -c "import faiss, numpy; print('faiss', faiss.__version__, '| numpy', numpy.__version__)"
[ -f "$VEC" ] || { echo "ERROR: corpus missing from the volume: $VEC" >&2; exit 1; }
echo "  corpus  : $VEC ($(stat -c %s "$VEC") bytes)"

# What this host is, and what the wheel links: the same record 029's session
# took, so the two sessions' hosts can be compared without guessing.
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
} 2>&1 | tee "/workspace/032b-host.txt"

echo "--------------------------------------------------------------"
echo "simulate, with the state emitted"
$PY -m oneground.cli simulate "$REQ" --emit-state

echo "--------------------------------------------------------------"
echo "what came out, with the digest a reader would check"
$PY - <<'PYEOF'
import hashlib, json, os
workdir = os.environ.get("ONEGROUND_WORKDIR", "runs/032b-state")
state = os.path.join(workdir, "state")
if not os.path.isdir(state):
    print("  NO state/ DIRECTORY -- the run did not emit state")
else:
    for name in sorted(os.listdir(state)):
        path = os.path.join(state, name)
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        print("  %-46s %10d  %s" % (name, os.path.getsize(path), digest))
    info_path = os.path.join(state, "state_info.json")
    if os.path.exists(info_path):
        with open(info_path, encoding="utf-8") as f:
            info = json.load(f)
        for cfg in info.get("configurations") or []:
            print("  %s -> %s (%s)" % (cfg.get("config_label"),
                                       cfg.get("file"), cfg.get("contract")))
PYEOF

echo "--------------------------------------------------------------"
echo "packaging (before any check, so a failure's evidence comes home)"
cp /workspace/032b-host.txt "$WORKDIR/host.txt" || true
tar -czf "$OUT" "$WORKDIR"
echo "  $OUT ($(stat -c %s "$OUT") bytes)"

echo "  finished: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "DONE"
