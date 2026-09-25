# Finding — a check that takes a different route than production is a check of a different program

*Prompted by three real pod-run failures against `sessions/036-models.
yaml`, in order: a corpus absent from the volume at the path the run
expects (tasks 065/068), a bare `python` resolving to the pod's system
interpreter because the venv was never activated for the run's own launch
(tasks 070/071), and `python corpora/036-ordering-experiment.py`, run as
a file the way the pod actually runs it, unable to import `oneground` at
all (this task). All three were "prepared" first: priced with `oneground
pod plan`, verified locally, reported as ready. All three were wrong in a
way nothing local caught, and all three were wrong for the same reason.*

## The claim

**A check that reaches the code being checked by a different route than
production takes is not a weaker check of the same program -- it is a
check of a different one.** The two programs can share every line of
source and still diverge, because what a script does depends on more than
its text: on the interpreter that runs it, on the working directory it
runs from, on whether it is invoked as a file or fed a module by another
mechanism entirely. Each of the three failures below passed every local
check because the local check took a route that quietly supplied
something production does not.

## The evidence, and the route each check actually took

1. **The missing corpus.** `run_036_models.sh`'s input check
   (`$ASSETS/arxiv-150k/sample.jsonl.zst`) was read from this repo's own
   comments and from `oneground pod plan`'s pricing output -- neither
   inspects the volume. The only way to have found the gap without
   spending was to ask the volume itself, which task 067 eventually built
   as its own session. Before that, every local check of the spec
   answered "is this well-formed" and never "is this true".

2. **The venv.** Every local verification of `run_036_models.sh`'s python
   calls this project ran used `.venv/Scripts/python.exe` explicitly, by
   path, on this laptop. The pod's actual launch resolves a bare `python`
   through whatever the shell's `PATH` happens to be at that moment --
   which task 070 traced to two separate ssh connections, one that
   activates a venv and one, later, that does not inherit it. No local
   check ever ran a bare `python` the way the pod's own launch does,
   because every local invocation named the interpreter.

3. **This task.** Every local check of `corpora/036-ordering-
   experiment.py` either inserted the repo root onto `sys.path` explicitly
   in an ad hoc snippet, or loaded the file with
   `importlib.util.spec_from_file_location`, which does not touch
   `sys.path[0]` the way `python <path>` does. The pod's actual invocation
   -- `python corpora/036-ordering-experiment.py`, exactly as
   `run_036_models.sh` writes it -- puts the script's own directory on
   `sys.path[0]`, not the repository root, and nothing installs
   `oneground` as a package to compensate. `ModuleNotFoundError: No
   module named 'oneground'`, one line into a script that had, one line
   of log output earlier, successfully imported `oneground.embed.
   registry` and `oneground.embed` -- from a **different** `python`
   invocation, the probe's own `python - <<'PY'` heredoc, which runs with
   an empty string on `sys.path[0]` and therefore resolves `oneground`
   from the current directory instead. **The probe's successful import
   one line earlier made the failure that followed it look impossible**:
   same pod, same venv, same working directory, same package on disk,
   and a `ModuleNotFoundError` for a package the log had just finished
   proving was importable. It was never the same check. `python -` and
   `python <path>` are different programs with respect to `sys.path`, and
   only one of them is what `run_036_models.sh` actually does at that
   line.

## What this is not

**Not a claim that any of the three individual fixes was wrong.** Each
was diagnosed correctly and each fix was verified as well as it could be
at the time. The finding is about what "verified" was allowed to mean
going in: a check that never takes production's own route cannot
distinguish between a program that works and a program that only works
along the route it happened to be checked by.

**Not a claim that local verification is worthless.** Every local check
this project ran did confirm something true -- that the imports resolve
*given a repo root on the path*, that the logic is correct *given numpy
is importable*, that the data loads *given the file is where a laptop
convention put it*. Each of those somethings was true. None of them was
the thing production needed to be true.

## The general form

> Checking a program by a route other than the one that will run it
> checks the assumptions that route happens to supply, not the ones
> production will actually make. The gap is invisible from inside the
> check, because everything the check touches really does work -- the
> code is correct along the path it was asked to prove itself on. It is
> only wrong about the path nobody asked it to take.

The tell, for next time a local check passes and a pod run does not:
**ask what the check supplied that the real invocation will not** --
an interpreter named by path instead of resolved from `PATH`, a working
directory chosen for convenience instead of the one the launch actually
uses, an import mechanism that reaches the same code without exercising
the same resolution rules. If the answer is "several things", the check
proved the code compiles, not that it runs.

## What was done about it here, not left as a naming exercise

`corpora/036-ordering-experiment.py` and `corpora/
036-truncation-per-model.py` were reconciled to the same `sys.path`
convention -- anchored to `__file__`, matching the majority already in
`corpora/` (`build_fixture.py`, `export_ground_view.py`,
`run_chunking.py`), not the minority, cwd-dependent form
(`036-truncation-per-model.py`'s previous `os.path.abspath(".")`, which
happened to work only because `run_036_models.sh` always `cd`s to the
repo root first). Verified by the fix this finding argues for: `python
corpora/036-ordering-experiment.py` and `python corpora/
036-truncation-per-model.py`, run as real subprocesses from the repo
root with `.venv/Scripts/python.exe`, `ONEGROUND_ASSETS` pointed at an
empty directory. Both now get past every `oneground.*` import and fail
at the same controlled, expected point a missing corpus produces --
proving the import fix by reaching class 1's own failure mode cheaply
and safely, exactly as this finding's route argument predicts it should.

## What is not decided here

Whether this project should build a standing check that runs `corpora/
*.sh` (or the scripts they invoke) as real subprocesses, from the route
production takes, before a pod session is ever priced -- a mechanised
version of what this finding's own verification did by hand. That is a
tooling decision for whoever owns `oneground/pod/`, not a gap this
finding closes by naming it.
