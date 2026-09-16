# Report: 022-fixture-verify-from-anywhere

## Repo state expected vs found

| expected | found |
|---|---|
| `main` at or after `27ed14b` | `7dc1303` (the brief's own commit, after `a9d953d` and `27ed14b`) |
| `stash@{0}` holds the 018e work | yes |
| `v0.1.0` not moved by this task | on `383c7a1`, **not moved** |

**The stash: popped, not rewritten.** Checked against `7dc1303` before popping
with `git stash show -p stash@{0} | git apply --check`: all five hunks applied,
offset by 4 lines, no conflict. `git stash pop` then merged cleanly; the
dropped stash object was `fbd3741`. One correction to the brief: the stash did
not predate 018b through 019. Its base is `383c7a1` (018d), which already
contains them. Since that base only 018f's one-line `DECLARED_GLOBS` change
had touched `verify.py`.

**Task 022a landed in the middle**, as `7c8889c`: `site/teaser/` only, a
separate commit on the developer's instruction. This commit does not touch
`site/teaser/`.

## What was done

### 1. Resolve from the installed package

- **Where a fixture comes from:** `--fixtures <dir>` if given (the existing
  `--fixtures-dir` stays as an alias); otherwise `fixtures/` in the current
  directory; otherwise `oneground/_fixtures/` inside the installed package. A
  fixture is its spec and its directory together: `<id>.fixture.yaml` **and**
  `<id>/MANIFEST.sha256` must both be present at a location for it to count.
  The directory used is printed, and so is every location looked in first.
- **Interpretation, stated:** an explicit `--fixtures` is the *only* place
  looked, not the first of three. A reader who pointed at a directory and was
  quietly given the package's copy would be reading a result about bytes they
  did not choose.
- **What the wheel ships:** a build hook (`setup.py`, `build_py`) copies the
  allowlist in `oneground/fixture/shipped.py`: every spec in `fixtures/`, plus
  `MANIFEST.sha256`, `characterization.json`, `build_info.json`,
  `query_ids.json` and `ground_truth.npy` from each fixture directory.
  `MANIFEST.in` carries the same files into the sdist, so a wheel built from
  the sdist is not silently empty; the hook refuses to build if `fixtures/` is
  missing. `vectors.npy`, `queries.npy`, `sample.jsonl.zst` and
  `projection.npy` never ship. Neither do the ground-view tables or the
  published report.
- **Deviation: four specs ship, not two.** `arxiv-smoke` because step 5 runs it
  from a bare install. `glove-100-angular` because the rule is "every spec"
  rather than a hand-kept list, and it adds 1,426 bytes.
- **The pinned set, from anywhere.** `--requirements <file>` if given;
  otherwise `requirements.txt` in the current directory; otherwise the exact,
  unconditional pins the installed distribution declares (its metadata), which
  is what `pip install oneground==<version>` installs. **This fixed a defect the
  brief did not name:** outside a checkout there is no `requirements.txt`,
  `read_requirements_pins` returned `{}`, and an empty pin set has no
  mismatches, so an environment nothing had been compared against was treated
  as pinned. `environment.running_pin_mismatches` gains an optional `pinned=`
  argument for this, an adjacent change to `oneground/environment.py`; its
  default behaviour is unchanged.

### 2. Name every missing precondition

Every run prints a `preconditions` block before the digests, with all three
lines always worked out:

- **fixture:** found (where, and where it was not); or missing, with every
  location looked in, the fixture ids that *were* found there, and the flag.
- **environment:** pinned (the versions, and where the pins came from); or
  UNPINNED (each package, running vs pinned, that a fresh virtual environment
  with `pip install oneground==<version>` installs the pinned set, and
  `--allow-unpinned`); or MISSING when no pinned set was found at all.
- **asset:** present; not needed (the spec publishes no values); or MISSING,
  naming the absent members, where it looked, the tarball's name and size, the
  release page and `--asset`. Name and size live in `verify.RELEASE_ASSETS`,
  and a test checks them against `RELEASE_NOTES.md`.

**Exit codes, changed as the brief requires:**

| situation | before | now |
|---|---|---|
| fixture not found | 1 (`error: no such fixture directory`), the same code as "contradicted" | 2, with all three preconditions |
| asset absent, values published | 0 | 2, digests still checked |
| environment unpinned, values published | 2 before anything ran (the guard refused the whole command) | 2, **digests still checked**, values not recomputed |
| environment unpinned, nothing published (arxiv-smoke) | 2 | 0: nothing is recomputed, so the pins cannot matter, and the line still says which package differs |
| a value the host cannot recompute | in the characterization or the drift pair: a traceback, non-zero, no value reported (018d's run). The reference rows were already per-value | that value couldnt_check, exit 0 if nothing contradicted |
| anything contradicted | 1 | 1 |

The guard change is worth reading twice. `fixture verify` still refuses to
recompute a value under the wrong libraries without `--allow-unpinned`. It no
longer refuses to compute sha256 of the files, which does not depend on them.

### 3. Three outcomes for the command's own failures (018e)

Taken from the stash as written, then extended. Every value row is now a
`ValueRow`: a plain `(name, outcome, detail)` 3-tuple to every existing caller,
plus the `cause` of a couldnt_check:

    not_attempted  a precondition is missing
    host           MemoryError, ImportError, OSError: this machine, not the fixture
    recompute      any other exception, or a measure that returned nothing
    input          the asset's files do not belong together
    unpinned       agreed, outside the pinned environment
    build_pins     the recorded build was not pinned
    spec           the spec's entry has no usable tolerance
    unpublished    the spec carries no number yet

`recompute_failed` blames the host only for the three environmental types the
brief names. A `TypeError` is reported as the recomputation failing. A
contradiction is never downgraded by any of this: `_downgrade` still touches
only `verified`.

### 4. The summary does not over-read its rows

`summary_sentences` writes one sentence per outcome and per cause, each naming
its rows, with a universal only where it holds. "All N listed files …" appears
only when every digest verified; "Every … reproduced" only when every value
row verified; "No value was recomputed" only when every row is not_attempted;
"No value is published" only when every row is a placeholder.

**It found a live over-read.** `published_value_names` reads every numeric
field the spec publishes. Both 150k specs publish
`semantic_sharded.routing_ceiling`, `.p50_copies`, `.p95_copies` and
`.p99_copies_per_vector`, and this command has never recomputed any of them.
So the old closing line, "every published value reproduced. This fixture's
status may be set to `verified`", was never true of those specs. It now reads
"Every value this command recomputes reproduced (8 of 8)" and names the four.
The `status` hint is printed only when the published set is fully covered, so
it no longer appears for arxiv-150k. In my investigation list before this task
I called that site latent; it was live.

Digest detail for a missing file now says what it is: a release asset member;
a file for which no release asset is published (arxiv-smoke's vectors); a file
not shipped with the installed package (and, for the ground-view tables and
report files, that the repository carries it). `projection.npy` gets no such
pointer: it is gitignored and not in the asset, so no published place has it.

### 5. Proven from a bare wheel install

Below, under Measurements.

### 6. Docs

`docs/EXTERNAL_RUN.md`: the instruction no longer clones the repository (the
`git clone https://github.com/oneproof/oneground` line also pointed at a URL
that returns 404). It now describes the preconditions block and the no-asset
run, replaces "With too little memory it does not finish at all … exited
non-zero" and "the eleven digests are checked first" with the new per-value
behaviour, gives the successful run's actual summary from a bare install with
the asset (and why ten digests are couldn't-check), and brings the list of
couldn't-check causes up to date.

`RELEASE_NOTES.md`: the verification block drops the clone and its `cd`, the
asset paths follow the tarball's layout, a paragraph describes the
preconditions, and the out-of-memory and unpinned paragraphs describe the new
behaviour. The historical "On the machine that cut this release" block and the
17-vs-11 sentence are unchanged: they are measurements, and still true.

**The `--asset` path, fixed where it was wrong** (core's question 1, below):
`README.md` and `docs/RELEASE.md` both said `--asset ./arxiv-150k`, and
`docs/FIXTURES.md` said `--asset ~/oneground-assets/stackexchange-150k`, a
layout only this development machine has. All three now say
`--asset <where you extracted it>/fixtures/<id>`, the form both full runs
below observed. These three files are outside the brief's doc list; the
developer directed the fix to go wherever the path was wrong.

## Core's two questions

Both answered by running them against what exists today: the published
`oneground==0.1.0rc1` from PyPI, the public repository's `main` (`7dc1303`),
and `arxiv-150k-v1.tgz` from `~/oneground-assets/`. Fresh venv, bare install,
`USERPROFILE` pointed at an empty directory so the default asset location is
empty.

### 1. The tarball's layout, and the `--asset` path that works

**The members are `fixtures/arxiv-150k/vectors.npy`, `queries.npy` and
`sample.jsonl.zst`,** wherever you extract it. (`stackexchange-150k-v1.tgz`:
the same, under `fixtures/stackexchange-150k/`; its sha256 `5d2a2be1…a66a`
matches the release notes.) So `--asset` must name `<extraction
directory>/fixtures/arxiv-150k`.

**Both documented forms were wrong as written, and both fail silently:**
exit 0, every value couldn't-check with "the release asset is not present".

- The README's `--asset ./arxiv-150k` is one level short from anywhere (runs
  07 and 08).
- `RELEASE_NOTES.md` at `HEAD` says `--asset ../fixtures/arxiv-150k`, which is
  right only if the tarball was extracted in the clone's *parent*. Its own
  sequence runs `tar -xzf` after `cd oneground`, inside the clone, where
  `../fixtures` does not exist (run 15). Run 12 extracted it in the parent, and
  then that path verified all eight values.

**The paths observed to work:** `../fixtures/arxiv-150k` from a clone whose
parent holds the extraction (run 12, all 8 values verified); an absolute path
to the extracted `fixtures/arxiv-150k` (run 13, all 8 values; and the 022
proof above); `fixtures/arxiv-150k` from the extraction directory itself, with
the 022 wheel (run 14: asset present, its three digests verified, stopped
during the values).

```
$ sha256sum arxiv-150k-v1.tgz
0b7a0209fa4085683950e4715d49597c820cadc575b4a4fe85ef2d4f5365c015 *arxiv-150k-v1.tgz

$ tar -tzvf arxiv-150k-v1.tgz
-rw-rw-rw- root/root 460800128 2026-09-09 13:25 fixtures/arxiv-150k/vectors.npy
-rw-rw-rw- root/root   6144128 2026-09-09 13:25 fixtures/arxiv-150k/queries.npy
-rw-rw-rw- root/root  49920799 2026-09-09 13:13 fixtures/arxiv-150k/sample.jsonl.zst

$ mkdir clean && tar -xzf arxiv-150k-v1.tgz -C clean && find clean -type f
     6144128  clean/fixtures/arxiv-150k/queries.npy
    49920799  clean/fixtures/arxiv-150k/sample.jsonl.zst
   460800128  clean/fixtures/arxiv-150k/vectors.npy
```

```
cwd: <scratch>/q/clean
fatal: not a git repository (or any of the parent directories): .git
$ oneground fixture verify arxiv-150k --asset fixtures/arxiv-150k
error: no MANIFEST.sha256 in fixtures\arxiv-150k
python  <scratch>\q\venv-rc1\Scripts\python.exe  (venv)
[exit 1]
```

```
cwd: <scratch>/q/clean
fatal: not a git repository (or any of the parent directories): .git
$ oneground fixture verify arxiv-150k --asset ./arxiv-150k
error: no MANIFEST.sha256 in fixtures\arxiv-150k
python  <scratch>\q\venv-rc1\Scripts\python.exe  (venv)
[exit 1]
```

```
$ git clone --depth 1 https://github.com/shamiksaharcciit-oss/oneground oneground
7dc13031c012b0d03bfe58dc712039e77b65a49e brief: 022 fixture verify from anywhere
$ tar -xzf arxiv-150k-v1.tgz    # in the clone's parent directory
     6144128  ./fixtures/arxiv-150k/queries.npy
    49920799  ./fixtures/arxiv-150k/sample.jsonl.zst
   460800128  ./fixtures/arxiv-150k/vectors.npy
```

```
cwd: <scratch>/q/layout/oneground
<scratch>/q/layout/oneground
$ python -m oneground.cli fixture verify arxiv-150k --asset ./arxiv-150k --verbose    # stopped after 240 s if still recomputing
python  <scratch>\q\venv-rc1\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

digests
  couldnt_check receipt  sample.jsonl.zst               artifact not present (release asset, or not built); looked in fixtures\arxiv-150k and ./arxiv-150k
  couldnt_check receipt  vectors.npy                    artifact not present (release asset, or not built); looked in fixtures\arxiv-150k and ./arxiv-150k
  couldnt_check receipt  queries.npy                    artifact not present (release asset, or not built); looked in fixtures\arxiv-150k and ./arxiv-150k
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 artifact not present (release asset, or not built); looked in fixtures\arxiv-150k and ./arxiv-150k
  verified      declared ground_view_base.parquet       aa371f3611f0a734477f60ec85a3a2d33f47b225c0aca656bd31cb9ebe3068e7
  verified      declared ground_view_queries.parquet    2e4815a45a01fe3d1b3bb2d2e4144be40d612b1c4cce593debdd5ed439b702c6
  verified      declared ground_view_centroids.parquet  60a82fe747adf315128ab5abf95591fcf10fbbf2d2d1b8d9b541cb8c957fabf8
  verified      declared report/report.json             e75387ff93514e2660ce8fc62ef7ca62fb49197481c6de53cb5e2006b07ce7f2
  verified      declared report/report.html             e462a6b48900ea8fa24148a051ec2af6ac5d9ba63e21d3ad356e08c7fb0d6b64
  verified      declared report/simulate.json           e084bb68a4d325de05b3643b5e9ae4f267549d2e1abefac787c210f6ff8eb250
  verified      declared report/verify.json             32071cfc08ecf2996a6d0bdca8aae8bb1280ff455597ca95fa94cad1f929cc93
  verified      declared report/verify_info.json        01f515cf7b29fbe64e9a2c9c24f6ecb3ba52eb9c9c2cc4b4979785b74a40c7b0
  verified      declared report/characterization.json   da41fb73897f52f845541931fb1005f9caef3cd59c285912faf9c2d902267199

values
  couldnt_check intrinsic_dimensionality                the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check boundary_crispness                      the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check skew_top10_share                        the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check ambiguous_query_rate                    the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check single_node_hnsw.recall_at_10           the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check semantic_sharded.recall_at_10           the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check semantic_sharded.storage_amplification  the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check drift                                   the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.

summary: digests 13 verified, 0 contradicted, 4 couldnt_check (6 receipt, 11 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check
[exit 0]
```

```
cwd: <scratch>/q/inside/oneground
<scratch>/q/inside/oneground
$ python -m oneground.cli fixture verify arxiv-150k --asset ./arxiv-150k --verbose    # stopped after 240 s if still recomputing
python  <scratch>\q\venv-rc1\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

digests
  verified      receipt  sample.jsonl.zst               404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655
  verified      receipt  vectors.npy                    141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa
  verified      receipt  queries.npy                    dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 artifact not present (release asset, or not built); looked in fixtures\arxiv-150k and ./arxiv-150k
  verified      declared ground_view_base.parquet       aa371f3611f0a734477f60ec85a3a2d33f47b225c0aca656bd31cb9ebe3068e7
  verified      declared ground_view_queries.parquet    2e4815a45a01fe3d1b3bb2d2e4144be40d612b1c4cce593debdd5ed439b702c6
  verified      declared ground_view_centroids.parquet  60a82fe747adf315128ab5abf95591fcf10fbbf2d2d1b8d9b541cb8c957fabf8
  verified      declared report/report.json             e75387ff93514e2660ce8fc62ef7ca62fb49197481c6de53cb5e2006b07ce7f2
  verified      declared report/report.html             e462a6b48900ea8fa24148a051ec2af6ac5d9ba63e21d3ad356e08c7fb0d6b64
  verified      declared report/simulate.json           e084bb68a4d325de05b3643b5e9ae4f267549d2e1abefac787c210f6ff8eb250
  verified      declared report/verify.json             32071cfc08ecf2996a6d0bdca8aae8bb1280ff455597ca95fa94cad1f929cc93
  verified      declared report/verify_info.json        01f515cf7b29fbe64e9a2c9c24f6ecb3ba52eb9c9c2cc4b4979785b74a40c7b0
  verified      declared report/characterization.json   da41fb73897f52f845541931fb1005f9caef3cd59c285912faf9c2d902267199

values
  couldnt_check intrinsic_dimensionality                the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check boundary_crispness                      the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check skew_top10_share                        the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check ambiguous_query_rate                    the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check single_node_hnsw.recall_at_10           the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check semantic_sharded.recall_at_10           the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check semantic_sharded.storage_amplification  the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check drift                                   the release asset is not present: ./arxiv-150k\vectors.npy, ./arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.

summary: digests 16 verified, 0 contradicted, 1 couldnt_check (6 receipt, 11 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check
[exit 0]
```

```
cwd: <scratch>/q/inside/oneground   (a git clone of main 7dc1303; tar -xzf arxiv-150k-v1.tgz was run here, as RELEASE_NOTES at HEAD sequence it)
$ ls ../fixtures 2>&1
ls: cannot access '../fixtures': No such file or directory
$ oneground fixture verify arxiv-150k --asset ../fixtures/arxiv-150k
python  <scratch>\q\venv-rc1\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

digests
  verified      receipt  sample.jsonl.zst               404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655
  verified      receipt  vectors.npy                    141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa
  verified      receipt  queries.npy                    dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 artifact not present (release asset, or not built); looked in fixtures\arxiv-150k and ../fixtures/arxiv-150k
  verified      declared ground_view_base.parquet       aa371f3611f0a734477f60ec85a3a2d33f47b225c0aca656bd31cb9ebe3068e7
  verified      declared ground_view_queries.parquet    2e4815a45a01fe3d1b3bb2d2e4144be40d612b1c4cce593debdd5ed439b702c6
  verified      declared ground_view_centroids.parquet  60a82fe747adf315128ab5abf95591fcf10fbbf2d2d1b8d9b541cb8c957fabf8
  verified      receipt  report/report.json             e75387ff93514e2660ce8fc62ef7ca62fb49197481c6de53cb5e2006b07ce7f2
  verified      receipt  report/report.html             e462a6b48900ea8fa24148a051ec2af6ac5d9ba63e21d3ad356e08c7fb0d6b64
  verified      receipt  report/simulate.json           e084bb68a4d325de05b3643b5e9ae4f267549d2e1abefac787c210f6ff8eb250
  verified      receipt  report/verify.json             32071cfc08ecf2996a6d0bdca8aae8bb1280ff455597ca95fa94cad1f929cc93
  verified      receipt  report/verify_info.json        01f515cf7b29fbe64e9a2c9c24f6ecb3ba52eb9c9c2cc4b4979785b74a40c7b0
  verified      receipt  report/characterization.json   da41fb73897f52f845541931fb1005f9caef3cd59c285912faf9c2d902267199

values
  couldnt_check intrinsic_dimensionality                the release asset is not present: ../fixtures/arxiv-150k\vectors.npy, ../fixtures/arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check boundary_crispness                      the release asset is not present: ../fixtures/arxiv-150k\vectors.npy, ../fixtures/arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check skew_top10_share                        the release asset is not present: ../fixtures/arxiv-150k\vectors.npy, ../fixtures/arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check ambiguous_query_rate                    the release asset is not present: ../fixtures/arxiv-150k\vectors.npy, ../fixtures/arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check single_node_hnsw.recall_at_10           the release asset is not present: ../fixtures/arxiv-150k\vectors.npy, ../fixtures/arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check semantic_sharded.recall_at_10           the release asset is not present: ../fixtures/arxiv-150k\vectors.npy, ../fixtures/arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check semantic_sharded.storage_amplification  the release asset is not present: ../fixtures/arxiv-150k\vectors.npy, ../fixtures/arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.
  couldnt_check drift                                   the release asset is not present: ../fixtures/arxiv-150k\vectors.npy, ../fixtures/arxiv-150k\queries.npy. It ships separately from the repository, so a fresh clone cannot check values.

summary: digests 16 verified, 0 contradicted, 1 couldnt_check (12 receipt, 5 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check
[exit 0]
```

```
cwd: <scratch>/q/layout/oneground
<scratch>/q/layout/oneground
$ oneground fixture verify arxiv-150k --asset ../fixtures/arxiv-150k
python  <scratch>\q\venv-rc1\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

digests
  verified      receipt  sample.jsonl.zst               404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655  (from ../fixtures/arxiv-150k)
  verified      receipt  vectors.npy                    141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa  (from ../fixtures/arxiv-150k)
  verified      receipt  queries.npy                    dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b  (from ../fixtures/arxiv-150k)
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 artifact not present (release asset, or not built); looked in fixtures\arxiv-150k and ../fixtures/arxiv-150k
  verified      declared ground_view_base.parquet       aa371f3611f0a734477f60ec85a3a2d33f47b225c0aca656bd31cb9ebe3068e7
  verified      declared ground_view_queries.parquet    2e4815a45a01fe3d1b3bb2d2e4144be40d612b1c4cce593debdd5ed439b702c6
  verified      declared ground_view_centroids.parquet  60a82fe747adf315128ab5abf95591fcf10fbbf2d2d1b8d9b541cb8c957fabf8
  verified      receipt  report/report.json             e75387ff93514e2660ce8fc62ef7ca62fb49197481c6de53cb5e2006b07ce7f2
  verified      receipt  report/report.html             e462a6b48900ea8fa24148a051ec2af6ac5d9ba63e21d3ad356e08c7fb0d6b64
  verified      receipt  report/simulate.json           e084bb68a4d325de05b3643b5e9ae4f267549d2e1abefac787c210f6ff8eb250
  verified      receipt  report/verify.json             32071cfc08ecf2996a6d0bdca8aae8bb1280ff455597ca95fa94cad1f929cc93
  verified      receipt  report/verify_info.json        01f515cf7b29fbe64e9a2c9c24f6ecb3ba52eb9c9c2cc4b4979785b74a40c7b0
  verified      receipt  report/characterization.json   da41fb73897f52f845541931fb1005f9caef3cd59c285912faf9c2d902267199

values
  verified      intrinsic_dimensionality                recomputed 32.5533, published 32.55, delta 0.00325699, tolerance 0.5
  verified      boundary_crispness                      recomputed 0.0362467, published 0.036, delta 0.000246667, tolerance 0.02
  verified      skew_top10_share                        recomputed 0.0754, published 0.075, delta 0.0004, tolerance 0.02
  verified      ambiguous_query_rate                    recomputed 0.8915, published 0.891, delta 0.0005, tolerance 0.02
  verified      drift                                   before recomputed 0.523212, published 0.522, delta 0.00121244; after recomputed 0.551401, published 0.549, delta 0.00240097; tolerance 0.02
  verified      single_node_hnsw.recall_at_10           recomputed 0.9968, published 0.997, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.recall_at_10           recomputed 0.9318, published 0.932, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.storage_amplification  recomputed 3.71516, published 3.715, delta 0.00016, tolerance 0.01

summary: digests 16 verified, 0 contradicted, 1 couldnt_check (12 receipt, 5 declared)
         values  8 verified, 0 contradicted, 0 couldnt_check

         every published value reproduced. This fixture's status may be set to `verified`.
[exit 0]
```

```
cwd: <scratch>/q/rel022
fatal: not a git repository (or any of the parent directories): .git
$ tar -xzf arxiv-150k-v1.tgz
     6144128  ./fixtures/arxiv-150k/queries.npy
    49920799  ./fixtures/arxiv-150k/sample.jsonl.zst
   460800128  ./fixtures/arxiv-150k/vectors.npy
$ oneground fixture verify arxiv-150k --asset fixtures/arxiv-150k    # 022 wheel; stopped after 150 s, during the values
python  <scratch>\022\venv-final\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

preconditions
  fixture      found      <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k  (the installed package)
                          not in <scratch>\q\rel022\fixtures (the current directory)
  environment  pinned     numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0
                          (pins from the installed oneground 0.1.0)
  asset        present    fixtures/arxiv-150k

digests
  verified      receipt  sample.jsonl.zst               404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655  (from fixtures/arxiv-150k)
  verified      receipt  vectors.npy                    141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa  (from fixtures/arxiv-150k)
  verified      receipt  queries.npy                    dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b  (from fixtures/arxiv-150k)
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 not shipped with the installed package; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k
  couldnt_check declared ground_view_base.parquet       not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k
  couldnt_check declared ground_view_queries.parquet    not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k
  couldnt_check declared ground_view_centroids.parquet  not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k
  couldnt_check declared report/report.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k
  couldnt_check declared report/report.html             not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k
  couldnt_check declared report/simulate.json           not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k
  couldnt_check declared report/verify.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k
  couldnt_check declared report/verify_info.json        not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k
  couldnt_check declared report/characterization.json   not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures/arxiv-150k

values
[stopped by timeout while recomputing]
```

Two stopped runs are not evidence and are left out: with `--asset
fixtures/arxiv-150k` inside a clone that holds the extraction (09), and from
the archive download (11). Each was stopped at 240 s while recomputing, and
output buffering lost every line before the stop. Run 13 replaces 11 with a run
to completion.

### 2. Is there a path to the full check today without a clone and without `pip install -r requirements.txt`?

**Observed: yes to both halves, but not without the repository's contents.**

- **`pip install -r requirements.txt` is not needed.** A bare `pip install
  oneground==0.1.0rc1` resolves numpy 2.5.3, faiss-cpu 1.15.0 and
  scikit-learn 1.9.0, which are the pins `requirements.txt` holds for the
  guarded packages. The guard passed, and all eight values verified (runs 12
  and 13). The environment is not `requirements.txt`'s, though: the bare
  install put 13 packages in the venv, against 69 pins in the file. 58 of those
  pins were never installed, and `threadpoolctl` resolved 3.7.0 against a pin
  of 3.6.0. The guard checks only numpy, faiss-cpu and scikit-learn
  (`environment.PINNED`), so neither difference registers.
- **A `git clone` is not needed.** GitHub's archive download of `main`
  (`main.zip`, not a git repository) plus that bare install plus the extracted
  asset verified all eight values (run 13, 7 m 50 s).
- **A reader of the archive zip also meets test failures.** Both identifier-scan
  tests in `oneground/test_environment.py` call `pytest.skip` on their
  not-a-checkout branch without importing `pytest`, so from the zip, or any tree
  without `.git`, both fail with `NameError`. A checkout never reaches that
  branch, which is why it went unseen. Two tests in
  `oneground/verify/test_matched.py` that ask git which files it tracks fail
  there too. All four are fixed below: from an exported copy, the suite's only
  failure is now the live RunPod stock test.
- **The repository's contents are needed, by clone or by archive.** `--asset`
  supplies the vectors, queries and sample, and nothing else. The spec, the
  manifest and the ground truth come from `fixtures/` under the current
  directory. With the package and the asset alone, 0.1.0rc1 stops before
  checking anything: `error: no MANIFEST.sha256 in fixtures\arxiv-150k` (runs 04
  and 05). The tarball's own `fixtures/arxiv-150k/` is mistaken for the
  fixture, so the message is not even "no such fixture directory".

So the sentence core can print today is: *the full check needs the
repository's contents (a clone or GitHub's archive download), the published
package installed with a plain `pip install oneground`, and the release asset,
run from the repository's root.* Once 022 ships, the repository's contents
drop out of that list.

```
$ python -m pip install oneground==0.1.0rc1    # bare: no extras, no -r
Successfully installed cloudpickle-3.1.2 faiss-cpu-1.15.0 joblib-1.6.0 narwhals-2.26.0 numpy-2.5.3 oneground-0.1.0rc1 packaging-26.3 pyyaml-6.0.3 scikit-learn-1.9.0 scipy-1.18.1 threadpoolctl-3.7.0 zstandard-0.25.0

$ python -m pip list
Package       Version
------------- --------
cloudpickle   3.1.2
faiss-cpu     1.15.0
joblib        1.6.0
narwhals      2.26.0
numpy         2.5.3
oneground     0.1.0rc1
packaging     26.3
pip           25.0.1
PyYAML        6.0.3
scikit-learn  1.9.0
scipy         1.18.1
threadpoolctl 3.7.0
zstandard     0.25.0
```

```
cwd: <scratch>/q/archive/oneground-main
fatal: not a git repository (or any of the parent directories): .git
$ oneground fixture verify arxiv-150k --asset <scratch>/q/clean/fixtures/arxiv-150k
python  <scratch>\q\venv-rc1\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

digests
  verified      receipt  sample.jsonl.zst               404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655  (from <scratch>/q/clean/fixtures/arxiv-150k)
  verified      receipt  vectors.npy                    141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa  (from <scratch>/q/clean/fixtures/arxiv-150k)
  verified      receipt  queries.npy                    dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b  (from <scratch>/q/clean/fixtures/arxiv-150k)
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 artifact not present (release asset, or not built); looked in fixtures\arxiv-150k and <scratch>/q/clean/fixtures/arxiv-150k
  verified      declared ground_view_base.parquet       aa371f3611f0a734477f60ec85a3a2d33f47b225c0aca656bd31cb9ebe3068e7
  verified      declared ground_view_queries.parquet    2e4815a45a01fe3d1b3bb2d2e4144be40d612b1c4cce593debdd5ed439b702c6
  verified      declared ground_view_centroids.parquet  60a82fe747adf315128ab5abf95591fcf10fbbf2d2d1b8d9b541cb8c957fabf8
  verified      receipt  report/report.json             e75387ff93514e2660ce8fc62ef7ca62fb49197481c6de53cb5e2006b07ce7f2
  verified      receipt  report/report.html             e462a6b48900ea8fa24148a051ec2af6ac5d9ba63e21d3ad356e08c7fb0d6b64
  verified      receipt  report/simulate.json           e084bb68a4d325de05b3643b5e9ae4f267549d2e1abefac787c210f6ff8eb250
  verified      receipt  report/verify.json             32071cfc08ecf2996a6d0bdca8aae8bb1280ff455597ca95fa94cad1f929cc93
  verified      receipt  report/verify_info.json        01f515cf7b29fbe64e9a2c9c24f6ecb3ba52eb9c9c2cc4b4979785b74a40c7b0
  verified      receipt  report/characterization.json   da41fb73897f52f845541931fb1005f9caef3cd59c285912faf9c2d902267199

values
  verified      intrinsic_dimensionality                recomputed 32.5533, published 32.55, delta 0.00325699, tolerance 0.5
  verified      boundary_crispness                      recomputed 0.0362467, published 0.036, delta 0.000246667, tolerance 0.02
  verified      skew_top10_share                        recomputed 0.0754, published 0.075, delta 0.0004, tolerance 0.02
  verified      ambiguous_query_rate                    recomputed 0.8915, published 0.891, delta 0.0005, tolerance 0.02
  verified      drift                                   before recomputed 0.523212, published 0.522, delta 0.00121244; after recomputed 0.551401, published 0.549, delta 0.00240097; tolerance 0.02
  verified      single_node_hnsw.recall_at_10           recomputed 0.9968, published 0.997, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.recall_at_10           recomputed 0.93175, published 0.932, delta 0.00025, tolerance 0.01
  verified      semantic_sharded.storage_amplification  recomputed 3.71516, published 3.715, delta 0.00016, tolerance 0.01

summary: digests 16 verified, 0 contradicted, 1 couldnt_check (12 receipt, 5 declared)
         values  8 verified, 0 contradicted, 0 couldnt_check

         every published value reproduced. This fixture's status may be set to `verified`.
[exit 0]
```

A detail from the two full runs: `semantic_sharded.recall_at_10` recomputed to
0.9318 in run 12 and 0.93175 in run 13, published 0.932, tolerance 0.01.
Both verified; the recomputation is not bit-stable between runs.

## Measurements

### Wheel size

Both built with `python -m build` (setuptools 80.9.0, wheel 0.45.1, isolated),
from a clean copy of the tree:

| | wheel bytes | files | uncompressed |
|---|---|---|---|
| before: `7dc1303` (`git archive`, `--wheel`) | 505,283 | 98 | 1,535,995 |
| after: final tree (sdist, then wheel from sdist) | **1,812,337** | 121 | 5,079,833 |

The +1,307,054 bytes are almost all fixture data: 3,487,037 bytes uncompressed
under `oneground/_fixtures/`, of which `ground_truth.npy` is 3,360,384 (1.6 MB
per 150k fixture). The brief expected a few hundred kilobytes; the ground truth
alone makes it about 3.5 MB uncompressed, 1.3 MB of wheel. sdist: 1,748,230
bytes. No `vectors`, `queries`, `sample`, `projection`, ground-view or report
file is in the wheel (`unzip -l`).

sha256 of this proof's build (not byte-reproducible; the retag rebuilds):
wheel `3e48a4a0eea367b8601d5cd1ba3879d84911bd8b5bbf52b24e2a2fa04e9ba01f`,
sdist `2989c0c5510eb83ed1f11c408bdbb3f425f2fd35e121c7aa088f15ca76bf36b8`.

### The proof, step 5

Paths under this session's scratch directory are shown as `<scratch>`; every other character of every output is as printed.

- Fresh venv from the system Python 3.12.10 (`py -3.12 -m venv`), then
  `pip install oneground-0.1.0-py3-none-any.whl` alone: no extras, no
  requirements file. It resolved numpy 2.5.3, faiss-cpu 1.15.0,
  scikit-learn 1.9.0, PyYAML 6.0.3, zstandard 0.25.0 (dependency wheels from
  pip's cache).
- Run from an empty directory that `git rev-parse` confirms is not a checkout,
  by the venv's own `oneground.exe`, which imported the package from the venv's
  `site-packages`.
- **`USERPROFILE` pointed at an empty directory for all runs.** This machine
  already has the arXiv asset extracted at the default `~/oneground-assets/`,
  so without the override "no asset" would have found it. The command text is
  exactly the brief's.
- The asset for command 2 is `arxiv-150k-v1.tgz` extracted fresh; its sha256
  `0b7a0209…c015` matches `RELEASE_NOTES.md`, and it extracted to
  `fixtures/arxiv-150k/` with the three members.
- **An earlier attempt was discarded.** The first run of commands 1 and 3
  resolved `oneground` to the project's own venv, because a `C:/` entry in
  bash's `PATH` split on the colon. Everything below was run by full path.
  Two wording defects found in those earlier outputs were fixed before this
  build (see Verification).

Wall clock: command 1, 61 s; command 3, 27 s; command 2, **37 min 31 s**.

**`oneground fixture verify arxiv-150k`** (no asset): exit 2.

```
$ oneground fixture verify arxiv-150k
python  <scratch>\022\venv-final\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

preconditions
  fixture      found      <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k  (the installed package)
                          not in <scratch>\022\elsewhere-final\fixtures (the current directory)
  environment  pinned     numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0
                          (pins from the installed oneground 0.1.0)
  asset        MISSING    vectors.npy, queries.npy and sample.jsonl.zst not found in <scratch>/022/home-final\oneground-assets\arxiv-150k or <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k
                          release asset arxiv-150k-v1.tgz, 483,468,013 bytes, at
                          https://github.com/shamiksaharcciit-oss/oneground/releases/tag/v0.1.0
                          extract it anywhere and pass --asset <the extracted folder>

digests
  couldnt_check receipt  sample.jsonl.zst               release asset member, not present; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check receipt  vectors.npy                    release asset member, not present; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check receipt  queries.npy                    release asset member, not present; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 not shipped with the installed package; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check declared ground_view_base.parquet       not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check declared ground_view_queries.parquet    not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check declared ground_view_centroids.parquet  not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check declared report/report.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check declared report/report.html             not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check declared report/simulate.json           not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check declared report/verify.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check declared report/verify_info.json        not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k
  couldnt_check declared report/characterization.json   not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/home-final\oneground-assets\arxiv-150k

values
  couldnt_check intrinsic_dimensionality                not recomputed, because the release asset is not present
  couldnt_check boundary_crispness                      not recomputed, because the release asset is not present
  couldnt_check skew_top10_share                        not recomputed, because the release asset is not present
  couldnt_check ambiguous_query_rate                    not recomputed, because the release asset is not present
  couldnt_check single_node_hnsw.recall_at_10           not recomputed, because the release asset is not present
  couldnt_check semantic_sharded.recall_at_10           not recomputed, because the release asset is not present
  couldnt_check semantic_sharded.storage_amplification  not recomputed, because the release asset is not present
  couldnt_check drift                                   not recomputed, because the release asset is not present

summary: digests 4 verified, 0 contradicted, 13 couldnt_check (6 receipt, 11 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check

         13 listed files are not present here, so their bytes were not checked:
         sample.jsonl.zst, vectors.npy, queries.npy, projection.npy,
         ground_view_base.parquet, ground_view_queries.parquet,
         ground_view_centroids.parquet, report/report.json, report/report.html,
         report/simulate.json, report/verify.json, report/verify_info.json and
         report/characterization.json.
         No value was recomputed, because the release asset is not present.
         4 published values are not recomputed by this command:
         semantic_sharded.routing_ceiling, semantic_sharded.p50_copies,
         semantic_sharded.p95_copies and
         semantic_sharded.p99_copies_per_vector.
         The digests were checked before any value, so the 4 files that
         verified are the published bytes whatever happened to the values.
[exit 2]
```

**`oneground fixture verify arxiv-150k --asset <extracted folder>`**: exit 0,
8 of 8 values verified.

```
$ oneground fixture verify arxiv-150k --asset <scratch>/022/asset-extract/fixtures/arxiv-150k
python  <scratch>\022\venv-final\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

preconditions
  fixture      found      <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k  (the installed package)
                          not in <scratch>\022\elsewhere-final\fixtures (the current directory)
  environment  pinned     numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0
                          (pins from the installed oneground 0.1.0)
  asset        present    <scratch>/022/asset-extract/fixtures/arxiv-150k

digests
  verified      receipt  sample.jsonl.zst               404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655  (from <scratch>/022/asset-extract/fixtures/arxiv-150k)
  verified      receipt  vectors.npy                    141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa  (from <scratch>/022/asset-extract/fixtures/arxiv-150k)
  verified      receipt  queries.npy                    dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b  (from <scratch>/022/asset-extract/fixtures/arxiv-150k)
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 not shipped with the installed package; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k
  couldnt_check declared ground_view_base.parquet       not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k
  couldnt_check declared ground_view_queries.parquet    not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k
  couldnt_check declared ground_view_centroids.parquet  not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k
  couldnt_check declared report/report.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k
  couldnt_check declared report/report.html             not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k
  couldnt_check declared report/simulate.json           not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k
  couldnt_check declared report/verify.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k
  couldnt_check declared report/verify_info.json        not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k
  couldnt_check declared report/characterization.json   not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>/022/asset-extract/fixtures/arxiv-150k

values
  verified      intrinsic_dimensionality                recomputed 32.5533, published 32.55, delta 0.00325699, tolerance 0.5
  verified      boundary_crispness                      recomputed 0.0362467, published 0.036, delta 0.000246667, tolerance 0.02
  verified      skew_top10_share                        recomputed 0.0754, published 0.075, delta 0.0004, tolerance 0.02
  verified      ambiguous_query_rate                    recomputed 0.8915, published 0.891, delta 0.0005, tolerance 0.02
  verified      drift                                   before recomputed 0.523212, published 0.522, delta 0.00121244; after recomputed 0.551401, published 0.549, delta 0.00240097; tolerance 0.02
  verified      single_node_hnsw.recall_at_10           recomputed 0.9968, published 0.997, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.recall_at_10           recomputed 0.9318, published 0.932, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.storage_amplification  recomputed 3.71516, published 3.715, delta 0.00016, tolerance 0.01

summary: digests 7 verified, 0 contradicted, 10 couldnt_check (6 receipt, 11 declared)
         values  8 verified, 0 contradicted, 0 couldnt_check

         10 listed files are not present here, so their bytes were not checked:
         projection.npy, ground_view_base.parquet, ground_view_queries.parquet,
         ground_view_centroids.parquet, report/report.json, report/report.html,
         report/simulate.json, report/verify.json, report/verify_info.json and
         report/characterization.json.
         Every value this command recomputes reproduced (8 of 8).
         4 published values are not recomputed by this command:
         semantic_sharded.routing_ceiling, semantic_sharded.p50_copies,
         semantic_sharded.p95_copies and
         semantic_sharded.p99_copies_per_vector.
[exit 0]
```

**`oneground fixture verify arxiv-smoke`**: exit 0.

```
$ oneground fixture verify arxiv-smoke
python  <scratch>\022\venv-final\Scripts\python.exe  (venv)
fixture: arxiv-smoke
directory: <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-smoke
manifest: MANIFEST.sha256 (11 files listed)

preconditions
  fixture      found      <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-smoke  (the installed package)
                          not in <scratch>\022\elsewhere-final\fixtures (the current directory)
  environment  pinned     numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0
                          (pins from the installed oneground 0.1.0)
  asset        not needed the spec publishes no values yet, so no asset is read

digests
  couldnt_check receipt  sample.jsonl.zst               not present, and no release asset is published for this fixture; building it produces this file; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <scratch>/022/home-final\oneground-assets\arxiv-smoke
  couldnt_check receipt  vectors.npy                    not present, and no release asset is published for this fixture; building it produces this file; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <scratch>/022/home-final\oneground-assets\arxiv-smoke
  couldnt_check receipt  queries.npy                    not present, and no release asset is published for this fixture; building it produces this file; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <scratch>/022/home-final\oneground-assets\arxiv-smoke
  verified      receipt  query_ids.json                 0081604bb50d8dd48b4ae5605a05fc894dcd2ae4db41511657464772c911b8e2
  verified      receipt  ground_truth.npy               13919bb5174ebeb4febe037017a2e2b8bbfe4998b3ce261e7989e4649c2a9cce
  verified      receipt  characterization.json          07b576e27e680596d8cb52c59f01dcb18e1039a9be135c48db921e5a56dc30e1
  verified      declared build_info.json                fa6168a52acb45283a51f73554e3683dd24abde014e0b82a4091e0e3ebb944c1
  couldnt_check declared projection.npy                 not shipped with the installed package; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <scratch>/022/home-final\oneground-assets\arxiv-smoke
  couldnt_check declared ground_view_base.parquet       not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <scratch>/022/home-final\oneground-assets\arxiv-smoke
  couldnt_check declared ground_view_queries.parquet    not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <scratch>/022/home-final\oneground-assets\arxiv-smoke
  couldnt_check declared ground_view_centroids.parquet  not shipped with the installed package; the repository carries it; looked in <scratch>\022\venv-final\Lib\site-packages\oneground\_fixtures\arxiv-smoke and <scratch>/022/home-final\oneground-assets\arxiv-smoke

values
  couldnt_check intrinsic_dimensionality                the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check boundary_crispness                      the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check skew_top10_share                        the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check ambiguous_query_rate                    the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check single_node_hnsw.recall_at_10           the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check semantic_sharded.recall_at_10           the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check semantic_sharded.storage_amplification  the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.
  couldnt_check drift                                   the spec publishes no value for this field yet, so there is nothing to reproduce. The recomputation was skipped rather than run against placeholders.

summary: digests 4 verified, 0 contradicted, 7 couldnt_check (6 receipt, 5 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check

         7 listed files are not present here, so their bytes were not checked:
         sample.jsonl.zst, vectors.npy, queries.npy, projection.npy,
         ground_view_base.parquet, ground_view_queries.parquet and
         ground_view_centroids.parquet.
         No value is published in the spec yet, so there was nothing to
         reproduce (8 placeholders).
[exit 0]
```

### Tests

- **Full suite, final tree: 803 passed, 1 failed** (6 m 46 s). The failure is
  `oneground/pod/test_pod.py::test_live_plan_against_the_real_api`, which runs
  only because this process inherits `RUNPOD_API_KEY`. It is read-only: it
  resolves a plan for `sessions/arxiv-build.yaml` against the live API. It
  failed on market state, not code: `PlanError: none of the requested GPU
  types is offered on SECURE in EU-RO-1. requested: RTX PRO 4500, RTX PRO
  6000, RTX 6000 Ada, RTX 4090; offered here: RTX 2000 Ada, RTX PRO 4000`.
  This task does not touch `oneground/pod/`; the test passed in 018f; it is not
  changed. An earlier full run, before the two wording fixes, gave 804
  passed, 0 failed (18 m 32 s).
- **23 new tests.** 18 in `oneground/fixture/test_verify.py`: resolution
  order, explicit-only `--fixtures`, spec-and-directory together, every
  precondition named in one run, the not-found case never printing the bare
  error, no pin source never read as pinned, the distribution's pins outside a
  checkout, **an injected `MemoryError` on one value leaving four verified and
  exiting 0**, a host failure beside a contradiction still exiting 1,
  `recompute_failed`'s causes, a placeholder spec needing no asset,
  `RELEASE_ASSETS` against `RELEASE_NOTES.md`, and four summary tests. 5 in
  `oneground/test_packaging.py`: the shipped set, never the asset, a stray
  vectors file on the build machine not reaching the wheel, the sdist carrying
  what the wheel ships, and `shipped.py` importing only the standard library.
- **The 019 rule, by hand:** `test_no_summary_sentence_asserts_more_than_its_rows`
  runs the summary over every mix of six value kinds × three rows × three
  digest outcomes × two files (1,944 cases). Each universal must hold for every
  row it quantifies over, and each value may be named only in its own outcome's
  and cause's sentence.
- **Negative controls:** `tasks/scratch/022-summary-mutants.py` (gitignored, as
  every scratch script is) reintroduces three over-reads: the pre-022 "every
  published value reproduced" whenever nothing is contradicted, every
  couldnt_check collapsed into "could not be recomputed on this host", and "All
  N listed files match" regardless. **3 of 3 caught**; unmutated, it passes.
- **One existing test helper changed:** `_fixture` in `test_verify.py` now
  writes a minimal spec that publishes no values. Four digest-exit-code tests
  built a manifest with no spec, which is now "fixture not found". The spec
  keeps them about the digest half.

### Scans

- Identifier scan over the staged tree: **0 findings.**
- Leak scan: the one known synthetic `DESKTOP-` probe in
  `oneground/test_environment.py`; pod ids kept.
- `tasks/scratch/018-docs-numbers.py`: ALL CHECKS PASSED.

## Verification

Against the acceptance list:

- **From a bare wheel install outside any checkout, all three commands behave
  as described:** passed. Outputs above.
- **A missing precondition never produces a bare "no such fixture directory":**
  passed, by test and by proof.
- **An injected MemoryError on one value leaves the other values reported and
  exits 0:** passed, by test.
- **Summary sentences pass the 019 rule:** passed, by the 1,944-case test and
  its three negative controls.
- **Wheel size before and after; scans clean:** above. **Suite green: not
  quite.** 803 passed, and the one failure is the live RunPod test failing on
  GPU stock in EU-RO-1 (above), not on this change.

Fixed during the proof, before the final build: for a wheel install, the
digest detail said a clone of the repository "carries" every file the wheel
does not ship, which is false for `projection.npy`; and it called arxiv-smoke's
vectors a "release asset member" when no asset is published for that fixture.
Both were over-reads by this task's own rule.

**Couldn't-check:**

- **A real out-of-memory on the real fixture.** This time the machine had room,
  and all eight values verified. The per-value path is proven by injection,
  not by a real allocation failure.
- **The release URL the command prints**,
  `…/releases/tag/v0.1.0`, returns 404 until the `v0.1.0` release is
  published. It is derived from the installed version, so it is right for the
  release this ships in.
- **Other platforms.** The wheel was built and proven on Windows only.
- **An editable install** (`pip install -e .`) run from outside the repository
  root. `oneground/_fixtures/` exists only in a built package, never in the
  source tree, so I expect the package fallback to find nothing there; not
  exercised. Inside a checkout the current directory resolves first, which the
  suite does exercise.

## Observed, not done

- **`pyproject.toml`'s `project.urls` point at
  `https://github.com/oneproof/oneground`, which returns 404.** The command
  prints `https://github.com/shamiksaharcciit-oss/oneground`, the repository
  018g's live release link resolved on. PyPI's project links would carry the
  dead one.
- **`fixture verify` recomputes 8 of the 12 values the 150k specs publish.**
  The routing ceiling and the three copy percentiles are now named in every
  summary, and still not recomputed.
- **`projection.npy` is in arxiv-150k's MANIFEST and published nowhere**
  (gitignored, not in the asset), so outside the build machine it is always
  couldn't-check.
- **The empty-pin-set defect remains in the shared guard.**
  `environment.guard` and the other guarded commands still read a missing
  `requirements.txt` as pinned. Only `fixture verify` resolves pins another way.
- **Other commands still read fixtures from the current directory only:**
  `analogy.FIXTURES_DIR` (the Tier-2 report's nearest fixture) and `calibrate`.
- `environment.guard`'s refusal text suggests `python -m oneground ...`, which
  fails: the package has no `__main__`.
- `oneground/fixture/test_verify.py` has an `if __name__ == "__main__":` block
  part-way down; running the file directly skips every test after it (pytest
  runs them all).
- The teaser's check-it-yourself panel (022a, `7c8889c`) is written for a world
  where this has not shipped. It changes once it has. It also says the full
  check needs "a checkout, the pinned environment and the release asset".
  Question 2 above observed that today the pinned environment comes from a
  plain `pip install oneground`, with no `-r requirements.txt` step.
- **The published 0.1.0rc1 prints the over-read this task removes.** Runs 12
  and 13 end "every published value reproduced. This fixture's status may be
  set to `verified`." with four published values never recomputed. It also
  counts the six `report/*` files as receipts (12 receipt, 5 declared), because
  it predates 018f's `DECLARED_GLOBS` change.
- **The stackexchange-150k tarball's headers carry this development machine's
  local user name and group id** (`tar -tzvf`); the arXiv tarball's say
  `root/root`. That is the identifier class tasks 014 and 017 scan the tree
  for, in a release asset those scans never see. It is named here without the
  value.

## Repo now contains

Changed:

    oneground/fixture/verify.py        resolution, preconditions, causes, summary
    oneground/fixture/test_verify.py   18 tests; the digest helper writes a spec
    oneground/environment.py           running_pin_mismatches(pinned=)
    oneground/test_packaging.py        5 tests
    docs/EXTERNAL_RUN.md               no clone; preconditions; per-value failures
    RELEASE_NOTES.md                   the same, in the verification block
    README.md                          --asset <where you extracted it>/fixtures/arxiv-150k
    docs/RELEASE.md                    the same, and why ./arxiv-150k was wrong
    docs/FIXTURES.md                   the same, for stackexchange-150k

New:

    oneground/fixture/shipped.py       what the wheel carries of each fixture
    setup.py                           the build hook that copies it
    MANIFEST.in                        the same files into the sdist
    tasks/022-fixture-verify-from-anywhere.report.md

Not committed: `tasks/020-simulator-state.md` (your brief);
`tasks/scratch/022-summary-mutants.py` (gitignored).

## Blocked on developer

1. **Push `main`.**
2. **Retag `v0.1.0` at this commit and re-cut the artifacts.** Wheels are not
   byte-reproducible, so the hashes above will not match your build; the size
   should be within a few hundred bytes.
3. **Publish the `v0.1.0` release** so the URL the command prints resolves.
4. **Revise the teaser panel (022a)** once a release carrying this is out.


---

## Additions after `c3615e1`

Four additions and one defect fix, from the developer, each from an execution
rather than a reading. Same commit prefix; `v0.1.0` still not moved.

### Repo state expected vs found

`main` at `c3615e1`, clean apart from `tasks/020-simulator-state.md`: found.

### What was done

**1. A wrong `--asset` is an error, not a quiet couldn't-check.** On 0.1.0rc1,
`--asset ./arxiv-150k` reported every value couldn't-check and exited 0: the
tool saying it checked when it did not. Passing the flag asserts the asset is
there, so `check_preconditions` now checks an explicit `--asset` first, whether
or not the fixture has values to recompute. When the folder holds none of
`vectors.npy`, `queries.npy` and `sample.jsonl.zst`, the asset precondition
is MISSING and the run exits 2, saying what it looked for and what it found
(`it does not exist`, `it is empty`, or `it holds <the first eight names>`).
When the members are one level down (`<given>/fixtures/<id>` or
`<given>/<id>`, the commonest wrong path, since the tarball extracts to
`fixtures/<id>/`), it names that folder and the flag to pass. For a spec with
nothing published (arxiv-smoke), a wrong `--asset` still exits 2, but its
rows still say the values are unpublished rather than "not recomputed because
of --asset". My first trial said the latter, which over-read the rows, and it
was fixed before the proof.

**2. `&&` in printed commands.** Windows PowerShell 5.1 rejects it
(observed below). Grepped every `*.md` and `*.html` in the repository, the
teaser included, `tasks/` excepted as the historical record:

| where | what | done |
|---|---|---|
| `README.md` contributor block | `git clone … && cd oneground`, `python -m venv .venv && . .venv/bin/activate`, `pip install -r requirements.txt && pip install -e .` | split, one command per line, with a macOS/Linux block and a Windows PowerShell block |
| `RELEASE_NOTES.md`, `docs/EXTERNAL_RUN.md` | none left: `c3615e1` had already removed their `git clone … && cd oneground` along with the clone | nothing to split |
| `docs/VERIFY.md:347`, `:411` | the two commands whose `&`/`&&` precedence *was* the pod bug that section diagnoses, quoted as they ran | **left as written**: splitting them would falsify the record the section explains |
| `site/teaser/app.js` | eleven hits, all JavaScript operators; no printed shell line | nothing to split |
| `oneground/pod/*.py` | `&&` in commands sent to the pod's bash over SSH, never printed for a reader | not a doc; untouched |

**3. The virtual environment is a stated requirement.** `README.md`'s Install
section and `docs/EXTERNAL_RUN.md` now say it is required and why: the
package pins numpy, faiss-cpu and scikit-learn exactly, so installing into the
system Python replaces the versions of whichever of those, and of their
dependencies, it already has. Each gives the commands for macOS/Linux and for
Windows PowerShell. The PowerShell commands call `.venv\Scripts\python.exe`
and `.venv\Scripts\oneground.exe` directly, so nothing depends on
`Activate.ps1` being allowed by the execution policy. The environment
precondition always says which interpreter it is. In a venv it prints `in a
virtual environment`. On a system interpreter it prints `SYSTEM INTERPRETER: a
virtual environment is required`, with the reason and the command. **The
guard's behaviour is unchanged:** the line is information; `met` and the exit
code are exactly what they were.

**Open question, for after the release: should the guard refuse a system
interpreter outright?** Today it warns and proceeds, and refuses only on a
version mismatch. A reader who installs the pins into their system Python has
already had their packages replaced by the time any guard runs.

**4. A tarball extracted where the fixture is looked for is named.** On
0.1.0rc1 that produced `error: no MANIFEST.sha256 in fixtures\arxiv-150k`:
the tarball's own `fixtures/arxiv-150k/` taken for the fixture. Now any
looked-in location whose `<id>/` holds asset members and no manifest is named
in the fixture line (`… holds vectors.npy, queries.npy and sample.jsonl.zst
and no MANIFEST.sha256: that is the release asset extracted there, not the
fixture. Pass --asset …`), whether or not the fixture was then found
elsewhere. Without `--asset`, the asset line names it too.

**5. `oneground/test_environment.py` imports `pytest`.** Both identifier-scan
tests call `pytest.skip` on their not-a-checkout branch, and the file never
imported `pytest`. Inside a git checkout that branch never runs. From a GitHub
archive zip, or any tree without `.git`, both tests failed with `NameError`.
Found by the lab stream; reproduced and fixed here:

```
cwd: GitHub's archive of main (7dc1303), unzipped; no .git
$ python -m pytest -q -p no:cacheprovider oneground/test_environment.py
E           NameError: name 'pytest' is not defined
oneground\test_environment.py:449: NameError
E           NameError: name 'pytest' is not defined
oneground\test_environment.py:462: NameError
FAILED oneground/test_environment.py::test_no_tracked_file_carries_a_machine_identifier
FAILED oneground/test_environment.py::test_the_scan_actually_reads_the_tree
2 failed, 30 passed in 26.50s

cwd: an exported copy of the working tree with the import added; no .git
$ python -m pytest -q -p no:cacheprovider oneground/test_environment.py -rs
SKIPPED [1] oneground\test_environment.py:454: not a git checkout; nothing to scan
SKIPPED [1] oneground\test_environment.py:467: not a git checkout; nothing to scan
30 passed, 2 skipped in 35.70s
```

### Measurements

**Wheel**, built as before from a clean copy of the tree, before the
`test_environment.py` import was added (the import changes only a test module):
1,815,318 bytes, 121 files, 5,093,607 uncompressed; +2,981 bytes over the
`c3615e1` proof build.

**Tests:** 8 new in `oneground/fixture/test_verify.py`:
- a correct `--asset` verifies;
- a wrong one exits 2 naming what it looked for and found;
- a folder that does not exist says so;
- a path one level short names the folder that holds the asset;
- a wrong `--asset` on a spec with nothing published exits 2, and its rows stay "unpublished";
- an asset extracted where the fixture is looked for is named, with the package's copy found;
- the same without a package copy;
- the environment line states the venv requirement without changing `met`.

The affected files: 124 passed.

**Full suite, in the checkout:** **812 passed, 0 failed** (3 m 59 s). The live RunPod plan test passed this time: EU-RO-1 had stock.

**Full suite, from an exported copy of the tree with no `.git`** (what a reader
of the archive zip runs): **3 failed, 804 passed, 5 skipped** (3 m 38 s). Skips include the two identifier-scan tests, which now skip rather than raise `NameError`. The failures: the live RunPod plan test, on GPU stock in EU-RO-1 four minutes after it passed in the checkout; and two tests in `oneground/verify/test_matched.py` that assume a git checkout. That was the count at `ba3350c`; those two now skip, and the final count is in the last section.

**`&&` in Windows PowerShell 5.1**, observed:

```
PS> $PSVersionTable.PSVersion.ToString()
5.1.26100.9444
PS> powershell.exe -NoProfile -Command "git --version && echo second"
At line:1 char:15
+ git --version && echo second
+               ~~
The token '&&' is not a valid statement separator in this version.
    + CategoryInfo          : ParserError: (:) [], ParentContainsErrorRecordException
    + FullyQualifiedErrorId : InvalidEndOfLine
[exit 1]
```

**Both directions of `--asset`, in Windows PowerShell 5.1.** The
`docs/EXTERNAL_RUN.md` PowerShell block, run line by line in a fresh
directory. One substitution: the built wheel in place of `oneground` on the pip
line, because the fix is not on PyPI; the tarball is named by full path because
it is not in that directory. `USERPROFILE` points at an empty directory, so
the default asset location holds nothing.

```
PS> tar -xzf ~\oneground-assets\arxiv-150k-v1.tgz    # the doc: tar -xzf arxiv-150k-v1.tgz, in this directory
     6144128  fixtures\arxiv-150k\queries.npy
    49920799  fixtures\arxiv-150k\sample.jsonl.zst
   460800128  fixtures\arxiv-150k\vectors.npy
[exit 0]
```

A wrong `--asset`: exit 2, naming what it looked for and what is there. The
fixture line also names the tarball extracted in the current directory.

```
PS> .venv\Scripts\oneground.exe fixture verify arxiv-150k --asset .\arxiv-150k
python  <scratch>\022b\ps\.venv\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

preconditions
  fixture      found      <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k  (the installed package)
                          not in <scratch>\022b\ps\fixtures (the current directory)
                          <scratch>\022b\ps\fixtures\arxiv-150k holds vectors.npy, queries.npy and sample.jsonl.zst and no MANIFEST.sha256: that is the release asset extracted there, not the fixture. Pass --asset <scratch>\022b\ps\fixtures\arxiv-150k
  environment  pinned     numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0
                          (pins from the installed oneground 0.1.0)
                          in a virtual environment
  asset        MISSING    --asset .\arxiv-150k holds none of vectors.npy, queries.npy and sample.jsonl.zst; it does not exist
                          release asset arxiv-150k-v1.tgz, 483,468,013 bytes, at
                          https://github.com/shamiksaharcciit-oss/oneground/releases/tag/v0.1.0
                          it extracts to fixtures/arxiv-150k/ wherever you extract it: pass --asset <that folder>

digests
  couldnt_check receipt  sample.jsonl.zst               release asset member, not present; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check receipt  vectors.npy                    release asset member, not present; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check receipt  queries.npy                    release asset member, not present; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 not shipped with the installed package; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check declared ground_view_base.parquet       not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check declared ground_view_queries.parquet    not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check declared ground_view_centroids.parquet  not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check declared report/report.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check declared report/report.html             not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check declared report/simulate.json           not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check declared report/verify.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check declared report/verify_info.json        not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k
  couldnt_check declared report/characterization.json   not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and .\arxiv-150k

values
  couldnt_check intrinsic_dimensionality                not recomputed, because --asset names a folder that holds none of the release asset
  couldnt_check boundary_crispness                      not recomputed, because --asset names a folder that holds none of the release asset
  couldnt_check skew_top10_share                        not recomputed, because --asset names a folder that holds none of the release asset
  couldnt_check ambiguous_query_rate                    not recomputed, because --asset names a folder that holds none of the release asset
  couldnt_check single_node_hnsw.recall_at_10           not recomputed, because --asset names a folder that holds none of the release asset
  couldnt_check semantic_sharded.recall_at_10           not recomputed, because --asset names a folder that holds none of the release asset
  couldnt_check semantic_sharded.storage_amplification  not recomputed, because --asset names a folder that holds none of the release asset
  couldnt_check drift                                   not recomputed, because --asset names a folder that holds none of the release asset

summary: digests 4 verified, 0 contradicted, 13 couldnt_check (6 receipt, 11 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check

         13 listed files are not present here, so their bytes were not checked:
         sample.jsonl.zst, vectors.npy, queries.npy, projection.npy,
         ground_view_base.parquet, ground_view_queries.parquet,
         ground_view_centroids.parquet, report/report.json, report/report.html,
         report/simulate.json, report/verify.json, report/verify_info.json and
         report/characterization.json.
         No value was recomputed, because --asset names a folder that holds
         none of the release asset.
         4 published values are not recomputed by this command:
         semantic_sharded.routing_ceiling, semantic_sharded.p50_copies,
         semantic_sharded.p95_copies and
         semantic_sharded.p99_copies_per_vector.
         The digests were checked before any value, so the 4 files that
         verified are the published bytes whatever happened to the values.
[exit 2]
```

No `--asset`, with the tarball extracted in the current directory: exit 2,
naming the extracted asset and the flag to pass.

```
PS> .venv\Scripts\oneground.exe fixture verify arxiv-150k
python  <scratch>\022b\ps\.venv\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

preconditions
  fixture      found      <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k  (the installed package)
                          not in <scratch>\022b\ps\fixtures (the current directory)
                          <scratch>\022b\ps\fixtures\arxiv-150k holds vectors.npy, queries.npy and sample.jsonl.zst and no MANIFEST.sha256: that is the release asset extracted there, not the fixture. Pass --asset <scratch>\022b\ps\fixtures\arxiv-150k
  environment  pinned     numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0
                          (pins from the installed oneground 0.1.0)
                          in a virtual environment
  asset        MISSING    vectors.npy, queries.npy and sample.jsonl.zst not found in <scratch>\022b\ps\home\oneground-assets\arxiv-150k or <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k
                          an extracted asset is at <scratch>\022b\ps\fixtures\arxiv-150k: pass --asset <scratch>\022b\ps\fixtures\arxiv-150k
                          release asset arxiv-150k-v1.tgz, 483,468,013 bytes, at
                          https://github.com/shamiksaharcciit-oss/oneground/releases/tag/v0.1.0
                          it extracts to fixtures/arxiv-150k/ wherever you extract it: pass --asset <that folder>

digests
  couldnt_check receipt  sample.jsonl.zst               release asset member, not present; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check receipt  vectors.npy                    release asset member, not present; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check receipt  queries.npy                    release asset member, not present; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 not shipped with the installed package; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check declared ground_view_base.parquet       not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check declared ground_view_queries.parquet    not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check declared ground_view_centroids.parquet  not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check declared report/report.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check declared report/report.html             not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check declared report/simulate.json           not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check declared report/verify.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check declared report/verify_info.json        not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k
  couldnt_check declared report/characterization.json   not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and <scratch>\022b\ps\home\oneground-assets\arxiv-150k

values
  couldnt_check intrinsic_dimensionality                not recomputed, because the release asset is not present
  couldnt_check boundary_crispness                      not recomputed, because the release asset is not present
  couldnt_check skew_top10_share                        not recomputed, because the release asset is not present
  couldnt_check ambiguous_query_rate                    not recomputed, because the release asset is not present
  couldnt_check single_node_hnsw.recall_at_10           not recomputed, because the release asset is not present
  couldnt_check semantic_sharded.recall_at_10           not recomputed, because the release asset is not present
  couldnt_check semantic_sharded.storage_amplification  not recomputed, because the release asset is not present
  couldnt_check drift                                   not recomputed, because the release asset is not present

summary: digests 4 verified, 0 contradicted, 13 couldnt_check (6 receipt, 11 declared)
         values  0 verified, 0 contradicted, 8 couldnt_check

         13 listed files are not present here, so their bytes were not checked:
         sample.jsonl.zst, vectors.npy, queries.npy, projection.npy,
         ground_view_base.parquet, ground_view_queries.parquet,
         ground_view_centroids.parquet, report/report.json, report/report.html,
         report/simulate.json, report/verify.json, report/verify_info.json and
         report/characterization.json.
         No value was recomputed, because the release asset is not present.
         4 published values are not recomputed by this command:
         semantic_sharded.routing_ceiling, semantic_sharded.p50_copies,
         semantic_sharded.p95_copies and
         semantic_sharded.p99_copies_per_vector.
         The digests were checked before any value, so the 4 files that
         verified are the published bytes whatever happened to the values.
[exit 2]
```

The documented relative path: all eight values verified, exit 0, 35 m 26 s.

```
PS> .venv\Scripts\oneground.exe fixture verify arxiv-150k --asset fixtures\arxiv-150k
python  <scratch>\022b\ps\.venv\Scripts\python.exe  (venv)
fixture: arxiv-150k
directory: <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k
manifest: MANIFEST.sha256 (17 files listed)

preconditions
  fixture      found      <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k  (the installed package)
                          not in <scratch>\022b\ps\fixtures (the current directory)
                          <scratch>\022b\ps\fixtures\arxiv-150k holds vectors.npy, queries.npy and sample.jsonl.zst and no MANIFEST.sha256: that is the release asset extracted there, not the fixture. Pass --asset <scratch>\022b\ps\fixtures\arxiv-150k
  environment  pinned     numpy 2.5.3, faiss-cpu 1.15.0, scikit-learn 1.9.0
                          (pins from the installed oneground 0.1.0)
                          in a virtual environment
  asset        present    fixtures\arxiv-150k

digests
  verified      receipt  sample.jsonl.zst               404cb92e6d7dd42bde81798d86926b3b64e3cd069547a8ebef5c06120ae73655  (from fixtures\arxiv-150k)
  verified      receipt  vectors.npy                    141a9220703a03afa2451e4be3e0f034a787bc46a01a61ecd83c03f61529b8fa  (from fixtures\arxiv-150k)
  verified      receipt  queries.npy                    dbed194a42c1e5273e9a5d5a7224074950ab38c54030739423b6c5714c625b9b  (from fixtures\arxiv-150k)
  verified      receipt  query_ids.json                 a0f3236cd5a91a6c373eea206a4619a3291b226e36995697422622bf62bc4a8d
  verified      receipt  ground_truth.npy               ee0ad1349b22db3c5dca1df0ab870e648c59234c49d1fd1e0e36df3f13d86b8e
  verified      receipt  characterization.json          7c6d4d8a3c0e23f6b409997cd7ab856f048241c51878c15a827f913786d2d580
  verified      declared build_info.json                bf5e8e1b49366f8eb11e31bf3e989c377830cab04f3cdd0a5e89a536de792afc
  couldnt_check declared projection.npy                 not shipped with the installed package; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k
  couldnt_check declared ground_view_base.parquet       not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k
  couldnt_check declared ground_view_queries.parquet    not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k
  couldnt_check declared ground_view_centroids.parquet  not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k
  couldnt_check declared report/report.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k
  couldnt_check declared report/report.html             not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k
  couldnt_check declared report/simulate.json           not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k
  couldnt_check declared report/verify.json             not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k
  couldnt_check declared report/verify_info.json        not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k
  couldnt_check declared report/characterization.json   not shipped with the installed package; the repository carries it; looked in <scratch>\022b\ps\.venv\Lib\site-packages\oneground\_fixtures\arxiv-150k and fixtures\arxiv-150k

values
  verified      intrinsic_dimensionality                recomputed 32.5533, published 32.55, delta 0.00325699, tolerance 0.5
  verified      boundary_crispness                      recomputed 0.0362467, published 0.036, delta 0.000246667, tolerance 0.02
  verified      skew_top10_share                        recomputed 0.0754, published 0.075, delta 0.0004, tolerance 0.02
  verified      ambiguous_query_rate                    recomputed 0.8915, published 0.891, delta 0.0005, tolerance 0.02
  verified      drift                                   before recomputed 0.523212, published 0.522, delta 0.00121244; after recomputed 0.551401, published 0.549, delta 0.00240097; tolerance 0.02
  verified      single_node_hnsw.recall_at_10           recomputed 0.9968, published 0.997, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.recall_at_10           recomputed 0.9318, published 0.932, delta 0.0002, tolerance 0.01
  verified      semantic_sharded.storage_amplification  recomputed 3.71516, published 3.715, delta 0.00016, tolerance 0.01

summary: digests 7 verified, 0 contradicted, 10 couldnt_check (6 receipt, 11 declared)
         values  8 verified, 0 contradicted, 0 couldnt_check

         10 listed files are not present here, so their bytes were not checked:
         projection.npy, ground_view_base.parquet, ground_view_queries.parquet,
         ground_view_centroids.parquet, report/report.json, report/report.html,
         report/simulate.json, report/verify.json, report/verify_info.json and
         report/characterization.json.
         Every value this command recomputes reproduced (8 of 8).
         4 published values are not recomputed by this command:
         semantic_sharded.routing_ceiling, semantic_sharded.p50_copies,
         semantic_sharded.p95_copies and
         semantic_sharded.p99_copies_per_vector.
[exit 0]
```

### Verification

- A correct `--asset` verifies; a wrong one exits 2: passed, by test and by
  execution.
- Every `&&` in a printed doc command split, or left with its reason: done.
- The venv requirement is stated in the README and `docs/EXTERNAL_RUN.md`, and
  named by the precondition, with the guard unchanged: done.
- The extracted-in-the-wrong-place case is named: passed, by test and by
  execution (runs 4 and 5 above).
- The `pytest` import: the `NameError` reproduced from the archive, and gone
  from an exported copy.

**Couldn't-check:**
- The macOS/Linux command blocks. This host is Windows; only the PowerShell
  blocks were run.
- The `SYSTEM INTERPRETER` wording outside the unit test. Producing it for real
  means installing the pins into this machine's system Python, which is the
  replacement the message warns about.
- The developer's figure of five replaced packages: not reproduced, and not
  quoted in the docs.

### Observed, not done

- ~~Two more tests fail only outside a git checkout~~ **Fixed in the final
  addition below.** At `ba3350c` this item recorded them as found and
  unfixed.
- **The live RunPod plan test is at the mercy of stock minute to minute.** It
  passed in the checkout run and failed in the exported-copy run started four
  minutes later: EU-RO-1 then offered L4, RTX 2000 Ada, RTX 5090 and RTX PRO
  4000, none of them the session's four types.
- With a correct `--asset` that names the tarball extracted in the current
  directory, the fixture line still suggests `Pass --asset <that folder>`.
  Redundant, not false (run 6 above).
- `RELEASE_NOTES.md`'s install block still says `. .venv/bin/activate   #
  Windows: .venv\Scripts\activate`. In PowerShell that runs `Activate.ps1`,
  which the default execution policy can block. It has no `&&`, so this task
  left it.
- The README's contributor block still clones
  `https://github.com/oneproof/oneground`, which returns 404 (first observed
  above). The lines were split, not re-pointed.

### Repo now contains (additions)

    oneground/fixture/verify.py        --asset checked explicitly; extracted asset named; venv line
    oneground/fixture/test_verify.py   8 tests
    oneground/test_environment.py      import pytest
    README.md                          venv required; macOS/Linux and PowerShell blocks; no &&
    docs/EXTERNAL_RUN.md               venv required; per-shell commands; wrong --asset stops the run
    tasks/022-fixture-verify-from-anywhere.report.md   this section, and the archive-zip finding

### Blocked on developer (additions)

1. Push `main`; the retag moves to the final commit named in the section
   below, not `c3615e1` or `ba3350c`.
2. The open question above: refuse a system interpreter outright, after the
   release?

---

## Final addition: the two git-dependent tests

### What was done

Both tests in `oneground/verify/test_matched.py` that ask git about the real
tree now call `_skip_unless_a_git_checkout()`. When `environment.tracked_files()`
cannot get an answer from git, the helper skips with the reason `not a git
checkout (no .git): git cannot say which files it tracks, and this test is
about what it tracks`. That is the same test the identifier scans use.

- `test_the_real_smoke_requirements_upload_exactly_the_vectors` skips before
  it loads anything.
- `test_the_arxiv_session_declares_a_tarball_and_a_manifest` skips only at its
  last step, the `git_carries` question. Its seven assertions about the
  session's fields run everywhere, including from a zip.

**Skip rather than read the tracked set another way:** an exported copy has no
index, so nothing outside git knows what git tracks. `.gitignore` alone says
what is ignored, not what is tracked.

### Measurements

The two tests, by name (`pytest -k`, `-rs`):

| where | result |
|---|---|
| the checkout | **2 passed.** They ran; the skip does not hide them where git can answer |
| an exported copy, no `.git` | **2 skipped**, `test_matched.py:413: not a git checkout (no .git): …` |

Full suite:

| where | passed | skipped | failed |
|---|---|---|---|
| the checkout | 812 | 0 | 0 |
| an exported copy, no `.git` | 804 | 7 | **1** |

**The one failure from the exported copy is the live RunPod plan test**, which
is environmental and stays recorded: `PlanError: none of the requested GPU
types is offered on SECURE in EU-RO-1 … offered here: A100 SXM, L4, RTX A4500`.
Nothing else fails.

**The seven skips from the exported copy, each with its reason:**
- the two identifier scans (`not a git checkout; nothing to scan`);
- these two tests;
- three that need a local workdir under `runs/`, which is gitignored and in
  no export (`no local arxiv-150k workdir …` in `test_end_to_end.py` and
  `test_matched.py`, `no local workdir for either fixture` in
  `test_claims.py`).

### Observed, not done

- **`runpod.git_carries` itself answers `untracked` when git cannot answer at
  all.** Outside a checkout, `git check-ignore` and `git ls-files` both exit
  128, and the function reads that as "untracked", the same over-read these
  tests had. It is only called while preparing a pod session, which runs from
  a checkout, so no run has met it; a third answer ("git could not say") would
  close it.

### Repo now contains (final addition)

    oneground/verify/test_matched.py   _skip_unless_a_git_checkout(), called by the two tests
    tasks/022-fixture-verify-from-anywhere.report.md   this section, corrected references above

### Blocked on developer

1. **Push `main` and retag `v0.1.0` at the commit that carries this section:**
   the one whose subject begins `task 022: the git-dependent tests skip`. Its
   hash is reported with the hand-off, not written here, since a commit
   cannot contain its own hash. Rebuild the artifacts and re-run the fresh-venv check.
2. The open question: refuse a system interpreter outright, after the
   release?
