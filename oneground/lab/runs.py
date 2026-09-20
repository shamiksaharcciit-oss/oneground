"""Reading a run directory for the lab (tasks 021b, 023, 024).

Which states a run holds, which epsilons were simulated for a configuration,
and what simulating another would cost. Shared by `corpora/render_from_state.py`
and `oneground lab`, so the command line and the server cannot disagree about a
run: one reader, not two.

It reads files and never writes one. It computes nothing a view draws: it
finds states, groups them by configuration, and reads the timings and the
requirements file name a run declared. `guard.check_transport` holds it to
that.
"""

import json
import os
import re

from . import contract
from .receipt import RUN_INDEX

COULDNT_CHECK = contract.COULDNT_CHECK

# What `oneground lab <workdir>` needs, and what it shows when it is there.
REQUIRED_FILES = ("simulate.json", "characterization.json")
OPTIONAL_FILES = ("verify.json", "report.json")
# Receipts characterize writes beside the characterization (task 025): which
# queries were used and which input rows were sampled, by the ids the corpus
# gave them. The interface searches queries and names neighbours by these.
QUERY_IDS_FILE = "queries_ids.json"
SAMPLE_IDS_FILE = "sample_ids.json"
IDS_PER_REQUEST = 100


class LabRunError(RuntimeError):
    """A directory the lab cannot serve. The message says what is missing and
    what to run."""


def states_in(state_dir, family=None):
    """Every state file in `state_dir` (of `family`, when given): through
    `state_info.json` when present, through the headers otherwise."""
    info_p = os.path.join(state_dir, "state_info.json")
    paths = []
    if os.path.exists(info_p):
        with open(info_p, encoding="utf-8") as f:
            info = json.load(f)
        for entry in info.get("configurations", []):
            if entry.get("file") and (family is None
                                      or entry.get("family") == family):
                paths.append(os.path.join(state_dir, entry["file"]))
    else:
        for name in sorted(os.listdir(state_dir)):
            if not name.endswith(".state.npz"):
                continue
            path = os.path.join(state_dir, name)
            if family is None or \
                    contract.load_header(path)["family"] == family:
                paths.append(path)
    return paths


def find_state(state_dir, family):
    """The one state file for `family` in `state_dir`. More than one
    configuration of the family is refused rather than picked from."""
    paths = states_in(state_dir, family)
    if not paths:
        raise SystemExit(f"no {family} state in {state_dir}")
    if len(paths) > 1:
        raise SystemExit(f"{len(paths)} {family} configurations in "
                         f"{state_dir}; pass --file to name one")
    return paths[0]


def configuration(head):
    """A configuration's parameters with epsilon left out: the states of one
    declared set differ in epsilon and in nothing else."""
    return json.dumps({k: v for k, v in head["params"].items()
                       if k not in ("epsilon", "shard_depth")},
                      sort_keys=True)


def run_info(state_dir):
    """The declared `simulate_info.json` beside a `state/` directory."""
    path = os.path.join(os.path.dirname(os.path.abspath(state_dir)),
                        "simulate_info.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def declared_set(base_path, simulated_dirs, family):
    """{epsilon: state path} for the base state's configuration, the declared
    build + query seconds of each, the requirements file name, and the base
    header.

    Collects every state of `family` in the base state's directory and in
    `simulated_dirs` whose parameters match the base state's in everything but
    epsilon. Reads headers only.
    """
    head0 = contract.load_header(base_path)
    key = configuration(head0)
    by_eps, seconds, requirements = {}, [], None
    for d in [os.path.dirname(os.path.abspath(base_path))] + \
            list(simulated_dirs):
        info = run_info(d)
        timings = info.get("timings") or {}
        req = (info.get("requirements_file") or {}).get("path")
        if req and requirements is None:
            requirements = re.split(r"[\\/]", req)[-1]
        for path in states_in(d, family):
            h = contract.load_header(path)
            if configuration(h) != key:
                continue
            eps = h["assignment"]["epsilon"]
            if eps is None:
                continue
            by_eps.setdefault(round(float(eps), 6), path)
            t = timings.get(h["config_label"])
            if t:
                seconds.append(float(t["build_seconds"])
                               + float(t["query_seconds"]))
    return by_eps, seconds, requirements, head0


def cost_and_action(head, family, want, seconds, requirements):
    """What the recall panel offers at an epsilon nobody simulated: the
    measured cost of simulating one, in minutes, and the exact command."""
    cost = (f"{COULDNT_CHECK}: no simulate_info.json timings were found for "
            "this configuration")
    if seconds:
        cost = {"low": round(min(seconds) / 60.0, 1),
                "high": round(max(seconds) / 60.0, 1),
                "basis": (f"build and query of this configuration at the "
                          f"{len(seconds)} simulated epsilon(s) with declared "
                          "timings, on the machine that ran them; loading "
                          "vectors, ground truth and k-means add to it")}
    params = {k: v for k, v in head["params"].items() if k != "shard_depth"}
    params["epsilon"] = want
    req = requirements or "<requirements.yaml>"
    action = {"kind": "simulate", "family": family, "epsilon": want,
              "params": params,
              "grid": {family: {k: [v] for k, v in params.items()}},
              "requirements": req,
              "command": f"oneground simulate {req} --emit-state"}
    return cost, action


def plan(base_path, simulated_dirs, family, epsilon=None):
    """Which state each view is drawn from, for the epsilon asked for, and the
    one `EpsilonSet` both views are handed."""
    by_eps, seconds, requirements, head = declared_set(
        base_path, simulated_dirs, family)
    base_eps = head["assignment"]["epsilon"]
    if base_eps is None and epsilon is not None:
        raise SystemExit(f"{family} has no epsilon; --epsilon does not apply")
    want = base_eps if epsilon is None else float(epsilon)
    trace_path = base_path
    if want is not None and round(float(want), 6) in by_eps:
        trace_path = by_eps[round(float(want), 6)]

    base = contract.load_state(base_path)
    trace = base if trace_path == base_path else \
        contract.load_state(trace_path)
    cost, action = cost_and_action(head, family, want, seconds, requirements)
    eps = contract.EpsilonSet.make(epsilon=want, simulated=sorted(by_eps),
                                   cost=cost, action=action)
    return {"base_path": base_path, "base": base,
            "trace_path": trace_path, "trace": trace,
            "epsilon": want, "simulated": sorted(by_eps),
            "cost": cost, "action": action, "eps": eps}


def declared_ambiguity(characterization_path):
    """The ambiguity ratio a run's characterization declared it measured with
    (`definitions.ambiguity_ratio`), or a couldnt_check reason. Read, never
    assumed: a view compares by the ratio the run's own figure used."""
    try:
        with open(characterization_path, encoding="utf-8") as f:
            ratio = (json.load(f).get("definitions") or {}).get(
                "ambiguity_ratio")
    except (OSError, ValueError) as e:
        return f"{COULDNT_CHECK}: characterization.json could not be read ({e})"
    if isinstance(ratio, (int, float)) and not isinstance(ratio, bool)             and ratio > 0:
        return float(ratio)
    return (f"{COULDNT_CHECK}: characterization.json declares no "
            "definitions.ambiguity_ratio, so no query is called ambiguous")


class LoadedRun:
    """One run, loaded once, for `oneground lab` to draw from (task 024).

    `workdir` is a run's directory: `state/`, `simulate.json` and
    `characterization.json`, and optionally `verify.json` and `report.json`.
    `also` adds other runs' directories whose states of the same configuration
    were simulated at other epsilons. Every state of the chosen configuration
    is read once, here, and never again; nothing is written.
    """

    def __init__(self, workdir, family=None, config=None, also=()):
        self.workdir = os.path.abspath(workdir)
        if not os.path.isdir(self.workdir):
            raise LabRunError(f"{workdir} is not a directory")
        state_dir = os.path.join(self.workdir, "state")
        missing = [f for f in REQUIRED_FILES
                   if not os.path.isfile(os.path.join(self.workdir, f))]
        if not os.path.isdir(state_dir):
            missing.insert(0, "state/")
        if missing:
            raise LabRunError(
                f"{workdir} has no {', '.join(missing)}. The lab serves a run "
                "that was characterized and simulated with its state "
                "emitted:\n\n    oneground characterize <requirements.yaml>\n"
                "    oneground simulate <requirements.yaml> --emit-state\n")
        own = states_in(state_dir)
        if not own:
            raise LabRunError(f"{state_dir} holds no .state.npz; run "
                              "`oneground simulate` with --emit-state")
        heads = {p: contract.load_header(p) for p in own}
        families = sorted({h["family"] for h in heads.values()})
        if family is None:
            family = ("semantic_sharded" if "semantic_sharded" in families
                      else families[0])
        elif family not in families:
            raise LabRunError(f"no {family} state in {state_dir}; it holds "
                              f"{', '.join(families)}")
        mine = [p for p in own if heads[p]["family"] == family]
        groups = {}
        for p in mine:
            groups.setdefault(configuration(heads[p]), []).append(p)

        def eps_of(p):
            e = heads[p]["assignment"]["epsilon"]
            return -1.0 if e is None else float(e)

        if config is not None:
            chosen = [p for p in mine if heads[p]["config_label"] == config]
            if not chosen:
                raise LabRunError(
                    f"no configuration {config!r} in {state_dir}; its "
                    f"{family} states are:\n" + "\n".join(
                        "    " + heads[p]["config_label"] for p in mine))
            base_path = chosen[0]
        elif len(groups) == 1:
            base_path = sorted(mine, key=lambda p: (eps_of(p), p))[0]
        else:
            raise LabRunError(
                f"{state_dir} holds {len(groups)} {family} configurations "
                "that differ in more than epsilon; pass --config with one "
                "of:\n" + "\n".join(
                    "    " + label for label in
                    sorted(heads[p]["config_label"] for p in mine)))

        self.also = [os.path.abspath(a) for a in also]
        also_state_dirs = []
        for a in self.also:
            sd = os.path.join(a, "state") \
                if os.path.isdir(os.path.join(a, "state")) else a
            if not os.path.isdir(sd):
                raise LabRunError(f"--also {a} is not a run directory")
            also_state_dirs.append(sd)

        self.by_eps, self.seconds, self.requirements, self.head = \
            declared_set(base_path, also_state_dirs, family)
        self.family = family
        self.base_path = base_path
        self.base = contract.load_state(base_path)
        self.states = {}
        for eps, path in self.by_eps.items():
            self.states[eps] = (self.base if path == base_path
                                else contract.load_state(path))
        self.state_dirs = [state_dir] + also_state_dirs
        self.present = {f: os.path.isfile(os.path.join(self.workdir, f))
                        for f in REQUIRED_FILES + OPTIONAL_FILES +
                        (QUERY_IDS_FILE, SAMPLE_IDS_FILE)}
        self.ambiguity = declared_ambiguity(
            os.path.join(self.workdir, "characterization.json"))
        self.query_ids = self._receipt(QUERY_IDS_FILE,
                                       int(self.head["n_queries"]))
        self.sample_ids = self._receipt(SAMPLE_IDS_FILE,
                                        int(self.head["n_base"]))

    def _receipt(self, name, length):
        """A list of ids characterize wrote, as strings, when it is present
        and names exactly `length` rows; None otherwise."""
        path = os.path.join(self.workdir, name)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            ids = json.load(f)
        if not isinstance(ids, list) or len(ids) != length:
            return None
        return [str(i) for i in ids]

    def ids_of(self, rows):
        """The corpus's own ids for base rows, by index: a lookup in the
        receipt, at most IDS_PER_REQUEST at a time."""
        rows = [int(v) for v in rows]
        if len(rows) > IDS_PER_REQUEST:
            raise ValueError(f"at most {IDS_PER_REQUEST} ids per request")
        n = int(self.head["n_base"])
        for v in rows:
            if not 0 <= v < n:
                raise ValueError(f"row {v} is not in [0, {n})")
        if self.sample_ids is None:
            return {"ids": None, "why": (
                f"{COULDNT_CHECK}: {SAMPLE_IDS_FILE} is missing from this run "
                "or does not name every base row")}
        return {"ids": [self.sample_ids[v] for v in rows]}

    @property
    def has_epsilon(self):
        return self.head["assignment"]["epsilon"] is not None

    @property
    def simulated(self):
        return sorted(self.by_eps)

    def epsilon_max(self):
        return max([0.5] + self.simulated)

    def epsilon_set(self, epsilon=None):
        """The one `EpsilonSet` both views are drawn with at `epsilon`."""
        if not self.has_epsilon:
            if epsilon is not None:
                raise ValueError(f"{self.family} has no epsilon")
            return contract.EpsilonSet()
        want = (float(self.head["assignment"]["epsilon"]) if epsilon is None
                else float(epsilon))
        cost, action = cost_and_action(self.head, self.family, want,
                                       self.seconds, self.requirements)
        return contract.EpsilonSet.make(epsilon=want,
                                        simulated=self.simulated,
                                        cost=cost, action=action)

    def trace_state(self, epsilon=None):
        """The state the query trace is drawn from: the one simulated at
        `epsilon` when there is one, and the base state otherwise."""
        if not self.has_epsilon or epsilon is None:
            return self.base
        return self.states.get(round(float(epsilon), 6), self.base)

    def digest_directories(self):
        """Every directory whose MANIFEST the lab verifies and reports."""
        out = []
        for d in [self.workdir, self.state_dirs[0]] + [
                x for a, sd in zip(self.also, self.state_dirs[1:])
                for x in (a, sd)]:
            if d not in out:
                out.append(d)
        return out

    def describe(self):
        """What the interface needs to lay itself out: declared facts from the
        state headers and the run directory, nothing drawn."""
        return {
            "family": self.family,
            "config_label": self.head["config_label"],
            "n_base": int(self.head["n_base"]),
            "n_queries": int(self.head["n_queries"]),
            "k": 10,
            "epsilon": self.head["assignment"]["epsilon"],
            "simulated_epsilons": self.simulated,
            "epsilon_max": self.epsilon_max() if self.has_epsilon else None,
            "files": self.present,
            "ambiguity": self.ambiguity,
            "query_ids": self.query_ids,
            "partition_regions": int(self.head["partition"].get(
                "n_regions") or 0) or None,
        }


# ------------------------------------------------- many runs (task 041)
# `LoadedRun` is the lab's loader: it needs `state/` and refuses a run without
# it. The UI lists runs that were never simulated with --emit-state, runs that
# stopped after characterize, and Tier-2 runs that measured nothing at all, so
# the index below asks much less of a directory than the lab does.
#
# It is transport, and the line transport must not cross is computing
# something a view draws. So this carries recorded values across -- the
# summary a report wrote, the outcomes it recorded -- and tallies none of
# them. The run-list view does the counting, because counting recorded
# outcomes is drawing a measurement, and a number on the page has to have
# come from a view.

#: Which stages a run has reached, by the receipt each one writes.
STAGE_RECEIPTS = (("characterize", "characterization.json"),
                  ("simulate", "simulate.json"),
                  ("verify", "verify.json"),
                  ("report", "report.json"))

#: A directory is a workdir if it holds any receipt at all. Anything else in
#: the runs directory -- a stray file, a notes folder -- is not listed.
def is_workdir(path):
    return os.path.isdir(path) and any(
        os.path.isfile(os.path.join(path, f)) for _, f in STAGE_RECEIPTS)


def _read_json(path):
    """The parsed receipt, or None if it is absent or unreadable.

    Unreadable is not the same as absent and the caller is told which: a run
    whose report.json is corrupt must be listed as unverified, not as a run
    that never reported.
    """
    if not os.path.isfile(path):
        return None, "absent"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, ValueError) as e:
        return None, f"unreadable: {e.__class__.__name__}"


def _producing_version(workdir):
    """Task 033's field, or None with the reason it is not there.

    Written by the stages into their `_info.json`; a run produced before 033
    simply has no such key, which is a fact about the run rather than a
    failure to read it.
    """
    for info in ("report_info.json", "verify_info.json", "simulate_info.json",
                 "characterization_info.json"):
        data, _ = _read_json(os.path.join(workdir, info))
        if isinstance(data, dict) and data.get("oneground"):
            return {"version": data["oneground"], "from": info, "reason": None}
    return {"version": None, "from": None,
            "reason": f"{COULDNT_CHECK}: no `oneground` block in this run's "
                      "_info.json receipts; it predates task 033"}


def _report_facts(data):
    """What a report records about its own outcome, copied, not computed.

    Two report kinds reach this. Tier 1 carries `claims` and a `summary` it
    counted itself. Tier 2 -- `run_declared`, for a corpus that was described
    rather than sampled -- carries neither: it has no options, and a flat
    `constraints` list in which every outcome is couldnt_check by
    construction. Both are returned in the same shape so the view draws one
    thing, and neither is tallied here.
    """
    if not isinstance(data, dict):
        return None
    tier2 = data.get("oneground_report") is not None or data.get("kind") == \
        "declared"
    if tier2:
        return {
            "tier": data.get("tier"),
            "kind": data.get("kind") or "declared",
            "schema": None,
            "headline": data.get("recommendation_reason"),
            "recommended": data.get("recommended"),
            # every outcome, uncounted: the view tallies
            "outcomes": [c.get("outcome") for c in data.get("constraints")
                         or [] if isinstance(c, dict)],
            "summary": None,
            "n_claims": 0,
        }
    rec = data.get("recommendation")
    return {
        "tier": 1,
        "kind": "measured",
        "schema": data.get("schema"),
        # Tier 1 states its conclusion as a claim rather than as a field, so
        # the headline is that claim's own text. The UI never writes one.
        "headline": next((c.get("text") for c in data.get("claims") or []
                          if c.get("kind") == "recommendation"), None),
        "recommended": rec,
        "outcomes": None,
        "summary": data.get("summary"),
        "n_claims": len(data.get("claims") or []),
    }


def run_row(workdir, verified=None):
    """One row of the run list: what this run is, and what it is not.

    `verified` is a `verify_manifests` entry for the same directory, passed in
    rather than computed here so the digests are checked once per listing.
    """
    workdir = os.path.abspath(workdir)
    stages, problems = {}, []
    receipts = {}
    for stage, fname in STAGE_RECEIPTS:
        data, why = _read_json(os.path.join(workdir, fname))
        stages[stage] = data is not None
        receipts[fname] = data
        if why and why != "absent":
            problems.append(f"{fname} {why}")

    ch = receipts["characterization.json"] or {}
    rep = _report_facts(receipts["report.json"])
    entry = verified or {}
    files = entry.get("files") or []

    return {
        "name": os.path.basename(workdir),
        "path": workdir,
        "stages": stages,
        # Recorded as the receipt has them. A Tier-2 run declares its corpus
        # rather than measuring it, so these are the string
        # "couldnt_check: declared, not measured" rather than numbers, and the
        # view renders what it is given rather than casting it to an int.
        "n_base": ch.get("n_base"),
        "dimension": ch.get("dimension"),
        "run_name": ch.get("run"),
        "report": rep,
        "version": _producing_version(workdir),
        "manifest": {
            "present": entry.get("manifest") is not None,
            "all_verified": entry.get("all_verified"),
            "failing": [f["name"] for f in files if not f.get("verified")],
            "n_files": len(files),
            "note": entry.get("note"),
        },
        "problems": problems,
    }


def index_runs(directory, verifier=None):
    """Every workdir under `directory`, each with its digests checked.

    `verifier` is `server.verify_manifests`, injected so that the one
    implementation of digest checking is reused rather than written twice --
    the same reason the UI is a front-end over the CLI rather than a second
    one.

    A run whose digests fail is listed, with the failing file named. It is
    never hidden and never shown as sound: a run the reader cannot trust is
    exactly the run they most need to see.
    """
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        raise LabRunError(f"{directory} is not a directory")
    dirs = sorted(os.path.join(directory, n) for n in os.listdir(directory)
                  if is_workdir(os.path.join(directory, n)))
    checked = {}
    if verifier is not None and dirs:
        for entry in verifier(dirs):
            checked[os.path.abspath(entry["directory"])] = entry
    return {
        "kind": RUN_INDEX,
        "directory": directory,
        "runs": [run_row(d, checked.get(os.path.abspath(d))) for d in dirs],
    }
