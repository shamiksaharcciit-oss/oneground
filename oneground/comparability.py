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
It is therefore never evidence of the same machine. A recorded pod id is, and
is used when both runs carry one.

Since task 043 a local run records an **installation digest** as well — a
truncated one-way hash of a salt held on the machine and never published — so
two local runs from one installation are evidence of the same place. Before
043 this ingredient was `unknown` for every pair of local runs, which made the
whole verdict `couldnt_check` for anyone not renting a machine. The digest
supports *"the same installation"*; it does not support *"the same machine"*,
because the salt is per installation and two installations on one machine
produce two digests.

Nothing here measures anything. It reads receipts and compares recorded
strings, which is why it can be imported by a lab transport module that is
forbidden every package that measures.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

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


# --------------------------------------------------------------------------
# where each fact may be carried (task 043)
# --------------------------------------------------------------------------
# This function had failed the same way four times before this declaration
# existed. Three were ABSENCES -- a fact reachable from several files, read
# from one, reported as missing:
#
#   `oneground`          read from the receipts only; a run whose report
#                        carried the commit reported `code: unknown` (041,
#                        published as a finding about the artifacts before
#                        anyone saw it was the reader)
#   `library_versions`   read from the receipts only (043, caught by
#                        `test_comparability_reader` on its first run, on a
#                        fact nobody was investigating)
#   `python_version`     the same, latent
#
# The fourth was a WRONG VALUE, which no exhaustive absence test can catch,
# because the field was present:
#
#   `report.json` carries TWO environment blocks on purpose. `environment` is
#   the machine that MEASURED; `run_environment` is the machine that WROTE THE
#   REPORT. The reader took the second. On the published arXiv fixture that
#   returned `environment_id: local:windows-amd64` and `pod: None` -- silently
#   discarding the pod id -- in the same dict as `platform:
#   Linux-6.8.0-...`. One facts dict describing a Linux pod and a Windows
#   laptop as one run, landing on the only ingredient that can make `machine`
#   knowable at all.
#
# So the carriers are DATA, and the order is the precedence rule written down
# rather than implied by the order somebody happened to write `if` statements.
# `facts_of` iterates this; nothing reads a receipt any other way; and
# `test_comparability_reader` asserts against this declaration rather than
# against a restatement of it, which is what makes both absence and
# wrong-carrier checkable by one test.

#: A carrier is `(file, dotted key path)`. `"*info"` means every file in
#: `INFO_FILES`, in their declared order. The FIRST carrier that yields a
#: value wins, so the list is the precedence.
ANY_INFO = "*info"

FACT_CARRIERS = {
    "code": (
        (ANY_INFO, "oneground"),
        ("report.json", "oneground"),
    ),
    "libraries": (
        (ANY_INFO, "library_versions"),
        ("report.json", "library_versions"),
        ("report.json", "environment.library_versions"),
        ("report.json", "run_environment.library_versions"),
    ),
    "platform": (
        (ANY_INFO, "platform"),
        ("report.json", "platform"),
        ("report.json", "environment.platform"),
    ),
    "python_version": (
        (ANY_INFO, "python_version"),
        ("report.json", "python_version"),
        ("report.json", "environment.python_version"),
        ("report.json", "run_environment.python_version"),
    ),
    "requirements_file": (
        (ANY_INFO, "requirements_file"),
        ("report.json", "requirements_file"),
    ),
    # THE MEASURING MACHINE FIRST, ALWAYS. `environment` is where it ran;
    # `run_environment` is where the report was written, and for a pod run
    # those are different machines. Reading the second is how a pod id was
    # discarded and a Linux run reported as a Windows laptop.
    "environment_id": (
        ("report.json", "environment.environment_id"),
        (ANY_INFO, "environment.environment_id"),
        (ANY_INFO, "environment_id"),
        ("report.json", "run_environment.environment_id"),
    ),
    "installation": (
        ("report.json", "environment.installation"),
        (ANY_INFO, "environment.installation"),
        (ANY_INFO, "installation"),
        ("report.json", "run_environment.installation"),
    ),
}


def _dig(doc, path):
    """A dotted key path into a nested dict, or None."""
    cur = doc
    for part in str(path).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _carried(infos, report, fact):
    """`(value, where)` for `fact`, from the first carrier that has it."""
    for where, path in FACT_CARRIERS[fact]:
        if where == ANY_INFO:
            for name in INFO_FILES:
                got = _dig(infos.get(name) or {}, path)
                if got:
                    return got, name
        else:
            got = _dig(report if where == "report.json" else {}, path)
            if got:
                return got, where
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

    code, code_from = _carried(infos, report, "code")
    libs, libs_from = _carried(infos, report, "libraries")
    plat, plat_from = _carried(infos, report, "platform")
    py, py_from = _carried(infos, report, "python_version")
    req, req_from = _carried(infos, report, "requirements_file")
    env, env_from = _carried(infos, report, "environment_id")
    installation, _ = _carried(infos, report, "installation")

    inputs = report.get("inputs") or {}
    sample = (inputs.get("characterization.json") or {}).get("sha256")

    # A pod records an identity; `local:<os>-<arch>` records a class.
    pod = env if (env and not str(env).startswith("local:")) else None

    # A commit identifies the code only if the tree was clean when it ran.
    # `dirty: true` means uncommitted changes were in the interpreter, so two
    # runs at the same commit were not necessarily the same code -- which is
    # exactly the case task 028c caught by re-measuring. Dirty is therefore
    # unknown, with its reason, and never a match.
    code_id, dirty = None, None
    if isinstance(code, dict):
        dirty = bool(code.get("dirty"))
        if code.get("commit") and not dirty:
            code_id = f"{code.get('version')}@{code['commit']}"
    elif code:
        code_id = str(code)

    return {
        "workdir": workdir,
        "run": report.get("run") or os.path.basename(workdir),
        "code": code_id, "code_from": code_from, "code_dirty": dirty,
        "code_block": code,
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
        "installation": installation,
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
     "the oneground version that measured one of these runs is not usable as "
     "an identity: either no artifact records it (the field task 033 added is "
     "absent, and nothing can add a version to an old artifact honestly), or "
     "it was recorded with `dirty: true`, meaning uncommitted changes were in "
     "the interpreter and the commit does not identify the code that ran"),
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
     "neither run records a pod id or an installation digest, so there is "
     "nothing that identifies where they ran. `environment_id` is "
     "`local:<os>-<arch>`, a class rather than an identity, and two different "
     "machines share one. An artifact produced before task 043 carries no "
     "installation digest and nothing can add one to it honestly"),
)


# --------------------------------------------------------------------------
# row-level provenance: two lists, and neither subsumes the other (task 043)
# --------------------------------------------------------------------------
# `facts_of` answers *may these two RUNS sit side by side*. A table places
# ROWS beside each other, and the rows in one report may come from different
# runs -- which is the whole of `docs/BRIDGE.md` section 4's table rule.
#
# A row carries TWO provenance lists because they answer different questions
# and neither implies the other:
#
#   WHAT WAS MEASURED     the corpus digest, the ground truth, the query subset
#   WHAT DID THE MEASURING  the code, the libraries, the settings, the machine
#
# Two rows can agree completely on one and differ on the other, in both
# directions: the same corpus measured by two different builds, or two
# different corpora measured by one build. Collapsing them into a single
# "provenance" field makes those two cases indistinguishable, and they license
# entirely different sentences -- the first is a question about the code, the
# second is not a comparison at all.

MEASURED_KEYS = ("sample", "ground_truth", "query_subset")
MEASURING_KEYS = ("code", "libraries", "settings", "platform",
                  "python_version", "machine")


@dataclass(frozen=True)
class Provenance:
    """A row's two provenance lists, and where each value was read."""

    measured: Dict[str, Any] = field(default_factory=dict)
    measuring: Dict[str, Any] = field(default_factory=dict)
    run: Optional[str] = None
    workdir: Optional[str] = None

    def as_dict(self):
        return {"run": self.run, "workdir": self.workdir,
                "measured": dict(self.measured),
                "measuring": dict(self.measuring)}


def provenance_of(facts):
    """Split one run's facts into the two lists a row carries.

    `query_subset` is **absent by construction**: `docs/BRIDGE.md` section 3.3
    records that no receipt expresses it -- no seed, no size, no selection,
    because no command has ever taken one. It is declared here as a key that
    is always `None` rather than omitted, so a comparison over it is
    `couldnt_check` and visibly so, instead of the list quietly having two
    members where the design says three.
    """
    measured = {
        "sample": facts.get("sample"),
        # The exact k-NN a row was scored against. Recorded per run today; a
        # row-level ground truth is what BRIDGE section 4 will need.
        "ground_truth": facts.get("sample"),
        "query_subset": None,
    }
    measuring = {
        "code": facts.get("code"),
        "libraries": facts.get("libraries"),
        "settings": facts.get("settings"),
        "platform": facts.get("platform"),
        "python_version": facts.get("python_version"),
        # A pod id, else the installation digest, else nothing. The same
        # precedence `verdict` uses, so run-level and row-level agree.
        "machine": facts.get("pod") or facts.get("installation"),
    }
    return Provenance(measured=measured, measuring=measuring,
                      run=facts.get("run"), workdir=facts.get("workdir"))


def rows_may_share_a_table(left, right):
    """May two ROWS sit in one table? `BRIDGE.md` section 4's rule, executable.

    Returns the three-valued verdict with a finding per key, and reports the
    two lists separately, because *the same corpus measured by two builds* and
    *two corpora measured by one build* are different answers and a caller
    needs to know which it has.
    """
    findings, states = [], []
    for group, keys in (("measured", MEASURED_KEYS),
                        ("measuring", MEASURING_KEYS)):
        for key in keys:
            a = getattr(left, group).get(key)
            b = getattr(right, group).get(key)
            state = _compare(a, b)
            states.append((group, key, state))
            findings.append({"list": group, "ingredient": key,
                             "state": state, "left": a, "right": b})

    measured_states = [s for g, _, s in states if g == "measured"]
    if DIFFERS in measured_states:
        # Different ground truth or different corpus: not a comparison at all,
        # whatever the code did.
        return {"verdict": NOT_COMPARABLE, "findings": findings,
                "why": ("these rows were measured against different data, so "
                        "they answer different questions and may not share a "
                        "table however they were produced")}
    if DIFFERS in [s for g, _, s in states if g == "measuring"]:
        return {"verdict": NOT_COMPARABLE, "findings": findings,
                "why": ("these rows were measured on the same data by "
                        "different means, which is a question about the "
                        "difference rather than a row to place beside "
                        "another")}
    if UNKNOWN in [s for _, _, s in states]:
        return {"verdict": COULDNT_CHECK, "findings": findings,
                "why": ("something these rows would have to agree about is "
                        "not recorded by one of them, so whether they may "
                        "share a table is not known -- which is not the same "
                        "as their being comparable")}
    return {"verdict": COMPARABLE, "findings": findings,
            "why": "same data, same means"}


def verdict(a, b):
    """The comparability verdict for two runs' facts, with its reasons.

    Returns the verdict, a sentence, and one finding per ingredient so a page
    can show *which* part is unknown rather than only that something is.
    """
    findings = []
    for key, required, unknown_note in INGREDIENTS:
        if key == "machine":
            # A pod id first, because it names a rented machine outright.
            # Failing that, the installation digest (task 043), which is an
            # identity where `environment_id` is only a class. `environment_id`
            # is still what is SHOWN, because the digest says nothing to a
            # reader and the class says where the run happened.
            state = _compare(a.get("pod"), b.get("pod"))
            if state == UNKNOWN:
                state = _compare(a.get("installation"), b.get("installation"))
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
