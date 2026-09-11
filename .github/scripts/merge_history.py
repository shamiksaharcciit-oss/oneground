#!/usr/bin/env python3
"""Merge appended calibration lines onto whatever the remote branch holds.

The calibration history is **append-only**, so two runs that both append must
end up with both sets of lines. A plain `git rebase` would conflict on the
last line, and resolving it either way silently discards one run's
measurement -- which is the one thing an append-only file must never do.

So the merge is semantic rather than textual: take the branch's current
history, append the lines this run produced, keep the order. Nothing is
rewritten and nothing is dropped.

Every line is parsed before it is written. A run that somehow produced
malformed JSON should fail here, loudly, rather than push a history file that
`calibrate show` cannot read.
"""

import argparse
import json
import sys


def read_lines(path, *, required=True):
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                except ValueError as e:
                    raise SystemExit(
                        f"{path}:{n}: not valid JSON, refusing to push a "
                        f"history nothing can read -- {e}")
                out.append(line)
    except FileNotFoundError:
        if required:
            raise
    return out


def merge(base_lines, new_lines):
    """Base first, then the new lines that are not already present.

    Identity is the exact line. A rerun that appends a byte-identical line is
    not a second measurement, and duplicating it would inflate every count
    read off the file. Two genuinely separate measurements differ in their
    date, run id or environment, so this cannot collapse them.
    """
    seen = set(base_lines)
    out = list(base_lines)
    added = 0
    for line in new_lines:
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
        added += 1
    return out, added


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True,
                    help="the history as the branch currently has it")
    ap.add_argument("--append", required=True,
                    help="the lines this run produced")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    base = read_lines(args.base, required=False)
    new = read_lines(args.append)
    merged, added = merge(base, new)

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        for line in merged:
            f.write(line + "\n")

    skipped = len(new) - added
    print(f"{len(base)} existing + {added} new = {len(merged)} line(s)"
          + (f"  ({skipped} already present)" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
