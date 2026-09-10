# Report: 007-package-characterize

## Repo state expected vs found

| Expected | Found |
|---|---|
| task 006c committed | yes — `3ba1f6d task 006c: price against the cloud bought, true-price check, watchdogs` |
| tree clean | yes, apart from the untracked brief |
| `requirements.example.yaml` at the repo root | **already present** (6,006 bytes, committed). The brief says to commit it; it was there, so it was read as the schema and left untouched. |
| the release asset extracted | yes — see below |

### `oneground/` before restructuring

    oneground/
      README.md
      __init__.py            (marker, added in task 006)
      fixture_verify.py      239 lines
      test_fixture_verify.py 11 tests
      pod/                   9 modules, 62 tests

That is the whole of it: the verifier, the pod helper, and a marker module.
Every measurement in the project lived in `corpora/build_fixture.py` (677
lines) and `corpora/export_ground_view.py` (381).

### The release asset — exact path

    ~/oneground-assets/arxiv-150k\
        vectors.npy         460,800,128 bytes   (150000, 768) float32
        queries.npy           6,144,128 bytes   (2000, 768) float32
        sample.jsonl.zst     49,920,799 bytes

Flat in that directory, not under a `fixtures/arxiv-150k/` prefix as the
tarball stores them.

**It is build 3, confirmed two independent ways.** The file digests match
`fixtures/arxiv-150k/MANIFEST.sha256` exactly (`141a9220…`, `dbed194a…`,
`404cb92e…`), and the *array* digests match the spec's published
`embedding.vectors_sha256` (`cb973a94…`) and `queries.queries_sha256`
(`16e0f488…`).

Worth stating because the first check looked like a failure: the file digest of
`vectors.npy` does **not** equal the spec's published value, and that is
correct. The spec publishes array digests for `vectors`/`queries`/
`ground_truth` and file digests everywhere else; `.npy` files carry a header
that the file digest covers and the array digest does not. `sha256_array` is
now documented in `oneground/receipts/` with that trap named, because it
briefly read as a corrupt asset.

## What was done

All seven steps.

### 1. Package layout

`pyproject.toml` with a pinned build backend (`setuptools==80.9.0`,
`wheel==0.45.1`), a `oneground` console script, and pinned runtime
dependencies. Optional extras keep torch off a vectors-only install:
`[embed]`, `[view]`, `[test]`.

    oneground/
      __init__.py        version
      cli.py             oneground <characterize|fixture|pod>
      intake/            requirements.yaml loading + validation
      sample/            loaders.py (npy/parquet/jsonl, subsample)
                         arxiv.py (the fixture's stratified sampling)
      embed/             pinned-model embedding, weight hashing
      truth/             exact k-NN
      measures/          lid, crispness, skew, ambiguity, drift
      receipts/          stable JSON, MANIFEST (LF-pinned), build_info
      fixture/           build.py, verify.py, reference.py
      pod/               unchanged
      characterize.py    the Tier-1 command

Every function moved **unchanged in logic**. `corpora/build_fixture.py` is now
a 60-line wrapper that calls `oneground.fixture.build` and re-exports the names
`corpora/export_ground_view.py` loads from it by path (`kmeans`,
`centroid_dists`, `one_region_exact_recall`, `sha256_file`, `round_floats`,
`write_json_stable`), so that module keeps working untouched.

### 2. Regression proof — the acceptance gate

The smoke fixture was rebuilt end to end through the refactored package
(`--skip-projection`) into a scratch directory, and every receipt compared to
the committed one. Result in Measurements: **all six byte-identical.**

### 3. `oneground characterize`

Reads a Tier-1 requirements file, measures the five values, writes
`characterization.json`, `sample_ids.json`, `queries_ids.json`,
`build_info.json` and `MANIFEST.sha256`, and prints a plain-text summary.

`build_info.json` records library versions including torch (as 003c), device,
CUDA device, python, platform, a digest for every input file, the requirements
file's own digest, and a `kind` map marking which outputs are receipts and
which are declared.

couldn't-check is reported, never filled in:

- `drift` without `metadata.timestamp_field` →
  `"couldnt_check: no timestamp_field"`
- `ambiguous_query_rate` below `queries.count_min` → names both counts
- Tier 2 (`corpus.declared`) → refused as not implemented, by name

The summary never contains the word "reproduced", and a test asserts that
against the real output rather than trusting the intention.

### 4. Proved on the fixture

`requirements.arxiv-150k.yaml` points at the release asset. Run, and the five
values compared against the fixture's published values. Both columns in
Measurements. **6/6 within tolerance**, and then a sharper comparison that the
brief did not ask for but that this one needed — see below.

### 5. `fixture verify` moved, old path shimmed

Now `oneground fixture verify <id>`. `oneground/fixture_verify.py` remains as a
deprecation shim printing one line to stderr, because that exact path is
invoked by `corpora/run_arxiv_150k.sh`, `POD_SETUP.md` and three task reports.
The run script itself was repointed at `python -m oneground.cli fixture verify`
so a pod build does not ride a deprecated path.

### 6. Tests

26 new (12 measure unit tests, 14 end-to-end/intake), and the existing 73 all
still pass. **99 under pytest.**

### 7. `README.md`

Three sentences in the product voice, install, the one `characterize` command
with the example file, the hero thumbnail, and an explicit "what exists today /
what is planned" split. Everything under "planned" is marked as not
implemented.

### Deviations

- **A bug I wrote and then fixed before shipping.** My first `characterize`
  drift block split queries with `timestamps[:len(queries)]` — the *first
  n_queries corpus* timestamps, not the queries' own. It would have produced a
  confident, wrong drift number. Fixed by requiring a separate
  `queries.metadata.timestamp_field`, and reporting couldn't-check by name when
  it is absent. Recording it because it nearly became a published measurement.
- **Reference results live in `fixture/reference.py`.** The brief's layout has
  no home for `ref_single_node` / `ref_semantic_sharded`. They are the
  *fixture's* reference results, not yet a runnable simulator family, and Phase
  2's `models/semantic_sharded/` is where the sweepable version belongs.
- **`.gitignore` gained `*.egg-info/` and `runs/`.** Both are produced by this
  brief's own acceptance criteria — `pip install -e .` writes the first, and
  `oneground characterize` writes the second (1.4 MB for the arXiv run). Not in
  the brief's step list; leaving them unignored would have committed them.
- **`base_meta.parquet` / `queries_meta.parquet` were derived** into the asset
  directory by `tasks/scratch/007-arxiv-metadata.py`. The fixture keeps
  `update_date` inside `sample.jsonl.zst`; the product path reads a columnar
  sidecar, which is what a user would actually have. It is a format conversion
  of one column, not a recomputed measurement — and the row counts it produces
  (965 before / 1035 after the 2019 cutoff) match the fixture's published
  `n_before`/`n_after` exactly, which is what confirms the rows line up.
- **A test expectation of mine was wrong** and I corrected the test, not the
  code — see Measurements.

## Measurements

### The acceptance gate: smoke rebuild through the package

Rebuilt with `corpora/build_fixture.py --spec fixtures/arxiv-smoke.fixture.yaml
--source tasks/scratch/001-synthetic-source.json --skip-projection`, into a
scratch directory so the committed fixture was never at risk.

| artifact | committed | rebuilt | |
|---|---|---|---|
| `sample.jsonl.zst` | `b6383e22…` | `b6383e22…` | **identical** |
| `vectors.npy` | `d9f44ded…` | `d9f44ded…` | **identical** |
| `queries.npy` | `2359ce71…` | `2359ce71…` | **identical** |
| `query_ids.json` | `0081604b…` | `0081604b…` | **identical** |
| `ground_truth.npy` | `13919bb5…` | `13919bb5…` | **identical** |
| `characterization.json` | `07b576e2…` | `07b576e2…` | **identical** |
| `build_info.json` | `fa6168a5…` | `56f17aee…` | differs — **declared**, carries the timestamp and host |

**All six receipts byte-identical.** The refactor moved 1,058 lines across
eleven modules and changed no computation.

`build_info.json` differing is the correct outcome, not a near-miss: it is the
declared artifact, and it holds `built_at` and the platform string.

### The product path against the fixture's published values

`oneground characterize requirements.arxiv-150k.yaml`, 150,000 vectors, 1.2
minutes on this laptop.

| value | fixture (published) | characterize | delta | tolerance | |
|---|---|---|---|---|---|
| `intrinsic_dimensionality` | 32.55 | 32.553257 | 0.00326 | 0.5 | OK |
| `boundary_crispness` | 0.036 | 0.036247 | 0.00025 | 0.02 | OK |
| `ambiguous_query_rate` | 0.891 | 0.8915 | 0.00050 | 0.02 | OK |
| `skew_top10_share` | 0.075 | 0.0754 | 0.00040 | 0.02 | OK |
| `drift.value_before` | 0.522 | 0.523212 | 0.00121 | 0.02 | OK |
| `drift.value_after` | 0.549 | 0.551401 | 0.00240 | 0.02 | OK |

**6/6 within tolerance**, the largest at 12% of its allowance.
`drift_n_before`/`drift_n_after` are 965/1035, matching the fixture exactly.

### Against build 3's own full-precision values

The published values are rounded, so the comparison above is coarse. Against
`fixtures/arxiv-150k/characterization.json` directly:

| value | build 3 | characterize | delta |
|---|---|---|---|
| `intrinsic_dimensionality` | 32.553257 | 32.553257 | **0** |
| `ambiguous_query_rate` | 0.8915 | 0.8915 | **0** |
| `skew_top10_share` | 0.0754 | 0.0754 | **0** |
| `boundary_crispness` | 0.036273 | 0.036247 | 0.000026 |
| `drift_before` | 0.522383 | 0.523212 | 0.000829 |
| `drift_after` | 0.548792 | 0.551401 | 0.002609 |

Three exact, three slightly off. That is interesting rather than reassuring,
because **this comparison confounds two variables**: the code path (fixture
builder vs `characterize`) and the environment (build 3 ran on a Linux pod,
this ran on a Windows laptop).

### Isolating the two — the measurement that actually answers the brief

`tasks/scratch/007-isolate-paths.py` runs `oneground.fixture.build.characterize`
**on this machine, over the same release-asset vectors**, and diffs it against
the `characterize` run:

| value | fixture path (here) | characterize (here) | delta |
|---|---|---|---|
| `intrinsic_dimensionality` | 32.553257 | 32.553257 | **0.000000000** |
| `boundary_crispness` | 0.036247 | 0.036247 | **0.000000000** |
| `ambiguous_query_rate` | 0.8915 | 0.8915 | **0.000000000** |
| `skew_top10_share` | 0.0754 | 0.0754 | **0.000000000** |
| `drift_before` | 0.523212 | 0.523212 | **0.000000000** |
| `drift_after` | 0.551401 | 0.551401 | **0.000000000** |

**Bit-identical on all six.** So:

- the product path and the fixture path are the same computation, which is what
  the brief was asking to establish;
- every difference against build 3 is **environmental**, not a path difference.

The size of the environmental effect is worth recording. `boundary_crispness`
moves by 2.6e-5, which over 150,000 vectors is **about four vectors** crossing
the 1.20 ratio boundary — a handful of float ulps in the k-means centroids,
from a different BLAS. `ambiguous_query_rate` and `skew_top10_share` do not
move at all, because 2,000 queries and a 4-decimal share are too coarse to show
four flipped vectors. This is the same "values agree, bytes do not" result
tasks 003b and 006b found, now measured on a fourth axis.

### Tests

| suite | result |
|---|---|
| `pytest oneground/ -m "not live"` | **99 passed, 1 deselected** |
| `python oneground/measures/test_measures.py` | 12 passed |
| `python oneground/test_characterize.py` | 14 passed |
| `python oneground/pod/test_pod.py` | 62 passed, 1 skipped |
| `python oneground/fixture/test_verify.py` | 11 passed |

26 new tests. The measure tests use synthetic geometry with known answers, and
say so in every name:

- crispness of two separated blobs 0.99+, of one isotropic cloud 0.23; the
  ratio test pinned at exactly 1.20 (`>` is strict) and 1.10 (`<=` is inclusive)
- LID recovers ~4 for a 4-dimensional plane embedded in 768-space, and
  increases monotonically with true dimensionality
- skew of 256 equal regions is exactly 10/256
- recall counts `-1` padding as a miss

### A test expectation of mine that was wrong

`test_values_are_in_range…` asserted crispness > 0.5 for "three well-separated
blobs". It measured **0.23**. The code was right and my assertion was not: the
definition fixes **256** centroids, so 2,000 points in 3 blobs get cut into ~85
sub-regions per blob and most points land near a *sub-region* boundary.

The test now asserts the property that is actually true and actually
meaningful: fitting 3 centroids to the same data gives 0.9+, and
over-partitioning strictly lowers crispness. That is the same effect that makes
arxiv-150k's 0.036 mean what it does, so the test now teaches the measure
rather than guessing at a number.

### Sizes

    oneground/receipts/__init__.py     172      oneground/characterize.py     ~340
    oneground/measures/  (5 files)     ~300     oneground/cli.py              ~110
    oneground/sample/    (3 files)     ~330     oneground/intake/__init__.py  ~175
    oneground/fixture/build.py         ~290     oneground/fixture/reference.py ~105
    oneground/embed/__init__.py         ~70     oneground/truth/__init__.py    ~25
    tests added                        ~640

    corpora/build_fixture.py    677 -> 60 lines (thin wrapper)

## Verification

**Passed**

- `pip install -e .` succeeds; `oneground --help` lists **characterize,
  fixture, pod**; the console script works from the venv's Scripts directory.
- Smoke rebuild through the package: **six receipts byte-identical**.
- `oneground characterize` on the arXiv release asset: **6/6 values within the
  spec's tolerances**.
- Product path and fixture path are **bit-identical on the same machine** —
  all six values, delta exactly zero.
- The product path's `MANIFEST.sha256` verifies under the same verifier the
  fixture uses (a test recomputes every digest it writes).
- couldn't-check is reported and never filled in: drift without a timestamp
  field, ambiguity below `count_min` (naming both counts), Tier 2 as not
  implemented.
- The summary never says "reproduced" — asserted against the real output.
- Intake refuses and names the field: `corpus.sample.text.model`,
  `corpus.sample`, `corpus.sample.queries.path`, `run.seed`, both-vectors-and-
  text.
- 99 tests pass; all four no-runner entry points work.
- `corpora/export_ground_view.py` is untouched and still resolves every name it
  loads from `build_fixture.py`.
- Old verifier path still works, with a deprecation line.
- **`fixtures/arxiv-150k/` untouched** — `git status --porcelain fixtures/` is
  empty.

**Failed**

Nothing at the end. Two things failed during the work and both are written up:
my own drift-query-timestamp bug, and a wrong test expectation.

**Couldn't check**

- **Whether the fixture *builder* end-to-end still produces a byte-identical
  arxiv-150k.** The gate was run on the smoke fixture, as the brief specifies.
  The 150k path differs only in scale and in `--skip-projection`, but that is
  reasoning, not a measurement, and a canonical rebuild is a 3-hour pod run.
- **The text-input path end to end on real text.** `corpus.sample.text` is
  implemented and its refusal-without-a-model is tested, but no run in this
  task embedded text — the arXiv comparison used the released vectors, and the
  synthetic tests use `.npy`. The embed module is the same one the fixture
  builder uses, which is evidence, not proof.
- **`.parquet` vector loading.** Implemented and code-reviewed, exercised only
  for metadata; no test loads vectors from parquet.
- **Whether `pip install -e .` works from a clean environment.** It was run in
  the existing `.venv`, which already had every pinned dependency. A fresh
  resolve could still surface a conflict.
- **UMAP/projection through the package.** `--skip-projection` was used for the
  regression run, so `project()` moved without being executed.

## Observed, not done

- **`oneground/README.md` overclaims.** It says the package "simulates
  retrieval architectures … verifies finalists … produces a decision", in the
  present tense, for three things that do not exist. The root `README.md` this
  task added has the honest split; that file now contradicts it. The brief
  named only the root README.
- **`sample_ids.json` is 1.4 MB for a 150k run** — one id per row, as JSON.
  It is the receipt that says which rows were measured, so it has to exist, but
  for a full-corpus run where no subsampling happened it records the identity
  permutation at 9 bytes per row. A `"range"` form when `len(idx) == n_full`
  would say the same thing in one line.
- **`characterize` recomputes exact ground truth solely for drift.** For the
  150k run that is 2,000 x 150,000 and it is thrown away afterwards. The
  fixture path already has `ground_truth.npy` on disk; the product path has no
  way to be handed one.
- **`corpora/export_ground_view.py` still loads `build_fixture.py` by file
  path** through `importlib`, rather than importing the package. It works
  because the wrapper re-exports every name, but it is now an indirection
  through a deprecated file. The brief said its recomputation "becomes
  `oneground.measures` calls"; I left the module untouched because rewriting it
  risks the ground-view assertions that guard the hero image, and nothing in
  this task exercises them.
- **`requirements.txt` and `pyproject.toml` now both pin dependencies**, with
  different scopes: the former is the canonical-build closure, the latter the
  installable subset. They agree today and nothing checks that they stay
  agreeing.
- **The drift cutoff defaults to the median timestamp** when
  `timestamp_cutoff` is absent. That is a reasonable generalisation of the
  fixture's fixed 2019-01-01, but it is a *new* definition choice that no
  fixture pins, and two runs over a growing corpus would use different cutoffs.
- **`run.mode` (`auto`/`measure`/`declare`) is parsed and ignored.** With only
  Tier 1 implemented there is nothing for it to select.
- **`category_field` is read and unused** — it colours the ground view, which
  this task does not produce.
- **No `py.typed` file** although `pyproject.toml` declares it as package data.
- **`smoke-small.tgz` and `oneground.code-workspace`** are unchanged from 006b.

## Repo now contains

New:

    pyproject.toml
    README.md
    requirements.arxiv-150k.yaml
    oneground/cli.py
    oneground/characterize.py
    oneground/test_characterize.py
    oneground/fixture_verify.py            (deprecation shim)
    oneground/intake/__init__.py
    oneground/sample/{__init__,arxiv,loaders}.py
    oneground/embed/__init__.py
    oneground/truth/__init__.py
    oneground/measures/{__init__,lid,crispness,ambiguity,skew,drift}.py
    oneground/measures/test_measures.py
    oneground/receipts/__init__.py
    oneground/fixture/{__init__,build,reference}.py
    tasks/007-package-characterize.report.md
    tasks/scratch/007-{arxiv-metadata,compare,isolate-paths}.py

Moved:

    oneground/fixture_verify.py       -> oneground/fixture/verify.py
    oneground/test_fixture_verify.py  -> oneground/fixture/test_verify.py

Modified:

    corpora/build_fixture.py   677 -> 60 lines, a wrapper that re-exports
    corpora/run_arxiv_150k.sh  verify step now calls the package CLI
    oneground/__init__.py      version + what exists today
    .gitignore                 +*.egg-info/, +runs/

Outside the repo, in the asset directory:

    ~/oneground-assets/arxiv-150k/base_meta.parquet
    ~/oneground-assets/arxiv-150k/queries_meta.parquet

Unchanged: `fixtures/` entirely, `corpora/export_ground_view.py`,
`corpora/render_ground.py`, `oneground/pod/`, `docs/`,
`requirements.example.yaml`.

### Dependencies added

None at runtime. `pyproject.toml` pins the build backend
(`setuptools==80.9.0`, `wheel==0.45.1`), which are build-time only and are not
in `requirements.txt`.

### Not committed

Nothing was committed.

## Blocked on developer

Nothing was blocked — the release asset was present and correct.

Four things to decide:

1. **`oneground/README.md` contradicts the new root README**, claiming three
   capabilities that do not exist. One paragraph; I did not touch it because
   the brief named only the root file.
2. **Whether `corpora/export_ground_view.py` should import the package**
   rather than loading the deprecated wrapper by file path. It works today and
   rewriting it touches the assertions that guard the hero image, so it wants
   its own brief.
3. **Whether `sample_ids.json` should collapse to a range** when no
   subsampling happened — 1.4 MB to say "all of them".
4. **A canonical 150k rebuild through the package** would extend the
   byte-identity proof from smoke to the real fixture. It is a ~3-hour pod run,
   and `sessions/arxiv-build.yaml` is now capped at 1 h / $1.50, so that cap
   would need revisiting first.
