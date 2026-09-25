# Report: 063-propose-translate-cli

## Repo state expected vs found

Expected `main` at `c2c65b2` (task 062's merge) with `oneground/
proposals/translate.py` fully built and tested (task 059) and no
`oneground propose translate` command anywhere in `oneground/cli.py`.
Found exactly that; branch `task-063` created from `main` at that
commit.

## What was done

**The finding, first, because it outranks the command.**
`tasks/finding-a-capability-with-no-command.md`: `translate.py` passed
every test it had, satisfied `docs/PROPOSALS.md` §2.1 in full, and had
no way for a person to reach it — no CLI verb, no endpoint. Not a bug in
the module or its tests; both did exactly their job. The general form:
tests call functions, users call commands, and nothing in this
project's practice connected the two automatically or asked whether
they were connected. A task's report template has a slot for what was
built and what tests exercise it; it has none for whether a person can
reach it, so a report can be complete by its own template and still
leave the door unbuilt.

**`oneground propose translate <workdir> --describe "..." --model
...`**, built per `docs/PROPOSALS.md` §2.1's own two-phase shape.
Dispatched before the shared `build_parser()` ever sees it
(`oneground/cli.py::_dispatch`), the same pattern `fixture`/`pod` already
use, because `translate`'s flags (`--describe`, `--model`, `--endpoint`,
the sampling parameters) do not fit `propose`'s existing `--policy`/
`--prediction` contract. Guards itself via `envmod.guard_or_exit`,
manually, the same way `_cmd_fixture` does — registered in `oneground/
test_environment.py`'s `GUARDS_ON_USE` rather than by decoration, for
the same reason `fixture verify`/`fixture build` are there.

**Refuses without `--model`, one line, exit 2 — `docs/PROPOSALS.md`
§2.1's own words, unchanged, verified reaching a real terminal.** No
default is threaded through anywhere in the new code; `--model` has no
argparse default of its own, so its absence reaches `translate()`'s own
refusal untouched.

**On success, prints the policy twice, deliberately — the plain
rendering and the file, in full — then stops.** `oneground.proposals.
translate.render_policy_plain(policy_doc)` is new: one sentence naming
the family and each parameter change, then the rationale quoted as the
proposer's own words (never as a claim the CLI is endorsing). The raw
`policy.yaml` is printed after it, byte for byte from the file just
written, so a reader checking the sentence against the source does not
have to trust the sentence. The command's last lines name what
approval actually is and the exact next command to run — `oneground
propose <workdir> --policy <file> --prediction <prediction.yaml>` —
never run automatically. Verified directly: the command's own `runs/*/
proposals/` directory does not exist afterward; nothing measured.

## The audit: is this an isolated incident?

Checked rather than assumed. Four more built, tested capabilities in
this tree have no CLI command or lab/interface endpoint: `oneground.
library.card_schema.submit_card` (task 058), `oneground/bridge/
import_result.py` (task 055), `oneground/bridge/export.py` (task 051),
`oneground/verify/load.py::run_load_per_node` (task 057). No further
undocumented case was found beyond these four and `translate.py` itself
— every other package (`adapters/`, `chunk/`, `simulate/`, `report/`,
`truth/`, `sample/`, `embed/`, `cost/`, `comparability.py`, `supervisor.
py`, `models/`) has confirmed CLI or lab-endpoint reachability.

**Every one of the four is a different case from `translate.py`, and
the difference is what matters.** Each was self-reported as unwired in
its own task report's "Observed, not done" section, at the moment it
shipped — `translate.py`'s was too. What sets `translate.py` apart is
what happened next: its gap closed one task cycle later, because this
finding's own trigger (the developer asking, directly, whether it was
reachable) made it the thing being looked at. The other four have sat
self-reported across as many as seven subsequent tasks — task 060's own
state-of-the-product inventory re-confirmed several of them by name in
its own audit — with no follow-up task closing any of them. Writing
"no CLI command" in a report does not turn out to be what closes that
gap; a later task actually building the command is the only thing that
has, so far, exactly once.

**Not fixed here.** Wiring the other four is a decision about each on
its own terms — `export.py`/`import_result.py` share an open question
`docs/BRIDGE.md` §7 already names ("does the export belong in `report`
or as its own command"); `card_schema.py`'s `submit_card` has no
submission surface to attach a command to yet (`docs/LIBRARY.md`'s own
scope); `run_load_per_node` has no requirements-file field to select it
from. This report names all four together, once, so the pattern is on
record; closing any of them is its own task.

## The pathguard catch, recorded — and a count checked rather than taken

**Confirmed: two genuinely new write sites caught and fixed by this
specific test** (`oneground/receipts/test_pathguard.py::test_no_
receipt_write_site_records_a_machine_local_path`), not four. Checked via
`git log --all -S"public_path" -- oneground/ corpora/` plus a grep for
this test's name across every `tasks/*.report.md`. Task 044f built the
guard and found its four *founding* sites — declared `KNOWN_OPEN`, a
permanent, argued exemption for a resolvability reason, not a catch the
guard forced a fix for. Task 053's own report explicitly states this
test ran and *nothing new triggered it*. That leaves exactly two: task
051 (the bridge exporter's card, fixed with `public_paths_in()`) and
task 062 (this session, `oneground/proposals/refusal.py`'s `policy_
path`, fixed with `public_path()`). **Task 062 is the first of the two
where the catch also exposed a bug in the test written to check it** —
`test_a_policy_beside_a_translation_card_is_authored_by_model` compared
the receipt's (correctly sanitised, post-fix) path against the raw,
unsanitised one the test itself still held, and failed until the test
was fixed alongside the module. If a third or fourth instance exists
beyond what this search found, it belongs named here by whoever can see
it; this report states two because two is what a repo-wide search and a
report-wide grep actually turned up.

## Measurements

4 of 4 new CLI tests pass (`oneground/test_cli_propose_translate.py`),
against the real `cli.main` entry point and a real local HTTP server —
the refusal (no `--model`, exit 2, no traceback), the argparse-level
refusal (`--describe` missing), a real successful run (policy written,
both renderings printed, the next command named correctly, nothing
measured), and `dispatchable_commands()` carrying the new command.
`oneground/test_cli.py` + `oneground/test_environment.py` + `oneground/
proposals/`: 150 of 150 pass, confirming the guard-coverage machinery
and existing CLI surface are unaffected.

## Verification

`oneground/test_cli_propose_translate.py`: 4 passed. Full suite, guard,
identifier scan and `site/teaser/`: reported at the merge, per the
established pattern.

## Observed, not done

**The other four unreachable capabilities are named, not wired.** Per
the audit above, each needs its own decision before a command makes
sense for it, not a mechanical repeat of this task's pattern.

**No lab/interface endpoint was considered for `translate`** — only a
CLI command, matching what `docs/PROPOSALS.md` §3.2's own default
(the developer's own review surface, not user-facing at the interface
level) already scopes for the adjacent triage question; `propose`
itself has no lab endpoint either, so this is consistent with the
existing surface rather than a new gap.

## Repo now contains

Changed:

- `oneground/cli.py` — `_translate_parser()`, `_cmd_propose_translate()`,
  the `_dispatch()` hook, `dispatchable_commands()`, the usage docstring
- `oneground/proposals/translate.py` — `render_policy_plain()`
- `oneground/test_environment.py` — `GUARDS_ON_USE` gains the new command

New:

- `oneground/test_cli_propose_translate.py` — 4 tests
- `tasks/finding-a-capability-with-no-command.md`
- `tasks/063-propose-translate-cli.report.md` — this file

## Blocked on developer

Nothing. Committing, pushing to `task-063`, and merging into `main`
once its checks are green, per standing instruction.
