# tasks/

Briefs (`tasks/NNN-name.md`) and the build agent's reports
(`tasks/NNN-name.report.md`). A brief is bounded: it is built, measured and
reported against, and anything discovered adjacent to it is recorded in the
report under "Observed, not done" rather than fixed in passing. Scratch
diagnostic scripts live in `tasks/scratch/`.

## Currently blocked

**041 — the interface, slice 1: read.** Cannot start. Its specification
(`docs/INTERFACE.md`) and its brief (`tasks/041-interface-read.md`) both
exist only on the unmerged branch `task-039`, so neither is on main. The
unmerged branch is the blocker, not the work; 041 begins the moment it
lands.

Three things settled while waiting, recorded here so they are not
rediscovered:

- **The pod session card is slice 2, not slice 1.** `docs/INTERFACE.md` §8
  assigns it to slice 1 as "a read"; the paper's own §4.2 mechanism forbids
  it, because `oneground/lab/guard.py` lists `oneground.pod` in `MEASURING`
  and the server refuses to start if a view imports it. Nor is there a
  recorded plan to render instead: `pod` `cmd_plan` prints and writes no
  receipt. The mechanism decides the slicing, not the sequencing, and the
  paper is to be corrected to say so.
- **The report page reads `report.json` as data.** `oneground.report` is in
  `MEASURING` as well, so the report page and its evidence drawer may not
  import `oneground/report/claims.py`. If the drawer needs something the
  JSON does not carry, that is a finding to report rather than an import to
  add.
- **`TRANSPORT_ALLOWLIST` is not a precedent to widen.** Both its entries
  are `vector-data`, and its own comment says the exemption covers naming a
  vector column, "never arithmetic or a measuring import".
