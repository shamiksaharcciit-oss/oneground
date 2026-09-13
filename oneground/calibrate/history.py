"""`calibration/history.jsonl` — one line per check per run, append only.

The file answers one question over time: *is this tool still telling the truth
about what it measures?* A single line is a measurement; only the accumulation
is a calibration.

Schema (task 012). Every field is required; a line missing one is refused at
write time rather than discovered later by a reader:

    date              UTC date of the run, YYYY-MM-DD
    check             which check produced it, e.g. `glove_curve` or
                      `simulator_vs_engine`
    dataset           the corpus the check ran on
    engine            what produced `measured`. `oneground/single_node_hnsw`
                      when the measurement is the simulator's own
    engine_version    version of that engine
    config            the architecture configuration, in the same label form
                      `simulate.json` uses
    measured          what this installation measured
    reference         what it was compared against, or null when there is none
    deviation         measured - reference, or null
    tolerance         the band `deviation` had to fall inside
    outcome           verified | contradicted | couldnt_check
    environment       where it ran (`local:<host>` or a pod id)
    pins_sha256       digest of requirements.txt, so a line says which
                      dependency set produced it
    oneground_version the package version

Two conventions that are not obvious from the field list:

**`deviation` is measured - reference.** Positive means this installation
scored *higher* than the published value. Note this is the opposite sign
convention from the pre-012 `calibration_error_recall` (simulated - measured)
that seeded the file; `simulator_vs_engine` lines keep that older definition
in `definition` and carry it in `deviation` as measured(sim) - reference
(engine), which is the same number. The `definition` field is written on every
line so no reader has to know which era a line came from.

**`outcome` is decided at write time, from `deviation` and `tolerance`.**
A reader never re-derives a verdict, so a tolerance changed later cannot
silently re-judge history. `couldnt_check` when `reference` is null: there was
nothing to compare against, and that is not a pass.

Append-only is enforced here, not just documented: `append()` opens with "a"
and there is no update or delete. A line measured wrongly is corrected by a
later line that says so.
"""

import functools
import json
import os
import platform
import time

VERIFIED = "verified"
CONTRADICTED = "contradicted"
COULDNT_CHECK = "couldnt_check"

FIELDS = ("date", "check", "dataset", "engine", "engine_version", "config",
          "measured", "reference", "deviation", "tolerance", "outcome",
          "environment", "pins_sha256", "oneground_version")

# The schema version stamped on new lines.
#
#   1   pre-012, hand-written from a verify run: `corpus`,
#       `simulated_recall_at_10`, `calibration_error_recall`, `environment_id`,
#       no `check` and no declared tolerance. `normalize` translates it.
#   2   task 012: the field list in this docstring, outcomes derived at write
#       time, append-only enforced.
#   3   task 012b: `simulator_vs_engine` lines must carry `efSearch` as its own
#       field. efSearch is not portable across HNSW implementations (faiss
#       reaches at e what hnswlib reached at ~1.4e-1.9e; see docs/MODELS.md),
#       so a point that does not say which efSearch it was taken at is not
#       comparable to one from another engine. Parsing it back out of a config
#       label works until a label changes shape, which is why it is a field.
SCHEMA = 3

# Checks whose lines must name the efSearch they were measured at, from
# schema 3 onward.
EFSEARCH_REQUIRED_FROM_SCHEMA = 3
EFSEARCH_REQUIRED_CHECKS = ("simulator_vs_engine",)

# `deviation` is rounded before the outcome is decided, at the same precision
# `receipts.FLOAT_DECIMALS` pins every other float in this project. Without it
# 0.52 - 0.50 is 0.020000000000000018 and a point exactly on a 0.02 tolerance
# is contradicted by the float representation rather than by the measurement.
DEVIATION_DECIMALS = 6

DEFAULT_PATH = os.path.join("calibration", "history.jsonl")

# A monthly CI job runs against a moving tag rather than the pinned one. Its
# lines are recorded so a drift is visible early, and marked so they can never
# block a release: the pinned run is the contract.
ADVISORY = "advisory"
BLOCKING = "blocking"


def utc_date():
    return time.strftime("%Y-%m-%d", time.gmtime())


def environment_id():
    """The pod id when there is one, else `local:<os>-<arch>`.

    Delegated to `oneground.environment`, which is stdlib-only -- importing
    `oneground.verify` here would pull the qdrant client and the load
    generator into `calibrate show`, which has to work on a machine with
    neither.

    This used to append `platform.node()`, which put a laptop's hostname into
    every line of a history file that every report cites.
    """
    from ..environment import environment_id as _eid
    return _eid()


def pins_digest(path="requirements.txt"):
    from ..receipts import sha256_file
    return sha256_file(path) if os.path.exists(path) else None


def decide(deviation, tolerance):
    """The only place an outcome is decided. couldnt_check is not a pass."""
    if deviation is None or tolerance is None:
        return COULDNT_CHECK
    return VERIFIED if abs(deviation) <= tolerance else CONTRADICTED


def _portable_source(path):
    """The source path as it would be written on any machine.

    Task 018. `run_engine` passes `os.path.join(workdir, "verify.json")`, and
    a workdir resolved from a requirements file is absolute -- so a line
    appended by `calibrate engine` carried the developer's home directory into
    `calibration/history.jsonl`, which is a TRACKED file. The identifier scan
    task 017 added catches it; this stops writing it.

    Relative to the repository root when the path is inside it, unchanged when
    it is not, because a path outside the tree is a genuine fact about where
    the artifact lived and shortening it would say something false. `~` is not
    substituted: the point is that the line should not depend on whose machine
    wrote it at all.

    Separators are normalised to `/`. Two lines about the same file, written on
    Windows and on Linux, must not differ in a field a reader compares by eye.
    """
    if not path:
        return path
    try:
        root = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", ".."))
        rel = os.path.relpath(os.path.abspath(path), root)
    except (OSError, ValueError):
        return str(path).replace("\\", "/")
    if rel.startswith(".."):
        return str(path).replace("\\", "/")
    return rel.replace("\\", "/")


def make_line(check, dataset, engine, engine_version, config, measured,
              reference, tolerance, definition, *, environment=None,
              outcome_scope=BLOCKING, source=None, note=None, extra=None):
    """Build a line. `deviation` and `outcome` are derived, never passed in."""
    from .. import __version__

    deviation = (None if (measured is None or reference is None)
                 else round(float(measured) - float(reference),
                            DEVIATION_DECIMALS))
    line = {
        "schema": SCHEMA,
        "date": utc_date(),
        "check": check,
        "dataset": dataset,
        "engine": engine,
        "engine_version": engine_version,
        "config": config,
        "measured": None if measured is None else float(measured),
        "reference": None if reference is None else float(reference),
        "deviation": deviation,
        "tolerance": None if tolerance is None else float(tolerance),
        "outcome": decide(deviation, tolerance),
        "environment": environment or environment_id(),
        "pins_sha256": pins_digest(),
        "oneground_version": __version__,
        "definition": definition,
        "outcome_scope": outcome_scope,
    }
    if source:
        line["source"] = _portable_source(source)
    if note:
        line["note"] = note
    if extra:
        line.update(extra)
    return line


def validate(line):
    missing = [f for f in FIELDS if f not in line]
    if missing:
        raise ValueError(f"calibration line is missing required fields: "
                         f"{', '.join(missing)}")
    if line["outcome"] not in (VERIFIED, CONTRADICTED, COULDNT_CHECK):
        raise ValueError(f"unknown outcome {line['outcome']!r}")
    if line["outcome"] != decide(line.get("deviation"), line.get("tolerance")):
        raise ValueError(
            "outcome does not follow from deviation and tolerance; outcomes "
            "are derived at write time so that changing a tolerance later "
            "cannot re-judge a line that is already written")
    if (int(line.get("schema") or 0) >= EFSEARCH_REQUIRED_FROM_SCHEMA
            and line.get("check") in EFSEARCH_REQUIRED_CHECKS
            and line.get("efSearch") is None):
        raise ValueError(
            f"a {line['check']} line must name the efSearch it was measured "
            f"at: efSearch does not mean the same thing across HNSW "
            f"implementations, so a point without it is not comparable to one "
            f"from another engine (see docs/MODELS.md)")
    return line


def append(line, path=DEFAULT_PATH):
    """Append one validated line. LF-pinned, like every other receipt here."""
    validate(line)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line, sort_keys=True, ensure_ascii=True) + "\n")
    return line


def append_all(lines, path=DEFAULT_PATH):
    for ln in lines:
        validate(ln)
    return [append(ln, path) for ln in lines]


def read(path=DEFAULT_PATH, raw=False):
    """Every line, as schema-2 views unless `raw=True`.

    Readers get one shape whatever era a line came from; `raw=True` is for
    anything that needs the bytes as written, such as a test asserting the
    file was appended to rather than rewritten.
    """
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for lineno, text in enumerate(f, 1):
            text = text.strip()
            if not text:
                continue
            try:
                ln = json.loads(text)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: not JSON: {e}") from None
            out.append(ln if raw else normalize(ln))
    return out


def is_legacy(line):
    """A line written before task 012's schema. Identified by the absence of
    `check`, which every schema-2 line has and no earlier line had."""
    return "check" not in line


def normalize(line):
    """A schema-2 *view* of any line. The file is never rewritten.

    `calibration/README.md` says lines are never edited, only appended -- a
    point measured wrongly gets a later line saying so, not a correction in
    place. That rule applies to a schema change too, so the one line task 011
    seeded is translated on read rather than migrated on disk.

    The translation is faithful and lossy in one direction only: the seeded
    line declared no tolerance, so it reaches no verdict. `couldnt_check` is
    the honest outcome for a measurement that was never gated, and task 011's
    report never claimed otherwise.
    """
    if not is_legacy(line):
        return line
    sim = line.get("simulated_recall_at_10")
    meas = line.get("measured_recall_at_10")
    dev = line.get("calibration_error_recall")
    if dev is None and sim is not None and meas is not None:
        dev = round(float(sim) - float(meas), DEVIATION_DECIMALS)
    out = dict(line)
    out.update({
        "schema": 1,
        "check": "simulator_vs_engine",
        "dataset": line.get("corpus"),
        "measured": None if sim is None else float(sim),
        "reference": None if meas is None else float(meas),
        "deviation": None if dev is None else float(dev),
        "tolerance": None,
        "outcome": COULDNT_CHECK,
        "environment": line.get("environment_id"),
        "pins_sha256": line.get("pins_sha256"),
        "oneground_version": line.get("oneground_version"),
        "outcome_scope": line.get("outcome_scope", BLOCKING),
        "note": (line.get("note") or
                 "schema-1 line, seeded by task 011 from a completed verify "
                 "run. It declared no tolerance, so it carries a measurement "
                 "and no verdict."),
    })
    return out


def comparable(a, b):
    """Whether two lines measure the same thing.

    The rule the pre-012 README already stated, made executable: engine,
    engine version and config must all agree, and so must the check and the
    dataset. Simulated recall depends on the parameters the simulator was
    given and measured recall on the parameters the engine was built with; a
    point where those disagree is not a calibration point at all.
    """
    keys = ("check", "dataset", "engine", "engine_version", "config")
    return all(a.get(k) == b.get(k) for k in keys)


def latest_by_check(lines):
    """Most recent line per (check, dataset, engine, config).

    Later lines win, which is what makes correction-by-appending work -- and
    what lets a check be *re-scoped*. Task 012b moved the hnswlib curve from
    blocking to advisory after measuring that its disagreement is a difference
    between two HNSW implementations rather than a defect in this one. The
    lines already written under the old scope cannot be edited, so the only
    way to record the change is a later line that supersedes them.

    An earlier version of this function refused to let an advisory line
    displace a blocking one, to stop a `qdrant:latest` reading becoming the
    answer. That safety property is real, but this was the wrong place for it:
    it also froze a check in a scope it had been deliberately moved out of.
    The property is enforced where it actually matters instead --
    `calibrate`'s exit code and `latest_for_engine` both ignore advisory lines
    entirely, so an advisory reading can be *seen* but can never gate a
    release or be cited as a report's calibration.
    """
    out = {}
    for ln in (normalize(x) for x in lines):
        key = (ln.get("check"), ln.get("dataset"), ln.get("engine"),
               ln.get("config"))
        out[key] = ln
    return out


def latest_for_engine(engine, lines=None, path=DEFAULT_PATH):
    """The most recent blocking line for an engine, for the report footer.

    Returns None when the engine has never been calibrated, and the caller
    says so out loud rather than printing nothing.
    """
    lines = read(path) if lines is None else lines
    hits = [ln for ln in (normalize(x) for x in lines)
            if ln.get("engine") == engine
            and ln.get("outcome_scope", BLOCKING) == BLOCKING]
    return hits[-1] if hits else None


def counts(lines):
    c = {VERIFIED: 0, CONTRADICTED: 0, COULDNT_CHECK: 0}
    for ln in (normalize(x) for x in lines):
        if ln.get("outcome") in c:
            c[ln["outcome"]] += 1
    return c


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------

def _fmt(v, nd=5):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def render(lines, width_config=46):
    """The history as a table, plus the latest outcome per check."""
    if not lines:
        return ("calibration/history.jsonl is empty.\n"
                "Run `oneground calibrate curve` or "
                "`oneground calibrate engine` to write the first line.")
    lines = [normalize(x) for x in lines]
    rows = [("date", "check", "config", "measured", "reference", "dev",
             "tol", "outcome")]
    for ln in lines:
        cfg = str(ln.get("config", ""))
        if len(cfg) > width_config:
            cfg = cfg[:width_config - 3] + "..."
        outcome = ln.get("outcome", "?")
        if ln.get("outcome_scope") == ADVISORY:
            outcome += " (advisory)"
        rows.append((ln.get("date", "?"), ln.get("check", "?"), cfg,
                     _fmt(ln.get("measured")), _fmt(ln.get("reference")),
                     _fmt(ln.get("deviation")), _fmt(ln.get("tolerance"), 3),
                     outcome))
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    out = []
    for n, r in enumerate(rows):
        out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(r)).rstrip())
        if n == 0:
            out.append("  ".join("-" * w for w in widths))

    c = counts(lines)
    out.append("")
    out.append(f"{len(lines)} line(s): {c[VERIFIED]} verified, "
               f"{c[CONTRADICTED]} contradicted, "
               f"{c[COULDNT_CHECK]} couldn't-check")
    out.append("")
    out.append("latest outcome per check")
    latest = latest_by_check(lines)
    for key in sorted(latest, key=lambda k: tuple(str(x) for x in k)):
        ln = latest[key]
        scope = ("" if ln.get("outcome_scope", BLOCKING) == BLOCKING
                 else "  [advisory]")
        out.append(f"  {ln.get('check')}  {ln.get('dataset')}  "
                   f"{ln.get('config')}  ->  {ln.get('outcome')}"
                   f"  ({ln.get('date')}){scope}")
    return "\n".join(out)
