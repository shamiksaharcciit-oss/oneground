# Report: 065-full-size-models-prepare

## Repo state expected vs found

Expected `sessions/036-models.yaml` (task 036) priced for the original
three-corpus, three-model run at 332.2M tokens, still unrun, and
`oneground/measures/crispness.py`'s `reading()`/distribution machinery
(tasks 044-044d) built but never wired into task 036's own tooling. Found
exactly that. This is a prepare-only task -- no pod session, no commit to
`tasks/scratch/` (gitignored, see below) -- so no branch was needed for the
scratch-script fixes; `sessions/036-models.yaml` and `corpora/
run_036_models.sh` are the two tracked files changed, on branch `task-065`.

## What was done

**First: does the spec produce the old shape, or bypass `reading()`
entirely? Bypassed it, confirmed by reading both modules against each
other.**

`tasks/scratch/036-ordering-experiment.py::measure()` called
`crispness.boundary_crispness(d)` directly -- the raw count, unchanged by
task 044 by design (`crispness.py`'s own docstring says so). It never
touched `crispness.reading()`, the function task 044 built specifically so
a near-zero count comes with why: where the 1.20 threshold sits in this
corpus's own ratio distribution, whether the count is even distinguishable
from zero, and -- at full size -- whether this embedding is reading the
threshold somewhere the measure has never been calibrated
(`against_published`'s transfer verdict). `oneground.characterize` itself
already calls `reading(d_base, with_distribution=True)` beside the
unchanged count (`characterize.py:228`); the ordering experiment never
adopted that pattern. Run as spec'd, the full-size session would have
reported exactly the same bare, collapsed e5 numbers the subsample already
showed were unreadable -- a wasted session for precisely the reason task
044 exists.

**Fixed**, mirroring `characterize.py`'s own call exactly:
`measure()` now also computes `crispness_reading = crispness.reading(d,
with_distribution=True)` and stores it beside the unchanged
`boundary_crispness`; the per-cell log line now prints the threshold's
percentile, resolvability, and transfer verdict. `036-render-ordering.py`
was updated to surface `resolvable`/`transfer` per cell (and to say plainly
when an older result has no `crispness_reading` at all, rather than silently
rendering it as fine). Verified locally, at no cost: `measure()` run against
synthetic vectors produces a valid, JSON-serialisable reading with the same
keys `characterize`'s own tests exercise; the render script was run against
the existing (old-shape) subsample results file unmodified (still renders,
correctly flags every cell as missing a reading) and against three fabricated
result files covering the `couldnt_check`-transfer, `resolvable`, and
`inside/outside-published-band` branches, all rendering without error.
**These are scratch-script fixes and are not committed** -- `tasks/scratch/`
is entirely gitignored (see the third item below for why that matters more
than usual this task) -- so they exist only in this local working tree, the
same as every other file already sitting in that directory.

**Second: what would the run settle that is not already settled.**

The arxiv-vs-stackexchange pair is confirmed the clean one: in the existing
subsample data, `stackexchange-150k` truncates 0.0% under all three models
(bge, MiniLM, e5); `arxiv-150k` truncates 1.1% under bge and e5 and 35.3%
under MiniLM -- materially lower than `sec-filings-10k`'s 86-94% under every
model. What full scale specifically adds for this pair, computed against
`crispness.distinguishable()` directly rather than estimated:

    arxiv/e5,   subsample n=3,000    n_above=2    NOT resolvable (< 5 floor)
    stackexchange/e5, subsample n=3,000  n_above=1    NOT resolvable
    arxiv/e5,   full n=150,000 (same rate)   n_above~100   resolvable, 10.0 sigma
    stackexchange/e5, full n=150,000 (same rate)  n_above~50    resolvable, 7.1 sigma

At subsample scale, e5's count-based ordering of this pair is built from two
numbers **neither of which clears `MIN_INFORMATIVE_COUNT`** -- so whatever
the render script reports as an "ordering" for e5 today is not a measured
comparison, it is noise formally indistinguishable from it. Full scale is
what makes it a comparison at all under e5; the arxiv-vs-stackexchange
directional ordering under bge (the anchor model, at 5,000-50,000 vectors)
is already independently established by task 036's own instrument check and
is not newly settled by this run. What this run settles that nothing else
has: **whether e5 and MiniLM agree with bge's ordering when their own counts
are, for the first time, statistically readable rather than couldn't-check.**

What it does **not** settle, whatever the outcome: anything about
`sec-filings-10k`'s position, for the reason below -- that corpus's problem
is not sample size and full scale does not touch it.

**Third: the filings tokenization mismatch -- confirmed, and excluded
rather than guessed at.**

`texts_filings()` calls `chunk_document(..., "structure", ...)` with no
`tokenizer=` argument. `chunk_document` (`oneground/chunk/strategies.py:491`)
then falls back to `WhitespaceTokens`, so `max_size: 512` there means 512
whitespace-delimited tokens -- not the 512 (bge/e5) or 256 (MiniLM) SUBWORD
tokens `max_seq_length` is stated in. This is a real, confirmed mismatch,
not a guess, and it is at least a candidate explanation for filings' 86-94%
truncation already measured at subsample scale (far above arxiv's or
stackexchange's).

Fixing it correctly means chunking with each model's own tokenizer -- and
that is where I stopped rather than building it: `036-ordering-experiment.
py`'s own docstring states the design invariant this experiment depends on,
"EVERY MODEL IS EMBEDDED HERE... on identical records," and per-model
chunking would make the chunk boundaries, and so the chunk count and
geometry crispness measures, differ by model. That entangles a chunking
difference with the model-geometry difference the whole experiment exists
to isolate, and resolving it (a shared reference tokenizer? per-model
chunking with the confound now structural instead of incidental? chunk in
characters?) is a design decision, not a wiring gap -- exactly the "no new
design, and if a paper does not say how, that is a finding to report"
instruction.

**Decision: `sec-filings-10k` is excluded from this session.** Implemented
as an allowlist (`ONEGROUND_036_CORPORA`, default `arxiv-150k,
stackexchange-150k`) in the experiment script, with `design["corpora"]`
recorded in the results file so the render script reports what was actually
intended rather than silently comparing against all three published values.
`run_036_models.sh` no longer checks for the filings input file and sets the
allowlist explicitly. This is stated as a recommendation with reasoning, not
a unilateral final call: re-chunking `sec-filings-10k` in subword tokens is
left as a separate task if the developer wants sec-filings measured
rigorously later.

**Re-priced.** Excluding filings removes 181.66M of the original 332.24M
tokens (`036-price.json`), leaving 150.58M. Recomputed caps:
`max_hours` 3.0 -> 2.0, `max_usd` 4.00 -> 3.00, `stall_minutes` 25 -> 15
(the longest single cell drops from filings/bge at ~72M tokens to
arxiv/bge-or-e5 at ~34.2M). `oneground pod plan sessions/036-models.yaml`
confirms the card resolves and prices; see Measurements.

**Fourth, found while checking "whatever it invokes" rather than asked for
directly, and reported because it is more serious than any of the three
questions above: this session would have failed on the pod regardless of
any of the fixes above.** `run_036_models.sh` runs two scripts under
`tasks/scratch/`, which is entirely gitignored. A pod session reaches the
pod as `git bundle create --all`, which "carries commits, not the working
tree" -- `oneground/pod/session.py`'s own `Input` docstring, which records
that session 20260909-195824 already spent four minutes of pod time
discovering exactly this for `runs/`. `oneground/pod/cli.py::
uncommitted_paths` (the pre-`up` dirty-tree refusal) explicitly excludes
gitignored paths -- "a scratch output should not block a session" -- so
nothing in the existing tooling would have caught this before billing
started: `up` would have created a pod, cloned a bundle with no
`tasks/scratch/036-ordering-experiment.py` in it, and died at that `python`
call having spent the setup time for nothing. Fixed with the mechanism this
project already built for exactly this class of bug: `sessions/036-models.
yaml` now declares `inputs:` for `036-ordering-experiment.py`,
`036-truncation-per-model.py`, and (`optional: true`) `036-price.json`,
uploaded by `scp` independent of git tracking. Confirmed the fixed local
copies resolve and exist via `Input.local_path()`.

## Measurements

- Crispness reading fix: verified locally against synthetic vectors
  (`crispness_reading` keys match `characterize.py`'s own usage; JSON-
  serialisable) and against the real subsample results file (old-shape,
  correctly flagged) and three fabricated cells covering
  couldnt_check-transfer / resolvable / inside-and-outside-band. No pod
  time spent.
- Re-priced token volume: 150,579,560 (was 332,240,840) -- recomputed from
  `036-price.json`'s own per-cell rows, filings rows excluded.
- `oneground pod plan sessions/036-models.yaml`, first call: RTX PRO 4500,
  $0.34-$0.72/hr (confirmed at $0.72/hr top of range), cost cap
  `2h x $0.72/hr = up to $1.44`, within `max_usd 3.00`. **Nothing was
  created.**
- Two further `pod plan` calls, run to get a fresh reading for this report,
  instead showed live GPU-availability volatility in EU-RO-1: the second
  found RTX PRO 6000 at $1.69-$2.09/hr (cost cap $4.18, over `max_usd`,
  refused), the third found none of the four listed cards offered at all
  (only RTX PRO 4000 and L4, neither in the spec's list). This is the same
  class of transient, real-time market fluctuation already logged elsewhere
  this project (live RunPod GPU-availability flake on
  `test_live_plan_against_the_real_api`), not a defect in the repriced
  spec -- the session's own `gpu:` list already names four alternatives for
  exactly this reason. **Re-run `oneground pod plan sessions/036-models.
  yaml` close to the developer's own `y` moment** for a current price
  before `up`.

## Verification

Passed: local sanity checks on the crispness-reading wiring (above); the
session spec loads (`oneground.pod.session.load`); `inputs` resolve to
real, existing local files; `oneground pod plan` runs, prices, and reports
"Nothing was created" on a card within cap. `py_compile` on both modified
scratch scripts. No pytest suite covers `sessions/*.yaml`, `corpora/
run_036_models.sh`, or `tasks/scratch/*` (grepped; nothing in `oneground/`
references any of the four 036 filenames), so the full check suite was not
run for this task -- there is nothing in it these changes could affect, and
the standing four-check protocol (full suite, `test_environment.py`,
`identifier_findings()`, `site/teaser/` diff) applies to `oneground/`
package changes, of which there are none this task.

Not verified, and not verifiable without spending: the probe's actual
throughput on whichever card `up` lands on, and the full-size run's real
numbers. That is what `up` and the probe inside `run_036_models.sh` are
for, not this task.

## Observed, not done

- `sec-filings-10k`'s subword re-chunking: named as a candidate separate
  task, not started. Whoever picks it up should decide the chunk-boundary
  invariant question stated above before writing code.
- `skew_top10_share`, also measured by `036-ordering-experiment.py`, has
  its own `reading()` since task 044c (`skew.py`) and was not wired in
  here: the developer's instruction was specifically about the crispness
  count that collapses under e5, and skew is not part of the ordering
  question this experiment answers (`036-render-ordering.py`'s `ordering()`
  reads only `boundary_crispness`). Flagged in case it turns out to matter
  for a future reading of this run's LID/skew columns.

## Repo now contains

- `sessions/036-models.yaml` (modified) -- two corpora not three, repriced
  caps, `inputs:` for the three `tasks/scratch/` dependencies, comment
  blocks explaining both changes.
- `corpora/run_036_models.sh` (modified) -- filings input check removed,
  `ONEGROUND_036_CORPORA` set, probe's hours estimate corrected to 150.58M
  tokens.
- `tasks/scratch/036-ordering-experiment.py`,
  `tasks/scratch/036-render-ordering.py` (modified, **not tracked** --
  gitignored; fixes exist only in this local working tree and are described
  above for whoever next touches them, since git history will not show them).
- `tasks/065-full-size-models-prepare.report.md` (new).

## Blocked on developer

The `y` at the terminal for `oneground pod up sessions/036-models.yaml`,
per the brief. Also worth a developer decision, not a blocker to `y`:
whether `sec-filings-10k`'s subword re-chunking is worth a follow-up task
now or later.
