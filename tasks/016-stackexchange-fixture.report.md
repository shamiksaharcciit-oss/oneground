# Report: 016-stackexchange-fixture

**Status: steps 1–4 complete, step 5 (the build) waiting on one `y`.**
Steps 6–9 depend on artifacts that do not exist yet. This report is written now
rather than after the build because the previous session ended in a crash and
the state it left behind was not self-describing.

## Repo state expected vs found

| Expected on resuming | Found |
|---|---|
| 014d outstanding — "add `merge_history.py`, which is not in the commit" | **Already done, and the premise is wrong.** 014d is committed as `444c250` with its report. `merge_history.py` is in the commit and always was; run #5's cause was 014c's push checking the `calibration` branch *into the working tree*, which deleted the script from disk between checkout and invocation. The 014d report states this at its head. Nothing was added this session. |
| a referenced-path test to be written | **already shipped** as `.github/scripts/test_referenced_paths.py` in `444c250` — it asserts every path `calibration.yml`, `pages.yml` and `record-calibration/action.yml` name, that every trigger filter still matches a tracked file, and the structural invariant that the push never checks the target branch out. |
| 016 stopped somewhere mid-flight | uncommitted work in the tree covering brief steps 1–4: source pinned, spec written, builder made field-map driven, pod session written. Step 3's regression gate had been written (`tasks/scratch/016-smoke-regression.py`) but there was no record of it ever having been run. |

Per CLAUDE.md rule 1 the correction sits at the top rather than buried. I did
not stop, because the 014d work was already complete and correct — there was
nothing to build, only to verify — and 016's remaining work is unchanged by it.

## What was done

### 014d — verified, not rebuilt

Re-ran the suite the commit claims: `44 passed` in `.github/scripts`, matching
its report. The one unpushed commit on `main` is `444c250`; `origin/main` is
`1537ff5`. No code was changed.

### 016 step 3 — the regression gate, and what it actually measured

The gate rebuilds `arxiv-smoke` from a regenerated synthetic source and
compares receipts against the committed `MANIFEST.sha256`. It **crashed**:

    Batches:  19%|#8   | 3/16 [03:16<14:40, 67.70s/it]
    CalledProcessError: returned non-zero exit status 3221225477

`3221225477` is `0xC0000005`, an access violation, inside CPU embedding. That
is not a byte-identity failure and it is not a diff — the run never reached the
comparison. Decomposing it rather than re-running it:

**The layer 016 changed is verified byte-identical.** `sample.jsonl.zst` and
`query_ids.json` are written *before* embedding, so the crashed run had already
produced both. Both match the committed manifest exactly:

| artifact | committed | rebuilt | |
|---|---|---|---|
| `sample.jsonl.zst` | `b6383e22…4c6c` | `b6383e22…4c6c` | identical |
| `query_ids.json` | `0081604b…b8e2` | `0081604b…b8e2` | identical |

That is the whole sampling path: `sample_for_spec` dispatch, `field_map`, and
`split_queries(cat_field=…)` — the part of the builder task 016 rewrote.

**The layer that crashed is one 016 did not touch.**
`oneground/embed/__init__.py`, which defines `embed` and `load_model`, is
unmodified (`git status`). The crash came during *base* embedding, before the
one 016-changed line in that block (`queries = embed(model, [r[fm["title"]] …])`)
had executed. Its input is the records in the byte-identical
`sample.jsonl.zst`. Same code, same input.

**The cause is the machine, measured.** `\Memory\Available MBytes` is **748 MB**
of 7.56 GB total, with committed bytes at 25.6 GB against a 31.3 GB limit — the
box is paging. bge-base at `batch_size: 128` on CPU does not fit. `batch_size`
was **not** lowered: it is a spec value, rule 3 forbids changing one to make a
check pass, and padding length varies with batch composition, so a smaller batch
would not have produced comparable bytes anyway.

The gate is therefore **verified for the sampling layer and couldn't-check
beyond it** on this machine. It is not reported as passed.

### 016 step 3 — pinning the other changed layer without an embedding

The gate's blocked half covers `characterize()`, the second place 016 reads the
field map. Two tests now pin that invariant directly, in
`oneground/sample/test_fields.py`:

- `test_declaring_arxivs_own_field_map_changes_no_measure_synthetic` — a spec
  declaring arXiv's own names and cutoff must characterize *identically* to one
  declaring neither: all five measures and the centroid array.
- `test_a_declared_cutoff_actually_moves_the_drift_split_synthetic` — the
  negative control, so the first cannot pass for the wrong reason.

The synthetic corpus uses **three** date tiers, not two. The first draft used
two and the control died with `ZeroDivisionError` inside `recall` rather than
failing its assertion: with a cutoff past both tiers the "after" half is empty,
which is not a different measurement. Three tiers let the cutoff move between
them with both halves populated.

### The negative control, and a false pass it produced first

`tasks/scratch/016-negative-control.py` restores pre-016 behaviour by force and
re-runs both tests. Its **first run reported both passing** — a false pass. The
cause is worth recording:

    from oneground.fixture import build      # this is the *function*, not the module

`oneground/fixture/__init__.py` re-exports `build.build` under the submodule's
own name, so `build.drift_cutoff = …` set an attribute on a function object and
changed nothing. The control now reaches the module through
`sys.modules["oneground.fixture.build"]` and **asserts the patch took** before
it reports anything. With that fixed it behaves as required:

    passed               test_declaring_arxivs_own_field_map_changes_no_measure_synthetic
    FAILED (as it must)  test_a_declared_cutoff_actually_moves_the_drift_split_synthetic
        drift_cutoff was ignored

### The thing worth reading first: a planned fixture is a live analogy

Landing the spec turned the full suite red, and the failure is not cosmetic.

    FAILED oneground/test_analogy.py::
        test_a_ticket_queue_gets_no_analogy_from_a_papers_fixture_real_specs

Chasing it down produced the finding of this session. `analogy.load_fixture_analogies()`
collects **every** spec that declares an `analogy:` block and does **not** look
at `fixture.status`. Brief step 2 requires both an `analogy:` block *and*
`status: planned`, so the moment the spec exists:

    qa corpus -> stackexchange-150k   score 1.0
    why: nearest of 2 fixture(s) by declared character, scoring 1.00
         (matched on corpus_type, text_length, topics_trend, time_ordered,
          dimension, model_family)

    arxiv-150k           status=verified
    stackexchange-150k   status=planned

A user with a Q&A corpus is now handed a **perfect-scoring** analogy to a
fixture whose every measured value is `TO_BE_FILLED`. Tier 2's whole promise is
that an analogy is backed by published numbers; here there are none.

This resolves itself at **step 5** — the build sets `status: built` and fills
the values, and then the 1.0 match is exactly what the analogy block is for. So
the exposure is the window between this commit and a successful build. It is
named here rather than fixed because whether a `planned` fixture should be
matchable at all is a product decision, and CLAUDE.md puts those elsewhere. If
the build is going to be deferred, this is the one thing in the tree that
should not be left sitting.

**What I did change** is the test, and only its stale premise. Its docstring
read "with only arxiv-150k available", which task 016 makes false. The verdict
it guards is untouched and still passes: a ticket queue still gets **no**
analogy, because 0.47 is below the 0.70 floor. What moved is which fixture is
*nearest* — now stackexchange-150k rather than arxiv-150k, which is correct, as
Q&A is genuinely nearer to a ticket queue than paper abstracts are. The
rewritten test no longer hardcodes the nearest fixture, and asserts more than
it did: the floor appears in the explanation, the nearest differs on
`corpus_type`, and the fixture named is a shipped one.

No threshold was touched. `MIN_SCORE` is still 0.70. The negative control
confirms the test is still a gate:

    FAILED (as it must) with floor lowered to 0.10: stackexchange-150k

### 016 step 4 — the pod session resolves

`oneground pod plan sessions/stackexchange-build.yaml` resolves live and
read-only. Nothing was created.

## Measurements

All on `.venv\Scripts\python.exe` (Python 3.12, pinned environment).

| Measurement | How obtained | Result |
|---|---|---|
| Workflow-script suite (014d) | `python -m pytest -q .github/scripts` | **44 passed** in 174.3 s |
| 016 unit tests | `python -m pytest -q oneground/sample/test_fields.py oneground/sample/test_stackexchange.py` | **31 passed** in 1.3 s |
| Full suite, before the analogy test was corrected | `python -m pytest -q` | 514 passed, **1 failed**, 1 skipped in 335.0 s |
| Full suite, after | `python -m pytest -q` | **515 passed, 1 skipped** in 312.6 s |
| — vs the 014d baseline | 484 passed, 1 skipped | **+31**, all task 016 (14 field-map, 17 stackexchange) |
| `fixture verify` before the build | `python -m oneground.cli fixture verify stackexchange-150k` | clean refusal, `no such fixture directory`, exit 1 — not a crash |
| `sample.jsonl.zst` byte-identity | rebuilt vs `fixtures/arxiv-smoke/MANIFEST.sha256` | **identical** |
| `query_ids.json` byte-identity | same | **identical** |
| Smoke rebuild, embedding onward | `tasks/scratch/016-smoke-regression.py` | **crashed**, `0xC0000005`, batch 3/16 |
| Free physical memory | `Get-Counter '\Memory\Available MBytes'` | **748 MB** of 7,924,988 KB total |
| Commit pressure | `\Memory\Committed Bytes` vs `\Memory\Commit Limit` | 25,622 MB / 31,291 MB |
| Peak reservoir footprint | `tasks/scratch/016-reservoir-footprint.py`, tracemalloc, N=20,000 | 871 B/record → **0.78 GiB** for 960,000 held records |
| Shard manifest | `sessions/stackexchange-shards.sha256` | **59** digests, no duplicates, all 64 hex — matches `source.shards: 59` |
| Pods on the account | `python -m oneground.pod ls` | **0** |
| Unpushed commits | `git log origin/main..main` | **1** (`444c250`) |
| Analogy for a `qa` corpus | `A.choose({corpus_type: qa, …})` against the shipped specs | **stackexchange-150k, score 1.00**, `status: planned` |
| Analogy for a ticket queue | same, `corpus_type: support_tickets` | **None**, nearest scores 0.47 against the 0.70 floor |

### What `plan` resolved

    volume     : vecbench, id rvoku0jgda, 50 GB
    datacenter : EU-RO-1   (derived from the volume, not the spec)
    gpu        : RTX PRO 4500 [NVIDIA RTX PRO 4500 Blackwell], stock Low
    price      : $0.34 - $0.72/hr live on-demand range, SECURE, EU-RO-1
    COST CAP   : 1.5 h x up to $0.72/hr = up to $1.08   within max_usd 2.50
    considered : RTX PRO 4500=$0.34-$0.72/Low  RTX PRO 6000=unavailable
                 RTX 6000 Ada=unavailable      RTX 4090=$0.34-$0.74/Low
    Nothing was created. This is a dry run.

## Verification

**Verified.**

- 014d's commit does what its report says: 44 workflow-script tests pass.
- The sampling half of the step 3 regression gate: two receipts byte-identical
  to the published manifest, from a rebuild through the new field-map path.
- `characterize()` is unchanged by declaring arXiv's own field map — and the
  test saying so fails against pre-016 behaviour.
- The shard digest manifest is internally consistent and agrees with the spec.
- `plan` resolves read-only, inside both caps, with zero pods on the account.
- The rewritten ticket-queue test still gates: it fails when `MIN_SCORE` is
  lowered, so it is not passing merely because the assertion was loosened.

**Failed.** Nothing failed that indicates a defect in the code under test. The
smoke rebuild failed to *complete*, from memory exhaustion on this machine.

**Couldn't check.**

- Byte-identity of `vectors.npy`, `queries.npy`, `ground_truth.npy` and
  `characterization.json` for `arxiv-smoke`. The rebuild cannot finish in
  748 MB. The argument that they must match — unmodified code, proven-identical
  input — is an argument, not a measurement, and is not counted as one.
- Byte-identity for **arxiv-150k**, which the brief also asks for. Its
  `vectors.npy` / `queries.npy` / `sample.jsonl.zst` are not in the clone (they
  are the release asset; `../oneground-assets/` does not exist here), and a 150k
  rebuild is a pod job regardless. Nothing was measured for it.
- Whether the `vecbench` volume has the ~36 GiB free the fetch needs (34 GiB of
  shards + 2 GiB headroom) against its 50 GB. Volume contents cannot be listed
  without a running pod. `corpora/fetch_stackexchange.py` refuses *before the
  first byte* if not, so the failure mode is a cheap early exit rather than a
  wasted transfer — but it costs a few pod-minutes to discover.

## Observed, not done

- **A `planned` fixture is matchable as an analogy** (see above). The one-line
  shape of a fix would be a `status` filter in `load_fixture_analogies`, or a
  rule that an analogy must carry published values — but which of those is
  right is a product decision, and the build makes the question moot. Not
  changed.
- **`oneground/test_analogy.py`'s module docstring says "the two tests named
  `_real_specs`" and there are three.** Pre-existing — `git show HEAD` has the
  same count and the same wording. Not changed; it is not mine and rule 2
  applies.
- **`oneground.fixture.build` the module is shadowed by `build` the function.**
  `oneground/fixture/__init__.py` re-exports `build.build` under the submodule's
  name, so `from oneground.fixture import build` silently yields a function. It
  produced a false pass in my own control before I caught it, and any future
  patch or monkeypatch against that module is exposed to the same trap. Not
  changed: renaming an export is outside this brief and would touch callers.
- The step 3 gate cannot run on the developer's machine while the box sits at
  748 MB free, and nothing in the repo says so. It is a scratch script, not a
  test, so it does not announce its requirements. Worth a note in it, or a
  skip-with-reason if it is ever promoted to a test. Not done.
- `corpora/run_arxiv_150k.sh` is deliberately left in place beside the new
  generic `run_fixture_build.sh`: `sessions/arxiv-build.yaml` names it and three
  task reports invoke it by path.

## Repo now contains

All task 016, on `main`.

| Path | |
|---|---|
| `fixtures/stackexchange-150k.fixture.yaml` | new — the spec, `status: planned`, every value `TO_BE_FILLED` |
| `oneground/sample/fields.py` | new — the canonical five-field map and drift cutoff, defaulting to arXiv's |
| `oneground/sample/stackexchange.py` | new — one-pass per-year-reservoir reader over parquet shards |
| `oneground/sample/test_fields.py` | new — 14 tests, incl. the two call-site tests added this session |
| `oneground/sample/test_stackexchange.py` | new — 17 tests, synthetic dumps, named as such |
| `oneground/sample/__init__.py` | reader dispatch on `source.format` |
| `oneground/sample/arxiv.py` | `split_queries` takes `cat_field` |
| `oneground/fixture/build.py` | field-map driven; `source_digest` hashes a sharded source by manifest |
| `oneground/test_analogy.py` | the ticket-queue test's stale "only arxiv-150k" premise replaced; verdict and floor unchanged |
| `fixtures/arxiv-150k.fixture.yaml`, `fixtures/arxiv-smoke.fixture.yaml` | declare `field_map` — arXiv's own names, a documented no-op |
| `corpora/fetch_stackexchange.py` | new — pinned-revision fetch, per-shard digest verify, disk preflight |
| `corpora/run_fixture_build.sh` | new — generic build runner, fixture from env |
| `corpora/run_stackexchange_build.sh` | new — fetch, then build |
| `sessions/stackexchange-build.yaml` | new — the pod session |
| `sessions/stackexchange-shards.sha256` | new — 59 pinned shard digests |
| `tasks/scratch/016-negative-control.py` | new (scratch is gitignored) |
| `tasks/scratch/016-reservoir-footprint.py` | new (scratch is gitignored) |

## Blocked on developer

1. **Push `444c250`** (task 014d). One commit. I do not push.
2. **Dispatch the calibration workflow** for run #6. Still open from 014c/014d,
   and still the only thing that settles whether GitHub's receive-pack accepts
   a push from the depth-1 checkout.
3. **The `y` for `oneground pod up sessions/stackexchange-build.yaml`** — brief
   step 5. `plan` resolves, the cap is $1.08 worst case against `max_usd` 2.50,
   and zero pods are running. Steps 6–9 (simulate, decision log, `fixture verify
   --asset`, `docs/FIXTURES.md`) all need the artifacts this produces.
