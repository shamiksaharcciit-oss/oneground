# Task 013 — Tier 2, `status: verified`, and 011's leftovers

## Expected repo state
Master at or after `a4a579a` (T2). Tree clean. You share the tree with the
teaser stream; commit only your own paths.

## Step 1 — 011 leftovers (one commit)
- `report.json` `scope` entry says "4 constraint(s)" and omits `qps`
  while five verdicts are issued. Fix the count and the list from the
  constraints actually judged; test.
- The runner-up line ("indistinguishable on recall from …") carries the
  runner-up's overall outcome and, if not `meets`, which constraints are
  unchecked. Test.
- `test_the_real_arxiv_workdir_gives_one_option_the_measurement` reads
  gitignored `runs/`: skip with a reason naming the missing workdir when
  absent, and rename so the name says it needs a local artifact.

## Why
Tier 2 is the zero-friction entry: a user with no data yet declares what
they expect and gets the fixture analogy and capacity arithmetic — never
a verdict. And `fixture verify` finally reproduces values, not just
digests, which is what lets `arxiv-150k` say `verified` truthfully.

## Do
2. **Tier 2 intake** — `requirements.yaml` with `corpus.declared` and no
   `corpus.sample`. `oneground characterize` in declared mode produces
   `characterization.json` with every measured field as
   `couldnt_check: declared, not measured` and a `declared` block echoing
   the inputs; `build_info.json` kind declared.
3. **Fixture analogy** — `nearest_fixture: auto` matches on
   `corpus_type`, `text_length`, `topics_trend`, `time_ordered`,
   `dimension`/model family against a small table in each fixture spec
   (add `analogy:` keys to arxiv-150k and glove-100k when 012 lands; for
   now arxiv-150k). The report shows the fixture's measured surface
   labelled "analogy — measured on <fixture>, not on your corpus", every
   verdict `couldnt_check`, and the final log entry: what sample size
   would turn each into a measurement (10–20k stratified vectors, 50+
   queries, timestamps for drift).
4. **Capacity arithmetic** — from `size_now`, `dimension`, footprint per
   family (from the models' `footprint()` on a synthetic sample of the
   declared dimension): nodes needed at the memory budget, storage at
   each ε for semantic-sharded, cost via the price table with error
   bands. All labelled derived-from-declared; budget verdict still
   couldn't-check (the input is declared).
5. **`fixture verify` value reproduction** — recompute characterization
   and the two reference results from the release asset when present
   (vectors, queries), compare to published values within tolerances,
   outcome per value; `couldnt_check` when the asset is absent or a pin
   differs (compare `build_info` pins to `requirements.txt`). Run it on
   arxiv-150k with the asset at `~/oneground-assets/arxiv-150k\`.
   If every value reproduces: set `status: verified` in the spec with a
   changelog line naming the run and the environment. If any doesn't:
   report the decomposition; status stays `built`.
6. **Tier 2 end to end** — `requirements.declared.example.yaml`
   (support-tickets-like, 2.1M, 768d, trends, time-ordered) →
   characterize → report; paste the log's final entry.
7. Docs: `docs/INTAKE.md` — the two tiers, what unlocks each
   measurement, the analogy's honesty rules.

## Acceptance
- Step-1 tests pass; scope entry correct on the arXiv workdir.
- Tier 2 produces a report with zero verdicts and a correct "what would
  make this measurable" entry.
- `fixture verify arxiv-150k` reports per-value outcomes; status flipped
  only on a clean reproduction.
- Tests pass; INTAKE.md exists.

## Do not
- Emit any verdict from declared inputs. Widen a tolerance. Touch
  `site/teaser/`. Create a pod.
