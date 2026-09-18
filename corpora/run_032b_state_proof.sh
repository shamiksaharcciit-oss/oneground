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

# THE PIN. Both halves of this comparison must run the same code, or it
# measures the revision rather than the environment -- which is exactly what
# task 028c spent three measurements untangling for the arxiv workdir, where a
# row from one commit was subtracted from a row from another. The laptop half
# ran at $ONEGROUND_PINNED_COMMIT; this refuses unless the code here is that
# code. It compares `oneground/`, not HEAD: a later commit that touches only a
# report or a session spec is the same simulator, and saying so is the honest
# check rather than the convenient one.
PIN="${ONEGROUND_PINNED_COMMIT:-}"
if [ -z "$PIN" ]; then
  echo "ERROR: ONEGROUND_PINNED_COMMIT is not set. The session spec pins the" >&2
  echo "       commit the laptop half ran at; without it this run cannot show" >&2
  echo "       the two halves measured the same simulator." >&2
  exit 1
fi
if ! git cat-file -e "$PIN^{commit}" 2>/dev/null; then
  echo "ERROR: pinned commit $PIN is not in this checkout (shallow clone?)." >&2
  echo "       Fetch it before running: git fetch --unshallow, or clone deep." >&2
  exit 1
fi
if ! git diff --quiet "$PIN" HEAD -- oneground/; then
  echo "ERROR: oneground/ differs from the pinned commit $PIN:" >&2
  git diff --stat "$PIN" HEAD -- oneground/ >&2
  echo "       The laptop half ran the pinned code. Check it out, or re-run" >&2
  echo "       the laptop half at this commit and re-pin." >&2
  exit 1
fi
echo "  pinned  : $PIN  (oneground/ identical to the laptop half's)"

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
