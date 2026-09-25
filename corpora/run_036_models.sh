#!/usr/bin/env bash
# Task 036 step 6, at full size: is the ordering of the three corpora by
# boundary crispness stable across embedding models?
#
# The laptop answered this on a seeded 3,000-record subsample. This runs the
# SAME script on the same seed with N=0 (every record), so the two are the
# same measurement at two sizes rather than two different experiments.
#
# Ordered so that the cheapest thing that can fail, fails first.
set -euo pipefail

cd /workspace/oneground

ASSETS="${ONEGROUND_ASSETS:-/workspace}"
OUT_DIR=/workspace/036-models
mkdir -p "$OUT_DIR"

say() { echo "[$(date -u +%H:%M:%S)] $*"; }

# ---------------------------------------------------------------- 1. inputs
# Before the model is loaded or a token is counted. A missing corpus should
# cost four minutes and name the path, not surface after the first embed.
#
# `sec-filings-10k` is not read this session (task 065): its chunking
# (`texts_filings` in the ordering experiment) cuts on WHITESPACE tokens,
# not the subword tokens `max_seq_length` is stated in, so its truncation
# and crispness numbers are entangled with that mismatch rather than being
# a clean read on the corpus. Re-chunking it correctly would chunk
# differently per model's own tokenizer, which breaks this experiment's own
# invariant that every model measures identical records -- a design
# decision left for a separate task, not guessed here.
say "checking inputs under $ASSETS"
for f in \
  "$ASSETS/arxiv-150k/sample.jsonl.zst" \
  "$ASSETS/stackexchange-150k/sample.jsonl.zst"
do
  if [ ! -f "$f" ]; then
    echo "MISSING INPUT: $f" >&2
    echo "The three corpora live on the network volume; this session does" >&2
    echo "not download them. Nothing has been spent on compute yet." >&2
    exit 2
  fi
  say "  ok  $(du -h "$f" | cut -f1)  $f"
done

# ------------------------------------------------------------ 2. the probe
# The one input the laptop could not measure is this card's throughput. The
# run is priced at 80,752 tokens/second (task 031's measured 196 chunks/s at
# 412 median tokens on an RTX PRO 4500). If this card is far slower, the cap
# is wrong and it is better to learn that in four minutes than at the cap.
say "probing throughput before committing to the run"
python - <<'PY'
import os, time, numpy as np
from oneground.embed.registry import resolve
from oneground.embed import embed

PRICED = 80752.0
rm = resolve("BAAI/bge-base-en-v1.5", device="cuda")
texts = ["the quick brown fox jumps over the lazy dog. " * 55] * 256
tok = len(rm.model.tokenizer(texts[0])["input_ids"])
t0 = time.time()
embed(rm.model, texts, batch=64, show_progress_bar=False)
dt = time.time() - t0
rate = len(texts) * tok / dt
print("  probe: %d texts x %d tokens in %.1f s -> %.0f tokens/s"
      % (len(texts), tok, dt, rate))
print("  priced at %.0f tokens/s; this card is %.2fx that" % (PRICED, rate / PRICED))
# Task 065: 150.58M, not the original 332.2M -- sec-filings-10k (181.66M of
# the original total) is excluded this session. See the input-check comment
# above and tasks/065-*.report.md for why.
hours = 150.58e6 / rate / 3600
print("  implied embedding time for the whole run: %.2f hours" % hours)
if rate < PRICED * 0.4:
    raise SystemExit(
        "REFUSED: this card is under 40%% of the priced rate, so the cap in "
        "the session spec is wrong for it. Nothing beyond the probe has been "
        "spent. Re-price against %.0f tokens/s and start again." % rate)
PY
say "probe accepted"

# --------------------------------------------------------- 3. the ordering
# N=0 is every record. Same seed, same centroid count, same script as the
# laptop's subsample -- the comparison between the two sizes is the point.
say "running the ordering experiment at full size"
export ONEGROUND_ASSETS="$ASSETS"
export ONEGROUND_036_OUT="$OUT_DIR/036-ordering-results-full.json"
export ONEGROUND_036_N=0
export ONEGROUND_036_CENTROIDS=256
export ONEGROUND_036_DEVICE=cuda
export ONEGROUND_036_BATCH=64
export ONEGROUND_036_CORPORA=arxiv-150k,stackexchange-150k
python corpora/036-ordering-experiment.py

# ------------------------------------------------------- 4. truncation too
# Reported BESIDE the ordering, not after it: if a corpus is being measured on
# a fraction of each record, that is a candidate explanation for where it
# lands, and a reader has to meet the confound at the same time as the number.
say "counting truncation per model"
python corpora/036-truncation-per-model.py \
  > "$OUT_DIR/036-truncation-full.txt" 2>&1 || true

# ------------------------------------------------------------- 5. bring home
say "packing receipts"
cp tasks/scratch/036-price.json "$OUT_DIR/" 2>/dev/null || true
tar -czf /workspace/036-models.tgz -C /workspace 036-models
say "DONE"
