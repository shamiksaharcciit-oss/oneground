"""`oneground bridge export` / `oneground bridge import` -- reachable.

`docs/BRIDGE.md` §7, "what this position does not settle": *"Whether the
export belongs in `report`... or as its own command. Probably the
latter, since it produces files for a tool we do not run."* Not a
ruling -- the section says so by its own heading -- but a stated lean,
with a reason, which is what this module builds from rather than a
guess: its own command, exposing `oneground.bridge.export.export` and
`oneground.bridge.import_result.read_result_file` exactly as they
already are. No new parameter, no new file format, no decision this
position paper left open (§7's other open questions -- filtered-search
cases, scalar labels, what a disagreeing recall means -- are untouched).

`import` is read-only by the same logic `oneground adapters`/`oneground
models` already use for a command that measures nothing of its own: it
reads a file a user's own VectorDBBench run produced and prints what
`import_result` computes from it. It writes nothing, so it is not
guarded the way `export` is.
"""

import argparse
import json
import sys


def build_parser():
    ap = argparse.ArgumentParser(prog="oneground bridge")
    sub = ap.add_subparsers(dest="action", required=True)

    e = sub.add_parser(
        "export",
        help="write train/test/neighbors.parquet and the card for "
             "VectorDBBench, from a characterized workdir")
    e.add_argument("requirements", help="the requirements.yaml the "
                   "workdir was built from")
    e.add_argument("--query-subset-seed", type=int, required=True,
                   dest="query_subset_seed")
    e.add_argument("--query-subset-size", type=int, required=True,
                   dest="query_subset_size")
    e.add_argument("--k", type=int, default=100,
                   help="ground-truth neighbours per query (default 100, "
                        "oneground.bridge.export's own default)")
    e.add_argument("--file-count", type=int, default=1, dest="file_count")
    e.add_argument("--workdir", default=None,
                   help="defaults to the requirements file's own workdir")
    e.add_argument("--out", default=None,
                   help="defaults to the workdir")

    i = sub.add_parser(
        "import",
        help="read a VectorDBBench result file and print its per-case "
             "raw numbers; writes nothing")
    i.add_argument("result", help="a VectorDBBench result_*.json file")
    return ap


def _cmd_export(args):
    from ..environment import guard_or_exit
    _stamp, code = guard_or_exit("oneground bridge export")
    if code:
        return code

    from .export import ExportError, export
    try:
        result = export(
            args.requirements, args.out, args.query_subset_seed,
            args.query_subset_size, k=args.k, file_count=args.file_count,
            workdir=args.workdir, log_fn=print)
    except ExportError as e:
        print(f"oneground bridge export: refused. {e}")
        return 2
    print(f"wrote {result['card']}")
    for name, sha in sorted(result["files"].items()):
        print(f"  {name}  {sha[:12]}")
    return 0


def _cmd_import(args):
    from .import_result import BridgeImportError, read_result_file
    try:
        result = read_result_file(args.result)
    except BridgeImportError as e:
        print(f"oneground bridge import: refused. {e}")
        return 2
    print(json.dumps(result, indent=2))
    measured = sum(1 for c in result["cases"] if c["outcome"] == "measured")
    couldnt = len(result["cases"]) - measured
    print(f"\n{len(result['cases'])} case(s): {measured} measured, "
         f"{couldnt} couldnt_check", file=sys.stderr)
    return 0


def main(argv):
    args = build_parser().parse_args(argv)
    if args.action == "export":
        return _cmd_export(args)
    if args.action == "import":
        return _cmd_import(args)
    build_parser().print_help()                   # pragma: no cover
    return 1
