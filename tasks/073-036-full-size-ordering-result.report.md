# Report: 073-036-full-size-ordering-result

## Repo state expected vs found

Expected `sessions/036-models.yaml` re-priced and passing every local
check (tasks 065-072), still unrun for real past the second checkpoint.
Session 20260925-210913 (pod `7g3hnfg8mriexg`), bundled at `3e82a9e`,
was already up and running when this task started. Watched to `DONE`,
fetched, pod terminated. Elapsed ~34 min; well inside the 2h/$3.00 cap
(exact billed cost not yet confirmed by the account, estimate ~$0.41 at
$0.72/hr). No branch needed -- this task reports a measurement, it does
not change code; the report itself is the one new tracked file.

## What was done, in the order asked

**1. The probe passed and the ordering experiment got past its imports
-- both checkpoints the last two attempts died at, evident in the log
itself:**

    probe: 256 texts x 552 tokens in 1.6 s -> 87430 tokens/s
    priced at 80752 tokens/s; this card is 1.08x that
    [21:13:38] probe accepted
    [21:13:38] running the ordering experiment at full size
    [21:13:39] loading arxiv-150k
    [21:13:40]   arxiv-150k: 150000 of 150000 records, mean 1072 chars
    [21:13:40] loading stackexchange-150k
    [21:13:41]   stackexchange-150k: 150000 of 150000 records, mean 469 chars

No traceback at either point. Both corpora loaded at their full
150,000-of-150,000 record count -- task 068's placement and task 072's
`sys.path` reconciliation both held under the actual run, not just under
this task's own local proxy checks of them.

**2. `reading()` was reached, not `boundary_crispness()` alone -- visible
in the output shape itself, not inferred.** Every one of the six cells'
log lines carries the shape only `crispness_reading` produces (a bare
`boundary_crispness()` call has no `threshold_percentile` or `transfer`
to print):

    [21:23:28]     crispness 0.0298  lid 32.8  skew 0.0693  (570 s, 263.3 rec/s)
    [21:23:28]       reading: threshold 1.20 sits at the 97.02th percentile of this corpus's ratio distribution (4475 of 150000 above it)
    [21:23:28]       transfer: inside the published band

Confirmed independently in the fetched `036-ordering-results-full.json`:
every cell's `crispness_reading` carries `n`, `n_above`,
`sigma_from_zero`, `threshold_percentile`, `resolvable`, `transfer`, and
`distribution` -- the full shape `characterize.py`'s own call produces,
not the bare scalar.

**3. e5's arxiv and stackexchange counts against `MIN_INFORMATIVE_COUNT`,
with their σ, against the projection (task 065's report: ~100 and ~50 at
10.0σ and 7.1σ):**

    corpus                e5's n_above    σ_from_zero    resolvable
    arxiv-150k             329             18.16          yes
    stackexchange-150k      66              8.13          yes

Both real numbers are higher than projected -- the projection
extrapolated the subsample's own rate linearly to 150,000 records; the
real rate was not identical at full scale, and came out somewhat richer
in both cells. What the projection got right is the thing it was for: at
subsample scale (n=3,000) e5's own counts were 2 and 1 -- both below
`MIN_INFORMATIVE_COUNT` (5), formally couldn't-check. At full scale both
are comfortably resolvable, at 18.16σ and 8.13σ against the 3.0σ floor.
**Full size did earn this leg of the comparison, exactly as the session
was built to test** -- e5's crispness on this pair is now a real,
statistically distinguishable-from-zero measurement, not noise.

**4. The ordering under all three models, with each corpus's transfer
verdict:**

    model                arxiv-150k crispness   transfer      stackexchange-150k crispness   transfer
    bge-base-en-v1.5     0.0298                 inside band   0.0078                          OUTSIDE band
    all-MiniLM-L6-v2     0.0468                 inside band   0.0312                          inside band
    e5-base-v2           0.0022                 OUTSIDE band  0.0004                          OUTSIDE band

**The ordering (arxiv-150k > stackexchange-150k) is the same under all
three models**, and it is the published direction. `corpora/
036-render-ordering.py`, run against the real fetched results, confirms
this as its own computed verdict:

    ORDERING PER MODEL
       bge-base-en-v1.5   arxiv-150k > stackexchange-150k
       all-MiniLM-L6-v2   arxiv-150k > stackexchange-150k
       e5-base-v2         arxiv-150k > stackexchange-150k

    VERDICT
       The ordering is the SAME under all three models, and it is
       the published one: arxiv-150k > stackexchange-150k
       AND IT HOLDS UNDER THE TRUNCATING MODELS TOO...

One correction to that render's own printed truncation percentages,
found while checking them against the pod's own log rather than trusting
the render tool's default: `corpora/036-render-ordering.py` defaults its
truncation source to `tasks/scratch/036-truncation-results.json`, a path
this run's own `036-truncation-per-model.py` also writes to **on the
pod**, at `/workspace/oneground/tasks/scratch/...` -- outside `$OUT_DIR`,
so `run_036_models.sh`'s own packing step (`tar -czf ... -C /workspace
036-models`) never bundles it, and the render above actually read a
stale local copy of that file from earlier subsample-scale work this
session. The real, full-scale truncation numbers, read from the
fetched `036-truncation-full.txt` (the run's own stdout capture, which
*is* packed) instead:

    corpus                bge      MiniLM   e5
    arxiv-150k             0.8%     35.7%    0.8%
    stackexchange-150k     0.0%      0.1%    0.0%

Close to what the stale file showed (1.1%/35.3%/0.0% at subsample scale)
but not identical, and the correct figures for this run. The confound
check the pod itself ran flags `all-MiniLM-L6-v2` for arxiv-150k (0.357
against ~0.008 for the other two) and nothing for stackexchange-150k --
which does not change the verdict above: the ordering holds under the one
model that truncates materially more than the others, on the one corpus
where truncation is a real confound. Recorded as an "Observed, not done"
below rather than fixed in this report.

**5. The filings exclusion, stated in this result, not left implicit:**
`sec-filings-10k` was not measured this session. `design["corpora"]`
records exactly `["arxiv-150k", "stackexchange-150k"]`, and the render
tool prints it plainly: *"corpora not run this session: sec-filings-10k
(published value only, not settled by this run)"*. The reason, as ruled
in task 065's report and accepted in the developer's own follow-up: its
chunking defaults to whitespace tokens, not the subword tokens
`max_seq_length` is stated in, and fixing that per-model would break this
experiment's own invariant that every model measures identical records --
a design decision left to a separate task, not guessed at here.

**6. What a held ordering does and does not establish, in my own
words.**

It establishes that the direction of this specific comparison -- arxiv is
crisper than stackexchange -- is not an artifact of one embedding
family's vocabulary or training objective. Three models with materially
different architectures (768-d/512-token bge and e5 against 384-d/256-token
MiniLM), different absolute crispness values spanning two orders of
magnitude (0.0004 to 0.047), and a truncation profile that differs by a
factor of forty-plus between the least- and most-truncating model on
arxiv, all agree on which corpus sits closer to a cluster boundary. That
is a real, non-trivial form of stability, and MiniLM's heavy truncation
of arxiv makes it the stronger of the two possible outcomes rather than
the weaker one: the ordering survived reading substantially less of the
corpus that truncation touched.

It does not establish that this ordering is stable in general. Task 044c
already measured, on this exact quantity, that a fixed corpus's threshold
position moves by more than ten percentile points as the centroid count
sweeps from 16 to 512 -- so "stable at 256 centroids" is a claim about
256 centroids, not about the measure. It says nothing about any corpus
pair other than this one, and nothing about sec-filings-10k, deliberately
excluded. And it does not license treating e5's own crispness numbers the
way bge's or MiniLM's are read: both of e5's cells land outside the
published calibration band, which this project's own `transfer` field is
explicit is "a reason to read the distribution rather than the number,"
not a demonstration the number is wrong -- but also not a demonstration
it means the same thing a same-sized in-band count would. The ordering
holding under e5 is evidence the *direction* transfers; it is not evidence
that e5's *crispness value* can be read the way arxiv's 96th-percentile
bge reading can. Say plainly what this is: `transfer` (task 044) has
existed since before this project had a real out-of-band reading to test
it against -- every prior exercise of it was either in-band or synthetic.
Both e5 cells landing outside the calibrated band, on a real full-scale
embedding, is the first time this machinery has been asked the question
it was built to answer, for real, and it answered exactly as designed:
not a refusal, not a silent number, but a count with its own percentile
stated and an explicit warning that it is being read somewhere the
measure has never been calibrated.

The observation that `bge-base-en-v1.5`'s own re-embedding of
`stackexchange-150k` reads narrowly outside the same published band its
own value helped define is not a cross-check footnote to this run -- it
is a finding about the instrument, and it now lives beside the band's own
definition in `docs/FIXTURES.md`, where the next person reading that band
will meet it, rather than here.

## Measurements

- 6 of 6 cells complete, `design["full_size"] = true`, `n_base = 0`
  (every record), `centroids = 256` (the published setting).
- e5 resolvability: arxiv 329/150,000 above threshold, 18.16σ;
  stackexchange 66/150,000, 8.13σ. Both far above the 3.0σ /
  5-informative-count floor.
- Ordering: arxiv-150k > stackexchange-150k under all three models,
  matching the published direction.
- Transfer: 4 of 6 cells inside the published band (both bge/arxiv,
  MiniLM/arxiv, MiniLM/stackexchange), 2 of 6 outside (both e5 cells) --
  plus bge/stackexchange OUTSIDE by a narrow margin, discussed above.
- Truncation (real, from the pod's own stdout, not the stale local
  default the render tool read): arxiv 0.8%/35.7%/0.8%
  (bge/MiniLM/e5), stackexchange 0.0%/0.1%/0.0%. MiniLM flagged as a
  confound on arxiv; nothing flagged on stackexchange.
- Elapsed: ~34 minutes create-to-terminate. Cost estimate ~$0.41 at
  $0.72/hr (not yet the billed figure).

## Verification

Passed: the log's own two checkpoints (probe accepted, both corpora
loaded at full count); the `crispness_reading` shape present in every
cell of the fetched JSON; `corpora/036-render-ordering.py` run against
the real fetched results, its own computed VERDICT matching this
report's independent reading of the same JSON; the real truncation
numbers cross-checked against the render tool's (stale) ones and the
discrepancy traced to its cause rather than left unexplained.

Not verified: the exact billed cost (RunPod's own accounting, not
available from this session's own estimate).

## Observed, not done

- `036-truncation-per-model.py` writes its JSON result to
  `tasks/scratch/036-truncation-results.json`, a path outside
  `run_036_models.sh`'s own `$OUT_DIR`, so it is never packed into
  `036-models.tgz` -- only its stdout capture (`036-truncation-full.txt`)
  survives the fetch. `corpora/036-render-ordering.py` then silently reads
  whatever stale copy happens to be on the local laptop instead, with no
  warning that the file it opened predates this run. Not fixed here:
  flagged as a real, if narrow, instance of the same "different route"
  shape task 072's finding is about (the render tool's default path is
  never the one that has this run's own data unless someone remembers to
  point `TRUNC` at the freshly-fetched receipt), left for whoever next
  touches these scripts.

## Repo now contains

- `tasks/073-036-full-size-ordering-result.report.md` (new). No code
  changed.
- `tasks/scratch/036-session-log/036-models/` (fetched receipts,
  gitignored, not tracked -- `036-ordering-results-full.json`,
  `036-truncation-full.txt`, `036-price.json`).

## Blocked on developer

None. This is a completed measurement, reported.
