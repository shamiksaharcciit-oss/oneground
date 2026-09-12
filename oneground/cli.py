"""`oneground <command>` — the one entry point.

    oneground characterize <requirements.yaml>   measure your own vectors
    oneground simulate <requirements.yaml>       sweep architectures on them
    oneground verify <requirements.yaml>         measure a real engine
    oneground report <requirements.yaml>         judge them against constraints
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


@envmod.guarded("oneground simulate")
def _cmd_simulate(args, rest):
    from . import simulate
    if rest:
        raise SystemExit(f"oneground simulate: unexpected arguments: "
                         f"{' '.join(rest)}")
    simulate.run(args.requirements)
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


@envmod.guarded("oneground report")
def _cmd_report(args, rest, env_stamp=None):
    from . import report
    if rest:
        raise SystemExit(f"oneground report: unexpected arguments: "
                         f"{' '.join(rest)}")
    report.run(args.requirements, env_stamp=env_stamp)
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


def build_parser():
    ap = argparse.ArgumentParser(
        prog="oneground",
        description="Measure a retrieval architecture decision on your own "
                    "vectors, with the receipt attached.")
    ap.add_argument("--version", action="version",
                    version=f"oneground {__display_version__} "
                            f"({__version__})")
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

    s_ = sub.add_parser("simulate",
                        help="sweep architecture families on a characterized "
                             "sample")
    s_.add_argument("requirements",
                    help="path to the same requirements.yaml characterize used")
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

    args, rest = build_parser().parse_known_args(argv)
    if args.command == "characterize":
        return _cmd_characterize(args, rest)
    if args.command == "simulate":
        return _cmd_simulate(args, rest)
    if args.command == "verify":
        return _cmd_verify(args, rest)
    if args.command == "report":
        return _cmd_report(args, rest)
    build_parser().print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
