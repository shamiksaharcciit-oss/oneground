# Task 012 — Calibration: the tool measures its own error, in public

## Setup — worktree, not the shared tree
Run in a separate worktree so commits are single-author:
`git worktree add ..\oneground-012 -b task-012 master`. Work there; the
developer merges `task-012` into master when the report is accepted.

## Expected repo state
Task 011 on master; `calibration/history.jsonl` seeded with one line
(−0.0018, Qdrant 1.19.1, pod tf8sd2usxbblsm, 2026-09-10) and a README.

## Why
Every user report will cite the calibration run it was generated under.
This task builds the harness that produces those lines: oneground
reproducing published benchmark numbers where they apply, and publishing
its own simulator-vs-engine error where it goes beyond them — on a
schedule, with contradiction blocking release.

## Do
1. **Calibration fixture** `fixtures/glove-100k.fixture.yaml` +
   build: GloVe-100 (angular) from the ANN-Benchmarks HDF5 (CC BY-SA;
   record the URL, sha256, and licence). Take the first 100,000 train
   vectors and the 10,000 test queries with their provided ground truth
   (do NOT recompute ground truth — the point is to use theirs; record
   `kind: declared` for it). Runs on the laptop; no pod.
2. **Reference curve** — `oneground calibrate curve`: single_node_hnsw at
   M=16, efConstruction=200 (ANN-Benchmarks' common hnswlib config),
   efSearch ∈ {10, 20, 40, 80, 120, 200, 400}; recall@10 per point.
   Compare against the published hnswlib GloVe-100 curve: download the
   ANN-Benchmarks results file for that algorithm/dataset, record its
   sha256, and store the reference points in the fixture as declared.
   Tolerance per point: 0.02 (state why: implementation and build-order
   noise between faiss HNSW and hnswlib). Outcome per point:
   verified / contradicted / couldnt_check (missing reference point).
3. **LID reference** — TwoNN on the same 100k, compared against the
   published value if one exists in the literature for GloVe-100
   (search; cite; if none is found, record couldnt_check: no reference,
   not a made-up number).
4. **Simulator-vs-engine** — `oneground calibrate engine --engine qdrant`
   on arxiv-smoke locally (Docker) and, when `ONEGROUND_QDRANT_URL` is
   set, on any workdir: simulated recall@10 for the matched
   configuration minus measured; append a history line. The arXiv line
   from 011 is already there; this makes the mechanism repeatable.
5. **`calibration/history.jsonl`** schema (one line per check per run):
   `date, check, dataset, engine, engine_version, config, measured,
   reference, deviation, tolerance, outcome, environment, pins_sha256
   (digest of requirements.txt), oneground_version`. Never edited by
   hand; the harness appends; `oneground calibrate show` renders the
   history as a table and the latest outcome per check.
6. **CI** `.github/workflows/calibration.yml`: (a) on every change to
   `requirements.txt` or any adapter's pinned engine version → run the
   full suite; (b) weekly (Monday 06:00 UTC) against current pins;
   (c) monthly, a second job against `qdrant:latest`, labelled advisory
   in the history (`outcome_scope: advisory`) and never blocking.
   Any `contradicted` on (a) or (b) fails the workflow and opens an
   issue with the history line in the body. `couldnt_check` never fails
   the workflow; it appears in the history as a gap. The bot commits the
   appended lines to a `calibration` branch that master merges from, so
   the harness never writes to master directly.
7. **Docs** `docs/VALIDATION.md`: the three layers (metrics against
   published definitions, simulator against engines, load methodology
   against VectorDBBench — the last documented as future with the case
   named), which measures are validated by reference and which by
   prediction (crispness, ambiguity, drift), the cadence, and what a
   reader can re-run. Link from README.
8. **Report wiring**: `oneground report` footer cites the latest
   history line for the engine/family it verified, or "no calibration
   line for <engine>" — never silent.

## Acceptance
- GloVe curve: all seven points verified within 0.02 (or the
  contradiction reported with the decomposition — a real disagreement is
  a finding, not a reason to widen tolerance).
- `history.jsonl` has the GloVe lines and the smoke engine line; `show`
  renders them.
- Workflow file validates (`act` or a dry run); the three triggers are
  distinct jobs.
- VALIDATION.md exists and names the VectorDBBench case as not yet done.

## Do not
- Widen any tolerance to pass. Recompute ANN-Benchmarks ground truth.
  Create a pod. Touch arxiv-150k artifacts.
