# Task 055 — The VectorDBBench importer

## Setup

New branch from `main`: `git checkout -b task-055 main`. Commit `055:` and
push after every commit. No pod required — the importer reads files a user's
own VectorDBBench run already wrote; oneground does not install, vendor or
run VectorDBBench itself (`docs/BRIDGE.md` §5).

## Why

`docs/BRIDGE.md` §8: "The first implementation is the exporter and its
verification... The importer follows." The exporter and its round-trip
verification are done (task 051, `oneground/bridge/export.py` +
`query_subset.py`). Nothing is blocking the importer — no pending decision,
no resource. §4 sets what it must and must not do; this brief is that
section made buildable.

## Do

1. **Read VectorDBBench 2.0.0's own result-writing source first**, the same
   primary-source method `docs/BRIDGE.md`'s epigraph describes for the
   exporter ("read from the source... not from its documentation"). §4 names
   *what* comes back — QPS, latency percentiles, recall, index build time,
   load duration, engine, engine version, VectorDBBench's version, host —
   but not the file format or column names to parse it from, because that
   research was not yet done when the position was written. Determine: the
   result file's format and location, the per-case row schema, how a
   failed or timed-out case is represented in it (a sentinel value, a
   missing row, a status column), and where the composite/aggregate score
   this task must never import actually lives in that same file, so it can
   be named and excluded rather than merely not reached for.
2. **Import only the raw per-case numbers.** Never VectorDBBench's
   composite score, even where it sits in the same row or file as the raw
   numbers this task does import — the exclusion is by field, not by file.
3. **A failed or timed-out case imports as `couldnt_check`**, naming the
   reason, never coerced into a number (§4: VectorDBBench's own scoring
   rounds a failure into "half the lowest QPS, double the maximum latency"
   — that rounding is exactly what must not cross the bridge). *Corrected
   after item 1's research: VectorDBBench's own runner catches the
   exception, logs it, and discards it — the persisted file carries a
   label (timeout-class or not) and nothing else. There is no captured
   "timeout value that fired" to name; where the case's own configuration
   declares a concurrency-search timeout, report that as the configured
   value for that one stage, not as the timeout that ended the case.*
4. **Label every imported row** with the engine and its version (§4's
   labels, as far as the file carries them). *Corrected after item 1's
   research: VectorDBBench's own version and the host it ran on are not in
   the result file at all — not in the schema, not in any real result file
   shipped in the package. `null` with a stated reason, not a refusal and
   not a fabrication.*
5. **The table rule, refused at construction.** A VectorDBBench row and an
   oneground row may share a table only when the ground truth, the query
   subset and the corpus digest all match — the construction path for any
   table mixing the two sources must make the non-matching case
   structurally unbuildable, on the pattern §4 cites from 026 and 034 — not
   a check a caller can skip, and not a warning beside a table that renders
   anyway. Task 051's `query_subset.json` closes the gap §4 flagged (no
   receipt could express the query subset before it existed) — this is the
   first place that receipt gets consulted rather than just written.
   *Corrected after building: `oneground.comparability.
   rows_may_share_a_table` (task 041/043) is not the right function to
   consult for the verdict, and this is worth stating plainly rather than
   using it anyway and hiding the mismatch. It requires a second axis —
   oneground's own code, libraries and platform ("measuring") — to agree
   as well as the three §4 actually names ("measured"). A VectorDBBench row
   was not measured by oneground and carries no `measuring` half at all, so
   that function's `comparable` branch is unreachable for any table a
   bridge row is in — it would refuse every bridge table on an axis §4
   never asked about. The refusal reimplements only the three keys §4's
   blockquote states, reusing `MEASURED_KEYS` and the same three-valued
   comparison `oneground.comparability` already defines, so the meaning of
   same/differs/unknown is one definition, not two — only which keys are
   asked about is narrower, and on purpose.*

## Acceptance

- A fixture shaped like a real VectorDBBench result (built from item 1's
  research, not guessed) imports its per-case QPS, latency percentiles,
  recall, index build time and load duration correctly, and a test proves
  the composite/aggregate score in the same fixture is *not* imported —
  present in the source, absent from the import. That is this task's
  mutant for item 2.
- A fixture representing a failed case and one representing a timed-out
  case each import as `couldnt_check` naming the reason (which of the two
  VectorDBBench itself distinguishes) — a second mutant, proving a number
  is never fabricated for a case that did not complete.
- A third mutant proves the table-construction refusal: two rows whose
  ground truth, query subset or corpus digest disagree cannot be placed in
  one table, by construction, not by a check the caller could have skipped.
- Every imported row carries the engine and its version where the file
  records one; `vectordbbench_version` and `host` are `null` with a stated
  reason on every row, since the file never carries either.
- Round-trip verified the way the exporter's own task did: a known,
  synthetic VectorDBBench-shaped result imports to exactly the numbers it
  was built from.
- Full suite green, guard clean, identifier scan runs rather than skips,
  `site/teaser/` diff empty.

## Do not

- Install, vendor or run VectorDBBench, or add it as a project dependency.
  The importer reads files the user's own run already produced.
- Resolve whether a VectorDBBench recall that disagrees with oneground's
  own, for the same configuration, is a finding about the engine, the
  harness, or oneground's own measurement (§7 — explicitly unsettled).
  Import and label the disagreement where the table rule allows it to be
  shown at all; do not adjudicate it.
- Import the filtered-search or streaming cases, or the scalar-labels path
  (§7 — both explicitly deferred, each its own comparability question).
- Decide whether the export belongs in `report` or its own command (§7) —
  that is the exporter's open question, not this task's.
- Build anything toward a UI presentation of a mixed table. This is the
  importer and the construction-time refusal only.
