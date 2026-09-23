"""Did replaying the recorded invocation produce the same artifacts?

`docs/INTERFACE.md` §2. Every UI action is exactly a CLI invocation; the
receipt names which (`provenance.invocation`); and this decides whether
running it again produced the same thing.

WHAT MUST MATCH, AND WHY THE LIST IS FIXED
------------------------------------------
That section already refuted the obvious rule. "Byte-identical" over
everything fails on the design: two runs of one command differ in
`simulate_info.json` at `run_at`, `elapsed_seconds` and `timings`, and
`MANIFEST.sha256` covers those files so it differs too. That is task 020b's
deliberate split -- facts *about* a run moved out of the rows precisely so the
rows would be byte-identical -- and asserting identity over everything would
fail on the thing that makes the rows trustworthy.

So the test names its exemptions. Three properties make that a test rather
than a concession:

1. **`MAY_DIFFER` is a declaration with a reason per entry**, not a set of
   names. An entry that cannot be justified in a sentence does not get added,
   because there is nowhere to put it.
2. **`test_replay.py` pins the list exactly.** Widening it means editing the
   declaration *and* the test *and* writing the reason, in one diff a reviewer
   sees whole. A quiet loosening is not available.
3. **Nothing is ignored wholesale.** `MANIFEST.sha256` is not skipped because
   it covers files that may differ; it is compared line by line with only the
   entries for those files set aside, so a manifest line for any other file
   still has to match exactly.

> **If something legitimate cannot match, that is a finding about the receipt,
> not a reason to widen this list.** A receipt that cannot be reproduced is
> telling you it records something it should not, or fails to record something
> it should. The first time that happens the temptation will be to add a name
> here; the honest move is to write it up and leave the list alone.
"""

import hashlib
import json
import os

#: Receipts whose *parsed* form is compared, with `MAY_DIFFER` set aside.
#: Everything else in a workdir is compared byte for byte.
INFO_FILES = ("build_info.json", "simulate_info.json", "verify_info.json",
              "chunk_info.json", "propose_info.json")

MANIFEST = "MANIFEST.sha256"

#: Dotted paths inside an `_info.json` that two runs of one command may
#: legitimately differ in, each with the reason it is here. Adding an entry
#: requires a reason, and `test_replay.py` pins this dictionary exactly.
MAY_DIFFER = {
    "run_at":
        "the wall clock when the run started; two runs are at two times",
    "elapsed_seconds":
        "how long it took, which is a property of the machine's load rather "
        "than of the result",
    "timings":
        "per-stage durations, for the same reason as elapsed_seconds",
    "oneground.dirty":
        "whether the working tree had uncommitted changes when the artifact "
        "was written. It can flip between two runs of one command without "
        "the code that ran changing -- an editor saving a docstring is "
        "enough -- and `oneground.commit` beside it does not move, which is "
        "the field that says what ran",
    "invocation.note":
        "empty for a command and a sentence for a library caller; the "
        "`command` beside it is the field a replay is about and it is not "
        "exempt",
}


class ReplayError(ValueError):
    """A replay could not be compared at all."""


def _flatten(obj, prefix=""):
    """Every leaf of a parsed document, as dotted paths."""
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(_flatten(v, f"{prefix}{i}."))
    else:
        out[prefix.rstrip(".")] = obj
    return out


def _exempt(path):
    """Whether a dotted path is one of the named exemptions.

    Matched on the path or any of its parents, so `timings` covers
    `timings.build` without `timings.build` needing its own entry -- but
    `oneground.dirty` does **not** cover `oneground.commit`, which is the
    distinction the whole list turns on.
    """
    parts = path.split(".")
    for i in range(len(parts)):
        if ".".join(parts[i:]) in MAY_DIFFER:
            return True
        if ".".join(parts[:i + 1]) in MAY_DIFFER:
            return True
    return False


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest_lines(path):
    """`{name: digest}` from a MANIFEST.sha256."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            digest, _, name = line.rstrip("\n").partition("  ")
            out[name.lstrip("*")] = digest
    return out


def compare(first, second):
    """Two workdirs from one invocation. Returns a verdict.

        {"matches": bool,
         "differing": [{"file", "field", "first", "second"}],
         "only_in_first": [...], "only_in_second": [...],
         "exempt": [{"file", "field"}],      # named, not hidden
         "compared": int}

    `exempt` is returned rather than discarded so a reader can see what was
    set aside on this particular comparison. A test that names its exemptions
    and then does not report them has only moved the silence.
    """
    for d in (first, second):
        if not os.path.isdir(d):
            raise ReplayError(f"not a directory: {d}")

    names_a = {n for n in os.listdir(first)
               if os.path.isfile(os.path.join(first, n))}
    names_b = {n for n in os.listdir(second)
               if os.path.isfile(os.path.join(second, n))}

    out = {"matches": True, "differing": [], "exempt": [],
           "only_in_first": sorted(names_a - names_b),
           "only_in_second": sorted(names_b - names_a),
           "compared": 0}
    if out["only_in_first"] or out["only_in_second"]:
        out["matches"] = False

    for name in sorted(names_a & names_b):
        a, b = os.path.join(first, name), os.path.join(second, name)
        out["compared"] += 1

        if name in INFO_FILES:
            try:
                with open(a, encoding="utf-8") as f:
                    fa = _flatten(json.load(f))
                with open(b, encoding="utf-8") as f:
                    fb = _flatten(json.load(f))
            except (OSError, ValueError) as e:
                raise ReplayError(f"{name}: {e}") from None
            for key in sorted(set(fa) | set(fb)):
                if fa.get(key) == fb.get(key):
                    continue
                if _exempt(key):
                    out["exempt"].append({"file": name, "field": key})
                    continue
                out["matches"] = False
                out["differing"].append({
                    "file": name, "field": key,
                    "first": fa.get(key), "second": fb.get(key)})
            continue

        if name == MANIFEST:
            # Not skipped. A manifest line for a file whose bytes may
            # legitimately differ is set aside; every other line must match,
            # which is what keeps this from being a hole the size of the
            # whole workdir.
            ma, mb = _manifest_lines(a), _manifest_lines(b)
            for entry in sorted(set(ma) | set(mb)):
                if ma.get(entry) == mb.get(entry):
                    continue
                if os.path.basename(entry) in INFO_FILES:
                    out["exempt"].append({"file": MANIFEST, "field": entry})
                    continue
                out["matches"] = False
                out["differing"].append({
                    "file": MANIFEST, "field": entry,
                    "first": ma.get(entry), "second": mb.get(entry)})
            continue

        if _sha256(a) != _sha256(b):
            out["matches"] = False
            out["differing"].append({"file": name, "field": None,
                                     "first": _sha256(a),
                                     "second": _sha256(b)})
    return out
