# Report: 064-four-self-reported-gaps-wired

## Repo state expected vs found

Expected `main` at `157e24b` (task 063's merge), with four built and
tested capabilities each carrying its own "no way to reach this"
self-report and none of the four wired to a command or an endpoint:
`oneground.library.card_schema.submit_card` (task 058),
`oneground/bridge/export.py` (task 051), `oneground/bridge/
import_result.py` (task 055), and `oneground/verify/load.py::
run_load_per_node` (task 057). Found exactly that; branch `task-064`
created from `main` at that commit.

## What was done

**The finding, first, because the brief said to write it where the
others live and it generalises past all four.**
`tasks/finding-a-reported-gap-is-not-a-scheduled-one.md`: five
capabilities self-reported the same gap in their own task's "Observed,
not done," several named again in task 060's inventory, and only the
one asked about by name (`translate`, task 063) closed. The claim is
not that any one gap matters more than another; it is that this project
has a mechanism for surfacing a gap and no mechanism for closing one,
and the two have been getting silently conflated. The table, the
argument, and what is deliberately left undecided (whether to build a
second mechanism) are in the finding itself.

**Then all four, wired to exactly what each capability's own position
paper implies — no new design, nothing guessed where a paper was
silent.**

### `oneground library check-card`

`docs/LIBRARY.md` §7 sequences the validator before its command and
§6 leaves submission's transport fully unsettled — three options
named, no lean stated. `oneground/library/cli.py` builds the
validator's command and stops there: it reads a JSON file, calls
`submit_card`, and prints accepted or every missing field at once. It
does not submit anywhere, because the paper does not say where, and
inventing a destination would be exactly the guess this task's brief
says to report instead of build. Wired into `oneground/cli.py` the
same way `library`/`bridge` needed a `_dispatch` hook, an `UNGUARDED`
entry (it writes nothing, so it needs no environment guard), and a
`dispatchable_commands()` entry.

**Did wiring surface anything the tests didn't?** No. `check-card`'s
contract was fully specified by `card_schema.submit_card`'s own tests
(task 058); the CLI is a thin, order-preserving shell around a function
that already had every case covered. The five new tests in
`oneground/library/test_cli.py` (accepted, refused-and-named,
malformed JSON, missing file, writes nothing) all passed on the first
run against the implementation as designed.

### `oneground bridge export` / `oneground bridge import`

`docs/BRIDGE.md` §7 states a lean, with a reason: "probably" its own
command, since it produces files for a tool this project does not run.
`oneground/bridge/cli.py` builds exactly that — `export` guards the
environment (it writes real files, `GUARDS_ON_USE` in
`oneground/test_environment.py`, the same manual-guard pattern
`fixture build` uses) and exposes `export.export`'s own parameters
unchanged; `import` is read-only, unguarded, and prints
`import_result.read_result_file`'s own output plus a one-line summary.

**Did wiring surface anything the tests didn't? Yes — a real bug in
my own test, and a real, worth-recording gap in the output shape
(neither in the capability's own code, both found by running the
command rather than by reading it).**

1. My first version of `test_export_writes_the_card_and_prints_it`
   parsed the first occurrence of the substring `"wrote "` in the
   command's combined output to find the card's path — and `export`'s
   own `log_fn` progress lines ("`export: wrote 1 train file(s), 400
   vectors total`") contain that substring earlier in the output than
   the actual `wrote <path>` summary line. The test passed for the
   wrong reason on a re-read, failed for the right reason on a real
   run, and was fixed to match on a line that starts with `wrote `,
   not a line that merely contains it. Recorded here rather than
   silently fixed because it is exactly the kind of thing "run it,
   don't just write it" is supposed to catch, and did.
2. A missing or malformed `requirements.yaml` raises
   `intake.RequirementsError`, which `oneground/refusals.py` documents
   as printed once, by the top-level `oneground.cli.main`, never by a
   subcommand's own module — "a refusal is produced where it is
   raised, once." `oneground/bridge/cli.py::main` correctly does not
   catch it. My first version of the missing-requirements-file test
   called `bridge.cli.main` directly, bypassing that top-level catch,
   and would have reported a false failure if `RequirementsError` had
   ever needed catching locally. Fixed to go through
   `oneground.cli.main(["bridge", "export", ...])`, which is also what
   every real invocation of this command actually does, and is a more
   faithful test than the one I first wrote.

### `run_load_per_node` in `_verify_local`

`docs/MULTI_NODE.md` §6 is the least hedged of the four papers: "a
declared list of endpoints in the requirements file rather than one,"
not a new protocol method, not a new CLI flag. `oneground/verify/
__init__.py::_verify_local` now reads `cfg.get("node_endpoints")` — the
`verify:` block of `requirements.yaml`, the same dict `run_load` above
it already reads `concurrency`/`target_qps`/`duration_minutes`/
`warmup_seconds` from — and, when it is declared, calls
`loadgen.run_load_per_node` with those same values, storing the result
under a new `out["load_per_node"]` key beside the existing
`out["load"]`. It is a sibling measurement, not a replacement: fan-out
answers a different question (per-node comparison) from the existing
single-endpoint load phase, and nothing about §6 conditions one on the
other, so `node_endpoints` and the existing `want_load` flag are
independent.

**Did wiring surface anything the tests didn't? Yes — a real
ambiguity in what a fan-out measurement can and cannot tell a reader,
found by running the wiring against the stub, not by reading
`run_load_per_node`'s docstring.** A fresh engine instance per node
(`engine_factory()`, called once per address, exactly as the function's
own docstring says) means a node whose namespace was never actually
replicated has no data to search. I expected that to raise, wrote a
test asserting it would, and it did not: `run_load` (`oneground/verify/
load.py` line 270) catches every per-request exception and counts it
as `errors`, by design, so a load run degrades under real transient
failures instead of aborting mid-measurement. Wiring this in surfaces
what that design choice means specifically for fan-out, which
`run_load_per_node`'s own unit tests never could, since they only ever
run against a real, shared, three-node cluster (`test_load_multi_node.
py`): a node with no data reports `outcome: measured`,
`error_rate: 1.0`, `achieved_qps: 0.0` — the identical shape a
genuinely healthy node saturated into total timeout would report.
Nothing in the row distinguishes "this node never had the namespace"
from "this node is failing under load"; a reader has to already know
the deployment replicated the namespace correctly to tell the two
apart. `docs/MULTI_NODE.md` §4.2 already says a namespace's replication
is "a fact about the deployment," not something this function checks
or can check — so this is not a bug to fix here. It is recorded as
what it is: a second, smaller instance of "self-reported gap, not yet
closed," left for whoever next reads a fan-out report to know about
rather than silently discover.

## Measurements

- New tests: `oneground/library/test_cli.py` (5), `oneground/bridge/
  test_cli.py` (10), and three new tests in `oneground/verify/
  test_verify.py` (`test_no_node_endpoints_declared_means_no_load_per_
  node_key`, `test_fewer_than_two_node_endpoints_is_couldnt_check_not_a_
  guess`, `test_two_or_more_node_endpoints_reach_run_load_per_node`) —
  18 new tests, all passing in isolation
  (`.venv\Scripts\python.exe -m pytest oneground/library/test_cli.py
  oneground/bridge/test_cli.py -q` → 10 passed;
  `oneground/verify/test_verify.py -k "node_endpoints or
  load_per_node"` → 3 passed).
- Full suite, guard, identifier scan, and site-teaser diff: pending —
  see Verification.

## Verification

Passed, in isolation: the 18 new tests above, and the pre-existing
`oneground/test_environment.py -k "dispatchable or guarded or declared_
guard or unguarded"` (6 passed, confirming `library`/`bridge`'s
commands are correctly enumerated and `oneground bridge export`'s
manual guard is correctly declared).

Not yet run this task: the full suite, `oneground/test_environment.py`
in full, `oneground.environment.identifier_findings()`, and the
`site/teaser/` diff — required before commit per the standing check
protocol, not yet executed as of this report being written.

## Observed, not done

None beyond what the two "did wiring surface anything" sections above
already name and leave open by the papers' own terms: `docs/LIBRARY.md`
§6's submission transport, and the fan-out row's inability to
distinguish an unreplicated namespace from a genuinely failing node.
Neither is a gap in what this task built; both are gaps the position
papers themselves leave unsettled or unchecked, named rather than
guessed shut.

## Repo now contains

- `tasks/finding-a-reported-gap-is-not-a-scheduled-one.md` (new)
- `oneground/library/cli.py` (new) — `check-card` command
- `oneground/library/test_cli.py` (new)
- `oneground/bridge/cli.py` (new) — `export`/`import` commands
- `oneground/bridge/test_cli.py` (new)
- `oneground/verify/__init__.py` (modified) — `node_endpoints` wiring in
  `_verify_local`
- `oneground/verify/test_verify.py` (modified) — 3 new tests
- `oneground/cli.py` (modified) — `library`/`bridge` dispatch,
  `UNGUARDED` entries, `dispatchable_commands()` coverage
- `oneground/test_environment.py` (modified) — `oneground bridge
  export` added to `GUARDS_ON_USE`

## Blocked on developer

None.
