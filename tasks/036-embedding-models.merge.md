# Merge report: task-036 → main

On `main` at `215fd94`, pushed. **Suite: 1396 passed, 40 skipped, 1 failed** —
the failure is pre-existing, is now diagnosed, and is not a code defect at all.

## What landed

- `oneground/embed/compare.py` — the three registers, enforced by
  `ComparisonRefused` rather than by a caption. Recall in the comparable block
  raises; geometry hidden under `per_model` raises; an **unclassified** measure
  raises, because defaulting to comparable is how the false table gets built.
- `oneground/embed/registry.py` — model resolution reading `dimension` and
  `max_seq_length` **from the model**, eager across every listed model before
  any of them embeds, and cost projected in **tokens** measured with each
  model's own tokenizer on the corpus's real text.
- `oneground/embed/multimodel.py` — one characterization per model, with
  `characterize.run` deliberately unmodified.
- `intake` accepting `models:`, with its refusals.
- `docs/EMBEDDINGS.md`, and `docs/MODELS.md`'s name collision resolved by
  admitting it.
- `sessions/036-models.yaml` and `requirements.arxiv-150k.models.yaml` — the
  full-size run, priced and **unspent**.
- 29 tests.

## The standing rule this merge produced

> **A task whose machinery is finished and reported merges on green, not at a
> convenient moment.**

Not a preference. The cost below is what the delay bought, and it is the
second time — 044b is the second task to work around machinery that was
already complete, tested and reported.

The rule's teeth are in what "finished and reported" means: if the checks are
green and the report is written, the branch is not a work in progress, it is
**unmerged finished work**, and every task started after it pays for the
delay without knowing it is paying.

## Why this merge was overdue, and what it cost

**Task 044b had to route around finished work.** Its measurement script needed
a resolved model and called `oneground.embed.load_model` directly, because
`embed.registry` was on a branch. That is the second task working around
machinery that was complete, tested and reported.

Concretely, 044b would not have needed to:

- call `load_model(name, device="cpu", max_seq_length=512)` and pass 512 by
  hand. `registry.resolve` reads the limit **from the model** — which is
  exactly the fact 036 found mattered, since MiniLM declares 256 and not 512.
  Passing a hard-coded 512 is the defect 036 documented, committed by 036's
  own successor because 036's fix was unavailable.
- reach for `model.get_sentence_embedding_dimension()` and carry the
  deprecation warning with it; `ResolvedModel.dimension` is the resolved value.
- skip the cost projection entirely. `registry.probe_rate` and `project_cost`
  would have priced the run before it started, which is what they exist for,
  and the run instead took 25 minutes with no estimate in front of anyone.

None of that produced a wrong number. It produced a second copy of a solved
problem, written by the person who had just solved it.

## The failure this merged onto, now diagnosed

`oneground/lab/test_evidence.py::test_every_couldnt_check_claim_carries_a_remedy`,
on `runs/arxiv-150k-via-characterize`.

Previously established: it reproduces with 044's changes stashed, and 044
writes into no artifact a claim is built from. What is new here is **why it
still fails after the interface stream fixed it**:

| | |
|---|---|
| the fix | `951450f`, 23 September — `verdict.py` now sets `couldnt_check_kind`, 6 references |
| the artifact under test | `runs/arxiv-150k-via-characterize/report.json`, last written **14 September** |

**The code is repaired and the stored artifact predates the repair by nine
days.** The test reads claims out of a `report.json` on disk; fixing the writer
does not rewrite files already written. So this is not a failing check of
working code — it is a check of an artifact produced by code that no longer
exists.

That is the third consequence of the thing already recorded in the 045
addition: **the test has no tracked case**, so it tests whatever happens to be
on the machine. Here it is testing a nine-day-old file against code fixed
today, on the one machine that has the file. A fresh clone skips it entirely.

Not fixed here. Regenerating that workdir would clear it, and that workdir is
`test_evidence`'s `TIER1` subject, so regenerating it is a change to what
several other tests read — which belongs to whoever owns the tracked-case
question, not to a merge report.

## Verification

| check | result |
|---|---|
| Full suite | 1396 passed, 40 skipped, 1 failed (above) |
| 036's machinery present after the rebase | **PASS** — `registry.py`, `compare.py`, `multimodel.py`, `EMBEDDINGS.md`, the session spec and the report all verified on the tree |
| 044's machinery still present | **PASS** — `ratio_distribution`, `reading` |
| Published bytes | **PASS** — `git status fixtures/ site/` empty |

**One thing to record about the history.** `git pull --rebase` flattened the
merge commit into linear history rather than preserving it. The content was
verified file by file afterwards and is complete; the shape of the history is
linear where a merge commit was intended. Said rather than left for someone to
notice in the graph.

## Blocked on developer

Nothing. The pod session `sessions/036-models.yaml` remains **unspent and
correct**, and the order of work recorded in 036's report stands: 044c on the
centroid count, the filings corpus re-chunked in subword tokens, then the
full-size run settles the pair and lets filings join.
