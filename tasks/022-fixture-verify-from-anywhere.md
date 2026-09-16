# Task 022 — `fixture verify`, from anywhere

## Expected repo state
`main` at or after `27ed14b` (the licence commit). The freeze is lifted
for this task. `stash@{0}` holds the unfinished 018e work on
`oneground/fixture/verify.py`; it is this task's starting point, not a
separate merge — check it against the current tree before popping, since
it predates 018b through 019 and may not apply cleanly. If it conflicts,
take its intent and write the change fresh; say which you did.

**This task moves the tag.** When it lands, `v0.1.0` is rebuilt from the
new commit and the artifacts are re-cut. Do not move the tag yourself —
report, and the developer drives the retag.

## Why
Core installed `oneground` from PyPI into a clean venv, outside any
checkout, and ran the command the announcement made loudest:

    oneground fixture verify arxiv-150k
    error: no such fixture directory: fixtures\arxiv-150k

The command is honest and the copy around it was not; the sentence has
been fixed. The command has not. It was built for someone standing
inside the repository, and every stranger who meets it stands outside.
Three defects, one stance.

## Do

1. **Resolve from the installed package, not only the cwd.** Fixture
   specs (`fixtures/<id>.fixture.yaml`) and directories
   (`fixtures/<id>/`) resolve in this order: an explicit `--fixtures
   <dir>` if given; the current working directory; then the installed
   package's own data. Ship the two fixture *specs* and their small
   artifacts (MANIFEST, characterization, build_info, query_ids,
   ground_truth) as package data in the wheel — they are a few hundred
   kilobytes and they are what the command reads. Vectors and queries
   remain a release asset and are never in the wheel. Report the wheel's
   size before and after.

2. **Name every missing precondition, not the first.** A run that cannot
   proceed prints all of them together, each with what it is and how to
   satisfy it: the fixture (found, or where it looked), the pinned
   environment (which packages differ, and that `pip install
   oneground==<version>` gives the pinned set), and the release asset
   (its name, its size, the release URL, and the `--asset <dir>` flag).
   A reader must learn the whole shape of what they need from one run,
   not from three.

3. **Three outcomes for the command's own failures** — the 018e intent.
   A value that cannot be recomputed for an environmental reason
   (MemoryError, a missing optional dependency, an unreadable input)
   becomes `couldnt_check` for *that value*, with its reason, and the
   command carries on with the rest, exiting 0 if nothing is
   contradicted. The digests are checked first, so a host that cannot
   hold a value has still confirmed the bytes — say that in the summary.
   A contradiction is never downgraded.

4. **The summary must not over-read its rows** — the defect core found
   in `check_hosted.py`, in this command's sibling. The closing sentence
   states what was observed, never a conclusion the rows do not support:
   "every value reproduced", "n values could not be recomputed on this
   host", "the asset is not present, so no value was checked" are
   different sentences and must not collapse into one. Apply the 019
   claim rule here by hand: every sentence reconstructible from the rows
   it cites, no universal quantifier unless it holds for every row.

5. **Prove it the way core found it.** Build the wheel, install it into a
   genuinely fresh venv from the wheel alone, `cd` to a directory that is
   not a checkout, and run:
   - `oneground fixture verify arxiv-150k` with no asset — must name all
     missing preconditions and exit non-zero, having checked what it can;
   - the same with `--asset <dir>` pointing at the extracted release
     asset — must verify digests and values;
   - `oneground fixture verify arxiv-smoke` — the scaffold fixture, whose
     values are `TO_BE_FILLED`; must report those as couldn't-check and
     exit 0.
   Paste each command's full output.

6. **Docs.** `docs/EXTERNAL_RUN.md` and `RELEASE_NOTES.md` updated to the
   new behaviour: the command now works from a bare install for digests
   and for values when the asset is supplied, and the preconditions are
   printed rather than guessed. Remove any sentence that is now false.

## Acceptance
- From a bare wheel install outside any checkout, all three commands in
  step 5 behave as described; outputs pasted.
- A missing precondition never produces a bare "no such fixture
  directory".
- An injected MemoryError on one value leaves the other values reported
  and the command exiting 0.
- Summary sentences pass the 019 rule; no sentence asserts more than its
  rows support.
- Wheel size reported before and after; suite green; identifier and leak
  scans clean.

## Do not
- Put vectors or queries in the wheel. Move the tag. Weaken a
  contradiction to a couldn't-check. Touch `site/teaser/`.
