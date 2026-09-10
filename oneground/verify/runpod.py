"""`verify.target: runpod` -- client and engine on the same machine.

Task 009 measured latency on this laptop against a container behind the
Windows Docker NAT, and `verify` refused to attribute the number: the
empty-collection round trip was 132% of the query p95. The path was the
measurement. This target removes the path.

What "matched environment" buys
-------------------------------
The load generator, the engine and the corpus all sit on one pod. The round
trip is a loopback rather than a NAT, so the RTT baseline is small relative to
the query and latency becomes attributable. And when two engines are compared,
they run **sequentially on the same host** with the same corpus, query set,
concurrency and duration -- so the comparison is between engines rather than
between two people's laptops.

Every row this produces carries `environment_id` = the pod id.
`verdict.latency_p95` and `verdict.qps` refuse to settle a constraint from a
row whose `environment_id` is not the one the constraint names, because two
pods are two machines.

The money boundary is unchanged
-------------------------------
This module **generates a session spec and prints the command**. It does not
create a pod. `oneground pod up` is the only thing that can, and it still
requires a typed `y` at a terminal -- see `oneground/pod/__init__.py`. Nothing
here has a `--yes`, and adding one would be the whole boundary deleted for a
convenience nobody asked for.
"""

import json
import os
import time

import yaml

# The remote script the session runs. It is written into the session spec
# rather than shipped as a file so the whole run is visible in one place.
REMOTE_RUNNER = "corpora/run_verify_pod.sh"

DEFAULT_CAPS = {"max_hours": 1.0, "max_concurrent": 1, "max_usd": 2.00}


def session_spec(req, workdir, cfg, engines, image, log_fn=None):
    """Build the `oneground pod` session spec for a verify run.

    CPU pod: this measures an engine, and no engine here uses a GPU. The
    image must have Docker available so the engine's compose file can run on
    the pod alongside the client.
    """
    constraints = (req.data.get("constraints") or {})
    lat = constraints.get("latency") or {}
    caps = {**DEFAULT_CAPS, **(cfg.get("caps") or {})}
    # The brief caps this at one hour and nothing here may raise it.
    caps["max_hours"] = min(float(caps.get("max_hours", 1.0)), 1.0)

    return {
        # Availability in a datacenter moves hour to hour, and the volume
        # fixes the datacenter -- so the list is wide and ordered cheapest
        # first rather than naming the one type that happened to be free when
        # this was written. `plan` prints what each candidate resolved to, and
        # the cost cap refuses anything the caps cannot afford.
        "gpu": cfg.get("gpu") or ["RTX PRO 4000", "RTX PRO 4500",
                                  "RTX A4000", "L4", "RTX PRO 6000",
                                  "RTX PRO 6000 WK"],
        "volume": cfg.get("volume", "vecbench"),
        "volume_mount_path": "/workspace",
        "image": image,
        "disk_gb": int(cfg.get("disk_gb", 40)),
        "env": {
            "ONEGROUND_VERIFY": "1",
            "ONEGROUND_CONCURRENCY": str(lat.get("concurrency", 8)),
            "ONEGROUND_TARGET_QPS": str(lat.get("at_qps", 0)),
            "ONEGROUND_DURATION_MIN": str(cfg.get("duration_minutes", 5)),
            "ONEGROUND_ENGINES": ",".join(engines),
            # Which requirements file the pod verifies. Without this the
            # remote script falls back to its default and a smoke session
            # would run the arXiv requirements -- whose vector path is a
            # Windows path that does not exist on the pod. Found while the
            # first smoke session was still in setup (task 011).
            "ONEGROUND_REQUIREMENTS": str(cfg.get(
                "requirements_on_pod",
                os.path.basename(str(getattr(req, "path", None)
                                     or "requirements.yaml")))),
            # Volume-first sessions only. The tarball the corpus is extracted
            # from if it is not already loose on the volume, and the repo
            # manifest its digests are checked against. Declared in the
            # requirements file so nothing in the runner is hardcoded to one
            # fixture; absent for a session whose corpus travels in the repo.
            **({"ONEGROUND_CORPUS_TARBALL": str(cfg["pod_corpus_tarball"])}
               if cfg.get("pod_corpus_tarball") else {}),
            **({"ONEGROUND_CORPUS_MANIFEST": str(cfg["pod_corpus_manifest"])}
               if cfg.get("pod_corpus_manifest") else {}),
        },
        "setup": "corpora/POD_SETUP.md",
        "run": f"bash {REMOTE_RUNNER}",
        "remote_repo": "/workspace/oneground",
        "remote_log": "/workspace/oneground-verify.log",
        "done_marker": "DONE",
        "stall_minutes": int(cfg.get("stall_minutes", 15)),
        # Everything `verify --on-pod` reads that git will not carry: the
        # characterize workdir (`runs/` is gitignored -- session
        # 20260909-195824) and whichever corpus files git ignores or does not
        # track (`fixtures/*/vectors.npy` is .gitignore line 10 -- session
        # 20260909-205151). The ground truth is uploaded rather than
        # recomputed because the whole point of `verify` is to compare an
        # engine against the same exact k-NN the local decision used.
        "inputs": _workdir_inputs(workdir) + corpus_inputs(
            pod_requirements(req, cfg) or req)[0],
        "outputs": [
            {"remote": "/workspace/verify-out.tgz",
             "local": os.path.relpath(workdir, start=os.getcwd()).replace(
                 "\\", "/") + "/",
             "extract": True},
        ],
        "caps": caps,
    }


def write_session(req, workdir, cfg, engines, image, path=None, log_fn=None):
    """Write the session spec and return its path."""
    spec = session_spec(req, workdir, cfg, engines, image, log_fn)
    path = path or os.path.join("sessions", f"verify-{req.name}.yaml")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    header = (
        "# Generated by `oneground verify --target runpod`.\n"
        "#\n"
        "# This file describes a session; it creates nothing. `oneground pod\n"
        "# up` is the only thing that can create a billable resource, and it\n"
        "# still requires a typed 'y' at a terminal.\n"
        f"# Generated {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
        "#\n"
        "# The pod runs the engine's compose file and the load generator on\n"
        "# the same host, so latency is attributable and throughput can be\n"
        "# measured at the requested concurrency. Every row it produces\n"
        "# carries environment_id = the pod id.\n")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(header)
        yaml.safe_dump(spec, f, sort_keys=False, default_flow_style=False,
                       allow_unicode=False)
    return path


def git_carries(path, repo_root=None):
    """(carried, why): would `git bundle --all` put this file on the pod?

    A bundle carries commits, so the question is only ever about git. Asked
    rather than assumed: `requirements.smoke.yaml` says in a comment that its
    vectors are "the committed smoke artifacts", and `.gitignore` line 10 says
    otherwise. The comment cost a pod.
    """
    import subprocess
    root = os.path.abspath(repo_root or os.getcwd())
    full = os.path.abspath(path)
    if not (full == root or full.startswith(root + os.sep)):
        return False, "outside the repository"
    rel = os.path.relpath(full, root).replace("\\", "/")
    ignored = subprocess.run(["git", "-C", root, "check-ignore", "-q", rel],
                             capture_output=True)
    if ignored.returncode == 0:
        return False, "git-ignored"
    tracked = subprocess.run(
        ["git", "-C", root, "ls-files", "--error-unmatch", rel],
        capture_output=True)
    if tracked.returncode == 0:
        return True, "tracked"
    return False, "untracked"


# What `verify --on-pod` actually reads from the corpus: the vectors and the
# queries, and nothing else. `characterize` reads metadata and text as well,
# but it does not run on the pod -- its output is the workdir, which is
# uploaded separately. Listing more than the run reads would put megabytes on
# the wire for nothing.
CORPUS_INPUTS = [("vectors", "vectors"), ("queries", "queries")]


def pod_requirements(req, cfg):
    """The requirements the *pod* will run, when it differs from this one.

    `verify.requirements_on_pod` names a file in the repo whose corpus paths
    point at the network volume -- the volume-first arrangement for a corpus
    too large to upload. The session's inputs and the "must already be on the
    pod" list have to be computed from that file rather than from the
    developer's, or they describe a run that is not the one about to happen.

    Returns None when the pod runs the same file, or when the named one
    cannot be loaded (the runner's own preflight is the backstop; a generator
    that raises here would refuse to describe a session over a file it may
    simply not be able to parse on this machine).
    """
    name = cfg.get("requirements_on_pod")
    if not name:
        return None
    if os.path.basename(str(name)) == os.path.basename(
            str(getattr(req, "path", "") or "")):
        return None
    from .. import intake
    try:
        return intake.load(name)
    except Exception:
        return None


def corpus_inputs(req, remote_repo="/workspace/oneground", repo_root=None):
    """(inputs, external): corpus files to upload, and ones that cannot be.

    `inputs` are session-spec entries for files git will not carry but which
    live inside the repo, placed at the same relative path on the pod.
    `external` is a list of (label, path, why) the developer has to resolve
    another way -- on the network volume, normally.
    """
    root = os.path.abspath(repo_root or os.getcwd())
    inputs, external = [], []
    for label, attr in CORPUS_INPUTS:
        cfg = getattr(req, attr, None) or {}
        p = req.resolve(cfg.get("path"))
        if not p:
            continue
        carried, why = git_carries(p, root)
        if carried:
            continue
        if why == "outside the repository":
            external.append((label, p, why))
            continue
        rel = os.path.relpath(p, root).replace("\\", "/")
        inputs.append({"local": rel, "remote": f"{remote_repo}/{rel}",
                       "optional": False})
    return inputs, external


# The workdir files the pod reads. `build_info.json` travels with them so the
# run on the pod can say which characterize produced what it is verifying.
WORKDIR_INPUTS = [
    ("characterization.json", False),
    ("sample_ids.json", False),
    ("queries_ids.json", False),
    ("ground_truth.npy", False),
    ("ground_truth_scores.npy", True),
    ("build_info.json", True),
    # Without simulate.json the pod cannot compute calibration_error_recall --
    # the simulated-minus-measured recall that says whether the simulator is
    # telling the truth about this corpus. Session 20260909-220900 came back
    # with `couldnt_check: no simulate.json in the workdir` for exactly this
    # reason, having measured everything needed for the comparison.
    ("simulate.json", True),
]


def _workdir_inputs(workdir, remote_repo="/workspace/oneground"):
    """`inputs` entries placing the workdir at the same relative path on the pod.

    Same relative path deliberately: the requirements file names the workdir
    as `./runs/<name>`, the pod runs the same requirements file, and a path
    that resolves differently on the two machines is a class of bug this
    project has already paid for once.
    """
    rel = os.path.relpath(workdir, start=os.getcwd()).replace("\\", "/")
    return [{"local": f"{rel}/{name}",
             "remote": f"{remote_repo}/{rel}/{name}",
             "optional": optional}
            for name, optional in WORKDIR_INPUTS]


def bundle_inputs(workdir, log_fn=None):
    """The files the pod needs from the workdir, and their digests.

    The sample, the queries and the ground truth -- nothing else. The pod does
    not need the reports, and a smaller bundle is a shorter sync.
    """
    from ..receipts import sha256_file
    wanted = ["sample_ids.json", "queries_ids.json", "ground_truth.npy",
              "ground_truth_scores.npy", "characterization.json"]
    out = {}
    for name in wanted:
        p = os.path.join(workdir, name)
        if os.path.exists(p):
            out[name] = sha256_file(p)
    return out


def instructions(session_path, workdir, engines, image, caps):
    """What the developer has to run. Printed, never executed."""
    return f"""
A pod session has been prepared. Nothing has been created and nothing has
been spent.

    session   {session_path}
    image     {image}
    engines   {', '.join(engines)}
    caps      max_hours {caps['max_hours']}, max_usd {caps['max_usd']}
    outputs   verify.json fetched back into {workdir}

Run these yourself -- `up` needs a typed 'y' at a terminal, and this process
has no terminal to type it at:

    python -m oneground.pod plan {session_path}      # dry run, priced
    python -m oneground.pod up   {session_path}      # asks before spending
    python -m oneground.pod watch <id>               # DONE -> fetch -> terminate

Then re-run `oneground verify` (it will pick up the fetched verify.json) or
go straight to `oneground report`.
"""
