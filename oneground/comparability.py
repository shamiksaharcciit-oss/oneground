"""The comparability verdict: may two runs be placed side by side?

`docs/LIBRARY.md` §2.2 specifies this and says plainly that it is *"written
here and implemented nowhere"*, that three positions depend on it — the
library's cards, the interface's side-by-side view, and the VectorDBBench
bridge — and that **whichever is built first builds it, and the other two
cite it rather than re-deriving a second answer to the same question.** Task
041 reached it first, so it lives here, at the package root, rather than
inside the interface: a verdict about provenance is not an interface concern
and a second copy of it would be the thing §2.2 exists to prevent.

It is deliberately *not* `oneground/calibrate/history.py:comparable`, which
compares `(check, dataset, engine, engine_version, config)` — engine
identity. §2.2 calls that "the right shape and the wrong subject", and it is
left alone.

THREE VALUES, AND WHY THE THIRD IS NOT A HEDGE
-----------------------------------------------
`comparable`, `not_comparable`, `couldnt_check` — the same three this project
keeps apart everywhere. A two-valued verdict forces an unknown into one of
them, and an unknown rounded up is the failure the product exists to refuse.

The ordering is not symmetric, and the asymmetry is the point:

* any ingredient that **differs** makes the pair `not_comparable`. One
  difference is enough, and knowing about it beats not knowing.
* otherwise any required ingredient that is **unknown** makes it
  `couldnt_check`. A missing version is never read as a match.
* only when every required ingredient is **known and equal** is a pair
  `comparable`.

WHAT CANNOT BE ASSERTED, EVER, FROM WHAT A RUN RECORDS TODAY
-------------------------------------------------------------
**The same code.** Task 033 records an `oneground` block on declared
artifacts, and a pair whose two runs carry the same commit can say
`comparable`. A run written before that field existed stays `couldnt_check`,
because nothing can add a version to an old artifact honestly. §2.2's own
example is why this is not pedantry: task 028c found today's build answering
`recall_at_1` 0.874 where a recorded row said 0.875, and no ingredient on the
card could have caught it — a card inferring `comparable` from matching
library versions would have asserted something false about exactly those two
rows.

**The same machine.** `environment_id` is `local:<os>-<arch>` by
construction: a class, not an identity, so two different laptops share one.
It is therefore never evidence of the same machine. A recorded pod id is,
and is used when both runs carry one.

Nothing here measures anything. It reads receipts and compares recorded
strings, which is why it can be imported by a lab transport module that is
forbidden every package that measures.
"""

import json
import os

COMPARABLE = "comparable"
NOT_COMPARABLE = "not_comparable"
COULDNT_CHECK = "couldnt_check"

SAME = "same"
DIFFERS = "differs"
UNKNOWN = "unknown"

#: The `_info.json` receipts a run may carry, in the order they are consulted
#: for a fact that any of them could record.
INFO_FILES = ("report_info.json", "verify_info.json", "simulate_info.json",
              "characterization_info.json", "build_info.json")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _first(infos, key):
    for name in INFO_FILES:
        d = infos.get(name)
        if isinstance(d, dict) and d.get(key) not in (None, {}, ""):
            return d[key], name
    return None, None


def facts_of(workdir):
    """What one run records about how it was produced.

    Every value is copied from a receipt and carries the file it came from,
    so a verdict can say not only that two runs differ but where each side
    was read.
    """
    workdir = os.path.abspath(workdir)
    infos = {n: _read(os.path.join(workdir, n)) for n in INFO_FILES}
    report = _read(os.path.join(workdir, "report.json")) or {}

    code, code_from = _first(infos, "oneground")
    libs, libs_from = _first(infos, "library_versions")
    plat, plat_from = _first(infos, "platform")
    py, py_from = _first(infos, "python_version")
    req, req_from = _first(infos, "requirements_file")

    inputs = report.get("inputs") or {}
    sample = (inputs.get("characterization.json") or {}).get("sha256")

    env = (report.get("run_environment") or {}).get("environment_id")
    # A pod records an identity; `local:<os>-<arch>` records a class.
    pod = env if (env and not str(env).startswith("local:")) else None

    return {
        "workdir": workdir,
        "run": report.get("run") or os.path.basename(workdir),
        "code": code, "code_from": code_from,
        "libraries": libs, "libraries_from": libs_from,
        "platform": plat, "platform_from": plat_from,
        "python_version": py, "python_from": py_from,
        # The requirements digest, not its path: the path is where the file
        # sat on somebody's machine, and the digest is which file it was.
        "settings": (req or {}).get("sha256") if isinstance(req, dict) else None,
        "settings_from": req_from,
        "sample": sample,
        "sample_from": "report.json:inputs" if sample else None,
        "environment_id": env,
        "pod": pod,
    }


def _compare(a, b):
    if a is None or b is None:
        return UNKNOWN
    return SAME if a == b else DIFFERS


#: Each ingredient: the key, whether `comparable` requires it, and the
#: sentence said when it is unknown. The sentences are the useful half --
#: "unknown" on its own tells a reader nothing they can act on.
INGREDIENTS = (
    ("code", True,
     "no artifact in one of these runs records the oneground version that "
     "measured it; the field task 033 added is absent, and nothing can add a "
     "version to an old artifact honestly"),
    ("libraries", True,
     "one of these runs records no library versions"),
    ("settings", True,
     "one of these runs records no requirements digest, so the run-level "
     "settings and the seed they declare cannot be compared"),
    ("sample", True,
     "one of these runs does not record its characterization digest, so the "
     "two may not have been measured on the same sample"),
    ("platform", False,
     "one of these runs records no platform"),
    ("python_version", False,
     "one of these runs records no python version"),
    ("machine", True,
     "environment_id is `local:<os>-<arch>`, a class rather than an "
     "identity, so two different machines share one; only a recorded pod id "
     "identifies a machine"),
)


def verdict(a, b):
    """The comparability verdict for two runs' facts, with its reasons.

    Returns the verdict, a sentence, and one finding per ingredient so a page
    can show *which* part is unknown rather than only that something is.
    """
    findings = []
    for key, required, unknown_note in INGREDIENTS:
        if key == "machine":
            state = _compare(a.get("pod"), b.get("pod"))
            left, right = a.get("environment_id"), b.get("environment_id")
        else:
            left, right = a.get(key), b.get(key)
            state = _compare(left, right)
        findings.append({
            "ingredient": key,
            "required": required,
            "state": state,
            "left": left,
            "right": right,
            "left_from": a.get(f"{key}_from"),
            "right_from": b.get(f"{key}_from"),
            "note": unknown_note if state == UNKNOWN else None,
        })

    differing = [f for f in findings if f["state"] == DIFFERS]
    unknown_required = [f for f in findings
                        if f["required"] and f["state"] == UNKNOWN]

    if differing:
        out = NOT_COMPARABLE
        reason = ("these runs differ in " +
                  ", ".join(f["ingredient"] for f in differing) +
                  ", so a difference between their numbers is not "
                  "attributable to the thing you are comparing")
    elif unknown_required:
        out = COULDNT_CHECK
        reason = ("; ".join(f["note"] for f in unknown_required))
    else:
        out = COMPARABLE
        reason = ("every ingredient that decides comparability is recorded "
                  "on both runs and agrees")

    return {
        "verdict": out,
        "reason": reason,
        "findings": findings,
        "left": a.get("run"),
        "right": b.get("run"),
        "differing": [f["ingredient"] for f in differing],
        "unknown": [f["ingredient"] for f in unknown_required],
    }


def compare_workdirs(left, right):
    """The verdict for two run directories."""
    return verdict(facts_of(left), facts_of(right))
