# Report: 023b-interaction-budget

## Repo state expected vs found

- **Branch:** as expected. `task-020` in the worktree at `9ddeda7` (task 023, accepted), six commits on `383c7a1`, clean tree. `main`, the tag and `site/teaser/` untouched; no rebase.
- **The brief:** the developer's message. Re-establish the interaction figure properly, with no new measurement of the code; then state the budget and the fallback in `docs/STATE.md`.
- **Nothing unexpected.**

## What was done

**No code was changed.** This task measures and documents. The diff is `docs/STATE.md` and this report.

**(1) The figure, re-established.** `tasks/scratch/023b-timing.py` times three paths and reports distributions:
- **Interleaved at every ε.** Task 021's unchanged recount (the control), `views.ground.recount`, and a whole `contract.draw(GroundView(...))` run back to back at each position, so drift lands on all three equally and the pairing survives it.
- **Six rounds of 40 positions**, ε order shuffled per round from a fixed seed, so no path can sit on a slow patch of wall clock.
- **A drift probe:** a fixed 4M-element numpy sum, timed once per round, touching neither the state nor the lab. It shows what the host is doing to everything else.
- **Reported as distributions** — median, p05, p25, p75, p95, max — pooled over 240 positions and per round, plus the paired `recount / control` ratio, which cancels drift.

**(2) The budget and the fallback, in `docs/STATE.md`.** A new section, "The interaction budget, and what a host that cannot meet it must do":
- **The threshold** is p95 of a whole ground draw within one frame of the host's refresh rate (16.7 ms at 60 Hz), not the median.
- **Why p95 and why it is an honesty question.** A median inside the frame with a p95 outside it stutters; a draw slower than the event rate builds a backlog, so what is on screen belongs to an ε the control has already left, and a screenshot then carries figures under the wrong ε.
- **The fallback** is render on release: while dragging, the ε readout follows the control and the ground stays as last drawn, captioned with both numbers ("showing ε 0.20; release to redraw at 0.35"); on release, one recount and one redraw.
- **The host decides**, by timing its own first draws on the machine and corpus in front of it, and the chosen mode goes in the ground's caption.
- **Marked not built:** there is no lab UI; mode selection is a requirement on the lab when it is built.

The measured block in the same section was replaced with the distributions below, and task 021's single figure is now described as what it was.

## Measurements

**Pooled over 240 positions** (6 rounds × 40), median with [p05–p95]:

| | 20,000 vectors | 150,000 vectors |
|---|---|---|
| task 021's recount, unchanged (control) | 1.4 ms [0.8–2.6], max 5.3 | 12.4 ms [7.9–20.6], max 45.9 |
| `views.ground.recount` | 1.1 ms [0.7–2.4], max 3.8 | 11.4 ms [7.2–17.9], max 29.3 |
| **whole ground draw** | **6.7 ms [4.3–11.2]**, max 25.6 | **21.3 ms [14.3–34.6]**, max 58.4 |

**The paired ratio, which drift cannot move:** `recount / control` is 0.845 [0.61–1.15] at 20k and 0.917 [0.73–1.13] at 150k. The view's recount is not slower than the path task 021 measured; it does slightly less work.

**Per-round medians, within one quiet session:**

| round | 150k control | 150k draw | 20k draw |
|---|---|---|---|
| 1 | 8.9 ms | 15.7 ms | 7.5 ms |
| 2 | 8.9 | 15.3 | 5.4 |
| 3 | 12.4 | 21.4 | 4.5 |
| 4 | 13.5 | 21.9 | 6.9 |
| 5 | 13.4 | 21.9 | 6.7 |
| 6 | 14.4 | 24.2 | 7.1 |

**The drift probe** (a fixed 4M-element numpy sum, once per round): 2.0, 3.6, 2.3, 3.5, 2.1, 2.2 ms — a 77% spread. The host varies by nearly 2× while nothing about the code changes, and the 150k draw's per-round median rises 58% across the same session.

**What this says about the earlier figures.**
- **Task 021's "14 ms, inside a frame"** was one pass on a machine whose state nobody recorded. It is near the fast end of today's distribution (p05 of a draw at 150k is 14.3 ms).
- **Task 023's 44.7 ms** was a worse day, and its own control established that at the time.
- **Neither was wrong as a reading; both were wrong as *the* figure.** A single number from this distribution cannot carry a design decision.
- **The decision is unchanged.** 21 ms typical against 194–398 s for a rebuild: four orders of magnitude, which no plausible machine state closes.

**Against the budget**, on this laptop: 20,000 vectors passes (p95 11.2 ms < 16.7 ms); 150,000 vectors does not (median 21.3, p95 34.6). By the rule now in `docs/STATE.md`, a lab on this laptop would redraw on move for a 20k corpus and on release for a 150k one.

## Verification

- **No code changed**, so task 023's suite result stands: 823 passed, 3 skipped. The diff is `docs/STATE.md` and this report; `git diff` over the commit shows no `.py` file.
- **Identifier scan** run over both changed files before the commit, and over the committed tree after.
- **The measurement is reproducible** from `tasks/scratch/023b-timing.py` with its recorded seed, rounds and positions; raw samples are summarised in `runs/023b-timing.json`.

## Observed, not done

- **Why the host drifts is not diagnosed.** Thermal state, power profile and background work are all plausible on a laptop; I measured that it drifts and by how much, not which of those it is. The drift probe makes it visible on any future run.
- **No optimisation, and no new measurement of the code.** The fixed per-draw cost task 023 attributed (the contract's defensive header copy, ~1–2 ms) is unchanged and still named there.
- **The mode selection is documented, not implemented.** No lab UI exists to select or display it, and `render_from_state.py` draws once per invocation, where the question does not arise.
- **The budget is stated for the ground.** The query trace's geometric half is far cheaper (0.66 ms at 150k, task 021), and its recall panel is never live, so neither changes the mode.
- **One laptop.** Every figure here is from the developer's machine. The rule in `docs/STATE.md` is written so that no host has to trust these numbers.

## Repo now contains

On `task-020`, not pushed, one new commit after `9ddeda7`:
- `docs/STATE.md`: the re-established distributions, the drift evidence, and the interaction budget with its fallback.
- This report.

No measured value, tolerance, seed, gate, fixture file or published figure was changed, and no code was touched.

## Blocked on developer

Nothing. Standing by: `task-020` holds until the 23 September release, and on release day it is rebased onto `main` before anything else. The branch will be seven commits deep.
