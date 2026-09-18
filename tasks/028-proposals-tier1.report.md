# Report: 028-proposals-tier1

## Repo state expected vs found

**The gate first.** The brief says to branch only after `task-020`'s rebase
onto `dba2fed` has landed. `git merge-base main origin/task-020` is
`dba2fed` — the rebase is there, and `origin/task-020` now carries task 027's
commits on top of it. Proceeded.

Expected `main` at `dba2fed`: found at **`570f07d`**, which is `dba2fed` plus
one commit, `brief: 028 proposals tier 1` — the brief itself. Branched from
`main` as instructed, so `task-028` starts at `570f07d` and contains
`dba2fed`. Nothing else differs.

Expected from task 026, and found: `oneground/proposals/` with `policy.py`,
`prediction.py`, `verdict.py` and no command, no card and no model;
`docs/PROPOSALS.md` at 182 lines; the 019 `Claim` renderer in
`oneground/report/claims.py` with its grep-guard in `report/test_claims.py`;
`simulate` citing a workdir's `prediction.json` by sha256 at the start of a
run.

Expected a real arXiv workdir: found `runs/arxiv-150k-via-characterize`,
150,000 vectors, 2,000 queries, seed 20260908, 8 measured rows, cached
`ground_truth.npy`, `build_info.json` recording the corpus digests. Two
things about it that shaped the work, both found rather than assumed:

* its `simulate_info.json` records `shard_depth: null` — it was written
  before that run-level setting was recorded, so its rows were measured under
  the family's own default;
* its `requirements_file.sha256` no longer matches
  `requirements.arxiv-150k.yaml`, which has been edited since 2026-09-09.

`main` was not touched, the tag was not touched, `site/` and `task-020` were
not touched. Every commit is on `task-028` and was pushed.

## What was done

### 1. The command

`oneground propose <workdir> --policy <file> --prediction <file>`, in
`oneground/proposals/propose.py`, guarded like every other command that
writes a canonical artifact. `--dry-run`, `--name`, `--requirements`,
`--allow-unpinned`.

It validates both files, refuses with **every problem named at once**, writes
the prediction into `<workdir>/proposals/<name>/`, measures **only the changed
configuration** through `simulate`'s own loader, ground-truth cache and
`measure_config`, judges it with 026's two-run rule against the baseline row
already in `simulate.json`, and writes the card.

The preconditions, all collected before anything runs: both files parse and
validate; the workdir has been characterized and simulated; the baseline row
for the policy's `configuration` exists; the requirements file the baseline
run recorded is readable and still names this workdir and this seed; the
corpus files still hash to what `characterize` recorded; the pinned libraries
match the ones the baseline row was measured under; and the proposal's
directory does not already hold a *different* prediction.

### 2. The baseline is not re-run

The workdir's row is cited by two digests — the file's and the row's own
canonical JSON — and both go into `prediction.json` before the run. A row
that has moved since is a refusal naming what to run, not a silent
comparison. `propose_info.json` records `measured: [<changed>]` and
`not_measured: [<baseline>]` with the reason.

**The run-level settings have to match too**, which is the part the arXiv
workdir made visible. A proposal measures under the `shard_depth` the
baseline row was measured under: the value `simulate_info.json` records, or —
when it records none, as this workdir does — the family's own default.
`simulate.measure_config` gained a `shard_depth` argument and a
`FAMILY_DEFAULT` sentinel for exactly this. Without it the changed
configuration would have been measured at depth 100 against a baseline
measured at 30, and the delta would have been partly the setting.

### 3. The card

`card.json` and `card.html` in the proposal's directory, built in
`oneground/proposals/card.py`. Every sentence is a `Claim`, rendered by seven
new renderers in `report/claims.py` and checked by `claims.check` against the
rows it cites before the card is written — a card that fails the invariant is
not written at all. `report/test_claims.py`'s grep-guard now covers the card
modules, so a sentence about rows cannot be formatted anywhere else.

The card carries the policy in full, the prediction with its digest and
whether the run cited it, both configurations (the baseline with its digests,
when it was measured and under which library versions), the sample, the
measured result per predicted metric, the side-effect budget against its
bounds, the environment stamp, the calibration line, and one outcome.

`card.html` is rendered from the bytes of `card.json`, not from the card in
memory, so a reader with the receipt can rebuild the page and get the same
file. No network call of any kind.

### 4. Failures are cards

A prediction that did not hold produces a card with the same completeness as
one that held. A run that could not complete produces a **couldn't-check**
card naming the failure and what would settle it, with every predicted metric
as a couldn't-check row. There is no path that produces nothing. The remedy
that card names — run it again, the prediction is not rewritten — is itself
tested.

### 5. The side-effect budget

A budget row is judged on the changed row's value against its bound, by the
same band rule as an expected change. A proposal whose predicted metric moved
as promised and whose budget was breached is **did not hold**, and
`card.order_rows` puts the breach first: in the headline sentence, in the row
sentences, and in the page's table.

### 6. What a card may never say

`card.FORBIDDEN` is the list, `card.card_violations` the scan, over every
sentence and over the page. The card's own limits sentence is the one
exemption, and it says the words plainly — *it does not say the change is
good, or recommended, or that it should be deployed; it says nothing about
any other corpus; and it does not say this result would hold at full scale* —
because a scan that punished the caveat for naming what it rules out would be
answered by deleting the caveat. Every phrase has a negative control.

### 7. No model, anywhere

`test_the_proposals_package_has_no_model_no_api_call_and_no_prompt` parses
every module in the package and fails on a network import, or on a prompt
string or model-ish name outside a docstring. Docstrings are exempt for the
reason task 014's `platform.node()` guard exempts them: this file's own
docstring says "no model, no API call, no prompt", and a guard that punished
the explanation would be answered by deleting it. It has its own negative
control.

## Measurements

Everything below on this machine, `.venv\Scripts\python.exe` (Python 3.12.10;
numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0: pinned, and the guard
passed on every run), against `runs/arxiv-150k-via-characterize` — 150,000
vectors of 768 dimensions, 2,000 queries, seed 20260908, ground truth k=100
reused from the workdir's cache.

### The two proposals, end to end

| | A: `probe` 1 → 2 | B: `epsilon` 0.1 → 0.2 |
|---|---|---|
| baseline row (not re-run) | `…epsilon=0.2,probe=1]` | `…epsilon=0.1,probe=1]` |
| configuration measured | `…epsilon=0.2,probe=2]` | `…epsilon=0.2,probe=1]` |
| `recall_at_10` | 0.83785 → **0.9318**, delta **+0.0940** | 0.7755 → **0.83785**, delta **+0.0624** |
| predicted | rises by at least 0.05 | rises by at least 0.02 |
| `storage_amplification` | **3.71516**, bound at most 4.0 | **3.71516**, bound at most 3.0 |
| outcome | **held** | **did not hold** — the budget |
| build / query | 307.0 s / 12.9 s | 181.3 s / 1.1 s |
| whole command | **369.6 s** (6.2 min) | **206.9 s** (3.4 min) |
| prediction sha256 | `3e959af84837…` | `964237daafca…` |
| policy sha256 | `5f41fb9da160…` | `b0d435bbe737…` |
| baseline cited | file `e084bb68a4d3…`, row `b95f9f1e3cc5…` | file `e084bb68a4d3…`, row `44d204167127…` |

Each run measured exactly one configuration:
`propose_info.json:measured` has one entry and `not_measured` names the
baseline with its reason.

### The check I did not plan, and what it says

Both changed configurations happen to be rows the 2026-09-09 sweep also
measured, so the re-measurement can be compared against the sweep's own row
for the same configuration — a like-for-like check of whether a row measured
today can be subtracted from a row measured nine days ago:

| configuration | sweep, 2026-09-09 | this run | difference |
|---|---|---|---|
| `…epsilon=0.2,probe=1]` (B's changed row) | 0.83785 | 0.83785 | **0** |
| `…epsilon=0.2,probe=2]` (A's changed row) | 0.93185 | 0.9318 | **0.00005** |
| `storage_amplification`, both | 3.71516 | 3.71516 | 0 |

0.00005 of recall@10 over 2,000 queries is **one returned neighbour in
20,000**. I did not expect a difference at all, and say so rather than
explain it away: the k-means is seeded and shared, the family is built with
`deterministic=True`, and one configuration reproduced exactly while the
other did not. The one that moved is the one that probes two shards and
merges their candidates, which is where an ordering difference would show;
that is a hypothesis, not a measurement, and diagnosing it is not this task.

It does not touch either verdict: A's margin over its threshold is 0.0440 and
B's is 0.0424, both more than 800 times the difference, and both cards are
decided at a calibration tolerance of 0.01 which is 200 times larger.

**This check is available only because the sweep had measured both
configurations already.** A proposal whose changed configuration has never
been measured has no such comparison, and the card does not claim one.

### The run-level setting

`simulate_info.json` for this workdir records `shard_depth: null`, so both
runs measured under the family's own default, as the baseline rows were:
`card.json:configurations.changed.shard_depth` is `"family default"` with the
reason. Had the command used today's rule instead (`max(30, largest k)` =
100), the changed configuration would have been measured with more candidates
per shard than its baseline, and part of every delta above would have been
the setting rather than the policy.

### Refusals, on the real workdir

`--dry-run` on proposal A, which runs every precondition including the
460 MB corpus digest, printed the plan and wrote nothing:

```
dry run: nothing was measured and nothing was written.

  workdir            runs\arxiv-150k-via-characterize
  requirements       …\requirements.arxiv-150k.yaml
  baseline (not run) semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=1]
                     simulate.json sha256 e084bb68a4d3..., row b95f9f1e3cc5...
  would measure      semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2]
  seed               20260908
  shard_depth        family default (…simulate_info.json records no shard_depth…)
  would write        runs\…\proposals\semantic_sharded_probe-1-to-2\card.json

  expects            recall_at_10 rises by at least 0.05
  budget             storage_amplification stays_at_or_below 4.0
```

The requirements file this workdir recorded has been edited since the
baseline run (`cecd4e7655a0…` then, `3e4eb25ee496…` now). That is **not** a
refusal: what has to be unchanged is the sample, so the corpus files are
checked against the digests `characterize` recorded — `vectors.npy`
`141a922070…` and `queries.npy` `dbed194a42…`, both matching — and
`propose_info.json` records both requirements digests so a reader can see the
file moved and what was checked instead.

### Tests

| suite | result |
|---|---|
| `oneground/proposals` | **61 passed**: 31 in the new `test_propose.py` (28 functions, one of them parametrised into four cases), 30 in `test_proposals.py` (026's, with the docs-example test widened and a prediction-example test added) |
| `oneground/report` | **101 passed** (the claim renderers and the widened grep-guard) |
| `oneground/test_environment.py`, `test_cli.py` | **52 passed** (the guard surface walk sees `oneground propose`) |
| whole suite | **907 passed, 1 skipped** in 403 s (6 m 43 s) |

The skip is `oneground/pod/test_pod.py:2089`, `RUNPOD_API_KEY not set; live
test skipped`, unrelated to this task. 908 collected against 876 on
`570f07d`: the 32 tests added here (31 in `test_propose.py`, 1 in
`test_proposals.py`), none removed.

Identifier scan with everything staged, including this report:
`env.identifier_findings()` → **0 findings** over the 333 paths
`env.tracked_files()` returned. It scanned rather than skipped:
`env.checkout_root()` is not None and the scan returned a list, which is what
022e made the difference between.

### The synthetic end to end

`tasks/scratch/028-smoke.py` drives the real command over a 2,000-vector
corpus through characterize → simulate → four proposals (held, breached
budget, a run that cannot complete, and a re-run) in **15.1 s** wall clock,
measured with `Measure-Command`. It is how the loop was developed;
`test_propose.py` is the same ground, asserted.

## The two cards, in full

Both from `runs/arxiv-150k-via-characterize`, produced by the command at
`b40e15d`. The text below is `card.json:text` verbatim — the same sentences
`card.html` renders and the console printed.

### Card A — held

The two files, written by hand before anything ran:

```yaml
policy:
  family: semantic_sharded
  configuration: {centroids: 256, epsilon: 0.2, probe: 1, M: 32, efSearch: 96}
  changes:
    - param: probe
      from: 1
      to: 2
  rationale: "One probed region reaches one region's neighbours. Probe a second."
```
```yaml
expects:
  - metric: recall_at_10
    direction: rises
    by_at_least: 0.05
side_effects:
  - metric: storage_amplification
    stays_at_or_below: 4.0
```

    Policy: semantic_sharded probe from 1 to 2. Measured as
    semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2] on
    150,000 vectors and 2,000 queries of arxiv-150k-via-characterize, seed
    20260908, against exact k-NN ground truth for that sample.

    The prediction held for
    semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=2].

    recall_at_10 rises by 0.0940, from 0.8378 to 0.9318; predicted to rise by
    at least 0.05. This one held.

    Side-effect budget: storage_amplification is 3.7152 on the changed
    configuration, bounded to at most 4.0. This one held.

    The baseline was not re-run:
    semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=1] is
    the row simulate.json already held (file e084bb68a4d3, row b95f9f1e3cc5),
    measured 2026-09-09T16:47:12Z.

    Judged at calibration tolerance 0.01. There is no calibration line for
    semantic_sharded in calibration/history.jsonl, so how far this
    installation's semantic_sharded sits from published numbers has not been
    measured here.

    This card reports one run of one policy on one sample: 150,000 vectors and
    2,000 queries drawn from arxiv-150k-via-characterize, judged against exact
    k-NN ground truth for that sample. It says what the measured difference
    was. It does not say the change is good, or recommended, or that it should
    be deployed; it says nothing about any other corpus; and it does not say
    this result would hold at full scale.

### Card B — did not hold, on the side-effect budget

```yaml
policy:
  family: semantic_sharded
  configuration: {centroids: 256, epsilon: 0.1, probe: 1, M: 32, efSearch: 96}
  changes:
    - param: epsilon
      from: 0.1
      to: 0.2
  rationale: "Widen the boundary so a query near an edge still finds its neighbours."
```
```yaml
expects:
  - metric: recall_at_10
    direction: rises
    by_at_least: 0.02
side_effects:
  - metric: storage_amplification
    stays_at_or_below: 3.0
```

    Policy: semantic_sharded epsilon from 0.1 to 0.2. Measured as
    semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=1] on
    150,000 vectors and 2,000 queries of arxiv-150k-via-characterize, seed
    20260908, against exact k-NN ground truth for that sample.

    The prediction did not hold for
    semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.2,probe=1].
    storage_amplification is 3.71516, bound stays_at_or_below 3.0, tolerance
    0.01

    Side-effect budget: storage_amplification is 3.7152 on the changed
    configuration, bounded to at most 3.0. This one did not hold.

    recall_at_10 rises by 0.0624, from 0.7755 to 0.8378; predicted to rise by
    at least 0.02. This one held.

    The baseline was not re-run:
    semantic_sharded[M=32,centroids=256,efSearch=96,epsilon=0.1,probe=1] is
    the row simulate.json already held (file e084bb68a4d3, row 44d204167127),
    measured 2026-09-09T16:47:12Z.

    Judged at calibration tolerance 0.01. There is no calibration line for
    semantic_sharded in calibration/history.jsonl, so how far this
    installation's semantic_sharded sits from published numbers has not been
    measured here.

    This card reports one run of one policy on one sample: 150,000 vectors and
    2,000 queries drawn from arxiv-150k-via-characterize, judged against exact
    k-NN ground truth for that sample. It says what the measured difference
    was. It does not say the change is good, or recommended, or that it should
    be deployed; it says nothing about any other corpus; and it does not say
    this result would hold at full scale.

**B is the card the task is for.** The change did exactly what it was
predicted to do — recall@10 rose by 0.0624 against a promised 0.02 — and the
proposal did not hold, because storage went from 2.67 copies per vector to
3.72 against a budget of 3.0. The breach is the second sentence and the first
row; the recall that rose is underneath it. A card that led with the recall
would be true and would mislead.

**Neither prediction surprised me, and the reason is worth stating.** Both
were written knowing the 2026-09-09 sweep's numbers for these configurations,
so they test the machinery rather than my judgement about retrieval. What the
machinery was not told is what it went on to check: that the prediction came
first, which baseline row it was judged against, whether that row had moved,
and whether the budget survived.

**One thing the cards say that I did not arrange.** Both read *"written by an
earlier run of this proposal, unchanged"*. The predictions were written by the
first runs at 20:38 and 20:46; after those, the limits sentence was reworded,
and the final cards are re-runs. The prediction files were reused byte for
byte rather than rewritten — which is the pre-registration property, appearing
here because an ordinary editing accident exercised it rather than because a
test did.

## Verification

- **Two real cards from the arXiv workdir, one held and one not**: above, in
  full, with their policies and predictions.
- **Every card sentence passes the 019 claim invariant**: enforced, not
  checked afterwards — `build_card` calls `claims.raise_on_violation` against
  rows built from the judged rows and the two measured rows, so a card that
  does not follow from its rows is never written. Asserted again from the
  written `card.json` in `test_every_card_sentence_follows_from_its_rows`,
  with two mutants: a sentence whose outcome its rows deny, and a number
  printed for a member the claim cites differently. Both caught.
- **The forbidden claims are tested**: four phrasings — recommending,
  deploying, full scale, another corpus — each injected into a real card and
  each caught, plus a test that the limits sentence does contain such words
  and is the only thing exempt.
- **A missing baseline row refuses, naming what to run**: the refusal lists
  the rows that are there and says to add the configuration to
  `simulate.include` and run `oneground simulate`.
- **A mismatched baseline digest refuses**: the row is edited under the
  command's feet in the test, and it refuses with *the baseline moved after
  the prediction was written*, naming both digests and what to run. A
  prediction that says something different in an existing proposal directory
  refuses too, naming `--name`.
- **A budget breach produces *did not hold* with the breach named first**:
  card B above, and `test_a_breached_budget_is_did_not_hold_with_the_breach_first_synthetic`
  asserts the headline names the breached metric and that the budget sentence
  precedes the metric sentence.
- **`--dry-run` runs nothing**: measured with a `measure` that raises if
  called, and by asserting the proposal directory does not exist afterwards.
- **A failed run still writes a card**: a `MemoryError` injected into the
  measurement produces a couldn't-check card with every predicted metric as a
  couldn't-check row, the failure named, and what would settle it — and a
  second test runs that proposal again to prove the remedy works and the
  prediction is not rewritten.
- **No model, no API call, no prompt**: asserted over the package's AST,
  with a negative control.
- **The guard**: `oneground propose` is in `GUARDED_COMMANDS` by decoration,
  and `test_environment.py`'s surface walk — which derives the command list
  from the parsers — passes with it.
- **The identifier scan ran rather than skipped**: 333 tracked paths read, 0
  findings, with `env.checkout_root()` not None — the distinction task 022e
  put there. The card carries no machine identifier either, asserted by
  `test_a_card_carries_no_machine_identifier_synthetic` over `card.json` and
  `card.html`; that test found a real one while being written (the workdir
  path had reached `shard_depth_source`, fixed in `b40e15d`).
- Couldn't check: **whether the simulator itself is unchanged since the
  baseline row was measured.** The run refuses on a pinned-library difference
  and the card states the versions both rows were measured under, but
  `simulate_info.json` records no version of oneground, so "the same code"
  cannot be shown. The 0.00005 above is the only evidence either way, and it
  is one neighbour.
- Couldn't check: **anything about a second machine.** Both cards were
  produced here; no run was made on a pod.

## Observed, not done

1. **`README.md` and `docs/README.md` list the command surface and do not
   mention `propose`.** The brief named `docs/PROPOSALS.md` and that is the
   only document changed. `oneground --help` does list it, from the parser.
2. **The two policy and prediction files the acceptance runs used live in
   `tasks/scratch/`, which is `.gitignore` line 62.** Both are pasted in full
   below and both appear in `docs/PROPOSALS.md`'s worked example, so the runs
   are reproducible; but there is no tracked directory of example proposals,
   and the brief did not ask for one.
3. **A card can show the two rows were measured under the same pinned
   libraries, not under the same code.** `simulate_info.json` records library
   versions and no oneground version or commit, so "the simulator has not
   changed since the baseline row" is not checkable. This run refuses on a
   pinned-library difference and states the baseline's versions in the card;
   the stronger check needs `simulate` to record what built it.
4. **There is no calibration line for `semantic_sharded` on this
   installation**, so both cards say how far this installation's
   `semantic_sharded` sits from published numbers has not been measured here.
   That is the honest statement, and it is what `calibrate curve` would fill.
5. **Cards are written inside the workdir, which is gitignored.** Nothing
   publishes them, and the public library of cards is explicitly unsettled in
   `docs/PROPOSALS.md` §5.

## Repo now contains

    oneground/proposals/propose.py          the command: preconditions, the one measurement, the judgement
    oneground/proposals/card.py             the card, its ordering, the forbidden scan, the page
    oneground/proposals/test_propose.py     31 tests, each guard with a negative control
    oneground/proposals/prediction.py       write_prediction takes out_dir and a baseline citation
    oneground/proposals/test_proposals.py   the docs-example tests now validate every block
    oneground/report/claims.py              seven card renderers, and `did not hold` as a label
    oneground/report/test_claims.py         the grep-guard covers the card modules
    oneground/simulate/__init__.py          measure_config takes shard_depth; FAMILY_DEFAULT
    oneground/cli.py                        `oneground propose`, guarded
    docs/PROPOSALS.md                       section 5a: tier 1, writing a policy yourself
    tasks/028-proposals-tier1.report.md     this report

## Blocked on developer

Merging `task-028` into `main` after the 23rd, as the brief says. Nothing
else.
