# Report: 035-rerank-stage

## Repo state expected vs found

The brief assumes 034 merged, with `flat` a declared index, because the exact
scoring pass is that index applied to a candidate set. Found: `main` at
`ba39c8a` carrying 034, `INDEX_ALGORITHMS = (flat, hnsw, ivf, ivf_pq)`,
`Param.belongs_to` as a generic `(key, values)` pair, and
`in_label_at_default` from 032. All three were reused rather than
reimplemented; `rerank` slots into the same machinery `index` uses.

---

## The headline: two dominations

### 1. At this size, not approximating beats approximating and then fixing it

| arxiv-150k | recall@10 | ms/query |
|---|---|---|
| **`flat`, whole corpus** | **1.0000** | **4.651** |
| `hnsw` + rerank@32 | 0.9968 | 1.935 |

On recall, `flat` wins outright. On latency `hnsw + rerank@32` is faster here
— but it is paying 2.4× its own un-reranked cost (0.819 ms) to recover
**exactly nothing**, so the comparison a team actually faces is `flat` at
1.0000/4.651 against `hnsw` alone at 0.9968/0.819. Reranking is not on that
frontier at all.

**A report that assumed approximation was required could never have said
this.** `flat` is one of the four declared algorithms rather than a separate
mode, so every sweep prices exact search over the whole corpus beside the
approximations. At 150,000 vectors of 768 dimensions that is 3.3–4.7 ms per
query at perfect recall, and for a team whose latency budget is above ~5 ms
the honest answer is **do not approximate at all**.

### 2. Reranking's one real use case is dominated on latency, so it is a memory case

| arxiv-150k | recall@10 | ms/query | index bytes |
|---|---|---|---|
| `hnsw` | 0.9968 | 0.819 | 501,632,162 |
| `ivf_pq` + rerank@32 | 0.8228 | 0.805 | **7,540,532** |

`ivf_pq + rerank` is the only configuration in the sweep where reranking
recovers anything — it nearly triples recall, 0.2872 → 0.8228. And at
essentially the same latency, plain `hnsw` returns 0.9968. On recall and
latency together it is beaten.

**Its case is a memory case and must be made with 034's memory numbers or not
at all.** Measured at 150k on this laptop: `ivf_pq` is **66× smaller than
`hnsw`** and 61× smaller than `flat`. That is the trade, stated as a trade:
0.17 of recall and nothing in latency, for 1/66th of the memory.

Worth recording beside it, because it is what 034 built `measured_bytes` for:
`est_memory_bytes` reports 460,800,000 for that same `ivf_pq` index. The
formula is **61× too high**, because it assumes `vectors × dim × 4` and
quantisation is precisely the case where that stops being true.

---

## The finding: only an index that scores from codes can mis-order what it already holds

**This is the mechanism, and it was stated before the measurement rather than
inferred from it.** The table below is the confirmation, not the finding.

An index that returns *true* scores for the vectors it found cannot have
mis-ordered what it holds. Whatever it got wrong is in what it *did not find*.
So:

| index | scores it returns | ordering loss possible |
|---|---|---|
| `flat` | exact, over everything | none — it is already the answer |
| `hnsw` | **true** inner products of the nodes it visited | **none** |
| `ivf` | **true** inner products of the cells it probed | **none** |
| `ivf_pq` | **approximate**, from quantised codes | **yes** |

Exact reranking recovers the ordering term and nothing else. Therefore for
three of the four declared algorithms it recovers nothing, and the only thing
it can change is the latency. The prediction is that `recovered` is exactly
`0.0000` for `flat`, `hnsw` and `ivf` at every multiplier, on every corpus.

### The evidence

Both fixtures, 2,000 queries, k=10, candidates 1→32.

| | recall@10 | recovered | ms/query | | recall@10 | recovered | ms/query |
|---|---|---|---|---|---|---|---|
| **arxiv-150k** | | | | **stackexchange-150k** | | | |
| `flat` | 1.0000 | +0.0000 | 4.651 | | 1.0000 | +0.0000 | 3.322 |
| `flat` @32 | 1.0000 | **+0.0000** | 7.117 | | 1.0000 | **+0.0000** | 3.781 |
| `hnsw` | 0.9968 | +0.0000 | 0.819 | | 0.9938 | +0.0000 | 0.842 |
| `hnsw` @32 | 0.9968 | **+0.0000** | 1.935 | | 0.9938 | **+0.0000** | 1.908 |
| `ivf` | 0.8569 | +0.0000 | 0.188 | | 0.7640 | +0.0000 | 0.295 |
| `ivf` @32 | 0.8569 | **+0.0000** | 0.922 | | 0.7640 | **+0.0000** | 1.104 |
| `ivf_pq` | 0.2872 | +0.0000 | 0.089 | | 0.2851 | +0.0000 | 0.110 |
| `ivf_pq` @4 | 0.5323 | +0.2451 | 0.155 | | 0.5000 | +0.2149 | 0.177 |
| `ivf_pq` @32 | 0.8228 | **+0.5356** | 0.805 | | 0.7387 | **+0.4536** | 0.770 |

The table is a sample; the sweep is not. **All 42 non-quantised rows read
exactly `+0.0000`** — three algorithms, six multipliers plus the un-reranked
baseline, two corpora, 2,000 queries each. Not 0.0001. A number that could not
have been otherwise, which is what it means for a mechanism to be the finding:
had one row been non-zero, the mechanism would be wrong and no amount of
tuning would rescue it.

**The two fixtures agree** — in sign, in mechanism and nearly in magnitude.
They disagreed about drift and agreed about architecture; this is the third
question they have been asked together and they agree on it.

### The crossover

For `ivf_pq`, recovered recall has not flattened by 32× on either corpus
(+0.5356 and +0.4536, still rising), while latency has grown 9.0× and 7.0×
from the un-reranked baseline. There is no crossover inside the swept range, and the
report says that rather than extrapolating one. `candidates: 1` recovers
`0.0000` on every algorithm — measured, not asserted: rescoring exactly `k`
candidates cannot move a neighbour into the top `k` that was not already
there.

---

## Measurements

### The decomposition

Recall's gap splits three ways and they sum to `1 - recall_before_rerank`:

    routing_loss    1 - ceiling                   never reachable
    candidate_loss  ceiling - candidate_recall    reachable, not retrieved
    ordering_loss   candidate_recall - recall     retrieved, ranked out

Reranking recovers the ordering term, so the reranked recall is
`1 - routing_loss - candidate_loss` exactly. `ivf`'s loss is **100% candidate
loss** on both corpora (0.1431 and 0.2360, unchanged at every multiplier),
which is the brief's case in its purest form: a configuration reranking cannot
help however it is tuned. Only `nprobe` reaches it.

### Cost

`query_seconds_without_rerank` is **measured** by searching the same
configuration with the stage off, not derived by subtracting the rescore: the
first pass of a reranked search retrieves `k × candidates`, so
`query_seconds − rerank_seconds` is the cost of the deeper retrieval, not the
cost of not reranking.

Timings stay beside the row rather than in it (020b), and the report joins
them: the rule is about where a number is stored, not about what a reader is
shown. A recall gain is never rendered without its latency.

### Runtime

Both sweeps ran on the laptop; no pod was needed. Index builds dominate:
`hnsw` 313–480 s, `ivf` 455–528 s, `ivf_pq` 557–698 s, `flat` 2–5 s. The sweep
builds each index **once** and varies only `candidates` at search time, which
is not a shortcut — the index does not depend on `candidates`, so sweeping it
through `measure_config` would rebuild the same index six times per algorithm
and measure nothing extra.

---

## Verification

Full suite **1261 passed, 6 skipped**, and the commit was *gated* on it.

- `rerank: none` does not re-label: `Config.make` with and without it yields
  the identical label. No published fixture value moves.
- `candidates` is refused when reranking is off, by 034's generic
  `belongs_to`, and an unknown mode is refused with the declared list.
- The rescore is proved to be the same arithmetic as `flat` over that subset,
  against `faiss.IndexFlatIP` directly.
- Both halves of the central claim are proved **by construction**: an exact
  rescore drives ordering loss to zero on a deliberately mis-ordered candidate
  set, and recovers nothing on one deliberately missing a true neighbour.
- Step 7's refusals are tested as the claim invariant is — no recommending, no
  carrying a multiplier between corpora, and the caption naming the latency so
  a gain cannot be stated without its cost.

**Couldn't check:** whether the crossover exists beyond 32×, and whether these
hold at a scale where `flat` stops being affordable. Both are larger runs, and
neither is extrapolated here.

---

## Two defects of mine, and what caught them

**The decomposition described the wrong thing.** As first written it
decomposed the *post-rerank* recall. But after an exact rescore ordering loss
is zero by construction — that is the property the stage rests on — so every
reranked row printed `ordering_loss: 0.0000` and the one term the task exists
to expose was invisible. On a quantised index recall rose 0.3133 → 0.6450 with
`ordering_loss` reading `0.0000` in both rows. The number was not wrong; it
answered a question nobody asked. Caught by reading the first real output
rather than by a test, which is why a test now covers it.

**The caption was inside the row.** Caught by the verdict-language guard, on
the word "pass" in "what the first pass lost" — the guard being right for a
reason adjacent to the one it was written for. The general form is now in
`docs/CLAIMS.md`: *a paragraph inside a measurement row is prose nobody
reviewed as prose.* A sentence in a document is read by someone deciding
whether it is true; the same sentence inside a dict literal, beside four
floats, is read as plumbing — which is how a claim about what a number means
avoids every check the project has for claims about what a number means.

### And two process failures

| | what I did | what caught it |
|---|---|---|
| 031 report | pushed prose to `main` with **no** checks | the identifier scan, on main, blocking another stream |
| this task | ran the checks, chained with `;`, **committed past the failure** | I noticed in the output |

The second is worse: skipping a check is an omission, running it and walking
past the result is ignoring evidence I asked for. The repair is not resolve —
the commit command now tests the suite's own output and cannot proceed past a
failure. When a later sweep left 0.4 GB free and the suite could not run, I
held the commit rather than weakening the gate the first time it was
inconvenient.

---

## Observed, not done

- **`est_memory_bytes` is 61× wrong for `ivf_pq` at 150k** (460,800,000
  reported against 7,540,532 measured). 034 added `measured_bytes` for exactly
  this reason and the estimate is kept deliberately beside it, so this is the
  documented behaviour rather than a defect — but a reader comparing families
  on the estimate alone would be badly misled, and the estimate is the older
  and more prominent field.
- **The sweep covers one family.** `rerank` works on all three — the 026
  invariant exercises every algorithm under both modes on each — but the
  published sweep is `single_node_hnsw`, to isolate the index effect from the
  partition's. The sharded families would add routing loss, which is the one
  term reranking provably cannot touch.
- **No crossover was found**, because none exists below 32×. A sweep to 128×
  would find it or show there is none, at four times the query cost.
- **`ivf`'s parameters were 034's, not tuned.** Its 0.1431 candidate loss is a
  property of `nprobe: 8`, not of the corpus, and a reader should not read
  "IVF loses 14%" as a fact about arXiv.

## Repo now contains

New: `oneground/models/rerank.py`, `oneground/models/test_rerank.py`, this
report, `runs/035-rerank-{arxiv,stackexchange}-150k.json` (copied to the main
checkout and verified by digest).

Changed: `oneground/models/base.py` (`rerank_params`, `RERANK_ONLY`,
`Candidates.reranked_from` and `.rerank_seconds`), all three family models
(declare the keys, search at rerank depth, one shared `apply`),
`oneground/simulate/__init__.py` (the three terms, the measured without-rerank
cost), `oneground/models/test_parameters.py` (026's invariant extended to the
rerank mode), `docs/MODELS.md`, `docs/INTAKE.md`, `docs/CLAIMS.md`.

## Blocked on developer

None.
