# Task 041 — The interface, slice 1: read

## Setup
Branch `task-041` from `main` after `task-039` has merged (it carries
`docs/INTERFACE.md`, which is this task's specification — read it whole
first; where this brief and the paper disagree, the paper wins and you
say so). Commit `task 041:` and push after every commit.

## Why
The interface becomes the primary way to operate oneground. This slice is
its read half, and only that: many runs, the report whole with its
evidence drawer, and the lab reached from a run rather than from a
separate command. **Nothing runs from the UI in this slice.** No job, no
form that writes a file, no session. Slice 2 adds those; this one has to
be shippable and honest without them.

It is the lab's own machinery extended. Everything the lab already
guarantees — loopback only, token in the URL, read-only proved by
unchanged digests, the rendering contract that forbids a view from
computing a measurement, the guard that refuses to start if a view or a
transport module imports a measuring package — carries forward unchanged
and now covers every view of a run, not two.

## Do

1. **The command grows, the lab does not shrink.** `oneground lab
   <workdir>` keeps working exactly as today. `oneground ui [<runs-dir>]`
   is the new entry — the same server, the same token, the same guard,
   pointed at a directory of workdirs rather than one. With no argument
   it uses `./runs`. A directory holding a single workdir behaves as the
   lab does today, so the lab is not a special case of the UI.

2. **Many runs.** The landing page lists every workdir under the runs
   directory: name, corpus (from `characterization.json` if present),
   when, which stages have run (which receipt files exist), the report's
   verdict if `report.json` exists, and the version that produced each
   (033's field, or `null` with its reason for older runs). Each row's
   receipts verified against its `MANIFEST.sha256` before it is listed,
   as the lab does today, and a run whose digests fail is listed as
   *unverified* with the failing file named — never hidden and never
   shown as sound.

3. **A run's pages, each a rendering of a file.** Selecting a run opens
   it. Its pages, each a view under the 021 contract, each reading only
   the declared columns of one receipt:
   - **characterize** — `characterization.json`: the five measures, with
     the definitions block beside them.
   - **simulate** — `simulate.json`: the table, with the routing/index
     decomposition and (after 034) the memory decomposition, labels as
     recorded.
   - **verify** — `verify.json`: the RTT baseline, the recall pass, the
     load rows, the spread across runs, the restart probes.
   - **report** — `report.json`: see 4.
   - **the ground** and **the trace** — as built, unchanged, now a page
     of the run.
   A page whose receipt is absent says so — *characterize has not run
   for this workdir* — and never renders an empty table as if it were a
   result.

4. **The report, whole, with the evidence drawer.** Every sentence in
   `report.json` is a `Claim` carrying the rows it cites (task 019). The
   report page renders the claims and the drawer renders their citations:
   select any figure or sentence, and the drawer shows the file and field
   it was read from, its kind (receipt or declared), the value at that
   field, and — for a couldn't-check — what would settle it, in the
   decision log's own words. The drawer never computes; it looks up what
   the claim already cites. Test it by rendering the real arXiv report and
   asserting that every claim has a drawer entry and every entry resolves
   to a real field in a real file.

   The three outcomes keep equal visual weight, in the tokens already
   published. Couldn't-check is a result with a reason, never a greyed-out
   absence.

5. **Two runs side by side, under the comparability verdict.** Selecting
   two runs shows them beside each other **only** with the verdict
   `docs/LIBRARY.md` §2.2 defines — comparable, not comparable,
   couldn't-check — computed from the two runs' receipts (same
   requirements digest, same sample digest, same seed, same run-level
   settings, same oneground version). A not-comparable pair renders as two
   observations with a divider and the reason; the page must not let a
   reader's eye line up two numbers the verdict says are not comparable.
   Today every pair of pre-033 runs is couldn't-check on the version, and
   the page says so rather than rounding it.

6. **The guard grows with the surface.** `guard.py`'s checks run over
   every new view module and over the transport, as they do for the lab's
   two, and the server still refuses to start if any imports a measuring
   package. Add a test that walks every module under `oneground/ui/` (or
   wherever the views land) and asserts it is either a view under the
   contract or transport under the transport rules — no third kind.

7. **Read-only, proved as the lab proves it.** After a session that
   exercises every page of every run in a real runs directory, every
   `MANIFEST.sha256` under it verifies unchanged and no file was added.
   The lab's existing test does this for one workdir; extend it to a
   directory of them.

8. **Looked at, not only tested.** Open it in a real browser against a
   runs directory holding at least the arXiv 150k workdir, the 20k
   synthetic one, and one with no report — at 1200 px and 500 px — and
   report what you see, as observations. A page that returns 200 and
   renders nothing readable is the defect 025 found, and the browser test
   from 025 is the one to extend.

9. **Docs.** `docs/LAB.md` becomes `docs/UI.md` (keep the old name as a
   pointer), covering the command, the run list, the pages, the drawer,
   the comparability verdict, and the unchanged security model. Say
   plainly what this slice does not do: nothing runs from it, no file is
   written by it, and no session is created by it.

## Acceptance
- `oneground lab <workdir>` unchanged; `oneground ui` lists a directory
  of runs with digests verified and unverified runs named as such.
- Every page is a view under the contract; the guard covers all of them;
  the no-third-kind test passes.
- The report renders every claim with a resolving drawer entry, tested on
  the real arXiv report.
- Side-by-side gated by the comparability verdict; not-comparable pairs
  never share a row.
- Read-only proved over a directory of workdirs.
- Browser observations at both widths, three runs.
- `docs/UI.md` written, with what the slice does not do stated.

## Do not
- Run any command from the UI. Write any file. Create any session. Compute
  a measurement in a view. Let two not-comparable numbers share a row.
  Render an absent receipt as an empty result. Weaken any guarantee the
  lab has today.
