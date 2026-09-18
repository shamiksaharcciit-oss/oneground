# Report: 024b-lab-mode-margin

## Repo state expected vs found

- **Branch:** as expected. `task-020` in the worktree, ten commits on `383c7a1` ending at `cdf0053`, clean tree. `main`, the tag and `site/teaser/` untouched; no rebase.
- **The brief:** the developer's message accepting 024, three items. It is not a file on the branch.
- **The host was not quiet, and I couldn't make it quiet.** For the whole task this laptop ran at 45–100% CPU with 0.1–0.5 GB of 7.6 GB physical memory free, nearly all of it taken by processes this task didn't start (the editor and other sessions). Every timing below was taken in that state. The five-restart result depends on it, and Measurements says how.

## What was done

**(1) The mode rule has a margin.**
- **The rule** (`oneground/lab/contract.py`, `oneground/lab/server.py`): at startup the server takes up to five readings, each a p95 of 20 whole ground draws across the ε range. It chooses **redraw on move only if every reading is within 12.5 ms**, which is `MARGIN = 0.25` inside the 16.7 ms frame (`THRESHOLD_MS`). When the readings **straddle** the threshold, or all sit **above** it, it chooses **render on release**. Ties go to release.
- **The first reading above the threshold settles it,** so measuring stops there. A slow host starts after one reading; only a host that is heading for redraw on move takes all five.
- **The margin is stated, not tuned.** A host whose p95 fits 12.5 ms has room for its p95 to rise by a third before a dragged control trails the drawing. I picked 25% because it is a round, defensible number, not to reach a particular outcome on this laptop.
- **What the decision carries.** `RenderMode` now carries every reading (`readings_ms`), the verdict (`within`/`straddled`/`above`), the threshold, the margin, and the p95 pooled over all draws (recorded, not used to decide). `p95_ms` is the highest reading, the one the decision turned on.
- **Where it shows.** The startup line, the page header, the check footer and the ground's caption all show the readings and the verdict, e.g. `render on release: ground draw p95 20.9 ms, the highest of 1 reading of 20 draws (20.9 ms: above), threshold 12.5 ms = 25% inside the 16.7 ms frame`.
- **Docs.**
  - `docs/STATE.md`, interaction budget: adds the rule, why a decision needs a margin as well as a measurement, and 024's four readings as the evidence. The stale "Not built" bullet now points at `oneground lab`. The 023b figure of 11.2 ms is now annotated as fitting the threshold by only 1.3 ms.
  - `docs/LAB.md`, render modes: the table now uses the threshold, with the reasons for the tie rule, the margin and the early stop.
- **Tests.**
  - `test_the_mode_needs_every_reading_inside_the_margin_synthetic` replaces the one-frame test. It covers:
    - all readings within the threshold → move;
    - one reading above → release, verdict straddled;
    - readings of 16.0–16.6 ms, inside the frame but outside the margin → release;
    - 024's real readings (16.3, 17.8, 36.3, 26.2) → release;
    - an override keeps the measured choice;
    - no readings at all → refused.
  - `test_measuring_stops_at_the_first_reading_above_the_threshold_synthetic` slows the draw to 20 ms and asserts exactly one reading was taken.

**(2) The interface, looked at in a browser.** Details are under Measurements.
- **How.** Headless Chrome, with a throwaway profile and background networking off, loaded the real page from a real `oneground lab` process at 20k (`runs/020-ref-stackexchange --also runs/021-eps-stackexchange`) and 150k (`runs/020-ref-arxiv --also runs/021-eps-arxiv`).
- **Shots.** For each corpus: ε 0.1 (simulated) and ε 0.15 (not simulated), with query 15, at 1440 px, plus ε 0.15 at 500 px. I read the screenshots themselves, not the responses.
- **To make that possible,** the page now takes `epsilon` and `query` from its own URL beside the token. They set the controls and nothing else. Documented in `docs/LAB.md`.
- **Fixed, because of what the screenshots showed:**
  - **The trace outlines had no key.** The figure caption named three kinds of outline, and nothing said which colour was which. There is now a key under the ground whose swatches use the canvas's own colours and weights.
  - **The routed region's outline covered its own vectors.** The 3 px outline was stroked over the first two rows and columns of that region's pixels, so the one region the trace is about had data hidden. Cells now have a 3 px gutter and every outline is drawn inside it. No outline covers a vector.
  - **Wording.** The header read `render on release — above: …`, with a bare verdict, and every surface said `1 reading(s)`. It now says `above the threshold` and `1 reading` / `5 readings`.
  - **Mixed path separators** in the footer (`…\state/MANIFEST.sha256`). Each path now uses the directory's own separator.
- **A defect of my own, caught by the second look.** The separator fix first put the JS literal `'\'` into `lab.js`, a syntax error that stops the whole script. All 44 lab tests passed with it, because they read `lab.js` as text and never run it.
  - I fixed the literal and added `test_the_interface_script_parses`, which runs `node --check` over the shipped `lab.js`.
  - The test doesn't pass by default: where node isn't installed it skips, and says why.
  - I confirmed it tells the two apart: `node --check` exits 1 on a copy with the broken literal and 0 on the shipped file.
  - The second set of screenshots is from the fixed script.

**(3) The faiss WMI line, dated.** It **predates the branch**. It also predates any oneground code in the stack, and it was first recorded on 2026-09-10, four days before the branch point.
- **It needs no oneground code.** A bare `python -X faulthandler -c "import faiss"`, run from a scratch directory outside any repo, prints `Windows fatal exception: code 0x8007000e`.
- **The stack:** CPython 3.12.10 `platform._wmi_query` ← `_get_machine_win32` ← `uname` ← `machine` ← faiss 1.15.0 `loader.py:33 is_sve_supported` ← `faiss/__init__.py:148`.
- **It is handled.** `_get_machine_win32` catches the `OSError` and falls back to `PROCESSOR_ARCHITECTURE`. faulthandler on Windows reports the exception when it is raised, before the handler catches it.
- **It appears only with faulthandler on.** pytest turns faulthandler on by default. No oneground file does (none of its `.py`, `.toml`, `.cfg` or `.ini` files mentions it), so the CLI, including the environment block it prints, doesn't show the line.
- **At the branch point.** `oneground/test_environment.py` from `383c7a1`, exported with `git archive` to the session scratchpad (no worktree or checkout touched), printed it in 1 of 4 runs. HEAD printed it in 1 of 4 runs, alternated with the base runs under the same host state.
- **Its recorded age.** Task 012 (`c4452d9`, 2026-09-10) recorded the same exception in the docstring of `oneground/calibrate/history.py:_node`: "Under memory pressure that query raises a Windows fatal exception (0x8007000E) that faulthandler prints on every call". Task 014 (`44c1773`, same day) removed `_node`, and that note went with it. What remains is the shorter note in `oneground/environment.py` (from `27173ae`, 0.1.0-preview), which doesn't give the code. faiss 1.15.0 was installed in the shared venv on 2026-09-08.

## Measurements

**What this laptop chose, five restarts at 20k.** Each restart is a real `python -m oneground.cli lab … --no-browser` process: I read its startup line and `/api/run`, then stopped it with Ctrl-Break (`tasks/scratch/024b-restarts.py`; results in `runs/024b-restarts.json`, token removed). I ran two sets. Set 1 used the rule before the wording fixes, with identical decision logic; set 2 used the committed code and recorded host load just before each start.

| 20k restart | set 1 p95 | set 1 choice | set 2 p95 | set 2 CPU / free memory | set 2 choice |
|---|---|---|---|---|---|
| 1 | 58.4 ms | release (above) | 20.9 ms | 99% / 0.34 GB | release (above) |
| 2 | **16.6 ms** | release (above) | 34.2 ms | 63% / 0.52 GB | release (above) |
| 3 | 22.4 ms | release (above) | 89.8 ms | 93% / 0.42 GB | release (above) |
| 4 | 34.3 ms | release (above) | 37.5 ms | 99% / 0.29 GB | release (above) |
| 5 | 20.7 ms | release (above) | 21.6 ms | 99% / 0.44 GB | release (above) |

- **The same answer every time: render on release, 10 of 10.** Every restart stopped after one reading, because its first reading was already above 12.5 ms.
- **The flip the brief named happened once, and the margin absorbed it.** Set 1 restart 2 read 16.6 ms, inside the 16.7 ms frame. 024's rule would have chosen redraw on move there, and render on release on the other four; the new rule chose release.
- **What this shows and what it does not.** It shows the choice is stable across restarts on this laptop in the state it was in: saturated CPU, under half a GB free. It does not show what a quiet laptop chooses, because no reading came near the threshold, so the straddle path never ran on the real host. 023b's quiet-host p95 at 20k was 11.2 ms, 1.3 ms inside the threshold. On a host like that, the rule chooses move only if all five readings fit, and release on any one that doesn't; I couldn't produce such a host to observe it.
- **150k, for context,** chose render on release on all 10 restarts: set 1 707.3, 340.1, 3,696.2, 530.3, 102.2 ms; set 2 63.0, 409.3, 82.5, 40.3, 29.3 ms. That spread, including one startup of 57 s, is the host's state: 024 measured 78.3 ms on the same run.

**What the browser showed.** Shots at 1440 px (ε 0.1 and 0.15) and 500 px (ε 0.15), for both corpora, saved to the session scratchpad, not the repo.
- **The ground at a simulated ε (0.1).**
  - **Layout.** A 16 × 16 grid of cells, one per region, each filled in id order and coloured by copy count from blue (1) to ochre (4). At 20k the cells are mostly partly filled strips; at 150k they are dense texture, about one screen pixel per vector at 1440 px.
  - **Readout.** The slider reads `0.100` with `simulated at ε 0, 0.1, 0.2, 0.3` (20k) or `0.1, 0.2, 0.3` (150k).
  - **The figures agree with the stored state.** I compared them with the simulated state at ε 0.1, read directly from its `copy_count` column rather than through the view:

    | figure | 20k | 150k |
    |---|---|---|
    | vectors copied | 15,819 | 112,190 |
    | storage | 2.872× | 2.667× |
    | p99 copies | 4 | 4 |
    | copies 1 / 2 / 3 / 4 | 4,181 / 3,688 / 2,643 / 9,488 | 37,810 / 31,689 / 23,119 / 57,382 |
  - **Caption:** "This epsilon was simulated, so the query trace's recall panel holds recall and candidates for it", then the rendering sentence.
- **The ground at an unsimulated ε (0.15).**
  - **The counters move:** 20k 18,759 copied, 3.557×; 150k 134,161, 3.326×. At 20k the copies histogram is 1,241 / 1,750 / 1,640 / 15,369, whose mean is 3.557, the storage figure.
  - **Caption:** "the geometry is recounted from state, and not simulated at this epsilon. No recall, candidate or missed-neighbour figure exists at this epsilon".
  - **The positions gap** reads in amber on both.
- **A query trace (query 15).**
  - **Steps.** Three numbered steps: scored against 2 regions with distances; routed to the nearest region, with the probed region and its reason; the ten true neighbours with their home regions.
  - **The outlines match.** At 20k: routed 246 in ochre, probed 113 in grey, neighbour homes 94, 190, 52, 65 and 5 in light outline, each where the layout puts that region.
  - **At ε 0.1 the recall panel shows the simulated figures:** 20k recall@10 0.80, 2 missed by the route; 150k 0.50, 5 missed. Both match the state's candidates when recounted from the stored columns, and both runs show 200 candidates returned.
  - **At ε 0.15 the panel is amber.** It reads "not simulated at this epsilon (0.15)", lists the simulated values, gives the cost (0.1–0.3 min at 20k, 3.2–6.6 min at 150k) and shows the `oneground simulate … --emit-state` command with its grid.
- **The mode caption.** A bordered line under the title, e.g. `rendering: render on release — above the threshold: ground draw p95 14.9 ms over 1 reading of 20 draws on this host against 12.5 ms (25% inside the 16.7 ms frame)`. The same sentence ends the ground's caption. Between the two looks, the first shot's `above:` and `reading(s)` were fixed.
- **The footer's digests.** One row per manifest: `…\020-ref-stackexchange\MANIFEST.sha256: 6 of 6 verified`, `…\state\MANIFEST.sha256: 3 of 3 verified`, and 6 of 6 and 4 of 4 for the `--also` run. arXiv shows 6/3/6/3. There is also a render-mode row with the readings, `writes: nothing: the lab has no write path`, and the token row. The paths are absolute, as the server reports them, and wrap without clipping at 500 px.
- **500 px.** Everything stacks into one column and wraps, with nothing clipped and no sideways scroll. My first narrow shot, at 420 px, appeared to clip. A probe page showed headless Chrome won't lay out narrower than 500 px (`innerWidth 500`) and crops the image, so that shot was an artifact of the capture and was replaced.

**The WMI line, counts.** Separate processes, each started fresh; the host state varied between batches.

| what ran | faulthandler | printed the line |
|---|---|---|
| `import faiss`, scratch directory | on | 1 of 3, then 6 of 15, then 1 of 15 |
| `import faiss`, scratch directory | off | 0 of 3, then 0 of 15 |
| `import platform; platform.machine()` | on | 3 of 15 |
| `test_environment.py` at `383c7a1` (pytest) | on | 1 of 4 |
| `test_environment.py` at HEAD (pytest) | on | 1 of 4 |

## Verification

- **The lab's tests:** `oneground/lab/` — 45 passed (27 lab, 18 server), including the two new mode tests and the parse test.
- **The full suite:** 841 passed, 3 skipped (024 had 839 and 3; the three are the same local arXiv workdir gates: `test_claims.py:443`, `test_end_to_end.py:348`, `test_matched.py:1182`).
- **The published figures still reproduce.** Task 020's unchanged acceptance script (sha256 `9fc0a0d9…`) passes 20 of 20 on the arXiv state rendered through `corpora/render_from_state.py` after this change. That is all it shows: it reads the published figures and nothing else.
- **The composer's output is unchanged.** The same rendering equals task 020's `render.json` in all 24 compared fields across 2,000 queries (`tasks/scratch/021-render-equivalence.py`). This task changed no view and no state column. `GroundView` appends the rendering sentence only when it is given a render mode (`views/ground.py:190`), and the composer doesn't give it one.
- **The lab sessions left the runs' manifested files intact.** All 24 lab processes in this task (20 restarts, and 4 screenshot sessions, one per corpus in each of the two looks) ended with `oneground lab: stopped. Nothing was written.` After the last of them, every manifest in the eight directories verifies (`tasks/scratch/024b-manifests.py`): 6 of 6 in each run directory; 3, 4, 3 and 3 in the four `state/` directories. That covers the files the manifests list. That no file is added, and no write attempted, is proved by the read-only test in `test_server.py`, not by this.
- **The environment guard's scan of tracked files,** run over the staged tree with this report in it: the identifier tests pass (5 selected from `oneground/test_environment.py`, including `test_no_tracked_file_carries_a_machine_identifier` and `test_the_scan_actually_reads_the_tree`). The whole file is re-run after the commit.

## Observed, not done

- **A latent `NameError` in the identifier-scan tests, on `main` too.**
  - **Where:** `oneground/test_environment.py`, in both `test_no_tracked_file_carries_a_machine_identifier` and `test_the_scan_actually_reads_the_tree`.
  - **What:** each calls `pytest.skip("not a git checkout; …")` in its non-git branch, but the file never imports `pytest`.
  - **Effect:** in a git checkout the branch is unreachable, so it never fires. From a `git archive` export (the WMI bisection above) both tests fail with `NameError` instead of skipping.
  - **Why I didn't fix it:** a one-line fix, but in a file on `main`, outside this brief, and just before the rebase.
- **Copies 3 and 4 are close in colour at 1:1.** Zoomed in, tan (`#B79C63`) and ochre (`#E0A83A`) separate; at the page's own scale a region mostly at 4 copies with some at 3 reads as one ochre block. The ramp is the teaser's own four values (`lab.css` says so), so I didn't change it.
- **The ground's caption prints the simulated set as a Python list** (`Simulated: [0.0, 0.1, 0.2, 0.3]`), while the recall panel prints `0, 0.1, 0.2, 0.3`, and the caption uses `--` for a dash. The caption comes from the view, and changing it changes drawings; left alone.
- **Nothing tests how the page renders.** The parse test only proves `lab.js` is valid JavaScript. The look was manual screenshots from a scratch script (`tasks/scratch/024b-look.py`). An automated browser test would need a browser wherever the suite runs.
- **Widths under 500 px are unverified.** Headless Chrome won't go narrower.

## Repo now contains

On `task-020`, not pushed, one new commit after `cdf0053`:
- **Changed:**
  - `oneground/lab/contract.py`: `MARGIN`, `THRESHOLD_MS`, the verdicts, and `RenderMode` with its readings and `evidence()`.
  - `oneground/lab/server.py`: `MODE_READINGS`, readings with an early stop, `choose_mode` over readings, and the startup line.
  - `oneground/lab/static/lab.js`: the verdict in words, the plural, the gutter layout, one separator in the footer, and `epsilon`/`query` from the URL.
  - `oneground/lab/static/index.html`, `lab.css`: the outline key.
  - `oneground/lab/test_server.py`: the mode tests replaced, the early-stop test, the parse test, and a runner that reports skips.
  - `docs/STATE.md`: the interaction budget's margin rule, and where the rule is built.
  - `docs/LAB.md`: render modes with the margin; the outline key and start parameters.
- **New:** this report.

No measured value, tolerance, seed, gate, fixture file or published figure was changed. The frame, 16.7 ms, is 023b's; the margin is new and stated.

## Blocked on developer

- **Whether 25% is the margin you want.** It is stated in one place (`contract.MARGIN`) and in both docs. On this laptop it decided nothing that 5% wouldn't also have decided, because every reading was far above either threshold. It matters only near the frame, which a quiet host would test.
- **The rebase is still held.** On the 23rd, before anything else, `task-020` is rebased onto `main`, which has moved (a licence file, and task 022 in progress). The branch will then be eleven commits deep.
