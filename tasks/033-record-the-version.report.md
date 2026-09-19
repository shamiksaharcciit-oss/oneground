# Report: 033-record-the-version

## Repo state expected vs found

On `task-032` at `43123b4`, which is where 033's brief was written and where
the developer asked for it to be built. Working tree clean apart from this
task. `main`, the tag, `site/` and the second worktree untouched.

Expected the three places that had paid for the missing field — 028b's commit
dating, 028c's three-revision measurement, `docs/LIBRARY.md` §2.2 — and found
all three, plus one the brief did not know about: **`calibration/history.jsonl`
already records an `oneground_version`**, the package version and not the
commit, in `FIELDS` since task 012. The project had made a quarter of this
decision already.

## The open decision, taken by measurement

The brief left one thing undecided and required it be decided with a count:
whether the **receipts** carry the version, or only the **declared** info
files. The count is `tasks/scratch/033-digest-count2.py`, and the first pass
(`033-digest-count.py`) was wrong in a way worth recording — it counted every
declared artifact, including `projection.npy` and the `ground_view_*.parquet`
files, which have nowhere to put a version and would not be rewritten by
either option. The corrected count is of documents that would actually gain a
field.

| | option A: declared only | option B: + receipts |
|---|---|---|
| fixture manifest lines that move | **6** | **13** |
| mentions in tracked prose | **8**, in 4 task reports | **20**, in 7 task reports |
| published fixture values that move | **0** | **0** |
| release asset digests that move | **0** | **0** |

Which lines, precisely: option A moves `build_info.json` in all four
fixtures plus `report/report.json` and `report/verify_info.json` in
`arxiv-150k`. Option B adds `characterization.json` in all four, plus
`report/characterization.json`, `report/simulate.json` and
`report/verify.json`.

**No fixture spec pins anything either option touches.** The specs pin the
corpus and its provenance — `snapshot_sha256`, `sample_sha256`,
`vectors_sha256`, `queries_sha256`, `weights_sha256`, `ground_truth_sha256`
— and `RELEASE_NOTES.md` pins the three tarball members, which are the corpus
files. So no published *value* moves under either option; what moves is
digests of files, prospectively, the next time a fixture is built.

### Whether the receipts already carry process facts

The developer's condition for reconsidering. The answer is **one artifact
does, and it is the one already carved out as the exception**:

| receipt | process facts today |
|---|---|
| `simulate.json` (written today) | **none** |
| `characterization.json` | **none** |
| `card.json` | `created_at`, `elapsed_seconds`, `environment` |

And the precedent is sharper than the absence: `simulate.json` **used to**
carry `build_seconds` and `query_seconds` in every row — the arxiv workdir's
copy still does, because it predates the change — and **task 020b moved them
out**, into `simulate_info.json:timings`, so that *"simulate.json depends only
on what was measured and two runs of the same code write the same bytes."*
This project has already decided this exact question once, in the direction
the developer's inclination points.

**Decision: option A.** The version is a fact about the process, the declared
files exist to hold facts about the process, and putting it in a receipt
would undo 020b's ruling for a field that has a home. `card.json` stays the
exception, for the reason the brief gave: a card's claim is a difference
between two rows, and the statement that the difference is real rather than a
difference of code needs both rows' versions.

## What was built

**One helper**, `receipts.producing_version()`, returning exactly five keys:

    {"version": "0.1.0", "commit": "<40 hex>" | None,
     "dirty": True | False | None,
     "source": "checkout" | "wheel" | "unknown", "note": "<why, when null>"}

It reads a build stamp first, then falls back to git in the package's own
tree, using `environment.checkout_root()` — task 022e's distinction — so that
*not a checkout* and *a checkout whose git cannot be run* are different
answers with different reasons rather than one silent null.

**The wheel case, answered by construction.** `setup.py`'s existing
`build_py` subclass now also writes `oneground/_build_stamp.json` with the
commit it was built from and whether that tree was dirty. Measured, not
asserted: a wheel built from this tree, unpacked into a directory that is not
a checkout and imported from there, answers

    {"version": "0.1.0", "commit": "43123b4d458d…", "dirty": true,
     "source": "wheel", "note": ""}

**Nine writers** record it beside the library versions they already
recorded: `build_info.json` from all three of its writers — `characterize`
(both paths), `fixture/build.py` and `calibrate/fixture.py`, because a
fixture build is the most canonical artifact this project produces and the
count above presumes its `build_info.json` moves — plus
`simulate_info.json`, `state/state_info.json`, `verify_info.json`,
`propose_info.json`, `report.json` (all three assembly sites), and every
calibration line.

`oneground_version` in a calibration line is **left as it is**: every line
ever written has one, and renaming it would make a reader compare old lines
to new by noticing a rename. The new `oneground` object sits beside it. It is
deliberately **not** added to `FIELDS`, which is the required set `validate`
enforces — making it required would invalidate every line already written,
which is the history this task exists to make readable.

**The card carries two.** `configurations.changed.oneground` is this run's;
`configurations.baseline.oneground` is read from the workdir's
`simulate_info.json`, and where that predates this task the card carries a
stated absence rather than nothing:

    {"version": null, "commit": null, "source": "unknown",
     "note": "the run that measured this row was written before task 033,
              so it recorded no version"}

## Measurements

| | |
|---|---|
| `oneground/receipts/test_provenance.py` | **18 passed** |
| whole suite | **1028 passed, 2 skipped** in 372 s |
| wheel built and inspected | stamp present, commit correct, `source: wheel` from outside a checkout |
| identifier scan | **0 findings over 396 paths** |

## Verification

- **The version is always answered; a commit is 40 hex or null with a
  reason.** Both asserted, and the null paths are driven rather than
  described: a stamp without a commit, no stamp and no checkout, and a
  checkout whose git cannot run each have a test that reads the reason.
- **The branch-name guard**, which the brief asked for as the defect one move
  away. It parses `receipts/__init__.py` and `setup.py` and fails on any short
  string literal containing `--abbrev-ref`, `symbolic-ref`, `branch`,
  `remote`, `describe`, `for-each-ref` or `config user`. Prose that explains
  the rule is allowed — the check is on string constants under 40 characters,
  which is what a git argument is — for the same reason task 014's
  `platform.node()` guard exempts docstrings.
- **Every writer records it**, asserted per file, plus an end-to-end
  synthetic `simulate` run that reads the field back out of both
  `build_info.json` and `simulate_info.json`.
- **An old artifact reads as couldn't-check**, and the arxiv workdir is
  asserted to *still* have no version — the test fails if anything ever
  writes one into it, which is the repair the brief forbids.
- Couldn't check: **the sdist path.** A wheel built from an unpacked sdist
  has no git and no stamp of its own, so it would answer `commit: null` with
  the reason. That is the honest fallback and it is untested here; PyPI ships
  both artifacts and pip prefers the wheel.

## Observed, not done

1. **`FIELDS` in `calibrate/history.py` now describes less than a line
   carries.** It is the required set, and correctly so, but a reader looking
   for the shape of a line will not find `oneground` in it. A separate
   optional-fields list would say so; the brief did not ask for one.
2. **The sdist path is the one place the claim is still conditional.** A
   wheel built from an unpacked sdist has neither git nor a stamp of its own
   and answers `commit: null` with the reason. Honest, and the only route by
   which a published artifact could carry no commit.
3. **Nothing consumes the field yet.** `docs/LIBRARY.md` §2.2 now says a card
   whose rows carry the same commit can say `comparable`, and no code computes
   that verdict — the library is unbuilt, which is where it belongs.

## Repo now contains

    oneground/receipts/__init__.py          producing_version, the build stamp reader
    oneground/receipts/test_provenance.py   18 tests, including the branch-name guard
    setup.py                                writes _build_stamp.json at build time
    oneground/characterize.py               build_info.json records it
    oneground/simulate/__init__.py          simulate_info.json and state_info.json record it
    oneground/verify/__init__.py            verify_info.json records it
    oneground/proposals/propose.py          propose_info.json, and the card's two
    oneground/report/__init__.py            report.json records it
    oneground/calibrate/history.py          every new line records it
    docs/VALIDATION.md                      what the field means, and that null is an answer
    docs/LIBRARY.md                         §2.2 points at the field rather than at a future
    tasks/033-record-the-version.report.md  this report
    tasks/scratch/033-digest-count*.py      the count (untracked, .gitignore:62)
