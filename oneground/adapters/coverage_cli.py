"""`oneground adapters coverage` -- ask each engine what it can build.

Task 034. The four index algorithms `simulate` measures are faiss's four, and
no engine offers all of them. Which ones an engine offers is a fact about that
engine at that version, so this command *asks it*, records the answer with the
version that gave it, and writes the result where the plan-time refusal and
`docs/ADAPTERS.md` can read it.

    oneground adapters coverage                 # every reachable engine
    oneground adapters coverage --engine qdrant
    oneground adapters coverage --out adapters/index-coverage.json

An engine that is not reachable is **skipped and reported as skipped**. It is
never filled in from documentation: a table typed in from a release note is a
guess about a version nobody ran, and it would be indistinguishable in a
report from an answer an engine actually gave.

Endpoints come from the same environment variables the conformance suite uses
(`ONEGROUND_QDRANT_URL`, `ONEGROUND_PGVECTOR_URL`) or from `--endpoint`.
"""

import argparse
import os
import sys

from . import get, index_families as IF
from .conformance import LIVE_ENGINES

DEFAULT_OUT = os.path.join("adapters", "index-coverage.json")


def resolve_one(engine_name, endpoint, log=print):
    """Connect, ask, disconnect. Returns an `IndexCoverage` or None."""
    adapter = get(engine_name)()
    adapter.connect(endpoint)
    coverage = adapter.index_families()
    problems = IF.problems(coverage)
    if problems:
        raise IF.CoverageError("index coverage refused:\n  - "
                               + "\n  - ".join(problems))
    log(f"  {engine_name} {coverage.engine_version}: builds "
        + (", ".join(coverage.buildable()) or "nothing this project declares"))
    return coverage


def _endpoint_for(engine_name, override=None):
    if override:
        return override
    for name, var in LIVE_ENGINES:
        if name == engine_name:
            return os.environ.get(var) or ""
    return "memory://" if engine_name == "stub" else ""


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(
        prog="oneground adapters",
        description="Ask each engine which index families it builds.")
    sub = ap.add_subparsers(dest="what", required=True)
    cov = sub.add_parser("coverage",
                         help="resolve index families against live engines")
    cov.add_argument("--engine", action="append", default=None,
                     help="only this engine; repeatable")
    cov.add_argument("--endpoint", default=None,
                     help="endpoint for the single engine named by --engine")
    cov.add_argument("--out", default=DEFAULT_OUT,
                     help=f"where to write the record (default {DEFAULT_OUT})")
    args = ap.parse_args(argv)

    wanted = args.engine or ([n for n, _ in LIVE_ENGINES] + ["stub"])
    print(f"adapters coverage: {len(wanted)} engine(s) asked")
    resolved, skipped, failed = [], [], []
    for name in wanted:
        endpoint = _endpoint_for(name, args.endpoint if args.engine and
                                 len(args.engine) == 1 else None)
        if not endpoint:
            var = dict(LIVE_ENGINES).get(name, "")
            skipped.append((name, f"{var} not set" if var
                            else "no endpoint given"))
            continue
        try:
            resolved.append(resolve_one(name, endpoint))
        except Exception as e:                            # noqa: BLE001
            failed.append((name, f"{type(e).__name__}: {e}"))

    for name, why in skipped:
        print(f"  {name} SKIPPED: {why} (a skip, not an answer -- its index "
              "families stay couldnt_check)")
    for name, why in failed:
        print(f"  {name} FAILED: {why}")

    if resolved:
        out = args.out
        directory = os.path.dirname(os.path.abspath(out))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        IF.write(out, resolved)
        print(f"\n  {len(resolved)} resolution(s) written to {out}")
    else:
        print("\n  nothing written: no engine answered")
    return 1 if failed else 0


if __name__ == "__main__":                                # pragma: no cover
    sys.exit(main())
