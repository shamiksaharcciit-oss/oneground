#!/usr/bin/env bash
# What is actually on the vecbench volume, where, and by what digest --
# session 20260925-185647 (task 065/066's re-priced 036-models.yaml) refused
# at its first input check: `/workspace/arxiv-150k/sample.jsonl.zst` was not
# there. That path is the LAPTOP's own convention
# (`ONEGROUND_ASSETS`/`~/oneground-assets/arxiv-150k/...`), never confirmed
# to be how the corpora actually sit on this volume -- the release tarballs'
# own manifests (tasks/022b) instead show `fixtures/arxiv-150k/
# sample.jsonl.zst`. This session settles which, if either, is right --
# without changing anything and without assuming the corpora are there at
# all, since a prior session put something on this volume and nobody has
# checked since.
#
# The whole run is read-only: a recursive listing, a name search for the
# corpus files anywhere on the volume (not only the one path the models
# session expects), and a sha256 of whatever is found. Nothing here embeds
# anything, loads a model, or touches the GPU.
set -euo pipefail

cd /workspace/oneground

ASSETS="${ONEGROUND_ASSETS:-/workspace}"
export ONEGROUND_ASSETS="$ASSETS"
OUT_DIR=/workspace/036-volume-inspect
mkdir -p "$OUT_DIR"

say() { echo "[$(date -u +%H:%M:%S)] $*"; }

# ------------------------------------------------- 1. the recursive listing
# Depth 4 under $ASSETS reaches a layout as deep as `fixtures/arxiv-150k/
# sample.jsonl.zst` (3 levels) with a level to spare, and excludes the
# cloned repo and the HF model cache -- neither is a corpus and both are
# large enough to bury the listing that matters under noise.
say "recursive listing of $ASSETS, depth 4, with sizes"
find "$ASSETS" -mindepth 1 -maxdepth 4 \
  ! -path "$ASSETS/oneground" ! -path "$ASSETS/oneground/*" \
  ! -path "$ASSETS/hf" ! -path "$ASSETS/hf/*" \
  -printf '%y %12s  %p\n' 2>/dev/null | sort -k3 \
  | tee "$OUT_DIR/listing.txt"
say "  $(wc -l < "$OUT_DIR/listing.txt") entries"

# --------------------------------------- 2. the corpus files, by name, anywhere
# Not "does the expected path exist" -- a name search across the whole
# volume, so a corpus placed under a different layout is still found.
say "searching the whole volume for the corpus files by name"
find "$ASSETS" -type f \( \
    -iname 'sample.jsonl.zst' -o -iname 'documents.jsonl.zst' \
    -o -iname 'vectors.npy' -o -iname 'queries.npy' \) \
  2>/dev/null | sort | tee "$OUT_DIR/candidates.txt" || true

# ------------------------------------- 3. whether each corpus is there at all
# By NAME of the corpus directory anywhere under $ASSETS, independent of
# which files it contains -- answers "present under some layout" separately
# from "present at the exact file this session's models run expects."
say "searching for each corpus's own directory, by name, anywhere"
for corpus in arxiv-150k stackexchange-150k sec-filings-10k; do
  hits="$(find "$ASSETS" -mindepth 1 -iname "$corpus" 2>/dev/null | sort)"
  if [ -n "$hits" ]; then
    say "  $corpus: found at"
    echo "$hits" | sed 's/^/    /'
  else
    say "  $corpus: no directory of this name anywhere under $ASSETS"
  fi
  echo "$hits" >> "$OUT_DIR/corpus-dirs.txt"
  echo "---" >> "$OUT_DIR/corpus-dirs.txt"
done

# --------------------------------------------------- 4. digest what was found
say "sha256 of every candidate file found"
: > "$OUT_DIR/digests.txt"
if [ -s "$OUT_DIR/candidates.txt" ]; then
  while IFS= read -r f; do
    [ -f "$f" ] || continue
    sha256sum "$f" | tee -a "$OUT_DIR/digests.txt"
  done < "$OUT_DIR/candidates.txt"
else
  say "  nothing to digest -- no candidate files found"
fi

# ------------------------------------------------------------ 5. bring home
say "assembling the receipt"
python3 - "$OUT_DIR" <<'PY'
import json
import os
import sys

out_dir = sys.argv[1]


def lines(name):
    p = os.path.join(out_dir, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip()]


listing = lines("listing.txt")
candidates = lines("candidates.txt")
digest_lines = lines("digests.txt")
digests = {}
for ln in digest_lines:
    parts = ln.split(None, 1)
    if len(parts) == 2:
        # sha256sum prints "<digest> *<path>" in binary mode (the default) --
        # the leading "*" is not part of the path candidates.txt carries.
        digests[parts[1].strip().lstrip("*")] = parts[0]

corpus_dirs = {}
raw = lines("corpus-dirs.txt")
current = None
CORPORA = ("arxiv-150k", "stackexchange-150k", "sec-filings-10k")
idx = 0
block = []
for ln in raw:
    if ln == "---":
        if idx < len(CORPORA):
            corpus_dirs[CORPORA[idx]] = block
        idx += 1
        block = []
    else:
        block.append(ln)

receipt = {
    "assets_root": os.environ.get("ONEGROUND_ASSETS", "/workspace"),
    "listing_entries": len(listing),
    "listing": listing,
    "candidate_files": [
        {"path": c, "sha256": digests.get(c)} for c in candidates
    ],
    "corpus_directories_found": corpus_dirs,
    "note": ("Read-only inspection (task 065/066's session refused at its "
             "first input check; this session finds out why rather than "
             "guessing). listing_entries/listing is a recursive find under "
             "assets_root, depth 4, excluding the cloned repo and the HF "
             "cache. candidate_files is every sample.jsonl.zst/"
             "documents.jsonl.zst/vectors.npy/queries.npy found anywhere, "
             "each with its sha256. corpus_directories_found is every path "
             "whose basename matches a corpus name, independent of what it "
             "contains."),
}
with open(os.path.join(out_dir, "036-volume-inspect.json"), "w",
          encoding="utf-8") as f:
    json.dump(receipt, f, indent=1)
print("wrote %s/036-volume-inspect.json" % out_dir)
PY

tar -czf /workspace/036-volume-inspect.tgz -C /workspace 036-volume-inspect
say "DONE"
