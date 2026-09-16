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

COULDNT_CHECK = contract.COULDNT_CHECK

# What `oneground lab <workdir>` needs, and what it shows when it is there.
REQUIRED_FILES = ("simulate.json", "characterization.json")
OPTIONAL_FILES = ("verify.json", "report.json")


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
                        for f in REQUIRED_FILES + OPTIONAL_FILES}

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
        }
