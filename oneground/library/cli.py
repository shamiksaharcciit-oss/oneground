"""`oneground library check-card` -- the validator, reachable.

`docs/LIBRARY.md` §7: "The first implementation is the card schema and
its validator... A library with nothing in it that refuses correctly is
further along than one full of cards nobody can read." That was built
(task 058) with no way for a person to reach it
(`tasks/finding-a-capability-with-no-command.md`). This is the command
the paper's own sequencing implies -- **validation only.**

**Submission is deliberately not here.** `docs/LIBRARY.md` §6 leaves the
transport unsettled -- "whether cards are submitted to a hosted index,
published as files in repositories and aggregated by a crawler, or
exchanged privately between teams... is its own decision" -- and §5's
"a card is submitted by its producer, never scraped" names no command,
no endpoint, no file format for the act of submitting. Building any of
those here would be exactly the guess this command exists to refuse:
the paper says what a card must contain and that submission validates
it; it does not say where a submission goes, so nothing here sends a
card anywhere. `check-card` reads a file, validates it, and reports --
the same shape `oneground fixture verify` already has for a different
kind of file.
"""

import argparse
import json
import sys

from . import card_schema


def build_parser():
    ap = argparse.ArgumentParser(prog="oneground library")
    sub = ap.add_subparsers(dest="action", required=True)
    c = sub.add_parser(
        "check-card",
        help="validate a card against docs/LIBRARY.md §2's required "
             "shape -- refuses with every missing field named at once; "
             "submits nothing anywhere")
    c.add_argument("card", help="a JSON file shaped like a library card")
    return ap


def main(argv):
    args = build_parser().parse_args(argv)
    if args.action != "check-card":               # pragma: no cover
        build_parser().print_help()
        return 1

    try:
        with open(args.card, encoding="utf-8") as f:
            card = json.load(f)
    except OSError as e:
        print(f"oneground library check-card: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"oneground library check-card: {args.card} is not valid "
             f"JSON: {e}", file=sys.stderr)
        return 2

    try:
        card_schema.submit_card(card)
    except card_schema.LibraryCardRefused as e:
        print(str(e))
        return 2

    print(f"{args.card}: accepted. Every field docs/LIBRARY.md §2 "
         "requires is present; nothing here submits it anywhere.")
    return 0
