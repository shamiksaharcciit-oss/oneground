# Task 007 — The package, and `oneground characterize`

## Expected repo state
Task 006c committed; tree clean. Report what `oneground/` currently
contains (pod/, fixture_verify, tests) before restructuring.

## Why
Everything measured so far lives in `corpora/build_fixture.py`. This task
turns it into the product: a package a user installs and points at their
own vectors, producing the same receipt-shaped output the fixture has —
`characterization.json`, `build_info.json`, `MANIFEST.sha256`. The fixture
builder becomes a thin caller of the package, and byte-identical smoke
receipts prove nothing moved.

## Do
1. **Package layout** (installable, `pip install -e .` via `pyproject.toml`;
   pin build backend; console script `oneground`):
       oneground/
         __init__.py            version
         cli.py                 `oneground <characterize|fixture|pod>`
         intake/                requirements.yaml loading + validation
         sample/                loading vectors (.npy/.parquet) or text (.jsonl),
                                stratified sampling, holdout of queries
         embed/                 pinned-model embedding, weight hashing, device
         truth/                 exact k-NN ground truth
         measures/              lid.py, crispness.py (k-means + ratios),
                                skew.py, ambiguity.py, drift.py
         receipts/              stable JSON writer, MANIFEST (LF-pinned),
                                receipt/declared kinds, build_info
         fixture/               verify (moved from fixture_verify.py), build
                                (the builder's orchestration, calling the above)
         pod/                   unchanged
   Move `corpora/build_fixture.py`'s functions into these modules
   **unchanged in logic**; `corpora/build_fixture.py` stays as a thin
   wrapper calling `oneground.fixture.build` so existing docs and the pod
   run script keep working. Same for `export_ground_view.py` (its
   recomputation becomes `oneground.measures` calls).
2. **Regression proof.** Rebuild the smoke fixture through the refactored
   code (`SKIP_PROJECTION=1`). All six receipt artifacts must be
   byte-identical to the committed smoke fixture (`git diff` empty for
   them). This is the acceptance gate for the refactor; if any byte moves,
   the refactor changed logic — find it, don't re-baseline.
3. **`oneground characterize <requirements.yaml>`** — Tier 1 only in this
   task:
   - input per `requirements.example.yaml` (commit it as
     `requirements.example.yaml` at repo root; it is the schema by example):
     `corpus.sample.vectors.path` (+ optional ids, metadata parquet with
     `timestamp_field`, `category_field`), `corpus.sample.queries.path`
     (vectors or text), `run.seed`, `target_sample_size`.
   - text input (`corpus.sample.text`) is supported through the same embed
     module; if `model` is absent, refuse with a message naming the field.
   - output to `run.workdir`: `characterization.json` (measurement only),
     `build_info.json` (declared), `MANIFEST.sha256`, plus
     `sample_ids.json` (which input rows were used) and `queries_ids.json`.
   - the five measures with their spec definitions (centroid count 256,
     seeds from `run.seed`, crispness 1.20, ambiguity 1.10). Drift only if
     `timestamp_field` given, else `"drift": "couldnt_check: no timestamp_field"`.
     Ambiguity only if ≥ 50 queries, else couldn't-check naming the count.
   - `build_info.json` records: library versions incl. torch (as 003c),
     device, cuda device, python, platform, input file digests, the
     requirements file digest, and `kind` per section.
   - a plain-text summary at the end, same shape as the fixture builder's,
     and never the phrase "reproduced" (nothing is being reproduced here).
4. **Prove it on the fixture.** Write `requirements.arxiv-150k.yaml`
   pointing at the release asset extracted to a path outside the repo
   (`~/oneground-assets/arxiv-150k\` — developer extracts the
   large tarball there; say so under "Blocked on developer" if absent, and
   fall back to running against the smoke fixture's vectors/queries).
   Run `oneground characterize` on it. The five values must match the
   fixture's published values within the spec tolerances — this is the
   first time the product path and the fixture path are compared.
   Report both columns.
5. **`oneground fixture verify`** moves under the new CLI; keep the old
   invocation working via a shim for one release, with a deprecation line.
6. Tests: unit tests per measure on tiny synthetic inputs with known
   answers (e.g. crispness of two well-separated blobs ≈ 1.0, of one
   isotropic blob ≈ 0.0); an end-to-end `characterize` test on a 2k
   synthetic `.npy`; the existing 73 keep passing.
7. `README.md` at repo root: what oneground is (three sentences in the
   product page's voice), install, the one `characterize` command with
   the example file, the hero thumbnail (`docs/img/ground_thumbnail.png`),
   and a "what exists today / what is planned" split that matches the
   charter. No claims beyond what this task delivers.

## Acceptance
- `pip install -e .` works; `oneground --help` lists the three commands.
- Smoke rebuild through the package: six receipts byte-identical.
- `oneground characterize` on arXiv vectors reproduces the five published
  values within tolerance (or, if the asset is absent, on smoke within
  tolerance of the smoke fixture's values).
- Tests pass; README exists and overclaims nothing.

## Do not
- Change any measure's definition, seed, or tolerance. Touch arxiv-150k
  artifacts. Implement Tier 2 (declared path) — next task.
