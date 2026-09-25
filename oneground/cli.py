"""`oneground <command>` — the one entry point.

    oneground characterize <requirements.yaml>   measure your own vectors
    oneground simulate <requirements.yaml>       sweep architectures on them
    oneground verify <requirements.yaml>         measure a real engine
    oneground report <requirements.yaml>         judge them against constraints
    oneground lab <workdir>                      look at a run, read-only
    oneground propose <workdir> --policy ... --prediction ...
                                                 measure one change you wrote,
                                                 against a prediction you wrote
                                                 first (tier 1: no model)
    oneground propose translate <workdir> --describe "..." --model ...
                                                 a model writes the policy from
                                                 a sentence; writes policy.yaml
                                                 and stops -- never runs it
                                                 (path 2, docs/PROPOSALS.md §2.1)
    oneground calibrate <curve|engine|show>      measure our own error
    oneground fixture verify <id>                check a fixture's digests
    oneground fixture build --spec ... --source ...
    oneground pod <plan|up|status|fetch|down|watch|ls>
    oneground library check-card <card.json>     validate, never submit
                                                 (docs/LIBRARY.md §2)
    oneground bridge export <requirements.yaml> --query-subset-seed ...
                                                 write VectorDBBench's files
    oneground bridge import <result.json>        read one back, raw numbers
                                                 only (docs/BRIDGE.md)

`fixture`, `calibrate` and `pod` are delegated rather than reimplemented. Each
has its own parser and its own tests, and `pod` has its own money boundary:
folding that one into this parser would put a billable path behind a shared
argument parser for no gain. `calibrate` is delegated for a smaller reason --
it has five actions with disjoint flags, and it must be importable on a
machine with neither faiss nor a qdrant client.
"""

import argparse
import sys

from . import provenance
from . import refusals
from . import __display_version__, __version__
from . import environment as envmod


# Commands that deliberately run no environment guard, each with its reason.
#
# Being on this list is a decision. Being absent from it *and* unguarded is a
# test failure -- `oneground/test_environment.py` walks the surface below and
# requires every dispatchable command to be one or the other. Task 013b
# asserted coverage against a hand-written list of six names, which a seventh
# command would have escaped silently; that is the same class of defect the
# guard itself exists to prevent, one level up.
UNGUARDED = {
    "oneground pod": (
        "creates no local canonical artifact -- the pod installs its own "
        "pinned environment from requirements.txt -- and owns its own parser "
        "and money boundary"),
    "oneground calibrate show": "renders calibration/history.jsonl; writes nothing",
    "oneground calibrate reference": (
        "prints what the downloaded ANN-Benchmarks file contains; writes "
        "nothing"),
    "oneground lab": (
        "serves drawings of a run that already exists; writes no file, starts "
        "no measurement, and runs its own guard over the modules it serves "
        "from before it binds a port (docs/LAB.md)"),
    "oneground ui": (
        "the same server as `oneground lab`, pointed at a directory of runs "
        "rather than one: it serves drawings of runs that already exist, "
        "writes no file, starts no measurement, creates no session, and runs "
        "its own guard over every module it serves from -- views, transport "
        "and contract machinery -- before it binds a port (docs/UI.md)"),
    "oneground adapters": (
        "asks each reachable engine which index families it builds and "
        "records the answer. It measures nothing on this machine and writes "
        "no canonical artifact -- what it records is a fact about an engine "
        "at a version, and the version it asked is in the record (task 034)"),
    "oneground models": (
        "runs the family conformance suite on a small synthetic corpus and "
        "prints per-check results. It writes no file and reads no fixture: "
        "what it checks is the protocol's contract, not any published value "
        "(task 042, docs/FAMILIES.md)"),
    "oneground library check-card": (
        "validates a card in memory against docs/LIBRARY.md §2's required "
        "shape and prints accept or refuse. Writes no file, submits "
        "nothing anywhere -- the transport is unsettled by the paper "
        "itself (§6), and this command does not decide it (task 064)"),
    "oneground bridge import": (
        "reads a VectorDBBench result file a user's own run already "
        "produced and prints its per-case raw numbers. Writes no file, "
        "runs nothing, measures nothing itself (docs/BRIDGE.md §5, "
        "task 064)"),
}


def dispatchable_commands():
    """Every command string `main` can route to, derived from the parsers.

    Derived rather than listed: a subcommand added to any parser appears here
    without anyone remembering to, which is what makes the guard-coverage test
    self-extending.
    """
    names = {f"oneground {c}" for c in _top_level_commands()}
    names.discard("oneground fixture")
    names.discard("oneground calibrate")
    names.discard("oneground pod")
    names.discard("oneground library")
    names.discard("oneground bridge")
    names |= {f"oneground fixture {a}" for a in _fixture_actions()}
    names |= {f"oneground calibrate {a}" for a in _calibrate_actions()}
    names |= {f"oneground library {a}" for a in _library_actions()}
    names |= {f"oneground bridge {a}" for a in _bridge_actions()}
    names.add("oneground pod")            # one money boundary, one entry
    names.add("oneground propose translate")   # its own parser, dispatched
                                                # before `propose`'s
    return names


def _choices(parser, dest):
    for action in parser._actions:                    # argparse has no public
        if getattr(action, "dest", None) == dest and \
                getattr(action, "choices", None):     # accessor for this
            return list(action.choices)
    return []


def _top_level_commands():
    return _choices(build_parser(), "command")


def _fixture_actions():
    return _choices(_fixture_parser(), "action")


def _calibrate_actions():
    from .calibrate import build_parser as calibrate_parser
    return _choices(calibrate_parser(), "action")


def _library_actions():
    from .library.cli import build_parser as library_parser
    return _choices(library_parser(), "action")


def _bridge_actions():
    from .bridge.cli import build_parser as bridge_parser
    return _choices(bridge_parser(), "action")


@envmod.guarded("oneground characterize")
def _cmd_characterize(args, rest, env_stamp=None):
    from . import characterize
    if rest:
        raise SystemExit(f"oneground characterize: unexpected arguments: "
                         f"{' '.join(rest)}")
    characterize.run(args.requirements, with_projection=args.project,
                     env_stamp=env_stamp)
    return 0


@envmod.guarded("oneground chunk")
def _cmd_chunk(args, rest):
    """The chunking stage, run alone (task 031).

    Answers "is my chunking cutting through answers" without committing to a
    full run. The same stage runs inside `characterize` when the corpus is
    given as text; here it is the whole of the command.
    """
    from .chunk import stage
    if rest:
        raise SystemExit(f"oneground chunk: unexpected arguments: "
                         f"{' '.join(rest)}")
    return stage.run(args.requirements, documents=args.documents,
                     anchors=args.anchors, device=args.device)


@envmod.guarded("oneground simulate")
def _cmd_simulate(args, rest):
    from . import simulate
    if rest:
        raise SystemExit(f"oneground simulate: unexpected arguments: "
                         f"{' '.join(rest)}")
    simulate.run(args.requirements, emit_state=args.emit_state)
    # Task 034, and task 046 contract change 5. A configuration that could
    # not be built is reported and the sweep goes on, so the rows already
    # measured are not lost. Couldn't-check is never rounded up to success --
    # but that is a claim the receipt already makes, in simulate_info.json;
    # the exit code saying it too was a finding travelling in a process, and
    # jobs.py's own rule is that a stage's exit code says whether it ran,
    # never what it found. It ran.
    dropped = getattr(simulate.run, "last_dropped", None) or []
    if dropped:
        planned = getattr(simulate.run, "last_planned", len(dropped))
        print(f"\n  {len(dropped)} of {planned} planned configuration(s) "
              f"were not measured. The rest were, and are in simulate.json;")
        print("  each one that was not is named with its reason in "
              "simulate_info.json:dropped.")
    return 0


@envmod.guarded("oneground verify")
def _cmd_verify(args, rest):
    from . import verify
    if rest:
        raise SystemExit(f"oneground verify: unexpected arguments: "
                         f"{' '.join(rest)}")
    verify.run(args.requirements, up=args.up, down=args.down,
               on_pod=args.on_pod)
    return 0


@envmod.guarded("oneground propose")
def _cmd_propose(args, rest, env_stamp=None):
    from .proposals import propose
    if rest:
        raise SystemExit(f"oneground propose: unexpected arguments: "
                         f"{' '.join(rest)}")
    try:
        return propose.run(args.workdir, args.policy, args.prediction,
                           name=args.name, dry_run=args.dry_run,
                           requirements_path=args.requirements,
                           env_stamp=env_stamp)
    except propose.ProposeError as e:
        # Every problem at once, and a non-zero exit: a refusal is not a
        # crash, and the 022 rule is that one run tells you everything wrong.
        print(str(e))
        return 2


@envmod.guarded("oneground report")
def _cmd_report(args, rest, env_stamp=None):
    from . import report
    if rest:
        raise SystemExit(f"oneground report: unexpected arguments: "
                         f"{' '.join(rest)}")
    report.run(args.requirements, env_stamp=env_stamp)
    return 0


def _cmd_ui(args, rest):
    """`oneground ui [<runs-dir>]`: serve every run under a directory.

    The same server, the same token, the same guard as `oneground lab`,
    pointed at a directory rather than at one run. Nothing runs from it, no
    file is written by it and no session is created by it: this is the read
    half.

    The render mode is not measured at startup, because it is a measurement of
    drawing one run's ground and no run has been opened yet.
    """
    import signal
    import time
    import webbrowser

    started = time.perf_counter()
    if rest:
        raise SystemExit(f"oneground ui: unexpected arguments: "
                         f"{' '.join(rest)}")
    from .lab import server as labserver
    from .lab.runs import LabRunError

    try:
        # One expression, used twice, rather than two that agree today:
        # the warning must describe the session that is about to exist, and
        # `runs_dir` is what decides whether it can write and enqueue.
        ui_runs_dir = None if args.demo else args.runs_dir
        labserver.check_host(args.host, args.i_know, runs_dir=ui_runs_dir)
        lab = labserver.LabServer(
            runs_dir=ui_runs_dir,
            demo=args.demo, host=args.host, port=args.port,
            i_know=args.i_know)
    except (LabRunError, labserver.LabRefused) as e:
        print(f"oneground ui: refused. {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"oneground ui: could not listen on {args.host}:{args.port}: "
              f"{e}", file=sys.stderr)
        return 2
    if lab.warning:
        print(lab.warning, file=sys.stderr)
    lab.start()
    print(lab.ui_startup_line(time.perf_counter() - started,
                              lab.runs_dir if args.demo else args.runs_dir),
          flush=True)
    if args.open:
        webbrowser.open(lab.url)

    def interrupted(signum, frame):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            try:
                signal.signal(getattr(signal, name), interrupted)
            except (OSError, ValueError):
                pass
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\noneground ui: stopped. Nothing was written.", flush=True)
    return 0


def _cmd_lab(args, rest):
    """`oneground lab <workdir>`: serve the lab for one run, read-only.

    The host is checked before anything is loaded, so a refused `--host`
    costs nothing. Then the run is loaded, the render mode measured and the
    port bound, and one line is printed. Ctrl-C -- or SIGTERM, or Ctrl-Break
    on Windows -- stops it and says so.
    """
    import signal
    import time
    import webbrowser

    started = time.perf_counter()
    if rest:
        raise SystemExit(f"oneground lab: unexpected arguments: "
                         f"{' '.join(rest)}")
    from .lab import contract as labcontract
    from .lab import server as labserver
    from .lab.runs import LabRunError, LoadedRun

    mode = {"move": labcontract.MOVE, "release": labcontract.RELEASE,
            None: None}[args.mode]
    try:
        labserver.check_host(args.host, args.i_know, runs_dir=None)
        run = LoadedRun(args.workdir, family=args.family, config=args.config,
                        also=args.also)
        lab = labserver.LabServer(run, host=args.host, port=args.port,
                                  mode=mode, i_know=args.i_know)
    except (LabRunError, labserver.LabRefused) as e:
        print(f"oneground lab: refused. {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"oneground lab: could not listen on {args.host}:{args.port}: "
              f"{e}", file=sys.stderr)
        return 2
    if lab.warning:
        print(lab.warning, file=sys.stderr)
    lab.start()
    print(lab.startup_line(time.perf_counter() - started, args.workdir),
          flush=True)
    if args.open:
        webbrowser.open(lab.url)

    def interrupted(signum, frame):
        raise KeyboardInterrupt
    for name in ("SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), interrupted)
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        lab.stop()
        print("oneground lab: stopped. Nothing was written.", flush=True)
        return 0


def _fixture_parser():
    """The `oneground fixture` parser. One definition, two entry points.

    `oneground fixture verify` and `python -m oneground.fixture.verify` used
    to parse different flags, because this function built its own verify
    subparser instead of the one `fixture/verify.py` owns: `--assets-dir` and
    `--verbose` worked on one path and not the other. The verify subparser is
    now defined once, in the module that owns the command.
    """
    from .fixture.verify import add_verify_arguments

    ap = argparse.ArgumentParser(prog="oneground fixture")
    sub = ap.add_subparsers(dest="action", required=True)
    v = add_verify_arguments(sub)

    b = sub.add_parser("build", help="build a fixture from its spec")
    b.add_argument("--spec", required=True)
    b.add_argument("--source", default=None,
                   help="local snapshot to read; omit for a spec that "
                        "names its own source and streams it")
    b.add_argument("--out", default="fixtures")
    b.add_argument("--skip-projection", action="store_true")
    envmod.add_argument(b)
    b.add_argument("--requirements", default=envmod.REQUIREMENTS,
                   help="the pinned requirements the guard checks against")

    # The projection as its own step. `build --skip-projection` then
    # `fixture project` is the same work in the same order as `build` alone;
    # splitting it lets the runner package the receipts in between, so a run
    # killed during UMAP still has a tarball to fetch.
    pr = sub.add_parser("project",
                        help="add projection.npy to an already-built fixture")
    pr.add_argument("--spec", required=True)
    pr.add_argument("--out", default="fixtures")
    envmod.add_argument(pr)
    pr.add_argument("--requirements", default=envmod.REQUIREMENTS,
                    help="the pinned requirements the guard checks against")
    return ap


def _translate_parser():
    """`oneground propose translate` -- its own parser, per `docs/
    PROPOSALS.md` §2.1: `--describe` and `--model` do not fit the shared
    `propose` subparser's `--policy`/`--prediction` shape, and `translate`
    is a second positional keyword after `propose`, not a flag."""
    ap = argparse.ArgumentParser(prog="oneground propose translate")
    ap.add_argument("workdir",
                    help="a workdir `characterize`, `simulate` and `report` "
                         "have already written -- translate shows the "
                         "model manifest.yaml's recommended configuration")
    ap.add_argument("--describe", required=True,
                    help="the change, in one sentence")
    ap.add_argument("--model", default=None,
                    help="ollama:<name> for a local Ollama, or <name> with "
                         "--endpoint for any other OpenAI-compatible "
                         "server. No default: omitting this refuses.")
    ap.add_argument("--endpoint", default=None,
                    help="the OpenAI-compatible base URL, for a --model "
                         "with no ollama: prefix")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--top-p", type=float, default=None, dest="top_p")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--max-tokens", type=int, default=None, dest="max_tokens")
    ap.add_argument("--requirements", default=None,
                    help="the requirements file the baseline run used; "
                         "defaults to the one simulate_info.json recorded")
    ap.add_argument("--out", default=None,
                    help="where policy.yaml and the disclosure are "
                         "written; defaults to <workdir>")
    envmod.add_argument(ap)
    return ap


def _cmd_propose_translate(argv):
    """`oneground propose translate`. Guards itself, like `fixture` and
    `pod`: its argument shape does not fit the shared `propose` parser's
    contract, so it is dispatched before `build_parser()` ever sees it
    (`GUARDS_ON_USE` in `oneground/test_environment.py` names this
    command for the same reason it names `fixture verify`)."""
    from .proposals import translate as tr

    args = _translate_parser().parse_args(argv)
    stamp, code = envmod.guard_or_exit(
        "oneground propose translate", allow_unpinned=args.allow_unpinned)
    if code:
        return code

    try:
        result = tr.translate(
            args.workdir, args.describe, args.model, endpoint=args.endpoint,
            temperature=args.temperature, top_p=args.top_p, seed=args.seed,
            max_tokens=args.max_tokens, out_dir=args.out,
            requirements_path=args.requirements, log_fn=print)
    except tr.TranslateError as e:
        # The same shape every other refusal in this command line takes:
        # printed, not raised, exit 2 -- docs/PROPOSALS.md §2.1's own
        # refusal without an explicit --model lands here.
        print(str(e))
        return 2

    print()
    print(f"wrote {result['policy_path']}")
    print()
    print(tr.render_policy_plain(result["policy"]))
    print()
    print("--- the policy file, in full ---")
    with open(result["policy_path"], encoding="utf-8") as f:
        print(f.read(), end="")
    print("--- end of policy file ---")
    print()
    print("This is not approval, and nothing has run. Read the policy "
         "above. Approval is running it yourself:")
    print(f"    oneground propose {args.workdir} --policy "
         f"{result['policy_path']} --prediction <prediction.yaml>")
    return 0


def _cmd_fixture(argv):
    """`fixture verify`, `fixture build` and `fixture project`."""
    ap = _fixture_parser()
    args = ap.parse_args(argv)
    if args.action == "verify":
        # cmd_verify guards itself: it needs the pin comparison anyway, to
        # decide each value's outcome.
        from .fixture import verify
        return verify.cmd_verify(args)

    # A fixture build is the most canonical artifact this project produces --
    # everything else is checked against it -- so it refuses an unpinned
    # interpreter before it reads a byte of source.
    # Passed explicitly: for `fixture`, args.requirements is the pins file,
    # while for characterize/simulate/verify/report it is the user's
    # requirements.yaml. `_guard` must never confuse the two.
    _stamp, code = envmod.guard_or_exit(
        "oneground fixture %s" % args.action, args.requirements,
        allow_unpinned=args.allow_unpinned)
    if code:
        return code
    if args.action == "project":
        from .fixture.build import project_fixture
        project_fixture(args.spec, out=args.out)
        return 0

    from .fixture.build import build
    build(args.spec, args.source, out=args.out,
          skip_projection=args.skip_projection)
    return 0


def _cmd_calibrate(argv):
    from .calibrate import main as calibrate_main
    return calibrate_main(argv)


def _cmd_pod(argv):
    from .pod.cli import main as pod_main
    return pod_main(argv)


def _cmd_adapters(argv):
    from .adapters.coverage_cli import main as coverage_main
    return coverage_main(argv)


def _cmd_library(argv):
    """`oneground library check-card` -- validation only, docs/LIBRARY.md
    §7's sequencing made reachable. See `oneground/library/cli.py`."""
    from .library.cli import main as library_main
    return library_main(argv)


def _cmd_bridge(argv):
    """`oneground bridge export`/`import` -- docs/BRIDGE.md §7's own
    stated lean ("probably... its own command") made reachable. See
    `oneground/bridge/cli.py`, which guards `export` itself (it writes
    real files) the same way `_cmd_fixture` guards its own actions."""
    from .bridge.cli import main as bridge_main
    return bridge_main(argv)


def _cmd_models(argv):
    """`oneground models conformance` -- the family contribution gate."""
    from .models.conformance import main as conformance_main
    if argv and argv[0] == "conformance":
        return conformance_main(argv[1:])
    print("usage: oneground models conformance [--family NAME] "
          "[--module path/to/model.py]\n"
          "       runs the family conformance suite. See docs/FAMILIES.md.")
    return 2


def build_parser():
    ap = argparse.ArgumentParser(
        prog="oneground",
        description="Measure a retrieval architecture decision on your own "
                    "vectors, with the receipt attached.")
    # Both strings, and only one when they coincide. `oneground 0.1.0 (0.1.0)`
    # invites the reader to look for a difference that is not there.
    ap.add_argument("--version", action="version",
                    version=(f"oneground {__display_version__}"
                             if __display_version__ == __version__
                             else f"oneground {__display_version__} "
                                  f"({__version__})"))
    sub = ap.add_subparsers(dest="command", required=True)

    c = sub.add_parser("characterize",
                       help="measure a corpus from a requirements file")
    c.add_argument("requirements",
                   help="path to a requirements.yaml "
                        "(see requirements.example.yaml)")
    c.add_argument("--project", action="store_true",
                   help="also write a 2-D UMAP projection of the sample "
                        "(illustrative, declared; needs oneground[view]). "
                        "The report embeds the ground view only when the run "
                        "produced one of its own.")
    envmod.add_argument(c)

    ck = sub.add_parser("chunk",
                        help="run the chunking stage alone and report "
                             "(docs/CHUNKING.md)")
    ck.add_argument("requirements",
                    help="path to a chunking requirements.yaml "
                         "(see requirements.chunking-sec-filings.yaml)")
    ck.add_argument("--documents", type=int, default=None,
                    help="override the declared subsample size")
    ck.add_argument("--anchors", type=int, default=None,
                    help="override the declared anchor count")
    ck.add_argument("--device", default=None,
                    help="embedding device; the requirements file decides "
                         "when this is omitted")
    envmod.add_argument(ck)

    s_ = sub.add_parser("simulate",
                        help="sweep architecture families on a characterized "
                             "sample")
    s_.add_argument("requirements",
                    help="path to the same requirements.yaml characterize used")
    s_.add_argument("--emit-state", action="store_true",
                    help="also write state/ beside simulate.json: where every "
                         "vector went, how every query was routed and what "
                         "every shard returned, one file per configuration "
                         "(docs/STATE.md). Off by default; simulate.json is "
                         "unchanged by it.")
    envmod.add_argument(s_)

    v_ = sub.add_parser("verify",
                        help="measure a real engine on the characterized "
                             "sample")
    v_.add_argument("requirements")
    v_.add_argument("--up", action="store_true",
                    help="start the pinned engine container first "
                         "(target: local)")
    v_.add_argument("--down", action="store_true",
                    help="stop and remove the container afterwards")
    v_.add_argument("--on-pod", action="store_true",
                    help="internal: this process IS the pod-side run. Off a "
                         "pod, verify.target: runpod only prepares a session.")
    envmod.add_argument(v_)

    r_ = sub.add_parser("report",
                        help="judge the measurements against your constraints")
    r_.add_argument("requirements")
    envmod.add_argument(r_)

    lab = sub.add_parser("lab",
                         help="look at a run in the lab: a local, read-only "
                              "server (docs/LAB.md)")
    lab.add_argument("workdir",
                     help="a run's directory: state/, simulate.json and "
                          "characterization.json")
    lab.add_argument("--port", type=int, default=0,
                     help="default: an ephemeral port")
    lab.add_argument("--host", default="127.0.0.1",
                     help="default 127.0.0.1; anything but loopback also "
                          "needs --i-know")
    lab.add_argument("--i-know", action="store_true", dest="i_know",
                     help="serve on a non-loopback --host, after a warning "
                          "naming what that exposes")
    browser = lab.add_mutually_exclusive_group()
    browser.add_argument("--open", action="store_true",
                         help="open the URL in a browser")
    browser.add_argument("--no-browser", action="store_true",
                         help="the default: open nothing")
    lab.add_argument("--mode", choices=("move", "release"),
                     help="override the render mode the startup measurement "
                          "chooses; the caption says it was overridden")
    lab.add_argument("--family",
                     help="the model family to look at (default "
                          "semantic_sharded)")
    lab.add_argument("--config",
                     help="the configuration label, when the run holds "
                          "several that differ in more than epsilon")
    lab.add_argument("--also", action="append", default=[],
                     help="another run's directory, same configuration at "
                          "other epsilons, read-only; repeatable")

    ui = sub.add_parser("ui",
                        help="look at every run under a directory: the same "
                             "local, read-only server (docs/UI.md)")
    ui.add_argument("runs_dir", nargs="?", default="runs",
                    help="a directory of run directories (default: ./runs)")
    ui.add_argument("--demo", action="store_true",
                    help="open the published arxiv-150k fixture's own run: "
                         "real receipts, real digests, real report. It is "
                         "someone else's corpus and the page says so")
    ui.add_argument("--port", type=int, default=0,
                    help="default: an ephemeral port")
    ui.add_argument("--host", default="127.0.0.1",
                    help="default 127.0.0.1; anything but loopback also "
                         "needs --i-know")
    ui.add_argument("--i-know", action="store_true", dest="i_know",
                    help="serve on a non-loopback --host, after a warning "
                         "naming what that exposes")
    ui_browser = ui.add_mutually_exclusive_group()
    ui_browser.add_argument("--open", action="store_true",
                            help="open the URL in a browser")
    ui_browser.add_argument("--no-browser", action="store_true",
                            help="the default: open nothing")
    p_ = sub.add_parser("propose",
                        help="measure a parameter change you wrote yourself "
                             "against a prediction you wrote first")
    p_.add_argument("workdir",
                    help="a workdir `characterize` and `simulate` have "
                         "already written")
    p_.add_argument("--policy", required=True,
                    help="the policy file: which family, which configuration, "
                         "which parameter changes (see docs/PROPOSALS.md)")
    p_.add_argument("--prediction", required=True,
                    help="what the change is expected to do, and what it must "
                         "not do -- written before the run, and judged as "
                         "written")
    p_.add_argument("--name", default=None,
                    help="the proposal's directory under <workdir>/proposals; "
                         "defaults to what the policy changes")
    p_.add_argument("--requirements", default=None,
                    help="the requirements file the baseline run used; "
                         "defaults to the one simulate_info.json recorded")
    p_.add_argument("--dry-run", action="store_true",
                    help="validate both files and print what would run, "
                         "measuring nothing and writing nothing")
    envmod.add_argument(p_)

    sub.add_parser("fixture",
                   help="build or verify a public fixture",
                   add_help=False)
    sub.add_parser("calibrate",
                   help="measure this installation against published numbers "
                        "and real engines",
                   add_help=False)
    sub.add_parser("pod",
                   help="run a session on a RunPod pod",
                   add_help=False)
    sub.add_parser("adapters",
                   help="ask each engine which index families it builds",
                   add_help=False)
    sub.add_parser("models",
                   help="run the family conformance suite",
                   add_help=False)
    sub.add_parser("library",
                   help="validate a card against the public library's "
                        "required shape; submits nothing",
                   add_help=False)
    sub.add_parser("bridge",
                   help="export a workdir for VectorDBBench, or import "
                        "its result -- docs/BRIDGE.md",
                   add_help=False)
    return ap


def main(argv=None):
    """The command line's entry point, and the one place a refusal is
    printed.

    Task 046. Until this, `intake.RequirementsError` -- the project's own
    refusal type, twenty-five messages each naming a field -- escaped as an
    unhandled traceback with the sentence on the last line. So the commonest
    refusal in the product was met as a crash by every command-line user, and
    the form looked clean only because `lab/compose.py` catches it from
    `intake.load()` directly and never comes through here.

    **This changes what the command line prints and returns**, for a case
    that is not rare: a missing or malformed requirements file now prints one
    line and exits 2, where it printed a traceback and exited 1. The code is
    the one `guard_or_exit` and `_cmd_propose` already use, so a refusal
    leaves the tool the same way whichever part produced it.
    """
    argv = list(sys.argv[1:] if argv is None else argv)

    # Recorded before anything runs, so every receipt written under this
    # command names it (task 046, docs/INTERFACE.md section 2). Here rather
    # than in each writer because there is one command per process and a
    # writer that had to be told would be a writer that could be forgotten.
    provenance.record_invocation(argv)

    try:
        return _dispatch(argv)
    except BaseException as e:                            # noqa: BLE001
        # Re-raised unless it is a declared refusal, so a genuine failure
        # keeps its traceback -- which is the thing a traceback is for. The
        # set is exact on the type and lives in `oneground/refusals.py` with
        # a reason per entry; anything not in it comes out of here unchanged.
        if not refusals.is_refusal(e):
            raise
        where = ("oneground " + argv[0]) if argv else "oneground"
        print(f"{where}: refused. {e}", file=sys.stderr)
        return refusals.REFUSED_EXIT


def _dispatch(argv):
    # `fixture` and `pod` own the rest of the command line; parsing them here
    # would mean maintaining two copies of their flags. `propose translate`
    # joins them for the same reason: its flags do not fit the shared
    # `propose` subparser's --policy/--prediction shape.
    if argv and argv[0] == "propose" and len(argv) > 1 and argv[1] == "translate":
        return _cmd_propose_translate(argv[2:])
    if argv and argv[0] == "fixture":
        return _cmd_fixture(argv[1:])
    if argv and argv[0] == "calibrate":
        return _cmd_calibrate(argv[1:])
    if argv and argv[0] == "pod":
        return _cmd_pod(argv[1:])
    if argv and argv[0] == "adapters":
        return _cmd_adapters(argv[1:])
    if argv and argv[0] == "models":
        return _cmd_models(argv[1:])
    if argv and argv[0] == "library":
        return _cmd_library(argv[1:])
    if argv and argv[0] == "bridge":
        return _cmd_bridge(argv[1:])

    args, rest = build_parser().parse_known_args(argv)
    if args.command == "characterize":
        return _cmd_characterize(args, rest)
    if args.command == "chunk":
        return _cmd_chunk(args, rest)
    if args.command == "simulate":
        return _cmd_simulate(args, rest)
    if args.command == "verify":
        return _cmd_verify(args, rest)
    if args.command == "report":
        return _cmd_report(args, rest)
    if args.command == "lab":
        return _cmd_lab(args, rest)
    if args.command == "ui":
        return _cmd_ui(args, rest)
    if args.command == "propose":
        return _cmd_propose(args, rest)
    build_parser().print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
