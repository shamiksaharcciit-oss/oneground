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

**Operable without a terminal is necessary and not sufficient.** A person
meeting this tool for the first time has to see, quickly, that it tells
them something they do not know. Three of the steps below are about that
first minute rather than about the surface: a run opens on its finding
rather than on its files (step 4), `--demo` gives someone with no corpus a
real run to look at (step 2), and a refusal is never the dullest thing on
the page (step 6). The file list is navigation; the finding is the product.
A reader who lands on a directory listing has to be taught what to look
for. A reader who lands on *nothing is recommended, because the storage
budget broke* has already understood the tool.

## Do

1. **The command grows, the lab does not shrink.** `oneground lab
   <workdir>` keeps working exactly as today. `oneground ui [<runs-dir>]`
   is the new entry — the same server, the same token, the same guard,
   pointed at a directory of workdirs rather than one. With no argument
   it uses `./runs`. A directory holding a single workdir behaves as the
   lab does today, so the lab is not a special case of the UI.

2. **`--demo`: a real run, one command from install.** `oneground ui
   --demo` opens on a published fixture's own run — the arXiv 150k
   workdir, with its real report, real receipts and the lab — fetching
   what it needs if absent, with the download **named and sized before it
   starts** and a refusal if the user declines.

   Three rules, and the first is the one that makes this worth having:

   - **It is a real run, not a mock.** Real receipts, real digests
     verifying, the real report with its real couldn't-checks. Nothing on
     screen is fabricated for the demonstration, and the page says which
     fixture it is and where the data came from.
   - **It is labelled as someone else's corpus**, in the view rather than
     as fine print: *this is the public arXiv-150k fixture, not your data*
     — and the label survives a screenshot, as the lab's projection
     caption does.
   - **It offers the way out.** One visible route from the demo to the
     user's own data: what a `requirements.yaml` needs and where their
     vectors go. In this slice that is documentation, since nothing writes
     a file yet; slice 2 makes it a form.

   The demo problem is real — a person installs this and has nothing to
   point it at — and the honest solution already exists: three fixtures
   with published values, digests and reports. Two minutes from install to
   understanding, without a single fabricated number. **The demo fetches a
   published asset and nothing else; it does not run a command to produce
   one.**

3. **Many runs.** The landing page lists every workdir under the runs
   directory: name, corpus (from `characterization.json` if present),
   when, which stages have run (which receipt files exist), the report's
   verdict if `report.json` exists, and the version that produced each
   (033's field, or `null` with its reason for older runs). Each row's
   receipts verified against its `MANIFEST.sha256` before it is listed,
   as the lab does today, and a run whose digests fail is listed as
   *unverified* with the failing file named — never hidden and never
   shown as sound.

4. **A run opens on its finding, not on its files.** Selecting a run
   opens a landing page that **leads with what the report concluded and
   the number that decided it**. The pages are below it.

   ```
   Nothing is recommended.
   semantic_sharded[ε=0.2, probe=2] — storage 3.72× against a budget of 2.0×
                                      recall 0.932 — meets
   1 meets · 6 fails · 1 couldn't check
   ```

   The headline sentence and its deciding row come from `report.json`'s
   own claims, rendered through the same renderer as everything else — no
   new prose, no summary written by the UI. The drawer opens from that
   number as from any other.

   A run with no report leads with the furthest stage it reached and what
   would take it further: the decision log's own remedy sentence where one
   exists, never a UI-written suggestion.

   Its pages, each a view under the 021 contract, each reading only the
   declared columns of one receipt:
   - **characterize** — `characterization.json`: the five measures, with
     the definitions block beside them.
   - **simulate** — `simulate.json`: the table, with the routing/index
     decomposition and (after 034) the memory decomposition, labels as
     recorded.
   - **verify** — `verify.json`: the RTT baseline, the recall pass, the
     load rows, the spread across runs, the restart probes.
   - **report** — `report.json`: see 5.
   - **the ground** and **the trace** — as built, unchanged, now a page
     of the run.
   A page whose receipt is absent says so — *characterize has not run
   for this workdir* — and never renders an empty table as if it were a
   result.

5. **The report, whole, with the evidence drawer.** Every sentence in
   `report.json` is a `Claim` carrying the rows it cites (task 019). The
   report page renders the claims and the drawer renders their citations:
   select any figure or sentence, and the drawer shows the file and field
   it was read from, its kind (receipt or declared), the value at that
   field, and — for a couldn't-check — what would settle it, in the
   decision log's own words. The drawer never computes; it looks up what
   the claim already cites. Test it by rendering the real arXiv report and
   asserting that every claim has a drawer entry and every entry resolves
   to a real field in a real file.

   The drawer is reachable from the headline of step 4 as from anywhere
   else: the deciding number on a run's landing page opens it.

6. **A refusal is never the dullest thing on the page.** Everything
   valuable in this tool comes from what it refuses to say, and a
   couldn't-check rendered as a grey box a reader skims past would quietly
   undo the property being demonstrated. So, each of these tested as the
   other rules are tested:

   - Couldn't-check has **equal visual weight** to meets and fails — not a
     muted variant of them, not a smaller row, not a collapsed section, in
     the tokens already published.
   - Selecting a couldn't-check is **the most informative click on the
     page**: it opens the drawer on the reason and the remedy, which is
     the only outcome that ends in something the reader can do.
   - Any summary that counts outcomes shows **all three counts always,
     including zeros**. `1 meets · 6 fails · 0 couldn't check` is a
     different statement from `1 meets · 6 fails`, and the second invites
     a reader to forget the third exists. This covers the run list of
     step 3 and the headline of step 4 as well as the report page.

7. **Two runs side by side, under the comparability verdict.** Selecting
   two runs shows them beside each other **only** with the verdict
   `docs/LIBRARY.md` §2.2 defines — comparable, not comparable,
   couldn't-check — computed from the two runs' receipts (same
   requirements digest, same sample digest, same seed, same run-level
   settings, same oneground version). A not-comparable pair renders as two
   observations with a divider and the reason; the page must not let a
   reader's eye line up two numbers the verdict says are not comparable.
   Today every pair of pre-033 runs is couldn't-check on the version, and
   the page says so rather than rounding it.

8. **The guard grows with the surface.** `guard.py`'s checks run over
   every new view module and over the transport, as they do for the lab's
   two, and the server still refuses to start if any imports a measuring
   package. Add a test that walks every module under `oneground/ui/` (or
   wherever the views land) and asserts it is either a view under the
   contract or transport under the transport rules — no third kind.

9. **Read-only, proved as the lab proves it.** After a session that
   exercises every page of every run in a real runs directory, every
   `MANIFEST.sha256` under it verifies unchanged and no file was added.
   The lab's existing test does this for one workdir; extend it to a
   directory of them.

10. **Looked at, not only tested.** Open it in a real browser against a
   runs directory holding at least the arXiv 150k workdir, the 20k
   synthetic one, and one with no report — at 1200 px and 500 px — and
   report what you see, as observations. A page that returns 200 and
   renders nothing readable is the defect 025 found, and the browser test
   from 025 is the one to extend.

11. **Docs.** `docs/LAB.md` becomes `docs/UI.md` (keep the old name as a
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
- A run opens on its report's own headline claim and deciding row,
  rendered through the claim renderer, with the drawer reachable from it.
- A run with no report leads with its furthest stage and the decision
  log's own remedy.
- `--demo` opens a real published run, names and sizes the download before
  fetching, labels the corpus as not the user's **in the view**, and
  points at how to use their own.
- Couldn't-check has equal visual weight, opens the drawer on its remedy,
  and appears in every outcome count including at zero — each tested.
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
- Fabricate anything for the demo, or let it run a command to produce what
  it shows: it fetches a published asset and nothing else.
- Fetch the demo's asset without naming and sizing it first, or leave the
  user without a refusal.
- Let the UI write the headline. The finding on a run's landing page is
  `report.json`'s own claim through the claim renderer, and a run with no
  report gets the log's own remedy rather than a suggestion.
- Render a couldn't-check as a muted, smaller or collapsed variant of the
  other two, or drop a zero count from an outcome summary.
