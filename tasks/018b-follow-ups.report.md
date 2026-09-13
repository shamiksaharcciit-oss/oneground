# Report: 018b-follow-ups

Three follow-ups to 018, taken while the release waits for the 23rd.

## Repo state expected vs found

| expected | found |
|---|---|
| `main` after task 018 | `6ddcb5e task 018: oneground 0.1.0 — and three more places the winner's verdict was lent`, tree clean |
| the `v0.1.0` tag, local | present, annotated, pointing at `6ddcb5e`; **not** moved by this task, which commits on top of it |
| 757 passed, 1 skipped | yes |

Nothing pushed, published or uploaded, before or after.

## What was done

### 1. The coverage walk now reaches every rendering path, not the sections

**The gap, stated plainly.** 018's source-derived registry collected the
functions `render_html` calls **directly**. That is six section functions plus
two helpers — eight names. `_verdict_cell` was not one of them, because it is
called by `_options_table` rather than by `render_html`.

`_verdict_cell` is where 018's defect lived. The registry that exists to stop
a rendering path going uncovered did not know about the function it had just
been written for, and a sibling added beside it would have escaped the same
way.

`_html_sections()` became `_html_render_paths()`: a **transitive** closure from
`render_html` over every module-level function, following calls recursively,
and including functions defined *inside* another (a rendering path does not
stop being one for being a closure). Eight names became thirteen.

**The thirteen, and how each is classified:**

| path | class | what it renders |
|---|---|---|
| `_recommendation` | **verdict** | one row per verdict; each carries its engine |
| `_options_table` | **verdict** | one cell per constraint |
| `_verdict_cell` | **verdict** | the cell itself: collapsed outcome + every engine |
| `_label` | **verdict** | an outcome word, including couldn't-check |
| `_log` | **verdict** | the decision log, verbatim, sentences and all |
| `_ground` | no verdict | characterization numbers and the projection |
| `render_projection` | no verdict | a PNG of this run's own projection, or None |
| `_receipts` | no verdict | the input digests table |
| `_calibration` | no verdict | the calibration citation in the footer |
| `_fmt` | no verdict | number formatting; takes a float, not a verdict |
| `esc` | no verdict | HTML escaping |
| `_tokens_css` | no verdict | the stylesheet, read from `docs/design/tokens.css` |
| `row` | no verdict | nested in `_ground`; one characterization row |

The five newly reached are `_verdict_cell`, `_label`, `_fmt`,
`render_projection` and `row`. Two of them — `_verdict_cell` and `_label` —
carry verdicts, and neither was in the old set.

**Classifying is not covering, so the registry is executable.** Naming a path
in a table proves nothing: that is precisely the trap 018's first negative
control sprang, where a check written against the whole rendered page *passed*
with the broken cell restored, because the page embeds the decision log and
the log names every engine. So
`test_the_property_actually_executes_every_verdict_carrying_path` wraps each
function in `HTML_VERDICT_PATHS` in a counter, runs the property's own
`_units()`, and fails on any that were never called. A path can only be
claimed as covered if the property demonstrably reaches it.

Two consequences fall out of that, both asserted:

- a nested function **cannot** be classified as verdict-carrying, because a
  closure is not reachable as a module attribute and the counter could not
  prove anything about it. `_ground.row` is therefore in the no-verdict half
  by construction, not by opinion;
- every classification, in either half, must carry a reason longer than a
  word, so the table cannot decay into a list of names.

### 2. `pyproject.toml`, the other direction

018 asserted that every pin matches `requirements.txt` and that every adapter
has an extra. It never asked the reverse question — whether what an extra
installs is what its capability needs — and that is the same blind spot that
let `[pgvector]` not exist for three tasks: nothing read the file, so nothing
could notice either direction.

Five tests added, each with the direction it checks:

| test | the defect it catches |
|---|---|
| `test_every_extra_installs_only_what_that_capability_needs` | an extra installing a distribution **nothing in the tree imports** — a download a user pays for and never uses |
| `test_no_extra_installs_another_extras_dependency` | `[qdrant]` dragging in matplotlib; a shared dependency belongs in the core list, stated once |
| `test_no_extra_repeats_a_core_dependency` | two pins for one package, free to drift apart |
| `test_every_guarded_pin_is_exact_and_matches_requirements` | `environment.PINNED` spelled out in one place: exact `==`, equal to `requirements.txt`, in the **core** list |
| `test_the_extras_the_readme_lists_are_exactly_the_extras_that_exist` | both directions — an advertised extra that does not exist fails at `pip install`; an extra nobody advertises is undiscoverable, which is how `[pgvector]` stayed missing |

**The distribution-to-module map is read from the interpreter, not written
here.** `top_level.txt` is absent from most modern wheels — torch, pyarrow,
matplotlib and qdrant-client all omit it — so the check inverts
`importlib.metadata.packages_distributions()`, which is built from the
installed files. A hand-maintained table would be one more thing to drift.

Two distributions are legitimately installed and imported by nothing here, and
each is listed with its reason rather than filtered out:

- **`pywin32`** — a Windows-only transitive of `qdrant-client` via
  `portalocker`, pinned so the version is fixed, with the marker that keeps a
  Linux install resolving;
- **`psycopg-binary`** — the compiled backend `psycopg` loads. `import
  psycopg` is ours; `psycopg_binary` is psycopg's, and installing it is what
  removes the libpq build dependency.

A distribution that cannot be resolved in the running interpreter is recorded
as unresolvable rather than treated as wrong, and a floor assertion stops an
all-unresolvable run from passing as a clean one. On this interpreter nothing
was unresolvable: all eleven extra dependencies resolved, nine imported, two
exempt.

### 3. The ten-minute figure now says what it assumes

One paragraph in `RELEASE_NOTES.md` and one in `docs/EXTERNAL_RUN.md`, beside
the existing "values take about ten minutes":

> **That ten minutes assumes the machine is not paging.** The recomputation
> loads the fixture's 460 MB of vectors and builds indexes over them, so it
> wants a few spare gigabytes; on a laptop already short of RAM the same work
> takes far longer in wall clock for the same few minutes of CPU — the run
> that cut this release took **2 h 06 m for 588 seconds of CPU**, about 95% of
> it waiting on page faults, with 225 MB of physical memory free. Nothing is
> wrong when that happens, and the answer is identical; only the clock is
> different.

`EXTERNAL_RUN.md` carries one extra sentence, because it is the document
written to be forwarded to a stranger who has no reason to trust us:

> (The peak memory the command actually needs has not been measured. On the
> run above the working set was being trimmed continuously, so what it
> reported was how little the machine would let it keep, not how much it
> wanted.)

**A first draft of this said "holds roughly 2 GB of vectors and index in
memory at once".** That number was not measured — it was a plausible-sounding
guess, in a document whose whole claim is that its numbers are not. The 460 MB
is the vectors file's exact size; the peak is unknown, and now says so.

## Measurements

### The suite

| point | passed | failed | skipped |
|---|---|---|---|
| after 018 | 757 | 0 | 1 |
| after 018b, run 1 (loaded machine) | 763 | **1** | 1 |
| after 018b, run 2 (same commit, quiet) | **764** | 0 | 1 |

**+7 over 018's 757**: `test_no_lent_outcomes.py` 13 -> 15 and
`test_packaging.py` 8 -> 13. `pytest --collect-only` reports **765
collected**, which is 764 run plus the one skip.

**Run 1 had one failure and run 2, on the same commit, did not.** The
difference is the machine, not the code, and the mechanism is proved below
rather than inferred from the two runs disagreeing. Both are reported: a green
run on its own would have hidden something a release-day run can hit.

### The failure in run 1: a latent timing flake in `restart_engine`'s test

```
FAILED oneground/verify/test_verify.py::test_the_engine_name_is_substituted
E   Failed: DID NOT RAISE VerifyError
```

**Not caused by 018b, and not by 018.** Neither
`oneground/verify/__init__.py` nor `oneground/verify/test_verify.py` has been
touched since `df5dcb6 task 017f`; nothing in either task went near them. It
passes in isolation, which is the first sign it is about the machine.

**The mechanism, reproduced deterministically**
(`tasks/scratch/018b-restart-flake.py`). The test passes `timeout=2.0` to
`restart_engine`, which spends that budget **twice**:

1. as the `subprocess.run` timeout for the restart command, and
2. as the budget for the readiness-probe loop.

The test's intent is the second — pgvector cannot answer a probe at
`http://localhost:1`, so the loop expires and raises `VerifyError`. But if the
restart command does not *finish* within 2.0 s, `subprocess.run` raises
`TimeoutExpired`, which `restart_engine` catches and **returns** on:

```python
except (OSError, subprocess.SubprocessError) as e:
    return f"not restarted: {how} could not be run ({e})"
```

A return, not a raise — and `pytest.raises` then fails. The function is right
to do that (a restart command that will not run is a fact about the session,
not a reason to abort), and the test is right about what it wants; they
disagree about which of the two seconds is being spent.

The command is `python -c "import sys; sys.exit(0)"`, so the flake is
"can this machine start a Python interpreter in under two seconds". Measured
here, during and after the suite:

```
under load (measured while chasing the failure)
  6 spawns: 0.60 0.21 0.31 1.04 0.53 2.93 s   -- one over the 2.0 s budget
quiet
  12 spawns: min 0.20  median 0.30  max 0.55  -- none over
```

And forced, so the diagnosis does not depend on catching the machine slow:

```
spawn exceeds the budget -> returned
  not restarted: `...python.exe -c "import sys; sys.exit(0)" # pgvector`
  could not be run (Command ... timed out after 2.0 seconds)
```

Nothing about the engine-name substitution — what the test is named for — is
wrong. **Not fixed here**; see *Observed, not done*, and *Blocked on
developer*, because it can turn the release-day suite run red for a reason
that is not a defect.

### The rendering-path walk

```
before (one level, from render_html only):  8 paths
after  (transitive, incl. nested defs):    13 paths
newly reached: _verdict_cell, _label, _fmt, render_projection, row
of those, carrying verdicts: _verdict_cell, _label
```

### The extras check, on this interpreter

```
files scanned for imports: 96      distributions resolved: 97

  calibrate  h5py                   IMPORTED
  embed      sentence-transformers  IMPORTED
  embed      torch                  IMPORTED
  pgvector   psycopg                IMPORTED
  pgvector   psycopg-binary         exempt (psycopg's compiled backend)
  qdrant     pywin32                exempt (Windows transitive of the client)
  qdrant     qdrant-client          IMPORTED
  test       pytest                 IMPORTED
  view       matplotlib             IMPORTED
  view       pyarrow                IMPORTED
  view       umap-learn             IMPORTED
```

Nothing unresolved, nothing unaccounted.

### Negative controls

Every new guard was run against the bug it guards, with the defect injected at
runtime so nothing on disk is left broken.

`tasks/scratch/018-negative-controls.py`, three added (6–8):

```
control_6_a_rendering_path_nobody_classified   caught
control_7_the_one_level_walk                   caught
control_8_a_path_named_but_never_executed      caught
unpatched                                      15 test(s) green
```

Control 7 is the one worth naming: it restores the **pre-018b one-level walk**
and requires the current test to fail on it, so the widening cannot be undone
by a refactor that looks like a simplification.

**Control 8 did not work on the first attempt**, and the reason is the same
mistake in miniature. It first claimed `render_projection` as verdict-carrying
on the reasoning that it returns `None` early when there is no workdir — but
*returning early is still being called*, the counter saw 1, and the control
passed against the bug. An early return is not an unreached path. The control
now installs a function nothing calls at all.

`tasks/scratch/018b-packaging-controls.py`, eight controls, all caught:

```
an extra installs something nothing imports   caught
two extras share a dependency                 caught
an extra repeats a core pin                   caught
a guarded pin becomes a range                 caught
a guarded pin drifts from requirements.txt    caught
an extra the README does not list             caught
the README advertises one that does not exist caught
[pod] quietly gains a dependency              caught
unpatched                                     13 test(s) green
```

Each rewrites what `_project()` returns rather than editing `pyproject.toml`,
so the file on disk is never in a broken state even if a control raises.

### Docs numbers

`tasks/scratch/018-docs-numbers.py` re-run after the doc edits: 15 + 15
published values present in `docs/FIXTURES.md`, 13 quoted numbers in
`README.md` and `docs/CHARTER.md` each traceable to a spec, the one-line
comparison verbatim. **ALL CHECKS PASSED.**

## Verification

**Passed.**

- The transitive walk reaches 13 paths where the old one reached 8, and the
  test fails if it ever finds only 8 again.
- Every verdict-carrying path is proved **executed** by the property, by call
  count rather than by assertion; a path that stops being reached is caught.
- All eleven extra dependencies resolve on this interpreter; nine are imported
  by this project and two are exempt with stated reasons.
- Sixteen negative controls across the two scripts, every one caught.
- The docs-numbers script still passes after the doc edits.

**Couldn't check.**

- **The peak memory `fixture verify` needs on a 150k fixture.** Stated as
  unknown in `docs/EXTERNAL_RUN.md` rather than estimated. Measuring it wants
  a run on a machine with headroom, which this one does not have.
- **The extras check only proves a distribution is imported *somewhere*,** not
  that it is imported by the capability the extra names. `[qdrant]`
  installing `h5py` would pass that test — it is caught instead by the
  no-overlap test, because `h5py` is already `[calibrate]`'s. A distribution
  used by exactly one capability and put in the wrong extra would pass both.
  See *Observed, not done*.
- **Nothing was run on a pod and no money was spent.**

## Observed, not done

- **Per-capability import attribution.** The honest version of "installs only
  what it needs" would map each extra to the modules that *its* code path
  imports — `[view]` to `characterize --project` and the HTML projection,
  `[calibrate]` to `oneground/calibrate/` — and require the distribution to be
  imported from there. That needs a capability-to-source-tree map, which is a
  declaration that can drift, so the cheaper check went in first and its limit
  is recorded above rather than left to be discovered.
- **The same transitive treatment is not applied to `report/__init__.py`.**
  The decision-log registry still derives from `add("<kind>")` literals in two
  named functions plus `compare_engines`'s dicts. That is the right shape for
  a log built from labelled entries, and no sentence there is produced by a
  helper the way `_verdict_cell` was — but the walk is by name, and a third
  log builder would have to be added to the list by hand.
- **`_fmt` and `esc` are classified as rendering no verdict, and that is true
  of what they *decide*.** Both are called from inside verdict-carrying paths,
  so a defect in either would show up in the property's output; neither is
  separately driven.
- **`restart_engine`'s test spends one budget on two things.** The flake
  above is not a bad number or a wrong assertion; it is `timeout=2.0` being
  handed to both the `subprocess.run` that starts the restart command and the
  probe loop that is actually under test. Two fixes are available and neither
  is "raise the timeout", which would be changing a threshold to make
  something pass:

  1. **Separate the budgets in `restart_engine`** — a spawn timeout and a
     readiness timeout are different quantities, and a session that wants to
     wait three minutes for an engine to come back does not want to wait three
     minutes for `pg_ctl` to *start*. This is the real fix and it is a change
     to shipped code.
  2. **Make the test not depend on spawn latency** — it is named for the
     `{engine}` substitution and the message, neither of which needs a real
     subprocess to be slow or fast.

  Not done: the brief names three items and this is none of them, and the
  first option changes behaviour on a pod two days before a release.

- **The suite now takes about seven minutes.** Nothing here made it slower,
  and the two new files add about eleven seconds between them, but it is worth
  recording that the loop from change to green is no longer fast -- and that a
  seven-minute suite on a loaded machine is exactly the condition that makes
  the flake above fire.

## Repo now contains

Changed:

    oneground/report/test_no_lent_outcomes.py   _html_render_paths (transitive);
                                                HTML_VERDICT_PATHS /
                                                HTML_NO_VERDICT_PATHS; two tests
                                                proving execution rather than
                                                naming
    oneground/test_packaging.py                 five tests on what extras install,
                                                plus the distribution->module
                                                resolution read from the
                                                interpreter
    RELEASE_NOTES.md                            the paging caveat
    docs/EXTERNAL_RUN.md                        the paging caveat, and that peak
                                                memory is unmeasured

New:

    tasks/018b-follow-ups.report.md             this report

Not tracked (`.gitignore:62`):

    tasks/scratch/018-negative-controls.py      three controls added (6-8)
    tasks/scratch/018b-packaging-controls.py    eight controls, new
    tasks/scratch/018b-extras-block.py          the inserted block, kept for review
    tasks/scratch/018b-restart-flake.py         the flake, measured and forced

## Blocked on developer

The 018 list stands unchanged — push `main` and the `v0.1.0` tag, create the
release with both assets, paste `RELEASE_NOTES.md`, `twine upload` — and none
of it has been done. **`RELEASE_NOTES.md` changed in this task**, so the
version pasted on the 23rd should be the one on `main` then, not a copy taken
earlier.

**One decision, before the 23rd.**
`test_verify.py::test_the_engine_name_is_substituted` can go red on a loaded
machine, for the reason diagnosed above and not for any defect. Release day
runs the suite (`docs/RELEASE.md` step 0), so it can fire then, and a red tick
beside a good release is the combination 017b called the worst one. The
options are in *Observed, not done*; the fix worth having is separating
`restart_engine`'s spawn timeout from its readiness timeout, which is a change
to code that runs on a pod and therefore wants its own brief rather than being
slipped in beside a release.
