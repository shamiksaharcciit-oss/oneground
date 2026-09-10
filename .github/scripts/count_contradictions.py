#!/usr/bin/env python3
"""Which of the lines a calibration run just appended are blocking failures.

Extracted from `.github/actions/record-calibration/action.yml`, where it lived
inside a YAML heredoc and therefore could not be tested. That is how its bug
shipped: run #1 of the calibration workflow failed on seven contradictions it
had not produced.

THE BUG THIS REPLACES
---------------------
The old code filtered the whole history for blocking contradictions and then
took the last N of *those*, where N was the number of lines the run had
appended:

    bad = [blocking contradictions in the whole file]
    bad = bad[-appended:]

Those are two different lists. `calibration/history.jsonl` already carried
seven blocking contradictions -- glove_curve lines recorded before task 012b
ruled that check advisory -- and the run appended seven advisory lines. So the
slice returned all seven historical ones and failed the build on them. The
filter was correct; the slice undid it.

The order has to be the other way round: take the lines this run appended,
*then* ask which of them are blocking contradictions.

WHAT COUNTS
-----------
A line fails the build only if it is `contradicted` **and** its
`outcome_scope` is `blocking`. `couldnt_check` never fails: it is a gap in the
reference, not a defect in this installation. An advisory contradiction never
fails either -- the glove curve compares two HNSW implementations that
genuinely differ, and the difference is published as an offset -- but it stays
in the history, where it is meant to be visible.

A line with no `outcome_scope` is treated as blocking, because that was the
default before the field existed and silence must not weaken a gate.
"""

import argparse
import json
import sys

BLOCKING = "blocking"
CONTRADICTED = "contradicted"


def read_lines(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def blocking_contradictions(lines, appended):
    """The blocking contradictions among the last `appended` lines.

    `appended` is how many lines this run added. Zero means the run appended
    nothing, so it cannot have contradicted anything -- an empty result, not
    "look at everything".
    """
    appended = int(appended or 0)
    if appended <= 0:
        return []
    recent = lines[-appended:]
    return [d for d in recent
            if d.get("outcome") == CONTRADICTED
            and d.get("outcome_scope", BLOCKING) == BLOCKING]


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Count blocking contradictions among newly appended "
                    "calibration lines.")
    ap.add_argument("--history", default="calibration/history.jsonl")
    ap.add_argument("--appended", required=True,
                    help="how many lines this run appended")
    ap.add_argument("--github-output", default=None,
                    help="write count= and body= here (GITHUB_OUTPUT)")
    args = ap.parse_args(argv)

    lines = read_lines(args.history)
    bad = blocking_contradictions(lines, args.appended)

    out = [f"count={len(bad)}"]
    if bad:
        body = "\n".join(json.dumps(d, indent=2, sort_keys=True) for d in bad)
        out += ["body<<ONEGROUND_EOF", body, "ONEGROUND_EOF"]

    text = "\n".join(out) + "\n"
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text)

    # Always exit 0: counting is not judging. The workflow decides what to do
    # with the count, and a step that both counts and fails cannot be reused
    # by the advisory jobs.
    return 0


if __name__ == "__main__":
    sys.exit(main())
