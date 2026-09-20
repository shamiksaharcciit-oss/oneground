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
    oneground calibrate <curve|engine|show>      measure our own error
    oneground fixture verify <id>                check a fixture's digests
    oneground fixture build --spec ... --source ...
    oneground pod <plan|up|status|fetch|down|watch|ls>

`fixture`, `calibrate` and `pod` are delegated rather than reimplemented. Each
has its own parser and its own tests, and `pod` has its own money boundary:
folding that one into this parser would put a billable path behind a shared
argument parser for no gain. `calibrate` is delegated for a smaller reason --
it has five actions with disjoint flags, and it must be importable on a
machine with neither faiss nor a qdrant client.
"""

import argparse
import sys

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
    names |= {f"oneground fixture {a}" for a in _fixture_actions()}
    names |= {f"oneground calibrate {a}" for a in _calibrate_actions()}
    names.add("oneground pod")            # one money boundary, one entry
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
    # Task 034. A configuration that could not be built is reported and the
    # sweep goes on, so the rows already measured are not lost -- but a run
    # that did not measure what it planned to exits non-zero, because
    # couldn't-check is never rounded up to success.
    dropped = getattr(simulate.run, "last_dropped", None) or []
    if dropped:
        planned = getattr(simulate.run, "last_planned", len(dropped))
        print(f"\n  exit 1: {len(dropped)} of {planned} planned "
              f"configuration(s) were not measured. The rest were, and are in "
              f"simulate.json;")
        print("  each one that was not is named with its reason in "
              "simulate_info.json:dropped.")
        return 1
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
        labserver.check_host(args.host, args.i_know)
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
    return ap


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    # `fixture` and `pod` own the rest of the command line; parsing them here
    # would mean maintaining two copies of their flags.
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
    if args.command == "propose":
        return _cmd_propose(args, rest)
    build_parser().print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
