# Task 041, addition — the first minute

*To be merged into `tasks/041-interface-read.md` before it is executed.*

---

## Why this addition exists

041 as briefed makes oneground operable without a terminal. That is
necessary and it is not sufficient, because a person meeting this tool for
the first time has to see, quickly, that it tells them something they do
not know.

Three changes. None is large; all three are about the first minute.

## 1. A run opens on its finding, not on its files

The brief has selecting a run open a set of pages. Re-order it: a run's
landing page **leads with what the report concluded and the number that
decided it**, and the pages are below.

    Nothing is recommended.
    semantic_sharded[ε=0.2, probe=2] — storage 3.72× against a budget of 2.0×
                                       recall 0.932 — meets
    1 meets · 6 fails · 1 couldn't check

The headline sentence and its deciding row come from `report.json`'s own
claims, rendered through the same renderer as everything else — no new
prose, no summary written by the UI. The drawer opens from that number as
from any other.

A run with no report leads with the furthest stage it reached and what
would take it further — the decision log's own remedy sentence where one
exists, not a UI-written suggestion.

**Why:** the file list is navigation; the finding is the product. A buyer
who lands on a directory listing has to be taught what to look for. A
buyer who lands on *nothing is recommended, because the storage budget
broke* has already understood the tool.

## 2. `--demo`: a real run, one command from install

`oneground ui --demo` opens on a published fixture's own run — the arXiv
150k workdir, with its real report, real receipts and the lab — fetching
what it needs if absent, with the download named and sized before it
starts and a refusal if the user declines.

Three rules, and the first is the one that makes this worth having:

- **It is a real run, not a mock.** Real receipts, real digests
  verifying, the real report with its real couldn't-checks. Nothing on
  screen is fabricated for the demonstration, and the page says which
  fixture it is and where the data came from.
- **It is labelled as someone else's corpus**, in the view rather than as
  fine print: *this is the public arXiv-150k fixture, not your data* —
  and the label survives a screenshot, as the lab's projection caption
  does.
- **It offers the way out.** One visible route from the demo to the
  user's own data: what a `requirements.yaml` needs and where their
  vectors go. In this slice that is documentation, since nothing writes a
  file yet; slice 2 makes it a form.

**Why:** the demo problem is real — a person installs it and has nothing
to point it at — and the honest solution already exists. Three fixtures
with published values, digests and reports. Two minutes from install to
understanding, without a single fabricated number.

## 3. A refusal must never be the dullest thing on the page

Everything valuable in this tool comes from what it refuses to say. A
couldn't-check rendered as a grey box a reader skims past would quietly
undo the property being demonstrated.

So, tested as the other rules are tested:

- Couldn't-check has **equal visual weight** to meets and fails — not a
  muted variant of them, not a smaller row, not a collapsed section.
- Selecting a couldn't-check is **the most informative click on the
  page**: it opens the drawer on the reason and the remedy, which is the
  only outcome that ends in something the reader can do.
- A summary that counts outcomes shows all three counts always, including
  zeros. `1 meets · 6 fails · 0 couldn't check` is a different statement
  from `1 meets · 6 fails`, and the second invites a reader to forget the
  third exists.

## What does not change

Every guarantee in the brief and in `docs/INTERFACE.md`: nothing runs
from the UI in this slice, no file is written, no session is created, no
view computes a measurement, and the guard covers every new module. The
demo fetches a published asset and nothing else; it does not run a
command to produce one.

## Acceptance, added to the brief's

- A run opens on its report's own headline claim and deciding row,
  rendered through the claim renderer, with the drawer reachable from it.
- A run with no report leads with its furthest stage and the log's own
  remedy.
- `--demo` opens a real published run, names the download before
  fetching, labels the corpus as not the user's in the view, and points
  at how to use their own.
- Couldn't-check has equal weight, opens the drawer on its remedy, and
  appears in every outcome count including at zero — each tested.
