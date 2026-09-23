# Report: 036-embedding-models

## Repo state expected vs found

Expected, and found:

- **031 merged.** The brief says to branch after it, and `main` carries
  `b1abee4` and `c70fc05`. Found.
- Three fixtures: `arxiv-150k`, `stackexchange-150k`, `sec-filings-10k`, with
  published crispness 0.0363, 0.0115 and 0.1073. Found, all three.
- 017's truncation accounting in `oneground/embed/count_truncated`. Found, and
  reused rather than rewritten.
- A single `corpus.sample.text.model` in the requirements schema. Found.

**Four things the brief did not state, each of which changed the work:**

1. **The corpora ship their source text**, so re-embedding is possible at all:
   `sample.jsonl.zst` for the two 150k corpora, `documents.jsonl.zst` for the
   filings. Without it this task could not have been started.
2. **`sec-filings-10k` has no vectors on this machine** — only documents. Its
   arm requires chunking before embedding, which is where this run's worst
   confound came from (below).
3. **Embedding is token-bound, not record-bound**, and the laptop does ~273
   tokens/second. The full task as written is ~338 hours here.
4. **The same model in another environment does not reproduce its vectors.**
   That is measured below and it decided the experiment's design.

## What was done

**The machinery** (steps 1, 3, 4, 5, 7, 8): `embed/compare.py` with the three
registers enforced by refusal, `embed/registry.py` for resolution and measured
cost, `embed/multimodel.py` to run one characterization per model,
`intake` accepting `models:`, and `docs/EMBEDDINGS.md` with the name collision
resolved. 35 tests, most of them attempts to build the false table.

**The measurement** (step 6): the crispness ordering across three corpora and
three models, on a seeded subsample, with truncation counted per model on the
same records.

**Not done:** the full-size run. It is priced, specified and resolved as
`sessions/036-models.yaml`, and it is **not to be run** — see the last section
for why the card stands unspent.

---

## The finding: the measure carries a constant calibrated to one embedding

**This leads the report. The ordering result that the brief set out to get is
subordinate to it, because it was obtained with an instrument that this run
showed does not read under every embedding.**

`boundary_crispness` counts the fraction of vectors whose second-nearest
centroid is more than **1.20×** the first. That constant is
`CRISP_RATIO = 1.20` in `oneground/measures/crispness.py`, under the comment:

> `# Definitions, not parameters.`

Measured, on identical records, seed and centroid count:

| model | condition | crispness | median ratio | **p95 ratio** |
|---|---|---|---|---|
| bge-base-en-v1.5 | raw | **0.1487** | 1.1035 | **1.2631** |
| e5-base-v2 | raw | 0.0063 | 1.0565 | **1.1475** |
| e5-base-v2 | `passage: ` | 0.0063 | 1.0584 | **1.1505** |
| e5-base-v2 | `query: ` | 0.0125 | 1.0644 | **1.1643** |

**Under e5 the 95th percentile of the ratio is 1.15. The threshold is 1.20.**
It sits above almost the entire distribution, so the measure returns a
near-zero for every corpus regardless of what is in it. Under bge the p95 is
1.2631 — just above the threshold, which is where a threshold has to sit to
discriminate at all.

So the five characterization measures are documented as **properties of the
embedding**, and at least one of them carries a constant calibrated to one
particular embedding's geometry.

**This is not a fact about e5.** The ratio is scale-invariant — a quotient of
two distances — so it is not a units artifact. e5 genuinely places these
vectors more equidistantly between k-means centroids than bge does. That
difference is real and measurable. What the fixed threshold does is convert it
into `0.0000` instead of into a number.

### Why this is the most serious thing in the run

A user who brings an embedding whose ratio distribution is compressed relative
to bge's gets **crispness ≈ 0 on every corpus they own**. The honest reading of
that output, as the tool presents it today, is *"my corpus has no boundary
structure"*. The true statement is *"this measure's threshold does not fit my
embedding's scale"*.

Those are different sentences, and **the tool currently offers only the first**.
That is the product stating a confident falsehood about the user's own data,
which is the single thing this project exists to refuse. It is the same defect
class as an alignment rate quoted without its ceiling and a gap quoted without
its scale: the number is true, the sentence it licenses is not, and nothing in
the artifact tells a reader which they are holding.

### How it was established, by elimination

The collapse was found in the ordering run (e5: arxiv **0.0007**,
stackexchange **0.0003** — two records against one at N=3000). Two candidate
explanations were tested and both were ruled out before the instrument was
suspected:

- **Truncation: ruled out.** bge and e5 share a tokenizer family and both cap
  at 512. They truncate *identically* on all three corpora — 1.1%, 0.0%,
  86.2% for both — so they read exactly the same tokens and returned 0.0823
  against 0.0007 on arxiv.
- **Protocol: ruled out.** All three models declare *empty* prompts in their
  sentence-transformers config, so raw text matches every config — but e5's
  published usage requires `query: `/`passage: ` prefixes its config does not
  encode, which would have made it off-protocol and its column void. Tested:
  `passage: ` changes nothing, `query: ` doubles it to a twelfth of bge's.

Only then does the threshold remain, and the p95 arithmetic above confirms it
directly rather than by elimination alone.

### Not fixed, deliberately

Changing `CRISP_RATIO` would move every published fixture value, and CLAUDE.md
rule 3 forbids changing a threshold so that something reads better. This is
reported as a decomposition — which layer is responsible — and the remedy is
scoped as **task 044**, which is a change to a published measure and therefore
the developer's to approve with the migration in front of them.

**Stated within its limits:** one sample size each (N=800 and N=3000), one
centroid count each (16 and 32), three corpora, one model family exhibiting
it. That e5's ratios are compressed on *these* corpora is measured; that this
holds of e5 generally, or of other models, is not.

`N_CENTROIDS = 256` sits under the same comment and **has not been examined at
all**.

---

## Measurements

### Cost, and why the task was reduced

Measured on this machine, with each model's own tokenizer on each corpus's
real text — not projected from record counts, because the three corpora differ
by 4× in record length and embedding is token-bound:

| | tokens |
|---|---|
| arxiv-150k × 3 models | 98.3M |
| stackexchange-150k × 3 models | 52.3M |
| sec-filings-10k × 3 models | 181.7M |
| **total** | **332.2M** |

| rate | where measured | full run |
|---|---|---|
| 273 tok/s | this laptop, 4 cores / torch's 2 threads | **338.1 h** |
| 80,752 tok/s | RTX PRO 4500, task 031 (196 chunks/s × 412 median tokens) | **1.14 h** |
| 99,774 tok/s | RTX PRO 4500, task 030 (152,000 × 512 tokens in ~13 min) | 0.92 h |

Both pod rates are this project's own measurements on the same card
`oneground pod plan` resolves onto.

**The reduction, stated as the brief requires.** Step 6 as written is three
fixtures × three models at full size: 338 hours here. It was run instead on a
seeded **N=3000** subsample at 32 centroids.

**The reduction is a measurement, not a convenience**, and that is the
difference worth recording. Before reducing, the subsample was validated as an
instrument on the *stored* anchor vectors, where it costs nothing: at every
size from N=1,000 to N=20,000 it reproduced the published ordering
`arxiv > stackexchange`, with the gap converging on the published 0.0248 as N
grew (0.1350 at 1,000 → 0.0293 at 20,000 → 0.0248 published at 150,000). A
subsample that had reversed the published ordering under the published model
would have been measuring sampling noise, and the experiment would not have
been worth running.

### Every model was embedded here, including the anchor

Re-embedding the stored text with the anchor's own name does **not** reproduce
the published vectors:

| corpus | mean cosine to stored | max element delta |
|---|---|---|
| arxiv-150k | 0.996871 | 0.020234 |
| stackexchange-150k | 0.998489 | 0.007550 |

About a thousand times float32 noise. The published vectors were built on
**CUDA on Linux** (`fixtures/*/build_info.json`: RTX PRO 4500 Blackwell, torch
2.14.0+cu130); this is Windows CPU. Both candidate text templates tokenize
identically, so the template is recovered and the residue is the platform.

So the anchor was re-embedded rather than read off disk. Reusing the stored
vectors would have been cheaper and would have put a platform difference
inside the comparison, where nothing could distinguish it from a model
difference.

### The ordering, with what each model actually read

N=3000, 32 centroids, seed 20260920, every model embedded on this machine.
Truncation counted with each model's own tokenizer on the same records.

| corpus | published | model | max_seq | truncated | crispness |
|---|---|---|---|---|---|
| sec-filings-10k | 0.1073 | bge-base-en-v1.5 | 512 | **86.2%** | 0.1153 |
| | | all-MiniLM-L6-v2 | **256** | **93.6%** | 0.2097 |
| | | e5-base-v2 | 512 | **86.2%** | 0.1120 |
| arxiv-150k | 0.0363 | bge-base-en-v1.5 | 512 | 1.1% | 0.0823 |
| | | all-MiniLM-L6-v2 | **256** | **35.3%** | 0.0933 |
| | | e5-base-v2 | 512 | 1.1% | **0.0007** |
| stackexchange-150k | 0.0115 | bge-base-en-v1.5 | 512 | 0.0% | 0.0107 |
| | | all-MiniLM-L6-v2 | **256** | 0.0% | 0.0253 |
| | | e5-base-v2 | 512 | 0.0% | **0.0003** |

All three orderings read `filings > arxiv > stackexchange`, which is the
published ordering. **That is not reported as a stable ordering, for three
separate reasons, and each is a confound rather than a finding.**

## The three confounds

### 1. MiniLM reads less and looks crisper

Its `max_seq_length` is **256, not 512** — read from the model, not assumed.
It is flagged by `truncation_confound` on two of three corpora (arxiv 35.3%
against 1.1%; filings 93.6% against 86.2%), and it returns **the highest
crispness of the three models on all three corpora**.

A model that read a third of arxiv's records only partially, and looks crisper
everywhere, is distinctive for a reason that has nothing to do with its
geometry. Per the brief's rule this is reported as a confound. MiniLM's column
does not support a claim about MiniLM.

### 2. The filings column is on differently-chunked text — and that one is mine

`sec-filings-10k` has no vectors here, so its arm had to be chunked first. I
used the `structure` strategy at `max_size: 512`, which counts **whitespace**
tokens. The published fixture used `fixed` at 512 tokens of **the embedding
model's own tokenizer** (task 030). Whitespace tokens are not subword tokens,
so my chunks overflow a 512-subword limit **86.2%** of the time — under every
model, including the anchor.

Two consequences:

- The filings column is measured on text chunked differently from the
  published fixture, so **it is not comparable to the published 0.1073**.
- My bge filings figure of **0.1153 sits close to the published 0.1073 and
  that is coincidence, not confirmation.** It is not banked. A figure that
  looks like agreement and is not is worse than one that looks wrong.

This is the token-unit mismatch `docs/EMBEDDINGS.md` §3 warns about, measured.
Re-chunking in subword tokens is what would let this column join the
comparison, and it is named in "Observed, not done".

### 3. e5's column measures the instrument, not the corpora

Under e5, arxiv is **0.0007** and stackexchange **0.0003** — two records
against one at N=3000. This is the confound that turned out not to be a
confound at all but the leading finding above: the threshold sits outside e5's
ratio distribution, so the column reports the measure failing to read rather
than a property of the corpora. Truncation and protocol were both ruled out
first; the elimination is recorded under **The finding**.

Its consequence for this run is narrow and firm: **e5's column cannot
participate in the ordering**, not because its numbers disagree but because
they are not readings of the corpora.



## The ordering result, subordinate to the finding above

The brief set out to learn whether the corpora's ordering by crispness is
stable across models. It was obtained, and it is reported second because it
was obtained with the instrument the previous section shows does not read
under every embedding. An ordering is only as good as the measure that
produced it, and one of the three columns turned out not to be a reading.

### The clean comparison this run can make

**`arxiv` against `stackexchange` under bge and MiniLM, and nothing else** —
e5 is excluded not because its numbers disagree but because the instrument
does not read under it.

stackexchange truncates **0.0% under all three models**, and arxiv truncates
1.1% under the two 512-token models. So for the anchor, the arxiv-vs-
stackexchange comparison carries **no truncation confound at all** — and it is
exactly the pair the instrument check validated across five subsample sizes.

Under that pair:

| model | arxiv | stackexchange | gap | ordering |
|---|---|---|---|---|
| published (full size, 256 centroids) | 0.0363 | 0.0115 | 0.0248 | arxiv > stack |
| bge-base (N=3000, 32 centroids) | 0.0823 | 0.0107 | 0.0716 | arxiv > stack |
| all-MiniLM (confounded, 35.3% on arxiv) | 0.0933 | 0.0253 | 0.0680 | arxiv > stack |

**What this establishes:** the ordering of arxiv above stackexchange survives a
change of embedding model from bge-base to MiniLM, at one sample size and one
centroid count, with the caveat that MiniLM's arxiv column is truncation-
confounded in the direction that would *inflate* its apparent crispness.

**What it does not establish:** that the ordering is stable in general. Two
models is not three; one sample size is not a range; and the third corpus —
the one that tops the published ordering — **cannot join this comparison until
it is re-chunked in subword tokens.** Stability at one sample size under two
models is a much weaker statement than the brief's step 6 was reaching for,
and the full-size pod run is what would strengthen it.

## A wall-clock figure that is not a measurement

The `e5 × stackexchange` cell reports **167,439 s** and its timestamp runs
backwards (21:02:36 → 19:33:16). The laptop suspended: the run started on
2026-09-20 and finished on 2026-09-23.

That figure is **not a slow measurement, it is no measurement** — the same
distinction this project makes between an absence and a zero, and between
couldn't-check and a verdict. It is excluded from every rate quoted here
rather than averaged in, and the cell's crispness is unaffected: the measure
is deterministic given the vectors, and the process resumed rather than
restarted.

The eight clean cells agree with the pre-run probe closely enough to say the
rates are sound: arxiv under bge took 3,329 s against 3,000 ÷ 0.9 = 3,333 s
predicted. I had earlier flagged these timings as contaminated by the test
suite competing for CPU; they were not, and that hedge was wrong.

## Verification

| check | result |
|---|---|
| Multiple models measured on one corpus, each with its own ground truth | **PASS** — nine cells, each embedded and measured independently |
| Comparable / per-model / not-measurable in visibly different registers | **PASS** — `embed/compare.py`, refusal-enforced, 13 tests |
| Truncation reported per model; material difference flagged | **PASS** — MiniLM flagged on 2 of 3 corpora |
| Cost stated before the first run | **PASS** — measured in tokens, `render_cost`, and in this report |
| Published values and reference labels unchanged | **PASS** — `characterize.run` untouched; `model` and `models: [one]` resolve identically, asserted by test |
| Three fixtures swept, findings written from the numbers | **PARTIAL** — three swept; the filings column is confounded by my own chunking and is not used, and e5's column is not a reading of the corpora |
| Whether the crispness ordering is stable across models | **PARTIAL, and the question changed** — stable for arxiv-vs-stackexchange under the two models where the measure reads; the third column showed the measure does not read under every embedding, which is the larger answer |
| Full suite | **PASS** — 1305 passed, 2 skipped |

**Couldn't check:**

- **Whether the ordering is stable at full size.** This is a subsample under
  two usable models. `sessions/036-models.yaml` is what settles it.
- **Whether the filings corpus orders where the published value says**, under
  any model, until it is re-chunked in subword tokens.
- **Every per-model recall number.** Not measured, deliberately: it is in the
  per-model register and this run had no question that needed it.

## Observed, not done

- **`CRISP_RATIO = 1.20` is not model-neutral — scoped as task 044, and the
  shape is ruled.** Two remedies were considered. Corpus-derived quantiles
  were **refused**: a threshold derived from the corpus makes the measure
  self-referential, and two corpora measured that way cannot be compared —
  which is precisely the property crispness exists to provide. The ruling is
  that **the distribution is the honest object and a thresholded count is a
  reading of it**, and a reading can be labelled with what it assumes. So
  crispness becomes the ratio distribution with its quantiles; the 1.20 count
  is retained as a named reading with its threshold stated beside it; and
  every published value keeps its meaning because the count remains computable
  from the distribution. Specified in `tasks/044-crispness-distribution.md`,
  not built — a change to a published measure is approved with its migration
  in front of the developer.
- **`N_CENTROIDS = 256` sits under the same comment and has not been examined
  at all.** Whether the same class of defect applies to it is unknown, and
  unknown is what this says rather than "probably fine".
- **A model whose published protocol its own config does not encode is a class
  of confound**, and it should be checked for every model added later. e5
  declares empty prompts while its card requires `query: `/`passage: `; the
  tool trusts the config and is therefore silently off-protocol. Here it
  turned out not to be the cause, but it was only ruled out because it was
  tested — nothing in the tool would have surfaced it.
- **Re-chunk the filings corpus in subword tokens** and re-run its column.
  This is the single change that would let the third corpus join the
  comparison. It is a `fixed`-strategy run at 512 tokens of the model's own
  tokenizer, matching task 030.
- **`chunk_document` counts whitespace tokens by default** while every model
  counts subword tokens, and nothing warns when a `max_size` in one unit is
  handed to a limit in the other. This produced an 86.2% truncation rate from
  a strategy whose parameter said 512 and a model whose limit said 512. A
  refusal or a warning belongs there; the brief did not ask for one.
- **`count_truncated` reports how often a model cut, not how much reached the
  encoder.** For the filings those are very different facts, and the second is
  the one the ordering has to be read against. `mean_tokens` was added
  alongside it in this task's scratch, not in the module.
- **The published `sec-filings-10k` crispness of 0.1073 tops the published
  ordering and was itself measured on chunks at a 512-token cap.** Whether it
  would move under a different chunk length is not asked here and is not
  answered by anything in this task.

## Repo now contains

New:

- `oneground/embed/compare.py`, `registry.py`, `multimodel.py`
- `oneground/embed/test_compare.py`, `test_multimodel.py`
- `docs/EMBEDDINGS.md`
- `requirements.arxiv-150k.models.yaml`
- `sessions/036-models.yaml`, `corpora/run_036_models.sh`
- `tasks/036-embedding-models.report.md` — this file

Changed:

- `oneground/embed/__init__.py` — `max_seq_length=None` leaves the model's own
- `oneground/intake/__init__.py` — `models:`, and its refusals
- `docs/MODELS.md` — the name collision, resolved by admitting it

Scratch (`tasks/scratch/`, gitignored): the cost probe, the anchor
reproduction control, the instrument check, the ordering experiment, the
truncation counts, the e5 protocol control, the renderer, and their logs.

## Blocked on developer

Nothing is blocked, and the one decision that was open has been ruled.

**The pod run is not happening, and the card stands unspent.**
`sessions/036-models.yaml` resolved live onto RTX PRO 4500 Blackwell in
EU-RO-1, stock High, $0.34–$0.72/hr, cap 3 h / $4.00, cost cap $2.16. Nothing
was created and nothing was spent.

It is held because **the threshold problem is not a sample-size problem**:
re-running e5 at 150,000 records buys a better-measured zero. The order of
work is therefore

1. **task 044** fixes the measure,
2. the filings corpus is **re-chunked in subword tokens**,
3. *then* the full-size run settles the arxiv/stackexchange pair and lets
   filings join the comparison.

Running it now would spend $2.16 to measure two corpora with an instrument
already known to be model-dependent and a third with chunks already known to
be wrong. The session spec, the runner and the price stay where they are and
need no rework when their turn comes.
