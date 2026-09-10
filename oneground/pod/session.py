"""Session specs: the YAML that says what a pod run is.

A session spec is small and declarative on purpose. It names the hardware
preference, the volume (by name -- the datacenter is *derived* from it, never
written down twice), the image, what to run, what to bring back, and the caps.
Everything else is resolved live by `plan`.

    gpu: ["RTX PRO 4500", "RTX 6000 Ada"]   # display names, first available
    volume: organic_orange_catfish_volume   # by name; datacenter derived
    image: runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404
    disk_gb: 20
    env: {HF_HOME: /workspace/hf}
    setup: corpora/POD_SETUP.md
    run: bash corpora/run_arxiv_150k.sh
    inputs:
      - {local: runs/arxiv-smoke/characterization.json,
         remote: /workspace/oneground/runs/arxiv-smoke/characterization.json}
    outputs:
      - {remote: /workspace/arxiv-150k-small.tgz, local: ./, extract: true}
      - {remote: /workspace/arxiv-150k-large.tgz, local: ../oneground-assets/}
    caps: {max_hours: 2, max_concurrent: 1, max_usd: 3.00}

Caps are enforced client-side, and the spec is refused without them. There is
no server-side spend limit behind this: RunPod will happily run a pod until
the account is empty, so the cap in this file is the only thing between a
hung build and a weekend of billing. That is why `load()` treats a missing
cap as a broken spec rather than an unlimited one.
"""

import os

import yaml

REQUIRED = ("gpu", "volume", "image", "run", "caps")
REQUIRED_CAPS = ("max_hours", "max_usd")


class SessionSpecError(ValueError):
    """The session spec is missing something, or says something impossible."""


class Output:
    """One file to bring back when the run finishes.

    `local` is resolved relative to the repo root, and may point outside it --
    the arxiv-150k release asset is 483 MB and belongs in
    ../oneground-assets/, not in git.
    """

    __slots__ = ("remote", "local", "extract")

    def __init__(self, remote, local, extract=False):
        if not remote or not str(remote).startswith("/"):
            raise SessionSpecError(
                "output.remote must be an absolute path on the pod; got %r"
                % remote)
        self.remote = str(remote)
        self.local = str(local)
        self.extract = bool(extract)

    def local_path(self, repo_root):
        return os.path.normpath(os.path.join(repo_root, self.local))

    def is_inside_repo(self, repo_root):
        root = os.path.normpath(os.path.abspath(repo_root))
        p = os.path.normpath(os.path.abspath(self.local_path(repo_root)))
        return p == root or p.startswith(root + os.sep)

    def __repr__(self):
        return "Output(%s -> %s%s)" % (self.remote, self.local,
                                       ", extract" if self.extract else "")


class Input:
    """One local path to place on the pod before the run starts.

    The repo reaches the pod as a git bundle, and a bundle carries commits --
    so anything git does not track never arrives. `runs/` is gitignored (one
    arxiv-150k workdir is 1.4 MB of sample ids alone) and the workdir is
    exactly what `verify --on-pod` needs: the sample, the queries and the
    ground truth the local decision was measured against. Session
    20260909-195824 spent four minutes of pod time discovering this.

    `optional` is for a file that legitimately may not exist (ground truth
    scores are not written by every path). A required input that is missing
    locally refuses the session **before** anything is created, because
    finding out on the pod costs money to find out.
    """

    __slots__ = ("local", "remote", "optional")

    def __init__(self, local, remote, optional=False):
        if not local:
            raise SessionSpecError("input.local is required")
        if not remote or not str(remote).startswith("/"):
            raise SessionSpecError(
                "input.remote must be an absolute path on the pod; got %r"
                % remote)
        self.local = str(local)
        self.remote = str(remote)
        self.optional = bool(optional)

    def local_path(self, repo_root):
        return os.path.normpath(os.path.join(repo_root, self.local))

    def __repr__(self):
        return "Input(%s -> %s%s)" % (self.local, self.remote,
                                      ", optional" if self.optional else "")


class Caps:
    """The client-side spend limits.

    max_hours       `watch` terminates the pod at this age, run finished or not
    max_usd         `plan`/`up` refuse if hours x rate would exceed it
    max_concurrent  `up` refuses if this many sessions are already live
    """

    __slots__ = ("max_hours", "max_usd", "max_concurrent")

    def __init__(self, max_hours, max_usd, max_concurrent=1):
        self.max_hours = float(max_hours)
        self.max_usd = float(max_usd)
        self.max_concurrent = int(max_concurrent)
        if self.max_hours <= 0 or self.max_usd <= 0:
            raise SessionSpecError("caps.max_hours and caps.max_usd must be > 0")
        if self.max_concurrent < 1:
            raise SessionSpecError("caps.max_concurrent must be >= 1")

    def worst_case_usd(self, usd_per_hr):
        return self.max_hours * usd_per_hr

    def __repr__(self):
        return ("Caps(max_hours=%g, max_usd=%.2f, max_concurrent=%d)"
                % (self.max_hours, self.max_usd, self.max_concurrent))


class Session:
    """A parsed, validated session spec. Resolving it live is `plan`'s job."""

    def __init__(self, name, data, path=None):
        self.name = name
        self.path = path
        self.gpu = list(data["gpu"]) if isinstance(data["gpu"], (list, tuple)) \
            else [data["gpu"]]
        self.volume = str(data["volume"])
        self.image = str(data["image"])
        self.disk_gb = int(data.get("disk_gb", 20))
        self.env = dict(data.get("env") or {})
        self.setup = data.get("setup")
        self.run = str(data["run"])
        self.outputs = [Output(**o) for o in (data.get("outputs") or [])]
        self.inputs = [Input(**i) for i in (data.get("inputs") or [])]
        caps = data["caps"]
        self.caps = Caps(caps["max_hours"], caps["max_usd"],
                         caps.get("max_concurrent", 1))
        self.cloud_type = str(data.get("cloud_type", "SECURE")).upper()
        self.volume_mount_path = str(data.get("volume_mount_path", "/workspace"))
        # Where the run's stdout lands on the pod. status/watch tail this file
        # rather than an API endpoint, because RunPod's REST API has no pod-log
        # path (checked against its OpenAPI document: 23 paths, none of them
        # logs).
        self.remote_log = str(data.get("remote_log",
                                       "/workspace/oneground-session.log"))
        self.remote_repo = str(data.get("remote_repo", "/workspace/oneground"))
        # The sentinel the run prints when it is finished. run_arxiv_150k.sh
        # already prints DONE as its third-from-last line.
        self.done_marker = str(data.get("done_marker", "DONE"))
        # How long the run's log may go without growing before `watch` calls
        # it stalled and terminates. Task 006b left a pod billing for ten
        # minutes with no run started at all; a pod with nothing to wait for
        # must not survive. Sessions whose slow phase is legitimately long
        # raise this rather than disabling it.
        self.stall_minutes = float(data.get("stall_minutes", 15))
        if self.stall_minutes <= 0:
            raise SessionSpecError("stall_minutes must be > 0")
        # How many megabytes of `inputs` this session may push up an scp
        # before `up` refuses -- checked before the create, because finding
        # out that a session wants to send 460 MB of vectors is not something
        # to discover with the meter running. A session that genuinely needs
        # more says so here; there is no flag, for the same reason the dirty
        # tree has no flag.
        self.input_size_cap_mb = float(data.get("input_size_cap_mb", 50))
        if self.input_size_cap_mb <= 0:
            raise SessionSpecError("input_size_cap_mb must be > 0")

    def __repr__(self):
        return "Session(%s, gpu=%s, volume=%s)" % (self.name, self.gpu,
                                                   self.volume)


def load(path):
    """Read and validate a session spec. Raises SessionSpecError, never
    returns a half-valid object."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise SessionSpecError("%s: expected a YAML mapping" % path)

    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise SessionSpecError(
            "%s: missing required key(s): %s" % (path, ", ".join(missing)))

    caps = data.get("caps")
    if not isinstance(caps, dict):
        raise SessionSpecError("%s: caps must be a mapping" % path)
    missing_caps = [k for k in REQUIRED_CAPS if k not in caps]
    if missing_caps:
        raise SessionSpecError(
            "%s: caps is missing %s. A session without a cap cannot be "
            "confirmed -- there is no server-side spend limit behind this."
            % (path, ", ".join(missing_caps)))

    if not data.get("gpu"):
        raise SessionSpecError("%s: gpu must name at least one type" % path)

    name = os.path.splitext(os.path.basename(path))[0]
    return Session(name, data, path=path)
