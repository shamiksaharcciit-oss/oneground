#!/usr/bin/env python3
"""Every field the export changed, computed rather than remembered.

**Run this before any hand-over of `site/teaser/data/` to core. It is a step,
not a convenience.**

    python corpora/declare_export_changes.py            # against HEAD
    python corpora/declare_export_changes.py <ref>      # against any commit

WHY THIS IS A STEP
------------------
Task 044e handed core four files with a list of what had changed in them. The
list was sincere and it was short by three: a full stop lost from
`verdict.price_table.source`, a path separator normalised in
`calibration.family_line.source`, and `inline.js` not being byte-reproducible.
Core found all three by diffing.

The fault was not inattention to those three fields. **It was handing over a
declaration with no comparison behind it** -- the list was written from
memory of what had been edited, which records what the author meant to change
and cannot record what the code did as well. The two differ precisely where it
matters, because a change you did not intend is the one you cannot recall.

When the comparison was finally computed, for task 044i, it found a **fourth**
that nobody had noticed on either side: `verdict.calibration.family_line` had
vanished entirely, 110 fields, because the report the verdict was rebuilt from
carries no glove calibration line.

> **A declaration of changes is only as good as the comparison behind it.**
> Writing the list from memory is how a careful person hands over an
> incomplete one and does not know it.

WHAT TO DO WITH THE OUTPUT
--------------------------
Every block it names goes in the hand-over, including the ones that are
obviously fine. "Obviously fine" is a judgement the recipient is entitled to
make for themselves, and the cost of listing a benign change is a line of
text; the cost of omitting one is that the next surprising change is met with
less trust than it needs.

Blocks that change by design -- a rebuilt `verdict`, a refreshed citation --
are declared as such with the reason, not left out because the reason is
known to the author.
"""

import argparse
import json
import os
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = "site/teaser/data/values.json"


def at_ref(ref, path):
    r = subprocess.run(["git", "show", "%s:%s" % (ref, path)], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit("cannot read %s at %s: %s" % (path, ref, r.stderr))
    return json.loads(r.stdout or "{}")


def flat(d, p=""):
    """Every leaf, by dotted path. Lists are indexed, so a reordering shows."""
    if isinstance(d, dict):
        for k, v in d.items():
            yield from flat(v, p + "." + str(k))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            yield from flat(v, "%s[%d]" % (p, i))
    else:
        yield p.lstrip("."), d


def by_block(keys):
    out = {}
    for k in keys:
        out.setdefault(k.split(".")[0].split("[")[0], []).append(k)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ref", nargs="?", default="HEAD",
                    help="the commit to compare against (default HEAD)")
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--show", type=int, default=6,
                    help="fields to print per block before summarising")
    a = ap.parse_args()

    old = at_ref(a.ref, a.path)
    with open(os.path.join(REPO, a.path), encoding="utf-8") as f:
        new = json.load(f)

    fa, fb = dict(flat(old)), dict(flat(new))
    groups = (
        ("CHANGED", sorted(k for k in set(fa) & set(fb) if fa[k] != fb[k])),
        ("REMOVED", sorted(set(fa) - set(fb))),
        ("ADDED", sorted(set(fb) - set(fa))),
    )

    print("%s: %s -> working tree\n" % (a.path, a.ref))
    total = 0
    for label, keys in groups:
        total += len(keys)
        blocks = by_block(keys)
        print("== %s: %d field(s) in %d block(s) ==" % (label, len(keys),
                                                        len(blocks)))
        for block in sorted(blocks):
            ks = blocks[block]
            print("  %-16s %d field(s)" % (block, len(ks)))
            for k in ks[:a.show]:
                if label == "CHANGED":
                    print("      %s\n          %r\n       -> %r"
                          % (k, fa[k], fb[k]))
                else:
                    src = fb if label == "ADDED" else fa
                    print("      %s = %r" % (k, src[k]))
            if len(ks) > a.show:
                print("      ... and %d more in this block" % (len(ks) - a.show))
        print()

    print("%d field(s) changed in total. Every block named above belongs in "
          "the hand-over,\nincluding the ones that are obviously fine."
          % total)


if __name__ == "__main__":
    main()
