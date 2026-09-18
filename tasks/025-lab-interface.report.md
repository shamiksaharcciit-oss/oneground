# Report: 025-lab-interface

## Repo state expected vs found

| Expected | Found |
|---|---|
| `task-020`, thirteen commits on `383c7a1`, HEAD `707a97a`, clean tree | branch and HEAD as stated — **the tree was not clean** |
| the brief at `tasks/025-lab-interface.md` | present, committed |
| `main` moved (022–022c, the licence); do not rebase | not rebased, not touched |

**The tree carried ~970 uncommitted lines** across nine paths under
`oneground/lab/`, from the session that crashed: `runs.py`, `server.py`,
`static/index.html`, `static/lab.css`, `test_lab.py`, `test_server.py`,
`views/__init__.py`, `views/query_trace.py`, and an untracked
`views/query_index.py` registered as a third view. Reported before touching
anything; on instruction it was committed first, under its own label
(`f24ce3a`), so its authorship and my later changes stay separable.

## What was done

### 1. The inherited work, assessed before building on it

- **Suite:** 842 passed, 5 skipped. The two skips beyond 024b's three are
  environmental — no `node` on PATH, no `RUNPOD_API_KEY` — not new holes.
- **Guard:** `check_views()` and `check_transport()` both clean.
- **`query_index.py` is a view, not something computing.** It declares
  `QueryTraceView.reads` and touches nothing else; it tallies (integer
  comparisons, sums, list building) and calls no distance, norm or neighbour
  search; it derives every row from the trace view's own `located`,
  `ambiguity` and `_recall`, so the list and the trace cannot disagree; and it
  splits by ε exactly as the contract requires — geometric columns at any ε, a
  `recall` panel only over a state simulated at the ε asked for. The guard
  passes over it. It costs 105 ms at 20k and 150 ms at 150k for 2,000 queries,
  and 0.10 MB of JSON.
- **It is tested.** `test_lab.py:790` draws the index and the trace for every
  query and compares them. I had said it carried no committed test; that was
  true only while it was untracked, and is wrong now. The interface work was
  the unfinished part, not the view.

### 2. The landing stall: diagnosed in a browser, not over HTTP

**Reproduced first.** A real browser at a real server, both workdirs: the page
frozen at `Loading the run…`, `#ov-facts` and `#ov-receipts` empty, and **one
uncaught `TypeError: Cannot set properties of null (setting 'textContent')`**.

**The cause.** The prior session rewrote `index.html` for this task's interface
and left `lab.js` addressing the markup it replaced. Fourteen of the twenty-two
element ids it looked up no longer existed. `boot()`'s second line was
`text($('config'), …)`, and `text` is `el.textContent = value`, so it threw on
null — and the handler meant to report it,
`boot().catch((error) => text($('config'), …))`, called the same missing
element and threw before it could say anything. Hence a hang with nothing said.

The Query-trace card accepting focus was plain HTML focusability, not the
script being alive.

**Why nothing caught it.** 024 drove endpoints over HTTP; 024b read
screenshots. A 200 says nothing about whether the script consuming it ran.
024b's own `node --check` test skips where node is absent, and node is absent
here — so `lab.js` was neither parsed nor executed by anything in the suite.

**The fix.** `lab.js` rewritten against the markup that exists, and made to
fail visibly: every lookup goes through `need(id)`, which throws naming the id
and saying the two files disagree; `fail()` touches elements defensively and
cannot itself throw; and the placeholder is replaced as work proceeds —
*Reading the run… / Checking the receipts… / Drawing the ground…* — so a stall
names the step it stalled on.

Two further defects found while looking: the landing page waited on the query
index before finishing (it now completes first, and the index loads with the
trace), and the picker's rows were not refetched when ε moved, which left its
note reading *at ε 0.150* while the control stood at a simulated 0.1.

### 3. The interface (brief items 1–3)

Landing state naming the run, workdir and per-manifest digests, offering both
views; tabs with hash routing and **one ε control shared across them**; ticks
on the simulated values; the ground's four readouts, copies legend, caption and
gaps; the picker with search, ambiguity filter and four orderings; the four
hops; the recall panel under the ε rule; the mode caption.

**Copies 3 vs 4, without forking the palette.** The legend writes out each
count and share, and selecting a row isolates those vectors on the ground and
dims the rest.

## Measurements

All in a real browser (Edge, headless) against real `oneground lab` processes,
read out of the settled page. Full logs in `tasks/scratch/025-states-run*.txt`.

**The ε recount moves the readouts, and matches an independent reading.**
arXiv 150k:

| ε | vectors copied | storage | p99 | ceiling@10 |
|---|---|---|---|---|
| 0.100 (simulated) | 112,190 | 2.667× | 4 | 0.8952 |
| 0.150 (not simulated) | 134,161 | 3.326× | 4 | 0.9237 |
| 0.200 (simulated) | 144,563 | 3.715× | 4 | 0.9323 |

The ε 0.1 row equals task 024b's figures read independently from the state's
`copy_count` column (112,190 and 2.667×).

**The keyboard path**, real key events on `runs/020-ref-stackexchange`:
start 0.200 → `→` 0.205 → `←`×2 0.195 → `PageUp` 0.245 → `PageDown` 0.195 →
`Home` 0.000 (simulated) → `End` 0.500 (not simulated; readouts recount to
19,999 copied, 4.000×). That is the step sizes the control's own hint prints.

**Queries at both extremes, found through the picker's own ordering:**

| | query | recall@10 | found | outside routed region |
|---|---|---|---|---|
| all ten found | 45 | 1.000 | 10 of 10 | 0 of 10 |
| none found | 55 | 0.000 | 0 of 10 | 10 of 10 |
| arXiv, worst | 312 | 0.000 | 0 of 10 | 10 of 10 |

**The picker at 2,000 queries:** search "7" → 542; "zzz" → 0 with a line saying
so and a way back; ambiguous 1,856 / not ambiguous 144 / all 2,000.

**Both sizes.** 1200 px and 500 px, twelve states each. Canvas scales 620 px →
447 px; **no sideways scroll in any of the 12 states at either width**; zero
uncaught errors in every session.

**Cost.** query-index 105 ms (20k) / 150 ms (150k), 0.10 MB. One trace 0.3–0.4
ms. Startup 0.3–1.3 s.

## Verification

- **Suite: 845 passed, 5 skipped** (from 842/5; three new tests). Same five
  skips, all environmental.
- **Guard: clean** over `views/` and over the transport, re-run after every
  change.
- **The workdirs are unchanged.** After every browser session, **47 of 47**
  manifest digests verify across five run directories, and every lab process
  ended `oneground lab: stopped. Nothing was written.`
- **Identifier scan:** 7 selected tests pass, before and after commit.
- **The new tests catch the defect when it is put back.** With one id renamed
  in `lab.js`, `test_every_element_the_script_needs_is_in_the_page` fails
  naming the missing id, and the browser test fails reporting the title as
  *This run did not load* — the visible failure the fix adds, in place of the
  silent stall.

**Couldn't check.**
- **How it looks to you.** I read screenshots and the settled DOM; the brief's
  acceptance is your judgement on the 20th, which no test replaces.
- **`lab.js` is still not parsed by the suite where node is absent.** The new
  static test covers the failure mode that actually bit (markup/script
  disagreement) without a browser, and the browser test covers execution where
  a browser exists — but a syntax error on a machine with neither would still
  reach a commit.
- **Widths under 500 px**, as in 024b: headless Chromium will not lay out
  narrower.

## Observed, not done

- **`oneground/lab/cdp.py`** is new: a very small DevTools-protocol client on
  the standard library alone — no new dependency, because a browser test that
  needed `playwright` or `selenium` would be a heavy pin for one test. Nothing
  at run time imports it and `oneground lab` never loads it, so it is outside
  the transport guard's surface. If you would rather the repo did not carry a
  websocket implementation, the two browser tests are the only callers.
- **The region cells are ragged.** Each cell is sized for the largest region,
  so smaller regions leave the lower part of their cell empty. It is honest —
  id order, one cell per region, and the caption says it is a layout — but it
  reads as texture rather than structure at 150k. Not changed; it would be a
  layout decision, not a fix.
- **The ground drawing is still sent whole on each redraw** (1.8 MB at 150k),
  as 024 noted. Unchanged.
- **`runs/020-synth20k` predates `assignment.nearest_region`**, so its ceiling
  shows `—` and a `couldnt_check` gap, and its ε cannot be recounted. That is
  the contract behaving correctly, and it made a good test case.
- **The prior session's `index.html` and `lab.css` were kept as written.** I
  changed neither; the work was to make the script drive them.

## Repo now contains

On `task-020`, pushed to `origin` after each commit:

| commit | |
|---|---|
| `f24ce3a` | the prior session's nine paths, checkpointed under its own label |
| `957c365` | `lab.js` rewritten; `cdp.py`; three tests in `test_server.py` |
| `718d1a4` | the empty-picker state; `docs/LAB.md` "Using it" |

New: `oneground/lab/cdp.py`. Changed: `oneground/lab/static/lab.js`,
`oneground/lab/test_server.py`, `docs/LAB.md`. Scratch (gitignored):
`tasks/scratch/025_states.py`, `025_keys.py`, `025_shots.py`, `025-browser.py`,
`025-shapes.py` and their logs and screenshots.

No measured value, tolerance, seed, gate, fixture file or published figure was
changed. No view was given anything to compute. `main` and `site/teaser/` were
not touched, and the branch was not rebased.

## Blocked on developer

- **Open it on the 20th** against a real workdir — that is the acceptance, and
  it is the one thing I cannot do for you. `oneground lab runs/020-ref-arxiv
  --also runs/021-eps-arxiv` reproduces what I looked at.
- **The rebase** is still held for the 23rd, now sixteen commits deep.
