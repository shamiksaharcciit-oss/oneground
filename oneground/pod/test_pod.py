"""Contract tests for `oneground pod`.

What these pin down is the money boundary, and they run entirely against a
stubbed transport -- no network, no account, nothing created. Passing here says
the guard holds; it says nothing about whether RunPod's API still has the
shape task 006 found it in. That is what the one `live` test is for.

    python oneground/pod/test_pod.py     # no test-runner dependency
    pytest oneground/pod/test_pod.py     # same tests, plus the live marker

The live test is skipped when RUNPOD_API_KEY is absent, so a fresh clone runs
the suite green without an account.
"""

import io
import json
import os
import re
import subprocess
import sys
import contextlib
import pathlib
import tempfile
import time

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground import refusals                           # noqa: E402
from oneground.pod import api, confirm, plan as planmod  # noqa: E402
from oneground.pod import session as sessionmod          # noqa: E402
from oneground.pod import state as statemod              # noqa: E402
from oneground.pod import sshx                           # noqa: E402
from oneground.pod import cli                            # noqa: E402

try:
    import pytest
except ImportError:                                       # pragma: no cover
    class _Mark:
        def __getattr__(self, _):
            return lambda f: f

    class pytest:                                         # noqa: N801
        mark = _Mark()

        @staticmethod
        def skip(msg):
            raise _Skipped(msg)


class _Skipped(Exception):
    pass


FAKE_KEY = "rpa_" + "K" * 46          # 50 chars, the real key's length
VOLUME = {"id": "rvoku0jgda", "name": "vol-a", "size": 50,
          "dataCenterId": "EU-RO-1"}


def _gql_response():
    """The shape task 006c measured live, and the trap inside it.

    RTX PRO 4500's floor ($0.34) is its *community* price, and its
    `communityCloud` flag is false -- so the floor is the price of a machine
    nobody on SECURE can be given. The secure list price, $0.72, is what task
    006b was actually billed.
    """
    return {"data": {"gpuTypes": [
        {"id": "NVIDIA RTX PRO 4500 Blackwell", "displayName": "RTX PRO 4500",
         "memoryInGb": 32, "secureCloud": True, "communityCloud": False,
         "securePrice": 0.72, "communityPrice": 0.34,
         "lowestPrice": {"uninterruptablePrice": 0.34, "stockStatus": "Medium"}},
        {"id": "NVIDIA GeForce RTX 4090", "displayName": "RTX 4090",
         "memoryInGb": 24, "secureCloud": True, "communityCloud": True,
         "securePrice": None, "communityPrice": None,
         "lowestPrice": {"uninterruptablePrice": None, "stockStatus": None}},
        # Offered in the datacenter, but with no list price for SECURE: the
        # couldn't-check case, which must refuse rather than use the floor.
        {"id": "NVIDIA L4", "displayName": "L4",
         "memoryInGb": 24, "secureCloud": True, "communityCloud": True,
         "securePrice": None, "communityPrice": 0.44,
         "lowestPrice": {"uninterruptablePrice": 0.44, "stockStatus": "Low"}},
        # Not stocked in this datacenter (no floor) but carrying a global
        # list price. This shape crashed render() on live data: `usd_max` is
        # set while `usd_min` is None.
        {"id": "NVIDIA RTX 6000 Ada Generation", "displayName": "RTX 6000 Ada",
         "memoryInGb": 48, "secureCloud": True, "communityCloud": True,
         "securePrice": 0.98, "communityPrice": 0.74,
         "lowestPrice": {"uninterruptablePrice": None, "stockStatus": None}},
    ]}}


def _transport(extra=None):
    responses = {
        "/networkvolumes": [VOLUME],
        "graphql": _gql_response(),
        "/pods": [],
        "*": {},
    }
    responses.update(extra or {})
    return api.RecordingTransport(responses)


def _client(transport=None):
    return api.RunPodClient(key=FAKE_KEY, transport=transport or _transport())


SPEC_YAML = """
gpu: ["RTX PRO 4500", "RTX 4090"]
volume: vol-a
image: runpod/pytorch:1.1.0-cu1300-torch291-ubuntu2404
disk_gb: 20
env: {HF_HOME: /workspace/hf}
run: bash corpora/run_arxiv_150k.sh
outputs:
  - {remote: /workspace/small.tgz, local: ./, extract: true}
  - {remote: /workspace/large.tgz, local: ../oneground-assets/}
caps: {max_hours: 4, max_concurrent: 1, max_usd: 3.00}
"""


def _spec_data(extra=None):
    """The reference spec as a mapping, so a test can add one key to it."""
    import yaml
    d = yaml.safe_load(SPEC_YAML)
    d.update(extra or {})
    return d


def _spec_file(tmp, text=SPEC_YAML, name="arxiv-build.yaml", extra=None):
    p = os.path.join(tmp, name)
    if extra:
        import yaml
        text = yaml.safe_dump(_spec_data(extra), sort_keys=False)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return p


# ------------------- a fetch never extracts over an existing run (035b)
# Task 032b's third session extracted into `runs/032b-state-pod/` and
# destroyed the second session's state files -- the only copy of the
# measurement its report was written from.

def _tarball(tmp, names, body=b"from the pod"):
    import tarfile
    src = os.path.join(tmp, "src")
    os.makedirs(src, exist_ok=True)
    for n in names:
        p = os.path.join(src, n)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(body)
    path = os.path.join(tmp, "out.tgz")
    with tarfile.open(path, "w:gz") as tf:
        for n in names:
            tf.add(os.path.join(src, n), arcname=n)
    return path


def test_an_extract_that_would_overwrite_is_named_before_it_happens():
    with tempfile.TemporaryDirectory() as tmp:
        tar = _tarball(tmp, ["runs/x/simulate.json", "runs/x/state/a.npz"])
        dest = os.path.join(tmp, "dest")

        # nothing there yet: no collision
        os.makedirs(dest, exist_ok=True)
        assert cli.extract_collisions(tar, dest) == []

        # one of the two already exists: named, and only that one
        p = os.path.join(dest, "runs", "x", "simulate.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"the previous session's")
        got = cli.extract_collisions(tar, dest)
        assert got == [os.path.join("runs", "x", "simulate.json")], got


def test_a_refused_extract_leaves_the_existing_file_untouched():
    """The whole point: the bytes already on disk survive."""
    with tempfile.TemporaryDirectory() as tmp:
        tar = _tarball(tmp, ["runs/x/simulate.json"], b"pod bytes")
        dest = os.path.join(tmp, "dest")
        p = os.path.join(dest, "runs", "x", "simulate.json")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"laptop bytes")

        class _Ssh:
            def exists(self, remote):
                return True

            def get(self, remote, local, timeout=None):
                import shutil
                shutil.copyfile(tar, local)

        failures = cli._fetch_one(
            _Ssh(), {"remote": "/workspace/out.tgz", "local": "dest/",
                     "extract": True}, tmp)
        assert failures == 1, "a refused extract is a failed output"
        with open(p, "rb") as f:
            assert f.read() == b"laptop bytes", "the existing file was replaced"
        # and the tarball is still there, so nothing has to be re-run
        assert os.path.isfile(os.path.join(dest, "out.tgz"))


def test_an_extract_with_no_collision_still_extracts():
    """The negative control: the guard must not block an ordinary fetch."""
    with tempfile.TemporaryDirectory() as tmp:
        tar = _tarball(tmp, ["runs/y/simulate.json"], b"pod bytes")
        dest = os.path.join(tmp, "dest")
        os.makedirs(dest, exist_ok=True)

        class _Ssh:
            def exists(self, remote):
                return True

            def get(self, remote, local, timeout=None):
                import shutil
                shutil.copyfile(tar, local)

        failures = cli._fetch_one(
            _Ssh(), {"remote": "/workspace/out.tgz", "local": "dest/",
                     "extract": True}, tmp)
        assert failures == 0
        with open(os.path.join(dest, "runs", "y", "simulate.json"), "rb") as f:
            assert f.read() == b"pod bytes"


# ------------------------ two places naming the same thing (task 034)
# Twice a session has failed after the pod existed because a value was
# written in two places and only one was read: ONEGROUND_ENGINES in 015, and
# ONEGROUND_WORKDIR in 032b's first session, which uploaded a run's inputs
# into one directory while `simulate` read its workdir from the requirements
# file and looked in another.

def _mirror_case(tmp, env, requirements_text):
    """A session and a requirements file beside it, in a throwaway root."""
    req_name = "requirements.yaml"
    with open(os.path.join(tmp, req_name), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(requirements_text)
    session = sessionmod.Session(
        "t", _spec_data({"env": dict(env, ONEGROUND_REQUIREMENTS=req_name)}),
        path=os.path.join(tmp, "sessions", "t.yaml"))
    return session


REQ_WITH_WORKDIR = """
oneground: 1
run: {name: r, mode: measure, seed: 1, workdir: ./runs/029-proof}
"""


def test_a_workdir_in_two_places_that_disagree_is_refused_at_plan_time():
    """032b's first session, reproduced from two files on disk."""
    with tempfile.TemporaryDirectory() as tmp:
        s = _mirror_case(tmp, {"ONEGROUND_WORKDIR": "runs/032b-state"},
                         REQ_WITH_WORKDIR)
        problems = sessionmod.requirements_disagreements(s, tmp)
        assert len(problems) == 1, problems
        # both values named, so the reader does not have to open two files
        assert "runs/032b-state" in problems[0], problems[0]
        assert "runs/029-proof" in problems[0], problems[0]
        assert "ONEGROUND_WORKDIR" in problems[0]
        assert "run.workdir" in problems[0]


def test_a_workdir_that_agrees_is_not_refused_however_it_is_spelled():
    """`./runs/x` and `runs/x` are the same directory, and a check that said
    otherwise would teach people to delete the check."""
    with tempfile.TemporaryDirectory() as tmp:
        s = _mirror_case(tmp, {"ONEGROUND_WORKDIR": "runs/029-proof"},
                         REQ_WITH_WORKDIR)
        assert sessionmod.requirements_disagreements(s, tmp) == []


def test_engines_in_two_places_that_disagree_are_refused():
    """015's case, the same defect one key over."""
    with tempfile.TemporaryDirectory() as tmp:
        s = _mirror_case(tmp, {"ONEGROUND_ENGINES": "qdrant"}, """
oneground: 1
verify: {engines: [qdrant, pgvector]}
""")
        problems = sessionmod.requirements_disagreements(s, tmp)
        assert len(problems) == 1, problems
        assert "qdrant" in problems[0] and "pgvector" in problems[0]
        # and the list form and the comma form of the same thing agree
        ok = _mirror_case(tmp, {"ONEGROUND_ENGINES": "qdrant,pgvector"}, """
oneground: 1
verify: {engines: [qdrant, pgvector]}
""")
        assert sessionmod.requirements_disagreements(ok, tmp) == []


def test_every_disagreement_is_named_at_once():
    """022's precondition rule: one refusal teaches the whole shape."""
    with tempfile.TemporaryDirectory() as tmp:
        s = _mirror_case(tmp, {"ONEGROUND_WORKDIR": "runs/a",
                               "ONEGROUND_VECTORS": "/workspace/v.npy"}, """
oneground: 1
run: {name: r, workdir: ./runs/b}
corpus: {sample: {vectors: {path: /elsewhere/v.npy}}}
""")
        problems = sessionmod.requirements_disagreements(s, tmp)
        assert len(problems) == 2, problems


def test_a_session_naming_no_requirements_file_is_not_checked():
    """A session that runs something else is not making this mistake."""
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.Session("t", _spec_data(), path="t.yaml")
        assert sessionmod.requirements_disagreements(s, tmp) == []


def test_a_requirements_file_that_is_not_in_the_checkout_is_refused():
    """A bundle carries commits, not the working tree."""
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.Session(
            "t", _spec_data({"env": {"ONEGROUND_REQUIREMENTS": "nope.yaml"}}),
            path="t.yaml")
        problems = sessionmod.requirements_disagreements(s, tmp)
        assert len(problems) == 1 and "nope.yaml" in problems[0]


def test_plan_refuses_and_creates_nothing_when_they_disagree():
    """The refusal has to be at plan time, which is before the create."""
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "requirements.yaml"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(REQ_WITH_WORKDIR)
        spec = _spec_file(tmp, extra={"env": {
            "ONEGROUND_REQUIREMENTS": "requirements.yaml",
            "ONEGROUND_WORKDIR": "runs/somewhere-else"}})
        said = []
        s = sessionmod.load(spec)
        refused = cli._mirror_refusal(s, tmp, log=said.append)
        assert refused
        text = "\n".join(said)
        assert "REFUSED" in text and "Nothing was created" in text
        assert "runs/somewhere-else" in text and "runs/029-proof" in text


# ------------------------------------------------------- the create guard
def test_billable_classification():
    """The guard's list is the security boundary; state it explicitly."""
    assert api.is_billable("POST", "/pods")
    assert api.is_billable("POST", "/pods/abc123/start")
    assert api.is_billable("POST", "/pods/abc123/restart")
    assert api.is_billable("POST", "/networkvolumes")
    assert api.is_billable("POST", api.REST_BASE + "/pods")
    # Terminating only ever stops the meter, which is why `down` never prompts.
    assert not api.is_billable("DELETE", "/pods/abc123")
    assert not api.is_billable("GET", "/pods")
    assert not api.is_billable("GET", "/pods/abc123")
    assert not api.is_billable("GET", "/billing/pods?podId=x")


def test_path_normalisation_does_not_let_ids_through():
    assert api.normalise_path("/pods/abc/start") == "/pods/{id}/start"
    assert api.normalise_path("/pods") == "/pods"
    assert api.normalise_path("/billing/pods?podId=x") == "/billing/{id}"


def test_create_blocked_without_confirmation():
    c = _client()
    try:
        c.create_pod({"name": "x"})
    except api.CreateCallBlocked as e:
        assert "billable" in str(e)
    else:
        raise AssertionError("create_pod succeeded without confirmation")


def test_blocked_create_makes_no_network_call():
    """The guard runs before the transport, so a blocked call is not a
    request that merely failed -- it never left the process."""
    t = _transport()
    c = api.RunPodClient(key=FAKE_KEY, transport=t)
    try:
        c.create_pod({"name": "x"})
    except api.CreateCallBlocked:
        pass
    assert t.calls == [], "a blocked create still hit the transport: %r" % t.calls


def test_allow_create_rejects_anything_but_a_real_token():
    c = _client()
    for impostor in (True, "y", "yes", 1, {"confirmed": True}, None):
        try:
            c.allow_create(impostor)
        except api.CreateCallBlocked:
            continue
        raise AssertionError("allow_create accepted %r" % (impostor,))


def test_allow_create_accepts_a_real_token_and_then_creates():
    t = _transport({"/pods": {"id": "pod-1", "name": "oneground-session-x"}})
    c = api.RunPodClient(key=FAKE_KEY, transport=t)
    token = confirm.CreateAuthorization("s", 0.34, 4, 3.0)
    c.allow_create(token)
    c.create_pod({"name": "oneground-session-x"})
    assert t.billable_calls(), "the create was not recorded as billable"


def test_graphql_refuses_mutations():
    c = _client()
    try:
        c.graphql("mutation { podFindAndDeployOnDemand(input:{}) { id } }")
    except api.CreateCallBlocked:
        return
    raise AssertionError("a graphql mutation was allowed")


# ------------------------------- no create call outside `up` (the brief's #3)
def _run_cli(argv, transport, tmp, monkey_root=True):
    """Drive the real CLI with a stubbed transport and a temp repo root."""
    made = {}

    def fake_client(args):
        return api.RunPodClient(key=FAKE_KEY, transport=transport)

    orig_client, orig_root = cli._client, cli._repo_root
    cli._client = fake_client
    if monkey_root:
        cli._repo_root = lambda: tmp
    buf = io.StringIO()
    orig_stdout = sys.stdout
    sys.stdout = buf
    try:
        code = cli.main(argv)
    except SystemExit as e:
        code = e.code
    finally:
        sys.stdout = orig_stdout
        cli._client, cli._repo_root = orig_client, orig_root
    # Anything cli.main did not handle is a crash, and a crash must fail the
    # test rather than be recorded as an exit code of None. An earlier version
    # swallowed it here, which hid a stubbing bug behind a green assertion.
    return code, buf.getvalue(), made


def _seed_session(tmp, pod_id="pod-1", sid="20260909-120000", hours_ago=0.5):
    rec = {
        "id": sid, "session": "arxiv-build", "spec": "sessions/arxiv-build.yaml",
        "pod_id": pod_id, "state": "running",
        "started_at_epoch": time.time() - hours_ago * 3600,
        "data_center_id": "EU-RO-1", "gpu": "RTX PRO 4500",
        "usd_per_hr_at_create": 0.34,
        "caps": {"max_hours": 4, "max_usd": 3.0, "max_concurrent": 1},
        "remote_log": "/workspace/oneground-session.log",
        "remote_repo": "/workspace/oneground", "done_marker": "DONE",
        "outputs": [],
    }
    statemod.save(rec, tmp)
    return rec


def test_the_launch_names_the_pod_so_environment_id_is_attributable_synthetic():
    """`environment_id: unknown-pod` settles no latency constraint at all."""
    class _Ssh:
        def __init__(self):
            self.env = None

        def put(self, *a):
            pass

        def run(self, cmd, timeout=None, check=True):
            return None

        def start_run(self, repo, cmd, log, env=None):
            self.env = env
            return {"pid": "1", "stdout": "", "stderr": "", "returncode": 0,
                    "launched": True}

    with tempfile.TemporaryDirectory() as tmp:
        sess = sessionmod.Session("t", _spec_data(), path="t.yaml")
        ssh = _Ssh()
        orig_bundle = sshx.bundle_repo
        sshx.bundle_repo = lambda root: (os.path.join(tmp, "b.bundle"), [])
        try:
            cli._sync_and_start(ssh, sess, tmp, "20260909-120000", "pod-xyz")
        finally:
            sshx.bundle_repo = orig_bundle
        assert ssh.env["RUNPOD_POD_ID"] == "pod-xyz", ssh.env
        assert ssh.env["ONEGROUND_SESSION"] == "20260909-120000", ssh.env
        # The spec's own env still travels.
        for k in sess.env:
            assert ssh.env[k] == sess.env[k], (k, ssh.env)


# ------------------------------------ fetched outputs (session ...220900)
def _tgz(path, members):
    import tarfile
    with tarfile.open(path, "w:gz") as tf:
        for name, body in members.items():
            data = body.encode()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


class _FetchSsh:
    """An ssh double that hands back a prepared tarball."""

    def __init__(self, tarball):
        self.tarball = tarball

    def exists(self, remote):
        return True

    def get(self, remote, local, timeout=None):
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        with open(self.tarball, "rb") as src, open(local, "wb") as dst:
            dst.write(src.read())
        return local


def test_an_output_extracts_into_its_own_local_directory_synthetic():
    """Session 20260909-220900: the result landed in a stray directory at the
    repo root while `report` went on reading a stale file in the workdir."""
    with tempfile.TemporaryDirectory() as tmp:
        src = _tgz(os.path.join(tmp, "src.tgz"),
                   {"verify.json": '{"environment_id": "pod-1"}',
                    "verify_info.json": "{}"})
        rec = {"id": "s1", "outputs": [
            {"remote": "/workspace/verify-out.tgz",
             "local": "runs/arxiv-smoke/", "extract": True}]}
        root = os.path.join(tmp, "repo")
        os.makedirs(root)
        code = cli._fetch_outputs(_FetchSsh(src), rec, root)
        assert code == 0
        landed = os.path.join(root, "runs", "arxiv-smoke", "verify.json")
        assert os.path.exists(landed), os.listdir(root)
        # And nothing beside runs/ -- the stray directory is the actual bug.
        assert not os.path.exists(os.path.join(root, "arxiv-smoke")), \
            os.listdir(root)


def test_an_output_with_local_dot_still_extracts_at_the_repo_root_synthetic():
    """The arxiv-build session says `local: ./` and its members are already
    repo-relative. That path must not change."""
    with tempfile.TemporaryDirectory() as tmp:
        src = _tgz(os.path.join(tmp, "src.tgz"),
                   {"fixtures/arxiv-150k/spec.yaml": "x"})
        rec = {"id": "s1", "outputs": [
            {"remote": "/workspace/small.tgz", "local": "./", "extract": True}]}
        root = os.path.join(tmp, "repo")
        os.makedirs(root)
        assert cli._fetch_outputs(_FetchSsh(src), rec, root) == 0
        assert os.path.exists(
            os.path.join(root, "fixtures", "arxiv-150k", "spec.yaml"))


def test_the_runner_packages_bare_filenames_so_they_land_in_the_workdir():
    """The two halves have to agree: members are what appears in `local`."""
    src = open("corpora/run_verify_pod.sh", encoding="utf-8").read()
    fn = src[src.index("package_outputs() {"):src.index("\n}", src.index(
        "package_outputs() {"))]
    assert 'tar -czf "$tarball" -C "$workdir"' in fn, fn
    # No member may carry a directory prefix. Checked on the code lines only:
    # the comment above the tar deliberately explains why basename is gone.
    code = [ln for ln in fn.splitlines() if not ln.strip().startswith("#")]
    assert not any("basename" in ln for ln in code), code


def test_the_verify_session_uploads_simulate_json_synthetic():
    """Without it the pod reports `couldnt_check: no simulate.json` for
    calibration, having measured everything the comparison needs."""
    from oneground.verify import runpod as rp
    names = [n for n, _optional in rp.WORKDIR_INPUTS]
    assert "simulate.json" in names, names
    optional = dict(rp.WORKDIR_INPUTS)
    # Optional: a workdir that has not been simulated is still verifiable.
    assert optional["simulate.json"] is True


# -------------------------------------------- inputs (session ...195824)
def test_a_missing_required_input_refuses_before_anything_is_created_synthetic():
    """The pod must not be created to discover a file is absent locally.

    Session 20260909-195824 ran setup, started qdrant and then died on
    `no characterization in ...`. All of that was billable.
    """
    with tempfile.TemporaryDirectory() as tmp:
        spec = _spec_file(tmp, extra={"inputs": [
            {"local": "runs/nope/characterization.json",
             "remote": "/workspace/oneground/runs/nope/characterization.json"}]})
        t = _transport({"/pods": []})
        asked = []
        orig = confirm.ask_to_create
        confirm.ask_to_create = lambda *a, **kw: asked.append(a)
        try:
            code, out, _ = _run_cli(["up", spec], t, tmp)
        finally:
            confirm.ask_to_create = orig
        assert code == 1, out
        assert "do not exist locally" in out, out
        assert "runs/nope/characterization.json" in out, out
        assert not asked, "the prompt was reached with a missing input"
        assert not t.billable_calls()


def test_an_optional_input_does_not_refuse_the_session_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        spec = _spec_file(tmp, extra={"inputs": [
            {"local": "runs/nope/ground_truth_scores.npy", "optional": True,
             "remote": "/workspace/oneground/runs/nope/gts.npy"}]})
        t = _transport({"/pods": []})
        asked = []
        orig = confirm.ask_to_create

        def stub(*a, **kw):
            asked.append(a)
            raise confirm.ConfirmationRefused("stubbed: no pod in a test")

        confirm.ask_to_create = stub
        try:
            code, out, _ = _run_cli(["up", spec], t, tmp)
        finally:
            confirm.ask_to_create = orig
        assert asked, out
        assert not t.billable_calls()


def test_an_input_remote_must_be_absolute_synthetic():
    try:
        sessionmod.Input(local="runs/x", remote="runs/x")
    except sessionmod.SessionSpecError:
        pass
    else:
        raise AssertionError("a relative input.remote was accepted")


def test_tar_directory_carries_contents_not_the_directory_synthetic():
    """Extraction is `-C <dest>`, so the archive must hold bare names."""
    import tarfile
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "workdir")
        os.makedirs(os.path.join(d, "sub"))
        for name in ("characterization.json", "ground_truth.npy"):
            with open(os.path.join(d, name), "w") as f:
                f.write("x")
        with open(os.path.join(d, "sub", "deep.txt"), "w") as f:
            f.write("y")
        tgz, names = sshx.tar_directory(d)
        try:
            with tarfile.open(tgz) as tf:
                members = sorted(tf.getnames())
            assert "characterization.json" in members, members
            assert "sub/deep.txt" in members, members
            assert not any(m.startswith("workdir") for m in members), members
            assert names == ["characterization.json", "ground_truth.npy", "sub"]
        finally:
            os.remove(tgz)


class _RecordingSsh:
    """An ssh double that keeps the archive it was handed."""

    def __init__(self):
        self.puts, self.cmds, self.archive = [], [], None

    def put(self, local, remote, timeout=None):
        # Copy it: `_upload_inputs` deletes the archive in its finally block.
        with open(local, "rb") as f:
            self.archive = f.read()
        self.puts.append((local, remote, timeout))

    def run(self, cmd, timeout=None, check=True):
        self.cmds.append((cmd, timeout))


def _upload_fixture(tmp, sizes):
    wd = os.path.join(tmp, "runs", "arxiv-smoke")
    os.makedirs(wd, exist_ok=True)
    for name, n in sizes.items():
        with open(os.path.join(wd, name), "wb") as f:
            f.write(b"x" * n)
    data = _spec_data()
    data["inputs"] = [
        {"local": "runs/arxiv-smoke/characterization.json",
         "remote": "/workspace/oneground/runs/arxiv-smoke/characterization.json"},
        {"local": "runs/arxiv-smoke/ground_truth.npy", "optional": True,
         "remote": "/workspace/oneground/runs/arxiv-smoke/ground_truth.npy"},
    ]
    return sessionmod.Session("t", data, path="t.yaml")


def test_upload_sends_one_archive_however_many_files_synthetic():
    """Twelve ssh handshakes to move 258 KB was the defect in session
    20260909-202938. Three connections, always."""
    import tarfile
    with tempfile.TemporaryDirectory() as tmp:
        sess = _upload_fixture(tmp, {"characterization.json": 10,
                                     "ground_truth.npy": 20})
        ssh = _RecordingSsh()
        placed = cli._upload_inputs(ssh, sess, tmp)
        assert len(placed) == 2, placed
        assert len(ssh.puts) == 1, ssh.puts
        assert len(ssh.cmds) == 1, ssh.cmds
        # No per-file mkdir: the archive's member names carry the destination.
        assert not any("mkdir" in c for c, _ in ssh.cmds), ssh.cmds
        cmd = ssh.cmds[0][0]
        assert "-C /" in cmd and "--no-same-owner" in cmd, cmd

        with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as f:
            f.write(ssh.archive)
            arc = f.name
        try:
            with tarfile.open(arc) as tf:
                names = sorted(tf.getnames())
        finally:
            os.remove(arc)
        # Member names are the remote absolute paths minus the leading slash,
        # which is what makes `tar -C /` land each file where the spec said.
        assert names == [
            "workspace/oneground/runs/arxiv-smoke/characterization.json",
            "workspace/oneground/runs/arxiv-smoke/ground_truth.npy"], names


def test_upload_skips_an_absent_optional_input_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        sess = _upload_fixture(tmp, {"characterization.json": 10})
        ssh = _RecordingSsh()
        placed = cli._upload_inputs(ssh, sess, tmp)
        assert placed == [("runs/arxiv-smoke/characterization.json",
                           "/workspace/oneground/runs/arxiv-smoke/"
                           "characterization.json")], placed


def test_the_transfer_timeout_scales_with_size_synthetic():
    """A fixed timeout is wrong at both ends: too short for a big transfer and
    too long to notice a hang on a small one."""
    small = sshx.transfer_timeout(0)
    big = sshx.transfer_timeout(200 * 1024 * 1024)
    assert small == sshx.TRANSFER_BASE_SECONDS, small
    assert big > small, (small, big)
    # 200 MB at the 256 KB/s floor is 800 s of payload allowance.
    assert abs(big - (sshx.TRANSFER_BASE_SECONDS + 800)) < 1, big
    # And it is bounded, so a mistake in a spec cannot hang `up` for a day.
    assert sshx.transfer_timeout(10 ** 12) == sshx.TRANSFER_MAX_SECONDS


def test_the_upload_timeout_is_the_one_derived_from_the_archive_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        sess = _upload_fixture(tmp, {"characterization.json": 4096,
                                     "ground_truth.npy": 4096})
        ssh = _RecordingSsh()
        cli._upload_inputs(ssh, sess, tmp)
        packed = len(ssh.archive)
        expected = sshx.transfer_timeout(packed)
        assert ssh.puts[0][2] == expected, (ssh.puts, expected)
        assert ssh.cmds[0][1] == expected, (ssh.cmds, expected)


def test_a_timeout_reports_what_the_command_said_synthetic():
    """Session 20260909-202938 left nothing to diagnose but a port number."""
    import subprocess as _sp

    class _Ssh(sshx.PodSsh):
        pass

    ssh = _Ssh("1.2.3.4", 22, timeout=5)
    orig = _sp.run

    def boom(*a, **kw):
        raise _sp.TimeoutExpired(cmd=a[0], timeout=5, output="partial out",
                                 stderr="ssh: connect refused")

    _sp.run = boom
    try:
        ssh.run("true")
    except sshx.SshError as e:
        msg = str(e)
        assert "timed out after" in msg, msg
        assert "connect refused" in msg, msg
        assert "partial out" in msg, msg
    else:
        raise AssertionError("no SshError raised")
    finally:
        _sp.run = orig


def test_ssh_never_prompts_synthetic():
    """A prompt on an unwatched terminal is indistinguishable from a hang, and
    it burns the caller's whole timeout before saying so."""
    assert "BatchMode=yes" in sshx.SSH_OPTS
    assert "ConnectTimeout=30" in sshx.SSH_OPTS


def test_inputs_over_the_size_cap_refuse_before_the_create_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        wd = os.path.join(tmp, "runs", "big")
        os.makedirs(wd)
        with open(os.path.join(wd, "vectors.npy"), "wb") as f:
            f.write(b"x" * (3 * 1024 * 1024))
        spec = _spec_file(tmp, extra={
            "input_size_cap_mb": 1,
            "inputs": [{"local": "runs/big/vectors.npy",
                        "remote": "/workspace/oneground/runs/big/vectors.npy"}]})
        t = _transport({"/pods": []})
        asked = []
        orig = confirm.ask_to_create
        confirm.ask_to_create = lambda *a, **kw: asked.append(a)
        try:
            code, out, _ = _run_cli(["up", spec], t, tmp)
        finally:
            confirm.ask_to_create = orig
        assert code == 1, out
        assert "cap is 1 MB" in out, out
        assert "input_size_cap_mb" in out, out
        assert not asked, "the prompt was reached over the input size cap"
        assert not t.billable_calls()


def test_the_size_cap_defaults_to_50_mb_and_has_no_flag_synthetic():
    sess = sessionmod.Session("t", _spec_data(), path="t.yaml")
    assert sess.input_size_cap_mb == 50
    src = open(os.path.join(os.path.dirname(os.path.abspath(cli.__file__)),
                            "cli.py"), encoding="utf-8").read()
    for flag in ("--allow-large-inputs", "--no-input-cap", "--force-inputs"):
        assert flag not in src, flag


def test_a_verify_session_declares_the_workdir_it_needs_synthetic():
    """The generated spec must carry the files `verify --on-pod` reads."""
    from oneground.verify import runpod as rp
    inputs = rp._workdir_inputs(os.path.join(os.getcwd(), "runs", "arxiv-smoke"))
    locals_ = [i["local"] for i in inputs]
    assert "runs/arxiv-smoke/characterization.json" in locals_, locals_
    assert "runs/arxiv-smoke/ground_truth.npy" in locals_, locals_
    for i in inputs:
        assert i["remote"].startswith("/workspace/oneground/"), i
        # Same relative path on both machines: the pod runs the same
        # requirements file, which names the workdir as ./runs/<name>.
        assert i["remote"].endswith(i["local"]), i
    assert [i["local"] for i in inputs if i["optional"]] == [
        "runs/arxiv-smoke/ground_truth_scores.npy",
        "runs/arxiv-smoke/build_info.json",
        "runs/arxiv-smoke/simulate.json"], inputs


# ----------------------------------------------- stale records (session ...194107)
def _pod(pod_id="pod-1", sid="20260909-120000"):
    return {"id": pod_id, "name": "oneground-session-" + sid,
            "desiredStatus": "RUNNING", "costPerHr": 0.34,
            "env": {"ONEGROUND_SESSION": sid},
            "machine": {"dataCenterId": "EU-RO-1"}}


def test_ls_marks_a_record_terminated_when_its_pod_is_gone_synthetic():
    """`ls` used to narrate the stale record and change nothing.

    Session 20260909-194107: the pod was gone, `ls` said so, and the record
    stayed `running` -- which then blocked `up`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, pod_id="pod-gone")
        t = _transport({"/pods": []})           # the account has nothing
        code, out, _ = _run_cli(["ls"], t, tmp)
        assert code == 0, out
        assert "now marked terminated" in out, out
        rec = statemod.load("20260909-120000", tmp)
        assert rec["state"] == "terminated", rec
        assert rec.get("finished_because") == "absent-from-account", rec
        assert not t.billable_calls()


def test_ls_leaves_a_record_alone_while_its_pod_is_on_the_account_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, pod_id="pod-1")
        t = _transport({"/pods": [_pod("pod-1")]})
        code, out, _ = _run_cli(["ls"], t, tmp)
        assert code == 0, out
        assert statemod.load("20260909-120000", tmp)["state"] == "running"


def test_ls_does_not_close_a_record_for_a_pod_renamed_in_the_console_synthetic():
    """A renamed pod loses the oneground label but is still billing.

    Reconciliation is against every pod on the account, not only the ones
    `ls` recognised as ours -- otherwise a rename in the console would close
    the record of a pod that is still costing money.
    """
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, pod_id="pod-1")
        renamed = {"id": "pod-1", "name": "my-experiment",
                   "desiredStatus": "RUNNING", "costPerHr": 0.34, "env": {}}
        t = _transport({"/pods": [renamed]})
        code, out, _ = _run_cli(["ls"], t, tmp)
        assert code == 0, out
        assert statemod.load("20260909-120000", tmp)["state"] == "running", out


def test_ls_keeps_a_seconds_old_record_the_account_has_not_listed_yet_synthetic():
    """GET /pods lags a create. Closing that record would let `up` double-book."""
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, pod_id="pod-new", hours_ago=0.0)
        t = _transport({"/pods": []})
        code, out, _ = _run_cli(["ls"], t, tmp)
        assert code == 0, out
        assert statemod.load("20260909-120000", tmp)["state"] == "running", out
        assert "not listed by the account yet" in out, out


def test_ls_leaves_records_alone_when_the_account_is_unreachable_synthetic():
    """Over-counting refuses a session; under-counting creates one."""
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, pod_id="pod-1")

        def boom():
            raise api.PodApiError("GET /pods -> timed out")

        t = _transport({"/pods": boom})
        code, out, _ = _run_cli(["ls"], t, tmp)
        assert statemod.load("20260909-120000", tmp)["state"] == "running", out


def test_down_marks_the_record_terminated_on_a_404_synthetic():
    """RunPod answers DELETE on an already-gone pod with 404.

    That is the outcome `down` was asked for. It used to surface as a failure
    and leave the record `running`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, pod_id="pod-gone")

        def gone():
            raise api.PodApiError("DELETE /pods/pod-gone -> HTTP 404 {}",
                                  status=404)

        t = _transport({"/pods/pod-gone": gone, "/pods": []})
        code, out, _ = _run_cli(["down", "20260909-120000"], t, tmp)
        assert code == 0, out
        assert "already terminated" in out, out
        rec = statemod.load("20260909-120000", tmp)
        assert rec["state"] == "terminated", rec
        assert not t.billable_calls()


def test_down_still_fails_loudly_on_any_other_api_error_synthetic():
    """A 500 is not proof the meter stopped, and must not close the record."""
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, pod_id="pod-1")

        def boom():
            raise api.PodApiError("DELETE /pods/pod-1 -> HTTP 500 oops",
                                  status=500)

        t = _transport({"/pods/pod-1": boom, "/pods": []})
        code, out, _ = _run_cli(["down", "20260909-120000"], t, tmp)
        assert code == 1, out
        assert "MAY STILL BE BILLING" in out, out
        assert statemod.load("20260909-120000", tmp)["state"] == "running"


def test_is_gone_reads_the_status_not_the_pod_id_synthetic():
    """A pod id containing 404 must not be mistaken for a missing pod."""
    assert api.is_gone(api.PodApiError("x", status=404))
    assert api.is_gone(api.PodApiError("DELETE /pods/p -> HTTP 404 {}"))
    assert not api.is_gone(api.PodApiError("DELETE /pods/abc404def -> HTTP 500"))
    assert not api.is_gone(api.PodApiError("x", status=500))


def test_up_does_not_count_a_record_whose_pod_is_absent_synthetic():
    """The bug that blocked the next session.

    max_concurrent is 1 and one stale record existed, so `up` refused before
    ever reaching the confirmation prompt -- for a session that was not
    billing a cent.
    """
    with tempfile.TemporaryDirectory() as tmp:
        spec = _spec_file(tmp)
        _seed_session(tmp, pod_id="pod-gone")
        t = _transport({"/pods": []})
        asked = []
        orig = confirm.ask_to_create

        def stub(*a, **kw):
            asked.append(a)
            raise confirm.ConfirmationRefused("stubbed: no pod in a test")

        confirm.ask_to_create = stub
        try:
            code, out, _ = _run_cli(["up", spec], t, tmp)
        finally:
            confirm.ask_to_create = orig
        assert "session(s) already live" not in out, out
        assert statemod.load("20260909-120000", tmp)["state"] == "terminated"
        # It got as far as the prompt -- which is where a test must stop.
        assert asked, out
        assert not t.billable_calls()


def test_up_still_refuses_when_the_pod_really_is_running_synthetic():
    """The cap is not weakened: a record backed by a real pod still refuses."""
    with tempfile.TemporaryDirectory() as tmp:
        spec = _spec_file(tmp)
        _seed_session(tmp, pod_id="pod-1")
        t = _transport({"/pods": [_pod("pod-1")]})
        asked = []
        orig = confirm.ask_to_create
        confirm.ask_to_create = lambda *a, **kw: asked.append(a)
        try:
            code, out, _ = _run_cli(["up", spec], t, tmp)
        finally:
            confirm.ask_to_create = orig
        assert code == 1, out
        assert "session(s) already live" in out, out
        assert not asked, "the prompt was reached despite the cap"
        assert not t.billable_calls()


def test_no_subcommand_except_up_reaches_a_billable_endpoint():
    """The brief's central acceptance test.

    Every read-only subcommand is driven end to end against a recording
    transport, and the recording is asserted to contain no billable call.
    """
    with tempfile.TemporaryDirectory() as tmp:
        spec = _spec_file(tmp)
        _seed_session(tmp)
        pod = {"id": "pod-1", "name": "oneground-session-20260909-120000",
               "desiredStatus": "RUNNING", "costPerHr": 0.34,
               "env": {"ONEGROUND_SESSION": "20260909-120000"},
               "machine": {"dataCenterId": "EU-RO-1"}}
        cases = [
            ["plan", spec],
            ["status", "20260909-120000", "--no-logs"],
            ["down", "20260909-120000"],
            ["ls"],
            ["fetch", "20260909-120000"],
        ]
        for argv in cases:
            t = _transport({"/pods/pod-1": pod, "/pods": [pod]})
            code, out, made = _run_cli(argv, t, tmp)
            billable = t.billable_calls()
            assert not billable, "%s made a billable call: %r" % (argv[0], billable)
            # And no GraphQL mutation slipped through either.
            for _, _, body in t.graphql_calls():
                q = (body or {}).get("query", "")
                assert "mutation" not in q, "%s sent a mutation" % argv[0]


def test_watch_terminates_but_never_creates():
    """`watch` is the unattended path. It must be able to DELETE and must
    never be able to POST."""
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, hours_ago=99)      # already past the 4 h cap
        pod = {"id": "pod-1", "desiredStatus": "RUNNING", "costPerHr": 0.34,
               "publicIp": None, "portMappings": {}}
        t = _transport({"/pods/pod-1": pod, "/pods": [pod]})
        code, out, made = _run_cli(["watch", "20260909-120000",
                                    "--interval", "1"], t, tmp)
        assert not t.billable_calls(), "watch made a billable call"
        assert any(m == "DELETE" for m, _, _ in t.calls), \
            "watch hit the cap and did not terminate: %r" % (t.calls,)
        assert "CAP REACHED" in out


# ------------------------------------------------ up refuses non-interactive
class _NotATty(io.StringIO):
    def isatty(self):
        return False


class _Tty(io.StringIO):
    def isatty(self):
        return True


def test_up_refuses_non_interactive_stdin():
    try:
        confirm.ask_to_create("s", 0.34, 4, 3.0,
                              stream=_NotATty("y\n"), out=io.StringIO())
    except confirm.ConfirmationRefused as e:
        assert "not a terminal" in str(e)
        assert "--yes" in str(e)
        return
    raise AssertionError("a non-interactive stdin was accepted")


def test_up_cli_refuses_non_interactive_and_creates_nothing():
    """The whole `up` path, with a pipe for stdin: it must stop at the prompt
    and the transport must show no create."""
    with tempfile.TemporaryDirectory() as tmp:
        spec = _spec_file(tmp)
        t = _transport()
        orig = sys.stdin
        sys.stdin = _NotATty("y\n")
        try:
            code, out, made = _run_cli(["up", spec], t, tmp)
        finally:
            sys.stdin = orig
        assert code == 1, "up did not refuse (exit %r)" % code
        assert not t.billable_calls(), "up created something without a tty"
        assert "Not created" in out


def test_only_y_proceeds():
    for answer in ("yes", "Y", "", "n", "sure", " y ", "yy"):
        try:
            confirm.ask_to_create("s", 0.34, 4, 3.0,
                                  stream=_Tty(answer + "\n"), out=io.StringIO())
        except confirm.ConfirmationRefused:
            continue
        raise AssertionError("%r was accepted as consent" % answer)
    token = confirm.ask_to_create("s", 0.34, 4, 3.0,
                                  stream=_Tty("y\n"), out=io.StringIO())
    assert isinstance(token, confirm.CreateAuthorization)


def test_prompt_states_the_rate_and_the_cap():
    out = io.StringIO()
    confirm.ask_to_create("s", 0.34, 4, 3.0, stream=_Tty("y\n"), out=out)
    text = out.getvalue()
    assert "$0.34/hr" in text and "4 hours" in text and "[y/N]" in text


def test_confirmation_is_single_use_and_expires():
    token = confirm.CreateAuthorization("s", 0.34, 4, 3.0)
    token.consume()
    try:
        token.consume()
    except confirm.ConfirmationRefused:
        pass
    else:
        raise AssertionError("one 'y' authorised two pods")
    old = confirm.CreateAuthorization("s", 0.34, 4, 3.0)
    old.granted_at = time.time() - 3600
    try:
        old.check_valid()
    except confirm.ConfirmationRefused:
        return
    raise AssertionError("an hour-old confirmation was still valid")


def test_no_yes_flag_exists():
    """The brief forbids a --yes. Assert it against the real parser rather
    than trusting that nobody adds one."""
    parser = cli.build_parser()
    text = parser.format_help()
    for sub in ("up",):
        for action in parser._subparsers._group_actions[0].choices[sub]._actions:
            for opt in action.option_strings:
                assert opt not in ("--yes", "-y", "--force", "--no-confirm"), \
                    "a non-interactive create flag exists: %s" % opt
    assert "--yes" not in text


# -------------------------------------------------------------- redaction
def test_key_never_appears_in_errors():
    assert FAKE_KEY not in api.redact("bearer " + FAKE_KEY + " failed", FAKE_KEY)
    assert "<redacted:RUNPOD_API_KEY>" in api.redact(FAKE_KEY, FAKE_KEY)


def test_key_is_read_from_env_only():
    try:
        api.key_from_env({})
    except api.PodApiError as e:
        assert "not set in the environment" in str(e)
    else:
        raise AssertionError("a missing key was tolerated")
    assert api.key_from_env({"RUNPOD_API_KEY": " " + FAKE_KEY + " "}) == FAKE_KEY


def test_graphql_errors_are_redacted():
    t = api.RecordingTransport({"graphql": {"errors": [{"message":
                                                        "bad token " + FAKE_KEY}]}})
    c = api.RunPodClient(key=FAKE_KEY, transport=t)
    try:
        c.gpu_price_ranges("EU-RO-1")
    except api.PodApiError as e:
        assert FAKE_KEY not in str(e)
        return
    raise AssertionError("no error raised")


def test_key_is_never_written_to_the_session_record():
    with tempfile.TemporaryDirectory() as tmp:
        rec = _seed_session(tmp)
        blob = open(statemod.path_for(rec["id"], tmp), encoding="utf-8").read()
        assert FAKE_KEY not in blob and "RUNPOD_API_KEY" not in blob


# ------------------------------------------------------------------ specs
def test_spec_without_caps_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        p = _spec_file(tmp, SPEC_YAML.replace(
            "caps: {max_hours: 4, max_concurrent: 1, max_usd: 3.00}", "caps: {}"))
        try:
            sessionmod.load(p)
        except sessionmod.SessionSpecError as e:
            assert "max_hours" in str(e)
            return
        raise AssertionError("a capless session spec loaded")


def test_missing_required_key_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        p = _spec_file(tmp, SPEC_YAML.replace("volume: vol-a\n", ""))
        try:
            sessionmod.load(p)
        except sessionmod.SessionSpecError as e:
            assert "volume" in str(e)
            return
        raise AssertionError("a spec missing `volume` loaded")


def test_relative_output_paths_may_leave_the_repo():
    """The release asset is 483 MB and belongs outside git; the spec has to be
    able to say so, and `is_inside_repo` has to know which is which."""
    o_in = sessionmod.Output("/workspace/small.tgz", "./", extract=True)
    o_out = sessionmod.Output("/workspace/large.tgz", "../oneground-assets/")
    assert o_in.is_inside_repo("/repo")
    assert not o_out.is_inside_repo("/repo")


def test_output_remote_must_be_absolute():
    try:
        sessionmod.Output("workspace/small.tgz", "./")
    except sessionmod.SessionSpecError:
        return
    raise AssertionError("a relative remote path was accepted")


# ------------------------------------------------------------------- plan
def test_plan_derives_the_datacenter_from_the_volume():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        p = planmod.resolve(_client(), s)
        assert p.data_center_id == "EU-RO-1"
        assert p.gpu["display_name"] == "RTX PRO 4500"
        # The confirmed rate is the top of the range, never the floor (006c).
        assert p.usd_per_hr == 0.72
        assert (p.usd_min, p.usd_max) == (0.34, 0.72)
        # The second choice is unavailable in this DC and must not be picked.
        assert ("RTX 4090", None, None, None) in p.candidates


def test_plan_skips_a_gpu_with_no_price_in_that_datacenter():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(
            tmp, SPEC_YAML.replace('["RTX PRO 4500", "RTX 4090"]',
                                   '["RTX 4090", "RTX PRO 4500"]')))
        p = planmod.resolve(_client(), s)
        assert p.gpu["display_name"] == "RTX PRO 4500", \
            "an unavailable GPU was chosen because it was listed first"


def test_plan_fails_clearly_on_an_unknown_volume():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(
            tmp, SPEC_YAML.replace("volume: vol-a", "volume: vecbench")))
        try:
            planmod.resolve(_client(), s)
        except planmod.PlanError as e:
            assert "vecbench" in str(e) and "vol-a" in str(e)
            return
        raise AssertionError("an unknown volume resolved")


def test_plan_creates_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        t = _transport()
        planmod.resolve(api.RunPodClient(key=FAKE_KEY, transport=t), s)
        assert not t.billable_calls()
        for method, url, _ in t.calls:
            assert method in ("GET", "POST"), method
            if method == "POST":
                assert url == api.GRAPHQL_URL, "a POST went to %s" % url


def test_cap_arithmetic_refuses_an_over_budget_plan():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(
            tmp, SPEC_YAML.replace("max_usd: 3.00", "max_usd: 1.00")))
        p = planmod.resolve(_client(), s)
        # 4 h at the TOP of the range ($0.72), not the floor ($0.34, which
        # would have given $1.36 and looked affordable -- the 006b defect).
        assert abs(p.worst_case_usd - 2.88) < 1e-9, p.worst_case_usd
        assert not p.within_cap
        try:
            p.check_cap()
        except planmod.PlanError as e:
            assert "cap exceeded" in str(e)
            return
        raise AssertionError("an over-cap plan passed check_cap")


def test_plan_exit_code_is_2_when_over_cap():
    """Task 046 contract change 6: a refusal, so `refusals.REFUSED_EXIT`
    rather than the code that means did-not-finish."""
    with tempfile.TemporaryDirectory() as tmp:
        spec = _spec_file(tmp, SPEC_YAML.replace("max_usd: 3.00",
                                                 "max_usd: 1.00"))
        t = _transport()
        code, out, _ = _run_cli(["plan", spec], t, tmp)
        assert code == refusals.REFUSED_EXIT == 2 and "REFUSED" in out


def test_deploy_spec_carries_the_session_label_twice():
    """RunPod has no label field, so the label lives in the name AND the env;
    `ls` matches on either."""
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        p = planmod.resolve(_client(), s)
        spec = p.deploy_spec("20260909-120000")
        assert spec["name"] == "oneground-session-20260909-120000"
        assert spec["env"]["ONEGROUND_SESSION"] == "20260909-120000"
        assert spec["networkVolumeId"] == VOLUME["id"]
        assert spec["dataCenterIds"] == ["EU-RO-1"]
        assert "22/tcp" in spec["ports"]
        assert cli._session_label({"name": spec["name"]}) == "20260909-120000"
        assert cli._session_label({"env": spec["env"]}) == "20260909-120000"


def test_plan_render_shows_the_price_and_the_cap():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        text = planmod.resolve(_client(), s).render()
        for want in ("EU-RO-1", "$0.34 - $0.72/hr", "COST CAP",
                     "RTX PRO 4500", "derived from the volume"):
            assert want in text, want


# ------------------------------------------------------------------ state
def test_max_concurrent_counts_only_live_records():
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, pod_id="pod-1", sid="a")
        assert len(statemod.live_sessions(tmp)) == 1
        statemod.mark("a", "terminated", tmp)
        assert statemod.live_sessions(tmp) == []


def test_up_refuses_when_max_concurrent_would_be_exceeded():
    with tempfile.TemporaryDirectory() as tmp:
        spec = _spec_file(tmp)
        _seed_session(tmp, sid="already-live")
        # The pod has to be on the account for the record to count as live --
        # that is the whole of the fix for session 20260909-194107.
        t = _transport({"/pods": [_pod("pod-1", "already-live")]})
        orig = sys.stdin
        sys.stdin = _Tty("y\n")
        try:
            code, out, _ = _run_cli(["up", spec], t, tmp)
        finally:
            sys.stdin = orig
        assert code == 1
        assert "session(s) already live" in out
        assert not t.billable_calls(), "the concurrency cap did not stop a create"


def test_cost_so_far_is_elapsed_times_rate():
    rec = {"started_at_epoch": time.time() - 7200, "usd_per_hr_at_create": 0.34}
    assert abs(statemod.cost_so_far(rec) - 0.68) < 0.01


def test_ls_flags_an_orphan_and_an_over_cap_pod():
    with tempfile.TemporaryDirectory() as tmp:
        orphan = {"id": "pod-orphan", "name": "oneground-session-zzz",
                  "desiredStatus": "RUNNING", "costPerHr": 0.34}
        t = _transport({"/pods": [orphan]})
        code, out, _ = _run_cli(["ls"], t, tmp)
        assert "ORPHAN" in out and "pod-orphan" in out
        assert not t.billable_calls()

        _seed_session(tmp, pod_id="pod-1", sid="old", hours_ago=99)
        pod = {"id": "pod-1", "name": "oneground-session-old",
               "desiredStatus": "RUNNING", "costPerHr": 0.34}
        t = _transport({"/pods": [pod]})
        code, out, _ = _run_cli(["ls"], t, tmp)
        assert "OVER CAP" in out


def test_ls_reports_zero_when_the_account_has_no_oneground_pods():
    with tempfile.TemporaryDirectory() as tmp:
        t = _transport({"/pods": [{"id": "someone-elses", "name": "jupyter"}]})
        code, out, _ = _run_cli(["ls"], t, tmp)
        assert "0 oneground pods" in out and "1 other pod" in out


# ------------------------------------------------- launching the remote run
#
# These three exist because of what the first live session (task 006b) cost:
# the pod deployed, synced and set itself up correctly, then the run never
# started, and the pod sat idle and billing while `watch` waited for a DONE
# that could not arrive. Nothing needed a pod to catch it.

def test_start_command_runs_through_a_shell_not_nohup_directly():
    """`nohup` execs its first argument; it is not a shell.

    A run command beginning with environment assignments -- which the smoke
    session's does -- makes nohup try to exec a program named `SPEC=...`.
    """
    cmd = sshx.build_start_command(
        "/workspace/oneground",
        "SPEC=fixtures/arxiv-smoke.fixture.yaml bash corpora/run.sh",
        "/workspace/oneground-session.log")
    assert "nohup bash -c" in cmd, cmd
    # The env assignment must not be sitting where nohup would read a program.
    assert "nohup SPEC=" not in cmd
    assert not re.search(r"nohup\s+[A-Z_]+=", cmd), \
        "an env assignment is still nohup's first argument: %s" % cmd


def test_start_command_survives_a_command_with_quotes():
    cmd = sshx.build_start_command(
        "/workspace/oneground", "bash -c 'echo \"hi there\"'", "/tmp/x.log")
    # The payload is one shell word, so the inner quoting cannot leak out and
    # split the command.
    assert cmd.count("nohup bash -c") == 1
    assert "ONEGROUND_PID=$!" in cmd


def test_the_log_is_created_before_anything_is_backgrounded_synthetic():
    """The bug that cost session 20260909-184937.

    `&` binds looser than `&&`, so `mkdir -p D && launch > LOG & echo $!`
    backgrounds the WHOLE list: the pid printed is a subshell's, and if the
    session is torn down before that subshell reaches the redirect, the log is
    never created at all. The setup must therefore be foreground, and the log
    must exist before the `&`.
    """
    cmd = sshx.build_start_command("/repo", "run.sh", "/tmp/x.log")
    truncate = cmd.index(": > /tmp/x.log")
    # The backgrounding operator specifically -- not the `&` in `>&2`, and not
    # the `&&` inside the quoted payload.
    background = cmd.index("< /dev/null &") + len("< /dev/null ")
    assert truncate < background, (
        "the log is created after something is backgrounded, so its existence "
        "depends on a race:\n" + cmd)
    # Outside the quoted payload, no `&&` may join the setup to the launch:
    # `&` binds looser, so `A && B &` backgrounds the whole list.
    setup = cmd[:cmd.index("nohup bash -c")]
    assert "&&" not in setup, (
        "`&&` in the setup makes `&` background the entire list:\n" + setup)


def test_start_command_confirms_the_launch_rather_than_echoing_a_pid_synthetic():
    """A bare `echo $!` returns a plausible pid for a launch that never
    happened -- measured in tasks/scratch/011-launch-repro.py, where the old
    shape exited 0 with a pid for a command that does not exist."""
    cmd = sshx.build_start_command("/repo", "run.sh", "/tmp/x.log")
    assert "ONEGROUND_LAUNCHED" in cmd
    assert "ONEGROUND_LAUNCH_FAIL" in cmd
    assert "exit 1" in cmd, "no non-zero exit path for a failed launch"


def test_the_launch_carries_the_session_env_synthetic():
    """A pod's `env` reaches the container's main process, not an ssh shell.

    Session 20260909-194107 measured the wrong thing for exactly this reason:
    every ONEGROUND_* value the runner printed was a default, so the smoke pod
    verified the arXiv requirements. The launch must export the session's env
    itself rather than trust the image's sshd wiring.
    """
    cmd = sshx.build_start_command(
        "/repo", "run.sh", "/tmp/x.log",
        env={"ONEGROUND_REQUIREMENTS": "requirements.smoke.yaml",
             "ONEGROUND_CONCURRENCY": "8"})
    assert "export ONEGROUND_REQUIREMENTS=requirements.smoke.yaml" in cmd
    assert "export ONEGROUND_CONCURRENCY=8" in cmd
    # Inside the quoted payload, so it applies to the run and not to the
    # launcher's own shell.
    payload_start = cmd.index("nohup bash -c '") + len("nohup bash -c '")
    payload_end = cmd.index("' >>", payload_start)
    payload = cmd[payload_start:payload_end]
    assert "export ONEGROUND_REQUIREMENTS=" in payload
    assert payload.index("cd /repo") < payload.index("export ")
    assert payload.rstrip().endswith("run.sh")


def test_env_values_survive_shell_quoting_synthetic():
    """A value with a space or a quote must not split the command.

    Values are quoted twice -- once for the `export`, once for the payload
    that `bash -c` receives -- so the right check is that a real shell reads
    the value back intact, not that some particular escaping appears.
    """
    import shutil
    import subprocess
    import tempfile
    import time as _time
    candidates = (os.path.join("C:" + os.sep, "Program Files", "Git", "bin",
                               "bash.exe"), "/usr/bin/bash", "/bin/bash")
    bash = next((c for c in candidates if os.path.exists(c)),
                shutil.which("bash"))
    if not bash:
        pytest.skip("no POSIX shell available")
    tricky = {"ONEGROUND_NOTE": "two words", "ONEGROUND_Q": "a'b"}
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "q.log").replace("\\", "/")
        cmd = sshx.build_start_command(
            tmp.replace("\\", "/"),
            'printf "NOTE=[%s] Q=[%s]\\n" "$ONEGROUND_NOTE" "$ONEGROUND_Q"',
            log, env=tricky)
        subprocess.run([bash, "-c", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
        text, deadline = "", _time.time() + 15
        while _time.time() < deadline:
            if os.path.exists(log):
                with open(log, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                if "NOTE=" in text:
                    break
            _time.sleep(0.2)
        assert "NOTE=[two words]" in text, text
        assert "Q=[a'b]" in text, text


def test_no_env_still_produces_a_valid_launch_synthetic():
    cmd = sshx.build_start_command("/repo", "run.sh", "/tmp/x.log")
    assert "export " not in cmd
    assert "nohup bash -c 'cd /repo && run.sh'" in cmd


def test_the_env_actually_reaches_the_command_in_a_real_shell_synthetic():
    """Run the generated line and read back what the run saw."""
    import shutil
    import subprocess
    import tempfile
    import time as _time
    candidates = (os.path.join("C:" + os.sep, "Program Files", "Git", "bin",
                               "bash.exe"), "/usr/bin/bash", "/bin/bash")
    bash = next((c for c in candidates if os.path.exists(c)),
                shutil.which("bash"))
    if not bash:
        pytest.skip("no POSIX shell available")
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "out.log").replace("\\", "/")
        cmd = sshx.build_start_command(
            tmp.replace("\\", "/"),
            'echo "REQ=$ONEGROUND_REQUIREMENTS CONC=$ONEGROUND_CONCURRENCY"',
            log,
            env={"ONEGROUND_REQUIREMENTS": "requirements.smoke.yaml",
                 "ONEGROUND_CONCURRENCY": "8"})
        subprocess.run([bash, "-c", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
        text = ""
        deadline = _time.time() + 15
        while _time.time() < deadline:
            if os.path.exists(log):
                with open(log, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                if "REQ=" in text:
                    break
            _time.sleep(0.2)
        assert "REQ=requirements.smoke.yaml" in text, (
            "the run did not see the session env: %r" % text)
        assert "CONC=8" in text, text


def test_setsid_is_optional_and_reported_synthetic():
    """setsid is hardening, not a requirement: nohup alone already ignores
    HUP, and Git Bash and some minimal images have no setsid. Which form was
    used is reported so a weaker launch is visible."""
    cmd = sshx.build_start_command("/repo", "run.sh", "/tmp/x.log")
    assert "command -v setsid" in cmd
    assert "ONEGROUND_LAUNCHER=" in cmd
    assert "setsid=$" in cmd, "the confirmation does not say which was used"


def _bash_that_shares_this_filesystem(probe_dir):
    """A bash that can see `probe_dir`, or None. Task 015b.

    `shutil.which("bash")` is not enough on Windows. `C:\\Windows\\System32\\
    bash.exe` is the WSL launcher: a real bash, but one that runs in a
    different filesystem namespace, where a Windows temp path simply does not
    exist. It writes the log somewhere this process cannot read, so the test
    waited out its 20-second deadline and failed on an empty string -- which
    reads like the feature is broken, and it is not.

    Which bash `which` returns depends on the PATH of the shell that launched
    pytest: Git Bash's own comes first from a Git Bash prompt, WSL's comes
    first from PowerShell. So this test quietly changed what it was testing
    depending on how it was started, and only failed one of those ways. Ask
    each candidate whether it can see the directory instead of assuming.
    """
    import shutil
    import subprocess
    candidates = []
    found = shutil.which("bash")
    if found:
        candidates.append(found)
    for p in (r"C:\Program Files\Git\bin\bash.exe",
              r"C:\Program Files\Git\usr\bin\bash.exe",
              r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if os.path.exists(p) and p not in candidates:
            candidates.append(p)
    posix = probe_dir.replace("\\", "/")
    for b in candidates:
        try:
            r = subprocess.run(
                [b, "-c", 'test -d "%s" && echo SHARED' % posix],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if "SHARED" in (r.stdout or ""):
            return b
    return None


def test_start_command_actually_works_in_a_real_shell():
    """Run the generated line locally and check the env prefix took effect.

    This is the test that would have failed before the fix, on any machine
    with bash, for free.
    """
    import shutil
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        bash = _bash_that_shares_this_filesystem(tmp)
        if bash is None:
            pytest.skip("no bash that can see this process's filesystem "
                        "(a WSL bash cannot read a Windows temp path)")
        log = os.path.join(tmp, "run.log").replace("\\", "/")
        cmd = sshx.build_start_command(
            tmp.replace("\\", "/"),
            "ONEGROUND_PROBE=itworked bash -c 'echo $ONEGROUND_PROBE; echo DONE'",
            log)
        # `setsid` is a Linux utility and Git Bash on Windows does not ship it.
        # It detaches the process group and is orthogonal to what is under test
        # here -- whether nohup can exec a command carrying an env prefix -- so
        # it is dropped when absent rather than skipping the test on the one
        # platform the developer actually works on.
        if shutil.which("setsid") is None:
            cmd = cmd.replace("setsid nohup ", "nohup ", 1)
        subprocess.run([bash, "-c", cmd], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
        deadline = time.time() + 20
        text = ""
        while time.time() < deadline:
            if os.path.exists(log):
                with open(log, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                if "DONE" in text or "No such file" in text:
                    break
            time.sleep(0.3)
        assert "No such file or directory" not in text, \
            "nohup could not exec the command: %r" % text
        assert "itworked" in text, \
            "the env assignment did not reach the command: %r" % text
        assert "DONE" in text, "the run did not complete: %r" % text


def test_subprocess_output_is_decoded_as_utf8_not_the_console_codepage():
    """pip prints bytes that are not valid cp1252.

    Decoding with the locale codec killed a reader thread mid-session with
    `UnicodeDecodeError: 'charmap' codec can't decode byte 0x81`. The call must
    pin encoding and never raise on a stray byte.
    """
    import inspect
    src = inspect.getsource(sshx.PodSsh._run)
    assert 'encoding="utf-8"' in src, "subprocess output is locale-decoded"
    assert 'errors="replace"' in src, "a stray byte can still raise"
    # And prove the chosen settings actually tolerate the byte that broke it.
    assert b"\x81".decode("utf-8", "replace") == "�"


# ==========================================================================
# Task 006c: the money boundary by design, not by margin.
#
# Task 006b confirmed $0.34/hr and was billed $0.72/hr, and its `max_usd` cap
# survived only because `max_hours` bounded the run in time. Its first pod
# billed for ten minutes with no run started. These cover both.
# ==========================================================================

# -- (a) the range is quoted; the floor never is ---------------------------
def test_price_range_uses_the_cloud_list_price_not_the_floor():
    prices = _client().gpu_price_ranges("EU-RO-1", "SECURE")
    e = prices["RTX PRO 4500"]
    assert e["usd_min"] == 0.34, e
    assert e["usd_max"] == 0.72, "the secure list price is not the max: %r" % e
    assert e["floor"] == 0.34


def test_plan_confirms_against_the_top_of_the_range():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        p = planmod.resolve(_client(), s)
        assert p.usd_min == 0.34
        assert p.usd_max == 0.72
        # The single rate everything else reads must be the worst case.
        assert p.usd_per_hr == 0.72, \
            "usd_per_hr is still the floor -- this is the 006b defect"
        # 4 h x 0.72, not 4 h x 0.34.
        assert abs(p.worst_case_usd - 2.88) < 1e-9, p.worst_case_usd


def test_plan_output_shows_a_range_and_a_worst_case_total():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        text = planmod.resolve(_client(), s).render()
        assert "$0.34 - $0.72/hr" in text, text
        assert "up to $0.72/hr" in text
        assert "up to $2.88" in text


def test_a_gpu_priced_only_on_a_cloud_it_is_not_sold_on_is_not_chosen():
    """RTX PRO 4500 has a communityPrice and communityCloud false.

    On a COMMUNITY session that phantom price must not be quoted at all.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(
            tmp, SPEC_YAML.replace("caps:", "cloud_type: COMMUNITY\ncaps:")))
        try:
            planmod.resolve(_client(), s)
        except planmod.PlanError as e:
            assert "COMMUNITY" in str(e)
            return
        raise AssertionError("a GPU not sold on COMMUNITY was selected")


def test_unpriceable_gpu_is_couldnt_check_and_up_refuses():
    """No list price -> refuse. Never fall back to the floor."""
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(
            tmp, SPEC_YAML.replace('["RTX PRO 4500", "RTX 4090"]', '["L4"]')))
        p = planmod.resolve(_client(), s)
        assert p.usd_max is None and not p.priced
        assert p.usd_min == 0.44, "the floor is still known, just not usable"
        assert "couldn't-check" in p.render()
        try:
            p.check_cap()
        except planmod.PlanError as e:
            assert "couldn't-check" in str(e)
        else:
            raise AssertionError("an unpriceable plan passed check_cap")

        t = _transport()
        orig = sys.stdin
        sys.stdin = _Tty("y\n")
        try:
            code, out, _ = _run_cli(["up", _spec_file(
                tmp, SPEC_YAML.replace('["RTX PRO 4500", "RTX 4090"]',
                                       '["L4"]'), "l4.yaml")], t, tmp)
        finally:
            sys.stdin = orig
        assert code == 1
        assert not t.billable_calls(), "an unpriced pod was created"


def test_no_lowest_price_is_ever_quoted_as_the_confirmed_rate():
    """Guard the specific regression: whatever else changes, the number the
    prompt and the cap use must not be the datacenter floor."""
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        p = planmod.resolve(_client(), s)
        floor = p.gpu["floor"]
        assert p.usd_per_hr != floor
        assert p.worst_case_usd != s.caps.max_hours * floor


def test_render_handles_a_gpu_absent_here_but_priced_globally():
    """Live data has types with a global list price and no datacenter floor.

    `render` formatted on `usd_max` alone and crashed with a TypeError on the
    first live run of this task.
    """
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(
            tmp, SPEC_YAML.replace('["RTX PRO 4500", "RTX 4090"]',
                                   '["RTX PRO 4500", "RTX 6000 Ada", "L4"]')))
        text = planmod.resolve(_client(), s).render()      # must not raise
        assert "RTX 6000 Ada=unavailable" in text, text
        assert "L4=couldn't-check" in text, text


# -- the prompt ------------------------------------------------------------
def test_prompt_quotes_the_worst_case_and_the_range():
    out = io.StringIO()
    confirm.ask_to_create("s", 0.72, 4, 3.0, stream=_Tty("y\n"), out=out,
                          usd_min=0.34)
    text = out.getvalue()
    for want in ("up to $0.72/hr", "range $0.34-$0.72", "4 hours",
                 "up to $2.88", "[y/N]"):
        assert want in text, "%r missing from %r" % (want, text)


def test_prompt_refuses_when_there_is_no_worst_case():
    try:
        confirm.ask_to_create("s", None, 4, 3.0, stream=_Tty("y\n"),
                              out=io.StringIO())
    except confirm.ConfirmationRefused as e:
        assert "couldn't-check" in str(e)
        return
    raise AssertionError("a priceless plan was confirmable")


# -- (b) the true price is checked after create ----------------------------
def _up_with_created_pod(tmp, cost_per_hr, spec=None):
    """Drive `up` to completion with a stubbed create returning a given rate.

    `_wait_running` is stubbed out: this is about the price check, which
    happens before any SSH work.
    """
    created = {"id": "pod-1", "name": "oneground-session-x",
               "costPerHr": cost_per_hr, "desiredStatus": "RUNNING"}
    t = _transport({"/pods": created, "/pods/pod-1": created})
    orig_wait, orig_stdin = cli._wait_running, sys.stdin
    cli._wait_running = lambda *a, **k: (_ for _ in ()).throw(
        sshx.SshError("stubbed: no ssh in this test"))
    sys.stdin = _Tty("y\n")
    try:
        code, out, _ = _run_cli(["up", spec or _spec_file(tmp)], t, tmp)
    finally:
        cli._wait_running, sys.stdin = orig_wait, orig_stdin
    deleted = [c for c in t.calls if c[0] == "DELETE"]
    return code, out, t, deleted


# ------------------------------- nothing after the create may leave a pod alive
def _up_failing_at(tmp, where, exc, spec=None):
    """Drive `up` to a created pod, then make one post-create step raise.

    Returns (exit code, output, DELETE calls, recorded finish reasons).
    """
    # publicIp and the 22 mapping are what `_wait_running` waits for; without
    # them it polls until boot_timeout instead of reaching the step under test.
    created = {"id": "pod-1", "name": "oneground-session-x",
               "costPerHr": 0.72, "desiredStatus": "RUNNING",
               "publicIp": "10.0.0.1", "portMappings": {"22": 44089}}
    t = _transport({"/pods": created, "/pods/pod-1": created})
    orig = getattr(cli, where)
    orig_stdin = sys.stdin
    # The readiness probe is real network work against a pod that does not
    # exist, and it is not what any of these tests is about. Stubbed unless
    # the test is deliberately failing at that step.
    orig_ready = cli._wait_ssh_ready

    def boom(*a, **kw):
        raise exc

    setattr(cli, where, boom)
    if where != "_wait_ssh_ready":
        cli._wait_ssh_ready = lambda *a, **k: {"attempts": 1,
                                               "waited_seconds": 0.0}
    sys.stdin = _Tty("y\n")
    try:
        code, out, _ = _run_cli(["up", spec or _spec_file(tmp)], t, tmp)
    finally:
        setattr(cli, where, orig)
        cli._wait_ssh_ready = orig_ready
        sys.stdin = orig_stdin
    deleted = [c for c in t.calls if c[0] == "DELETE"]
    reasons = [r.get("finished_because") for r in statemod.load_all(tmp)]
    return code, out, deleted, reasons


def test_an_input_upload_timeout_terminates_the_pod_synthetic():
    """Session 20260909-202938 exactly: the upload timed out and `up` exited
    telling the developer to run `down` themselves."""
    with tempfile.TemporaryDirectory() as tmp:
        code, out, deleted, reasons = _up_failing_at(
            tmp, "_sync_and_start",
            sshx.SshError("timed out after 120s: ssh -p 44089"))
        assert code == 1, out
        assert deleted, "the pod was left running after an upload timeout"
        assert reasons == ["failed-after-create"], reasons
        # And it must not tell the developer to do what it just did.
        assert "still billing" not in out, out


def test_any_post_create_exception_terminates_the_pod_synthetic():
    """The brief's acceptance test, over every post-create step and several
    exception types -- including the ones nobody anticipated, which is the
    only class this guarantee exists for."""
    cases = [
        ("_wait_running", sshx.SshError("no ssh endpoint")),
        ("_wait_running", RuntimeError("something nobody predicted")),
        ("_sync_and_start", sshx.SshError("timed out: scp -P 44089")),
        ("_sync_and_start", OSError("local disk full while packing inputs")),
        ("_sync_and_start", ValueError("a bug in oneground itself")),
        ("_await_first_log", MemoryError("out of memory")),
    ]
    for where, exc in cases:
        with tempfile.TemporaryDirectory() as tmp:
            code, out, deleted, reasons = _up_failing_at(tmp, where, exc)
            assert code == 1, (where, exc, out)
            assert deleted, ("no DELETE after %s raised %r" % (where, exc), out)
            assert reasons == ["failed-after-create"], (where, exc, reasons)


def test_a_launch_failure_terminates_and_records_its_own_reason_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        code, out, deleted, reasons = _up_failing_at(
            tmp, "_sync_and_start",
            sshx.LaunchFailed("nothing started", returncode=14,
                              stderr="ONEGROUND_LAUNCH_FAIL not-running"))
        assert code == 1, out
        assert deleted, out
        assert reasons == ["launch-failed"], reasons
        rec = statemod.load_all(tmp)[0]
        assert rec["launch"]["returncode"] == 14, rec
        assert "not-running" in rec["launch"]["stderr"], rec


def test_a_keyboard_interrupt_after_create_terminates_the_pod_synthetic():
    """The pod does not care that a human changed their mind; it bills."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            code, out, deleted, reasons = _up_failing_at(
                tmp, "_sync_and_start", KeyboardInterrupt())
        except KeyboardInterrupt:
            # Re-raised on purpose -- but only after the terminate, which is
            # what the record proves.
            deleted = None
            reasons = [r.get("finished_because") for r in statemod.load_all(tmp)]
        assert reasons == ["interrupted"], reasons


def test_up_never_tells_the_developer_to_terminate_a_pod_it_could_terminate():
    """`up` printing "still billing, run down" is a bill with instructions.

    The one place that language is still allowed is the create that returned
    no pod id, because there is nothing to name in a DELETE.
    """
    src = open(os.path.join(os.path.dirname(os.path.abspath(cli.__file__)),
                            "cli.py"), encoding="utf-8").read()
    body = src[src.index("def cmd_up("):src.index("def _run_session(")]
    tail = src[src.index("def _run_session("):]
    tail = tail[:tail.index("\ndef ", 10)]
    for chunk, name in ((body, "cmd_up"), (tail, "_run_session")):
        for phrase in ("still running and still billing",
                       "oneground pod down %s     # terminate now"):
            assert phrase not in chunk, (name, phrase)


def test_true_price_6_percent_over_confirmed_terminates():
    with tempfile.TemporaryDirectory() as tmp:
        # confirmed max is 0.72; +6% = 0.7632
        code, out, t, deleted = _up_with_created_pod(tmp, 0.72 * 1.06)
        assert "PRICE OVER CONFIRMED" in out, out
        assert deleted, "a pod priced above the confirmation was not terminated"
        reasons = [r.get("finished_because") for r in statemod.load_all(tmp)]
        assert reasons == ["price-exceeded"], reasons
        assert code == 1


def test_true_price_4_percent_over_confirmed_does_not_terminate():
    with tempfile.TemporaryDirectory() as tmp:
        code, out, t, deleted = _up_with_created_pod(tmp, 0.72 * 1.04)
        assert "PRICE OVER CONFIRMED" not in out, out
        # It proceeds to the SSH phase, which this test stubs into failing.
        # Since every post-create failure terminates, "was there a DELETE" no
        # longer separates a price termination from any other -- the recorded
        # reason does, and that is what this test is actually about.
        reasons = [r.get("finished_because") for r in statemod.load_all(tmp)]
        assert "price-exceeded" not in reasons, reasons
        assert reasons == ["failed-after-create"], reasons


def test_true_rate_is_recorded_and_used_for_cost_not_the_quote():
    rec = {"started_at_epoch": time.time() - 3600,
           "usd_per_hr_confirmed": 0.72, "usd_per_hr_true": 0.90}
    assert statemod.effective_rate(rec) == 0.90
    assert abs(statemod.cost_so_far(rec) - 0.90) < 0.01
    # Falls back to the confirmed worst case, never to a floor.
    assert statemod.effective_rate({"usd_per_hr_confirmed": 0.72,
                                    "usd_per_hr_quoted_min": 0.34}) == 0.72


def test_unpriced_pod_is_terminated():
    with tempfile.TemporaryDirectory() as tmp:
        code, out, t, deleted = _up_with_created_pod(tmp, None)
        assert "couldn't-check" in out
        assert deleted, "a pod with no known price was left running"
        assert code == 1


# -- (c) max_usd refusal before create -------------------------------------
def test_max_usd_refused_before_create_at_the_true_worst_case():
    """4 h x $0.72 = $2.88. A max_usd of $2.00 must refuse.

    Under the 006b arithmetic (4 x $0.34 = $1.36) this plan looked affordable,
    which is the bug: the cap held by luck.
    """
    with tempfile.TemporaryDirectory() as tmp:
        spec = _spec_file(tmp, SPEC_YAML.replace("max_usd: 3.00",
                                                 "max_usd: 2.00"))
        t = _transport()
        orig = sys.stdin
        sys.stdin = _Tty("y\n")
        try:
            code, out, _ = _run_cli(["up", spec], t, tmp)
        finally:
            sys.stdin = orig
        assert code == 1
        assert "cap exceeded" in out
        assert not t.billable_calls(), "an over-budget pod was created"
        assert "$1.36" not in out, "the floor is still being budgeted with"


# -- (d) the watchdogs -----------------------------------------------------
class _FakeSsh:
    """Stands in for PodSsh so the watchdogs can be driven without a pod."""

    def __init__(self, sizes, finished=False):
        self.sizes = list(sizes)
        self._finished = finished
        self.host, self.port = "10.0.0.1", 22

    def log_size(self, remote_log):
        return self.sizes.pop(0) if self.sizes else None

    def run_is_finished(self, remote_log, marker="DONE"):
        return self._finished

    def wait_ready(self, timeout=None, probe=None, log=None, **kw):
        """Already up. A fake pod has no sshd to wait for, and modelling the
        wait here would only test the fake."""
        return {"attempts": 1, "waited_seconds": 0.0}


def _watch_with(tmp, sizes, finished=False, stall_minutes=None, sid="w1"):
    _seed_session(tmp, pod_id="pod-1", sid=sid, hours_ago=0.01)
    pod = {"id": "pod-1", "desiredStatus": "RUNNING", "costPerHr": 0.72}
    t = _transport({"/pods/pod-1": pod, "/pods": [pod]})
    fake = _FakeSsh(sizes, finished)
    orig_from_pod, orig_sleep = sshx.PodSsh.from_pod, cli.time.sleep
    sshx.PodSsh.from_pod = staticmethod(lambda pod, **kw: fake)
    cli.time.sleep = lambda s: None
    argv = ["watch", sid, "--interval", "0"]
    if stall_minutes is not None:
        argv += ["--stall-minutes", str(stall_minutes)]
    try:
        code, out, _ = _run_cli(argv, t, tmp)
    finally:
        sshx.PodSsh.from_pod = orig_from_pod
        cli.time.sleep = orig_sleep
    return code, out, [c for c in t.calls if c[0] == "DELETE"]


def test_watch_terminates_on_a_stalled_log():
    with tempfile.TemporaryDirectory() as tmp:
        # The log exists and never grows. stall_minutes 0.0001 -> immediate.
        code, out, deleted = _watch_with(tmp, [100] * 40, stall_minutes=0.0001)
        assert "STALLED" in out, out
        assert deleted, "a stalled run was not terminated"


def test_watch_terminates_when_the_log_never_appears():
    with tempfile.TemporaryDirectory() as tmp:
        # log_size None throughout: this is 006b attempt 1 exactly.
        code, out, deleted = _watch_with(tmp, [], stall_minutes=0.0001)
        assert "STALLED" in out, out
        assert deleted, "a pod with no run at all was not terminated"


def test_watch_does_not_terminate_a_log_that_is_growing():
    with tempfile.TemporaryDirectory() as tmp:
        # Growing every poll, and DONE on the first check -> finishes cleanly.
        code, out, deleted = _watch_with(tmp, [10, 20, 30, 40],
                                         finished=True, stall_minutes=0.0001)
        assert "STALLED" not in out, out
        assert "DONE seen" in out


def test_watch_terminates_at_max_usd_using_the_true_rate():
    with tempfile.TemporaryDirectory() as tmp:
        _seed_session(tmp, pod_id="pod-1", sid="spend", hours_ago=1.0)
        statemod.mark("spend", "running", tmp, usd_per_hr_true=0.72,
                      caps={"max_hours": 99, "max_usd": 0.50,
                            "max_concurrent": 1})
        pod = {"id": "pod-1", "desiredStatus": "RUNNING", "costPerHr": 0.72}
        t = _transport({"/pods/pod-1": pod, "/pods": [pod]})
        fake = _FakeSsh([10, 20, 30])
        orig_from_pod, orig_sleep = sshx.PodSsh.from_pod, cli.time.sleep
        sshx.PodSsh.from_pod = staticmethod(lambda pod, **kw: fake)
        cli.time.sleep = lambda s: None
        try:
            code, out, _ = _run_cli(["watch", "spend", "--interval", "0"],
                                    t, tmp)
        finally:
            sshx.PodSsh.from_pod = orig_from_pod
            cli.time.sleep = orig_sleep
        # 1 h x $0.72 = $0.72, over a max_usd of $0.50.
        assert "SPEND CAP REACHED" in out, out
        assert [c for c in t.calls if c[0] == "DELETE"], \
            "the spend cap did not terminate the pod"


def test_up_terminates_when_the_log_never_appears():
    """The no-run watchdog inside `up`, which is where 006b lost ten minutes."""
    with tempfile.TemporaryDirectory() as tmp:
        created = {"id": "pod-1", "costPerHr": 0.72, "desiredStatus": "RUNNING"}
        t = _transport({"/pods": created, "/pods/pod-1": created})
        fake = _FakeSsh([])           # log never appears
        orig = (cli._wait_running, cli._sync_and_start,
                sshx.PodSsh.from_pod, cli.time.sleep, sys.stdin)
        cli._wait_running = lambda *a, **k: created
        cli._sync_and_start = lambda *a, **k: None
        sshx.PodSsh.from_pod = staticmethod(lambda pod, **kw: fake)
        cli.time.sleep = lambda s: None
        sys.stdin = _Tty("y\n")
        try:
            code, out, _ = _run_cli(["up", _spec_file(tmp),
                                     "--log-timeout", "0"], t, tmp)
        finally:
            (cli._wait_running, cli._sync_and_start, sshx.PodSsh.from_pod,
             cli.time.sleep, sys.stdin) = orig
        assert "NO RUN" in out, out
        assert [c for c in t.calls if c[0] == "DELETE"], \
            "a pod with no run was left billing"
        assert code == 1


# -- (e) the provenance guard ----------------------------------------------
def test_provenance_warning_lists_the_files_the_tarball_does_not_carry():
    """006b's exact situation: 8 of 11 files replaced, 3 left local."""
    import tarfile
    with tempfile.TemporaryDirectory() as tmp:
        fx = os.path.join(tmp, "fixtures", "arxiv-smoke")
        os.makedirs(fx)
        carried = ["MANIFEST.sha256", "characterization.json",
                   "ground_truth.npy"]
        local_only = ["vectors.npy", "queries.npy", "sample.jsonl.zst"]
        for n in carried + local_only:
            with open(os.path.join(fx, n), "w", encoding="utf-8") as f:
                f.write(n)
        tarball = os.path.join(tmp, "small.tgz")
        with tarfile.open(tarball, "w:gz") as tf:
            for n in carried:
                tf.add(os.path.join(fx, n),
                       arcname="fixtures/arxiv-smoke/" + n)

        lines = cli.provenance_warning(tarball, tmp)
        text = "\n".join(lines)
        assert "PROVENANCE" in text, text
        for n in local_only:
            assert n in text, "%s not named as local: %s" % (n, text)
        for n in carried:
            assert ("    %s   <-" % n) not in text, \
                "%s is carried by the tarball and must not be flagged" % n
        assert "contradicted" in text


def test_provenance_warning_is_silent_when_the_tarball_carries_everything():
    import tarfile
    with tempfile.TemporaryDirectory() as tmp:
        fx = os.path.join(tmp, "fixtures", "arxiv-smoke")
        os.makedirs(fx)
        for n in ("MANIFEST.sha256", "characterization.json"):
            with open(os.path.join(fx, n), "w", encoding="utf-8") as f:
                f.write(n)
        tarball = os.path.join(tmp, "small.tgz")
        with tarfile.open(tarball, "w:gz") as tf:
            for n in ("MANIFEST.sha256", "characterization.json"):
                tf.add(os.path.join(fx, n),
                       arcname="fixtures/arxiv-smoke/" + n)
        assert cli.provenance_warning(tarball, tmp) == []


def test_provenance_warning_ignores_a_tarball_with_no_manifest():
    import tarfile
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "logs")
        os.makedirs(d)
        p = os.path.join(d, "a.log")
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")
        tarball = os.path.join(tmp, "t.tgz")
        with tarfile.open(tarball, "w:gz") as tf:
            tf.add(p, arcname="logs/a.log")
        assert cli.provenance_warning(tarball, tmp) == []


# ------------------------------------------ a dirty tree refuses, before create
#
# Task 011's first session cloned a repo without the task's own new files: a
# bundle carries commits, and the warning that should have caught it listed
# only modified tracked files. The pod was billing before anyone could read it.

def _git(tmp, *args):
    import subprocess
    return subprocess.run(["git", "-C", tmp, *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _repo(tmp):
    """A tiny real git repo with one commit."""
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@example.com")
    _git(tmp, "config", "user.name", "t")
    with open(os.path.join(tmp, "a.txt"), "w", encoding="utf-8") as f:
        f.write("one\n")
    _git(tmp, "add", "-A")
    _git(tmp, "commit", "-qm", "first")
    return tmp


def test_a_clean_tree_is_allowed_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _repo(tmp)
        assert cli.uncommitted_paths(tmp) == []
        assert cli.refuse_if_dirty(tmp, log=lambda *a: None) is True


def test_a_modified_file_makes_the_tree_dirty_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        _repo(tmp)
        with open(os.path.join(tmp, "a.txt"), "w", encoding="utf-8") as f:
            f.write("two\n")
        assert cli.uncommitted_paths(tmp), "a modified file was not detected"
        assert cli.refuse_if_dirty(tmp, log=lambda *a: None) is False


def test_an_UNTRACKED_file_makes_the_tree_dirty_synthetic():
    """The case that cost a pod: a brand new file is exactly what a new task
    adds, and it is the one the old warning missed."""
    with tempfile.TemporaryDirectory() as tmp:
        _repo(tmp)
        with open(os.path.join(tmp, "new_runner.sh"), "w",
                  encoding="utf-8") as f:
            f.write("echo hi\n")
        dirty = cli.uncommitted_paths(tmp)
        assert any("new_runner.sh" in d for d in dirty), dirty
        assert cli.refuse_if_dirty(tmp, log=lambda *a: None) is False


def test_a_gitignored_file_does_not_block_synthetic():
    """Scratch output that git ignores is not part of the repo and must not
    stop a session."""
    with tempfile.TemporaryDirectory() as tmp:
        _repo(tmp)
        with open(os.path.join(tmp, ".gitignore"), "w", encoding="utf-8") as f:
            f.write("scratch/\n")
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-qm", "ignore")
        os.makedirs(os.path.join(tmp, "scratch"))
        with open(os.path.join(tmp, "scratch", "out.txt"), "w",
                  encoding="utf-8") as f:
            f.write("x\n")
        assert cli.uncommitted_paths(tmp) == []
        assert cli.refuse_if_dirty(tmp, log=lambda *a: None) is True


def test_up_refuses_a_dirty_tree_BEFORE_creating_anything_synthetic():
    """The money-boundary property: the refusal must land before the create,
    and before the developer is even asked to confirm."""
    with tempfile.TemporaryDirectory() as tmp:
        _repo(tmp)
        spec = _spec_file(tmp)
        with open(os.path.join(tmp, "uncommitted.py"), "w",
                  encoding="utf-8") as f:
            f.write("# not committed\n")

        t = _transport()
        asked = {"prompted": False}
        orig_ask = confirm.ask_to_create

        def spy(*a, **kw):
            asked["prompted"] = True
            return orig_ask(*a, **kw)

        confirm.ask_to_create = spy
        orig_stdin, sys.stdin = sys.stdin, _Tty("y\n")
        try:
            code, out, _ = _run_cli(["up", spec], t, tmp)
        finally:
            confirm.ask_to_create = orig_ask
            sys.stdin = orig_stdin

        assert code == 1, "up did not refuse a dirty tree"
        assert "REFUSED" in out and "uncommitted" in out
        assert not t.billable_calls(), "a pod was created from a dirty tree"
        assert not asked["prompted"], (
            "the developer was asked to confirm a session that could not "
            "carry their code")


def test_the_refusal_has_no_override_flag_synthetic():
    parser = cli.build_parser()
    up = parser._subparsers._group_actions[0].choices["up"]
    for action in up._actions:
        for opt in action.option_strings:
            assert opt not in ("--dirty", "--allow-dirty", "--force",
                               "--skip-clean-check", "--no-verify-clean"), opt


# -------------------------------------------------------------------- live
@pytest.mark.live
def test_live_plan_against_the_real_api():
    """Read-only, and the only test that touches the network.

    Skipped without a key so a fresh clone runs green. It creates nothing: the
    client it builds has no confirmation token, so a create would raise.
    """
    if not os.environ.get("RUNPOD_API_KEY"):
        pytest.skip("RUNPOD_API_KEY not set; live test skipped")
    root = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    spec_path = os.path.join(root, "sessions", "arxiv-build.yaml")
    s = sessionmod.load(spec_path)
    c = api.RunPodClient()
    assert not c.create_allowed()
    p = planmod.resolve(c, s)
    assert p.data_center_id, "no datacenter resolved"
    assert p.usd_per_hr and p.usd_per_hr > 0, "no live price"
    assert p.volume["dataCenterId"] == p.data_center_id
    print("live plan: %s in %s at $%.2f/hr"
          % (p.gpu["display_name"], p.data_center_id, p.usd_per_hr))


# Skip exceptions to honour when running without pytest as the driver. When
# pytest is installed, `pytest.skip()` raises pytest's own Skipped rather than
# the shim's -- so the no-runner path has to know about both, or installing a
# test runner silently breaks running the tests without one.


# ===================================================================
# `volume: none` -- the datacenter is chosen, not derived (task 016c)
# ===================================================================
# EU-RO-1, where the vecbench volume lives, stopped offering anything this
# project can use: a $5.98/hr B200, over cap, and an AMD MI300X our cu130
# torch cannot run on. A session that needs no volume should not be pinned to
# that region's stock. These cover both placement rules and, as much as
# anything, that they stay separate.


class DcTransport:
    """A stubbed API answering both GraphQL queries the chooser makes.

    It dispatches on the request body rather than a call counter, and parses
    the alias->datacenter mapping out of the real query text, so a change to
    the query shape surfaces here as a failure rather than as a stub that
    quietly keeps agreeing.

    `table`    {datacenter_id: {gpu_display_name: (floor, stock)}}
    `globals_` {gpu_display_name: (type_id, securePrice, secureCloud)}
    """

    def __init__(self, table, globals_, listed=None):
        self.table = table
        self.globals = globals_
        self.listed = listed if listed is not None else sorted(table)
        self.calls = []
        self.queries = []

    def __call__(self, method, url, body, headers, timeout):
        self.calls.append((method, url, body))
        if "graphql" not in url:
            return {}
        q = (body or {}).get("query", "")
        self.queries.append(q)
        if "dataCenters" in q:
            return {"data": {"dataCenters": [
                {"id": d, "name": d, "location": "Test",
                 "storageSupport": True, "listed": d in self.listed}
                for d in sorted(self.table)]}}

        pairs = re.findall(
            r'(dc\d+):\s*lowestPrice\(input:\{gpuCount:1,\s*'
            r'dataCenterId:("(?:[^"\\]|\\.)*")\}\)', q)
        assert pairs, "the aliased price query did not match: %r" % q[:200]
        alias_dc = [(a, json.loads(d)) for a, d in pairs]

        types = []
        for name, (type_id, secure_price, secure_cloud) in self.globals.items():
            g = {"id": type_id, "displayName": name, "memoryInGb": 48,
                 "secureCloud": secure_cloud, "communityCloud": False,
                 "securePrice": secure_price, "communityPrice": None}
            for alias, dc in alias_dc:
                floor, stock = self.table.get(dc, {}).get(name, (None, None))
                g[alias] = {"uninterruptablePrice": floor,
                            "stockStatus": stock}
            types.append(g)
        return {"data": {"gpuTypes": types}}


DC_GLOBALS = {
    "RTX PRO 4500": ("NVIDIA RTX PRO 4500 Blackwell", 0.72, True),
    "RTX 4090": ("NVIDIA GeForce RTX 4090", 0.74, True),
    "B200": ("NVIDIA B200", 6.79, True),
}


def _anywhere_spec(tmp, **over):
    """The reference spec with `volume: none`, plus any overrides."""
    import yaml as _y
    d = _spec_data()
    d["volume"] = "none"
    d.update(over)
    p = os.path.join(tmp, "anywhere.yaml")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        _y.safe_dump(d, f, sort_keys=False)
    return p


def _resolve_anywhere(table, tmp, listed=None, globals_=None, **over):
    t = DcTransport(table, globals_ or DC_GLOBALS, listed=listed)
    c = api.RunPodClient(key=FAKE_KEY, transport=t)
    s = sessionmod.load(_anywhere_spec(tmp, **over))
    return planmod.resolve(c, s), t


# -------------------------------------------------------------- the schema
def test_volume_none_parses_as_no_volume():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_anywhere_spec(tmp))
    assert s.volume is None
    assert s.uses_volume is False


def test_an_explicit_yaml_null_is_also_no_volume():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_anywhere_spec(tmp, volume=None))
    assert s.volume is None and s.uses_volume is False


def test_the_word_none_is_matched_case_insensitively():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_anywhere_spec(tmp, volume="None"))
    assert s.volume is None


def test_a_named_volume_still_uses_a_volume():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
    assert s.volume == "vol-a" and s.uses_volume is True


def test_volume_is_still_a_required_key():
    """No silent default in either direction: a lost workspace and an
    unplaceable pod are both expensive."""
    import yaml as _y
    with tempfile.TemporaryDirectory() as tmp:
        d = _spec_data()
        d.pop("volume")
        p = os.path.join(tmp, "novol.yaml")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            _y.safe_dump(d, f, sort_keys=False)
        try:
            sessionmod.load(p)
        except sessionmod.SessionSpecError as e:
            assert "volume" in str(e)
            return
    raise AssertionError("a spec with no volume key was accepted")


# ----------------------------------------------------------- the placement
def test_the_cheapest_datacenter_offering_the_gpu_wins():
    table = {"EU-CZ-1": {"RTX PRO 4500": (0.50, "Low")},
             "US-KS-2": {"RTX PRO 4500": (0.34, "High")},
             "US-NC-1": {"RTX PRO 4500": (0.60, "Medium")}}
    with tempfile.TemporaryDirectory() as tmp:
        p, _t = _resolve_anywhere(table, tmp)
    assert p.data_center_id == "US-KS-2", p.data_center_id
    assert p.gpu["display_name"] == "RTX PRO 4500"
    assert p.usd_min == 0.34
    assert p.usd_max == 0.72          # the global list price, not the floor
    assert len(p.dc_candidates) == 3


def test_gpu_preference_order_beats_a_cheaper_second_choice():
    """The gpu list is a preference order, not a shortlist to price-shop. A
    cheaper region for a card the session did not ask for first is a
    different answer, not a better one."""
    table = {"EU-CZ-1": {"RTX 4090": (0.20, "High")},
             "US-KS-2": {"RTX PRO 4500": (0.90, "Low")}}
    with tempfile.TemporaryDirectory() as tmp:
        p, _t = _resolve_anywhere(table, tmp)
    assert p.gpu["display_name"] == "RTX PRO 4500", p.gpu["display_name"]
    assert p.data_center_id == "US-KS-2"


def test_it_falls_through_to_the_next_gpu_when_the_first_is_nowhere():
    table = {"EU-CZ-1": {"RTX 4090": (0.34, "Low")},
             "US-KS-2": {"B200": (5.98, "High")}}
    with tempfile.TemporaryDirectory() as tmp:
        p, _t = _resolve_anywhere(table, tmp)
    assert p.gpu["display_name"] == "RTX 4090"
    assert p.data_center_id == "EU-CZ-1"


def test_an_unlisted_datacenter_is_not_chosen():
    table = {"EU-CZ-1": {"RTX PRO 4500": (0.50, "Low")},
             "US-KS-2": {"RTX PRO 4500": (0.10, "High")}}
    with tempfile.TemporaryDirectory() as tmp:
        p, _t = _resolve_anywhere(table, tmp, listed=["EU-CZ-1"])
    assert p.data_center_id == "EU-CZ-1", p.data_center_id


def test_a_tie_is_broken_stably_by_datacenter_id():
    """Two `plan` runs must not silently move the pod between regions."""
    table = {"US-NC-1": {"RTX PRO 4500": (0.34, "High")},
             "EU-CZ-1": {"RTX PRO 4500": (0.34, "High")}}
    with tempfile.TemporaryDirectory() as tmp:
        first, _t = _resolve_anywhere(table, tmp)
        second, _t2 = _resolve_anywhere(table, tmp)
    assert first.data_center_id == "EU-CZ-1"
    assert second.data_center_id == first.data_center_id


def test_a_gpu_not_sold_on_this_cloud_is_not_chosen_anywhere():
    """The task 006b trap, now across regions: a floor without the cloud flag
    is the price of a machine nobody can be given."""
    g = dict(DC_GLOBALS)
    g["RTX PRO 4500"] = ("NVIDIA RTX PRO 4500 Blackwell", 0.72, False)
    table = {"EU-CZ-1": {"RTX PRO 4500": (0.34, "High"),
                         "RTX 4090": (0.40, "Low")}}
    with tempfile.TemporaryDirectory() as tmp:
        p, _t = _resolve_anywhere(table, tmp, globals_=g)
    assert p.gpu["display_name"] == "RTX 4090", p.gpu["display_name"]


def test_nothing_available_anywhere_refuses_and_says_where_it_looked():
    table = {"EU-CZ-1": {"B200": (5.98, "High")},
             "US-KS-2": {"B200": (6.10, "Low")}}
    with tempfile.TemporaryDirectory() as tmp:
        try:
            _resolve_anywhere(table, tmp)
        except planmod.PlanError as e:
            assert "any of the 2 listed datacenters" in str(e), str(e)
            assert "volume: none" in str(e)
            return
    raise AssertionError("an unavailable GPU list resolved")


def test_a_volume_less_session_makes_no_volume_lookup():
    table = {"EU-CZ-1": {"RTX PRO 4500": (0.34, "High")}}
    with tempfile.TemporaryDirectory() as tmp:
        _p, t = _resolve_anywhere(table, tmp)
    assert [u for _m, u, _b in t.calls if "networkvolume" in u.lower()] == []


def test_the_price_matrix_costs_one_graphql_call():
    """33 datacenters must not mean 33 round trips."""
    table = {"dc-%02d" % i: {"RTX PRO 4500": (0.30 + i / 100.0, "Low")}
             for i in range(12)}
    with tempfile.TemporaryDirectory() as tmp:
        _p, t = _resolve_anywhere(table, tmp)
    price_queries = [q for q in t.queries if "lowestPrice" in q]
    assert len(price_queries) == 1, len(price_queries)
    assert price_queries[0].count("lowestPrice") == 12


def test_resolving_without_a_volume_creates_nothing():
    table = {"EU-CZ-1": {"RTX PRO 4500": (0.34, "High")}}
    with tempfile.TemporaryDirectory() as tmp:
        _p, t = _resolve_anywhere(table, tmp)
    assert [(m, u) for m, u, _b in t.calls if api.is_billable(m, u)] == []


# --------------------------------------------------- the payload and render
def _anywhere_plan(tmp, table=None, **over):
    table = table or {"EU-CZ-1": {"RTX PRO 4500": (0.34, "High")},
                      "US-KS-2": {"RTX PRO 4500": (0.55, "Low")}}
    p, _t = _resolve_anywhere(table, tmp, **over)
    return p


def test_the_payload_omits_the_volume_keys_entirely():
    """Absent, not null: a mount path with no volume id describes a mount
    that does not exist."""
    with tempfile.TemporaryDirectory() as tmp:
        spec = _anywhere_plan(tmp).deploy_spec("20260911-test")
    assert "networkVolumeId" not in spec
    assert "volumeMountPath" not in spec
    assert spec["dataCenterIds"] == ["EU-CZ-1"]
    assert spec["containerDiskInGb"] == 20


def test_the_volume_payload_still_carries_both_keys():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        spec = planmod.resolve(_client(), s).deploy_spec("20260911-test")
    assert spec["networkVolumeId"] == VOLUME["id"]
    assert spec["volumeMountPath"] == "/workspace"


def test_render_names_the_chosen_datacenter_and_its_price():
    with tempfile.TemporaryDirectory() as tmp:
        text = _anywhere_plan(tmp).render()
    assert "volume     : none" in text
    assert "EU-CZ-1" in text
    assert "chosen by GPU availability" in text
    assert "<- chosen" in text
    assert "$0.72/hr" in text                     # confirmed at the top
    assert "datacenters offering RTX PRO 4500" in text


def test_render_says_the_mount_is_container_disk():
    with tempfile.TemporaryDirectory() as tmp:
        text = _anywhere_plan(tmp, disk_gb=60).render()
    assert "60 GB container disk" in text
    assert "not a volume" in text


def test_render_of_a_volume_session_is_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        text = planmod.resolve(_client(), s).render()
    assert "derived from the volume" in text
    assert "chosen by GPU availability" not in text


def test_the_cap_still_binds_without_a_volume():
    """The region became negotiable; the money boundary did not."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _anywhere_plan(tmp, caps={"max_hours": 10, "max_usd": 1.00,
                                      "max_concurrent": 1})
        try:
            p.check_cap()
        except planmod.PlanError as e:
            assert "cap exceeded" in str(e)
            return
    raise AssertionError("an over-cap volume-less plan was accepted")


def test_the_state_record_notes_there_was_no_volume():
    with tempfile.TemporaryDirectory() as tmp:
        rec = statemod.record_for(_anywhere_plan(tmp), "20260911-test", None)
    assert rec["volume"] is None
    assert rec["volume_id"] is None



# ===================================================================
# Waiting for sshd before the first real command (task 016d)
# ===================================================================
# Session 20260911-200558 (pod x514af1cflnw6m, volume: none) reached RUNNING,
# resolved its endpoint, and its first real command hung for the full 60 s and
# died having printed only the known-hosts line. RUNNING is the *container's*
# state; sshd was still starting. The pod billed for all of it and the session
# was torn down over a race that resolves itself in seconds.


class _Proc:
    """Just enough of subprocess.CompletedProcess for PodSsh._run's callers."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class RefusingSsh(sshx.PodSsh):
    """A pod whose sshd refuses the first `refusals` connections.

    Overrides `_run`, not `run`, so the real argv construction, the real
    `wait_ready` loop, the real backoff and the real deadline are all
    exercised. `mode` picks how it refuses:

        "refused"  -- connection refused, the ordinary "sshd not up yet"
        "timeout"  -- the connection hangs, which is what 20260911-200558 saw
    """

    def __init__(self, *a, refusals=0, mode="refused", **kw):
        super().__init__(*a, **kw)
        self.refusals = refusals
        self.mode = mode
        self.attempts = []              # the argv of every attempt

    def _run(self, cmd, timeout=None, check=True):
        self.attempts.append((list(cmd), timeout))
        if len(self.attempts) <= self.refusals:
            if self.mode == "timeout":
                raise sshx.SshError(
                    "timed out after %gs: %s" % (timeout or 0,
                                                 " ".join(cmd[:3])),
                    command=" ".join(cmd), stdout="", stderr="",
                    timed_out=True)
            return _Proc(255, "", "ssh: connect to host port: "
                                  "Connection refused")
        return _Proc(0, "", "")


class _Clock:
    """Monotonic time the test controls; `sleep` advances it."""

    def __init__(self):
        self.t = 1000.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, n):
        self.slept.append(n)
        self.t += n

    def tick(self, n):
        self.t += n


def _ready_ssh(refusals=0, mode="refused"):
    return RefusingSsh("1.2.3.4", 22222, refusals=refusals, mode=mode)


def test_ssh_ready_returns_immediately_when_sshd_is_up():
    ssh = _ready_ssh(refusals=0)
    clock = _Clock()
    out = ssh.wait_ready(sleep=clock.sleep, now=clock.now)
    assert out["attempts"] == 1, out
    assert clock.slept == []
    assert len(ssh.attempts) == 1


def test_ssh_ready_retries_until_sshd_accepts():
    ssh = _ready_ssh(refusals=3)
    clock = _Clock()
    out = ssh.wait_ready(sleep=clock.sleep, now=clock.now, log=lambda m: None)
    assert out["attempts"] == 4, out
    assert len(ssh.attempts) == 4
    # Three refusals, so three backoffs, taken from the front of the table.
    assert clock.slept == list(sshx.READY_BACKOFF_SECONDS[:3]), clock.slept


def test_ssh_ready_survives_a_hung_connection_not_just_a_refusal():
    """20260911-200558 hung rather than being refused; both must retry."""
    ssh = _ready_ssh(refusals=2, mode="timeout")
    clock = _Clock()
    out = ssh.wait_ready(sleep=clock.sleep, now=clock.now, log=lambda m: None)
    assert out["attempts"] == 3, out


def test_ssh_ready_logs_every_attempt():
    lines = []
    ssh = _ready_ssh(refusals=2)
    clock = _Clock()
    ssh.wait_ready(sleep=clock.sleep, now=clock.now, log=lines.append)
    text = "\n".join(lines)
    assert text.count("sshd not ready yet") == 2, text
    assert text.count("retrying in") == 2, text
    assert "ssh ready after 3 attempt(s)" in text, text


def test_ssh_ready_gives_up_at_the_deadline_and_says_what_it_tried():
    ssh = _ready_ssh(refusals=10_000)          # never comes up
    clock = _Clock()
    try:
        ssh.wait_ready(timeout=30, sleep=clock.sleep, now=clock.now,
                       log=lambda m: None)
    except sshx.SshNotReady as e:
        assert e.attempts >= 2, e.attempts
        assert e.waited <= 30 + max(sshx.READY_BACKOFF_SECONDS), e.waited
        assert "did not accept a connection within 30s" in str(e)
        assert "the container's state" in str(e)
        return
    raise AssertionError("a pod that never came up was reported ready")


def test_ssh_ready_never_overruns_its_deadline():
    """The wait exists to bound a race, so it must itself be bounded."""
    ssh = _ready_ssh(refusals=10_000)
    clock = _Clock()
    start = clock.now()
    try:
        ssh.wait_ready(timeout=60, sleep=clock.sleep, now=clock.now,
                       log=lambda m: None)
    except sshx.SshNotReady:
        pass
    assert clock.now() - start <= 60, clock.now() - start


def test_each_probe_is_bounded_well_below_the_whole_wait():
    """A probe that hangs for the full window teaches nothing and spends the
    budget the retry loop needs."""
    ssh = _ready_ssh(refusals=2)
    clock = _Clock()
    ssh.wait_ready(sleep=clock.sleep, now=clock.now, log=lambda m: None)
    for _cmd, timeout in ssh.attempts:
        assert timeout <= sshx.READY_PROBE_SECONDS, timeout
        assert timeout < sshx.READY_TIMEOUT_SECONDS


def test_the_probe_is_a_harmless_command():
    """`true` changes nothing, so a probe that half-succeeds cannot matter."""
    ssh = _ready_ssh(refusals=0)
    clock = _Clock()
    ssh.wait_ready(sleep=clock.sleep, now=clock.now)
    argv = ssh.attempts[0][0]
    assert argv[0] == "ssh"
    assert argv[-1] == "true", argv[-1]
    assert "root@1.2.3.4" in argv


# ------------------------------------------- what the session file records
def test_a_timed_out_command_is_recorded_in_full():
    """The gap 20260911-200558 fell into: the timeout path recorded neither
    the command nor the streams, so the record could not say what hung."""
    ssh = _ready_ssh(refusals=10_000, mode="timeout")
    clock = _Clock()
    try:
        ssh.wait_ready(timeout=30, sleep=clock.sleep, now=clock.now,
                       log=lambda m: None)
    except sshx.SshNotReady as e:
        d = e.as_dict()
        assert d["timed_out"] is True, d
        assert d["command"].startswith("ssh "), d["command"]
        assert d["command"].endswith("true"), d["command"]
        assert "attempts" in d and d["attempts"] >= 1
        assert "waited_seconds" in d
        return
    raise AssertionError("no SshNotReady raised")


class _FakeSubprocess:
    """Stands in for the `subprocess` name inside sshx.

    The name in sshx's namespace is rebound, not the real module mutated:
    patching `subprocess.run` process-wide also patches it for pytest and for
    every other test in this file, which is a wedge rather than a stub.
    """

    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self, run):
        self.run = run


def _with_fake_subprocess(run, fn):
    real = sshx.subprocess
    sshx.subprocess = _FakeSubprocess(run)
    try:
        return fn()
    finally:
        sshx.subprocess = real


def test_a_real_command_timeout_also_carries_its_command():
    """Not only the probe. Any ssh timeout now leaves the argv behind."""
    ssh = sshx.PodSsh("1.2.3.4", 22222)

    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))

    def body():
        try:
            ssh.run("bash corpora/run_fixture_build.sh", timeout=5)
        except sshx.SshError as e:
            assert e.timed_out is True
            assert "run_fixture_build.sh" in e.command, e.command
            assert e.as_dict()["command"].endswith("run_fixture_build.sh")
            return True
        return False

    assert _with_fake_subprocess(boom, body),         "a timed-out command raised nothing"


def test_an_exit_code_failure_carries_the_whole_command_too():
    ssh = sshx.PodSsh("1.2.3.4", 22222)

    def nonzero(cmd, **kw):
        return _Proc(3, "", "no such file")

    def body():
        try:
            ssh.run("stat /workspace/nope", timeout=5)
        except sshx.SshError as e:
            assert e.timed_out is False
            assert "/workspace/nope" in e.command, e.command
            return True
        return False

    assert _with_fake_subprocess(nonzero, body),         "a non-zero command raised nothing"


def test_ssh_not_ready_is_an_ssh_error():
    """So the `up` guard's `except sshx.SshError` cannot miss it."""
    assert issubclass(sshx.SshNotReady, sshx.SshError)



def test_up_terminates_and_records_the_command_when_ssh_never_comes_up():
    """The whole point, end to end: a pod that cannot be reached is stopped,
    and the record says what was tried rather than that something timed out.

    Session 20260911-200558 was terminated correctly but left a record whose
    entire evidence was a port number.
    """
    with tempfile.TemporaryDirectory() as tmp:
        exc = sshx.SshNotReady(
            "sshd did not accept a connection within 180s (7 attempt(s))",
            attempts=7, waited=180.0, timed_out=True,
            command="ssh -p 44089 -o BatchMode=yes root@10.0.0.1 true")
        code, out, deleted, reasons = _up_failing_at(
            tmp, "_wait_ssh_ready", exc)
        assert code == 1, out
        assert deleted, "a pod that could not be reached was left running"
        assert reasons == ["ssh-never-ready"], reasons

        rec = statemod.load_all(tmp)[0]
        assert rec["ssh_ready"] is False, rec
        err = rec["ssh_error"]
        assert err["command"].endswith("true"), err["command"]
        assert err["attempts"] == 7, err
        assert err["waited_seconds"] == 180.0, err
        assert err["timed_out"] is True, err
        assert "SSH NEVER CAME UP" in out, out


def test_a_successful_readiness_wait_is_recorded_too():
    """Not only failures. How long sshd took is the number that says whether
    the window is the right size."""
    with tempfile.TemporaryDirectory() as tmp:
        code, out, deleted, reasons = _up_failing_at(
            tmp, "_sync_and_start",
            sshx.SshError("stubbed: not what this test is about"))
        assert code == 1, out
        rec = statemod.load_all(tmp)[0]
        assert rec["ssh_ready"] == {"attempts": 1, "waited_seconds": 0.0}, rec


def test_any_ssh_failure_after_readiness_records_its_command():
    """The generic guard, not only the probe: an scp that times out during the
    sync leaves the argv in the record."""
    with tempfile.TemporaryDirectory() as tmp:
        exc = sshx.SshError(
            "timed out after 120s: scp -P 44089",
            command="scp -P 44089 bundle root@10.0.0.1:/workspace/x.bundle",
            timed_out=True)
        code, out, deleted, reasons = _up_failing_at(
            tmp, "_sync_and_start", exc)
        assert code == 1, out
        assert reasons == ["failed-after-create"], reasons
        rec = statemod.load_all(tmp)[0]
        assert rec["last_ssh"]["timed_out"] is True, rec["last_ssh"]
        assert "x.bundle" in rec["last_ssh"]["command"], rec["last_ssh"]



# ===================================================================
# Falling through candidates when a create is refused (task 016e)
# ===================================================================
# Three creates in a row were refused -- EU-CZ-1 RTX 4090 twice, EU-RO-1
# RTX PRO 4500 once, all "Low" stock -- and each one ended the session and
# made a human retype 'y' for a machine they had already agreed to pay for.
# `ask_to_create` shows a rate and a total and names no GPU, so what was
# authorised is a ceiling, not a card.

NO_CAPACITY = ("POST https://rest.runpod.io/v1/pods -> HTTP 500 "
               '{"error":"There are no instances currently available '
               'with the requested specifications."}')


def _cand(dc, name, usd_max, usd_min=None, stock="Low"):
    return {"data_center_id": dc,
            "gpu": {"id": "NVIDIA " + name, "display_name": name},
            "usd_max": usd_max,
            "usd_min": usd_min if usd_min is not None else usd_max - 0.10,
            "stock": stock}


class _CreateStub:
    """A client whose first N creates are refused for want of capacity.

    Only `create_pod` is modelled: the fallthrough is the whole subject, and
    a real client would drag the guard and the transport in with it.
    """

    def __init__(self, refusals, error=None, fail_all_with=None):
        self.refusals = refusals
        self.error = error or NO_CAPACITY
        self.fail_all_with = fail_all_with
        self.specs = []

    def create_pod(self, spec):
        self.specs.append(spec)
        if self.fail_all_with is not None:
            raise self.fail_all_with
        if len(self.specs) <= self.refusals:
            raise api.PodApiError(self.error, status=500)
        return {"id": "pod-%d" % len(self.specs), "name": spec["name"]}


class _Plan:
    """Just the surface `_create_with_fallthrough` touches."""

    def __init__(self, candidates):
        self.deploy_candidates = candidates

    def candidates_within(self, ceiling):
        return planmod.Plan.candidates_within(self, ceiling)

    def deploy_spec(self, session_id, candidate=None):
        c = candidate or self.deploy_candidates[0]
        return {"name": "oneground-session-%s" % session_id,
                "gpuTypeIds": [c["gpu"]["id"]],
                "dataCenterIds": [c["data_center_id"]]}


def _token(usd_per_hr=0.84):
    return confirm.CreateAuthorization("s", usd_per_hr, 1.5, 2.50)


def _fallthrough(candidates, refusals, ceiling=0.84, **kw):
    stub = _CreateStub(refusals, **kw)
    lines = []
    pod, chosen = cli._create_with_fallthrough(
        stub, _Plan(candidates), "20260911-test", _token(ceiling),
        log=lines.append)
    return pod, chosen, stub, "\n".join(lines)


# ---------------------------------------------------------- the happy path
def test_the_first_candidate_is_used_when_capacity_exists():
    cands = [_cand("EU-CZ-1", "RTX 4090", 0.74),
             _cand("US-KS-2", "L4", 0.43)]
    pod, chosen, stub, _log = _fallthrough(cands, refusals=0)
    assert pod["id"] == "pod-1"
    assert chosen is cands[0]
    assert len(stub.specs) == 1


def test_it_falls_through_to_the_next_candidate_without_re_prompting():
    """The three refusals that prompted this, then a card that is free."""
    cands = [_cand("EU-CZ-1", "RTX 4090", 0.74),
             _cand("EU-RO-1", "RTX PRO 4500", 0.72),
             _cand("US-KS-2", "L4", 0.43)]
    pod, chosen, stub, log = _fallthrough(cands, refusals=2)
    assert pod is not None
    assert chosen is cands[2], chosen["gpu"]["display_name"]
    assert len(stub.specs) == 3
    # No prompt was reached: the only stdin reader in the package is
    # confirm.ask_to_create, and this never calls it.
    assert "attempt 1/3" in log and "attempt 3/3" in log
    assert log.count("no instances available") == 2, log


def test_each_attempt_is_logged_with_its_card_region_and_rate():
    cands = [_cand("EU-CZ-1", "RTX 4090", 0.74),
             _cand("US-KS-2", "L4", 0.43)]
    _pod, _chosen, _stub, log = _fallthrough(cands, refusals=1)
    assert "RTX 4090 in EU-CZ-1 at up to $0.74/hr" in log, log
    assert "L4 in US-KS-2 at up to $0.43/hr" in log, log
    assert "created on L4 in US-KS-2" in log, log


def test_the_fallback_spec_names_the_fallback_card_and_region():
    cands = [_cand("EU-CZ-1", "RTX 4090", 0.74),
             _cand("US-KS-2", "L4", 0.43)]
    _pod, _chosen, stub, _log = _fallthrough(cands, refusals=1)
    assert stub.specs[0]["gpuTypeIds"] == ["NVIDIA RTX 4090"]
    assert stub.specs[0]["dataCenterIds"] == ["EU-CZ-1"]
    assert stub.specs[1]["gpuTypeIds"] == ["NVIDIA L4"]
    assert stub.specs[1]["dataCenterIds"] == ["US-KS-2"]


# ------------------------------------------------------------- the ceiling
def test_a_candidate_above_the_confirmed_rate_is_never_tried():
    """The developer authorised a price. A dearer card is outside it."""
    cands = [_cand("EU-CZ-1", "RTX 4090", 0.74),
             _cand("US-WA-1", "RTX PRO 6000", 2.09),      # over the ceiling
             _cand("US-KS-2", "L4", 0.43)]
    pod, chosen, stub, log = _fallthrough(cands, refusals=1, ceiling=0.84)
    assert chosen is cands[2], chosen["gpu"]["display_name"]
    tried = [s["gpuTypeIds"][0] for s in stub.specs]
    assert "NVIDIA RTX PRO 6000" not in tried, tried
    assert "above the $0.84/hr already confirmed" in log, log
    assert "needs a new 'y'" in log


def test_a_candidate_exactly_at_the_ceiling_is_inside_it():
    cands = [_cand("EU-CZ-1", "RTX 4090", 0.74),
             _cand("US-WA-1", "RTX 6000 Ada", 0.84)]      # == the ceiling
    pod, chosen, _stub, _log = _fallthrough(cands, refusals=1, ceiling=0.84)
    assert pod is not None
    assert chosen is cands[1]


def test_everything_refused_creates_nothing_and_says_so():
    cands = [_cand("EU-CZ-1", "RTX 4090", 0.74),
             _cand("US-KS-2", "L4", 0.43)]
    pod, chosen, stub, log = _fallthrough(cands, refusals=99)
    assert pod is None and chosen is None
    assert len(stub.specs) == 2
    assert "NO CAPACITY" in log
    assert "Nothing was created and nothing is billing." in log


def test_dearer_untried_candidates_are_named_when_everything_else_fails():
    """So the developer knows a second 'y' would have somewhere to go."""
    cands = [_cand("EU-CZ-1", "RTX 4090", 0.74),
             _cand("US-WA-1", "RTX PRO 6000", 2.09)]
    _pod, _chosen, _stub, log = _fallthrough(cands, refusals=99, ceiling=0.84)
    assert "1 dearer candidate(s) were not tried" in log, log
    assert "RTX PRO 6000 $2.09/hr" in log, log
    assert "Re-run `up`" in log


# ------------------------------- only this one error may be retried
def test_any_other_create_failure_is_not_retried():
    """A create that failed for another reason may have made a pod this
    process never saw the id of. Retrying it could put two pods behind one
    'y', so it propagates."""
    cands = [_cand("EU-CZ-1", "RTX 4090", 0.74),
             _cand("US-KS-2", "L4", 0.43)]
    other = api.PodApiError("POST /pods -> HTTP 502 bad gateway", status=502)
    try:
        _fallthrough(cands, refusals=0, fail_all_with=other)
    except api.PodApiError as e:
        assert "502" in str(e)
        return
    raise AssertionError("a non-capacity failure was swallowed and retried")


def test_is_no_capacity_matches_runpods_phrase_and_little_else():
    assert api.is_no_capacity(api.PodApiError(NO_CAPACITY, status=500))
    assert api.is_no_capacity(
        api.PodApiError("There are no instances available", status=500))
    for other in ["HTTP 502 bad gateway",
                  "HTTP 500 internal server error",
                  "HTTP 401 unauthorized",
                  "timed out"]:
        assert not api.is_no_capacity(api.PodApiError(other)), other


# --------------------------------------------- what the plan hands it
def test_the_plan_orders_candidates_by_preference_then_price():
    table = {"EU-CZ-1": {"RTX PRO 4500": (0.50, "Low"),
                         "RTX 4090": (0.20, "High")},
             "US-KS-2": {"RTX PRO 4500": (0.34, "High")}}
    with tempfile.TemporaryDirectory() as tmp:
        p, _t = _resolve_anywhere(table, tmp)
    order = [(c["data_center_id"], c["gpu"]["display_name"])
             for c in p.deploy_candidates]
    # First choice first, cheapest region of it first; the second choice
    # follows even though it is cheaper than either.
    assert order == [("US-KS-2", "RTX PRO 4500"),
                     ("EU-CZ-1", "RTX PRO 4500"),
                     ("EU-CZ-1", "RTX 4090")], order


def test_a_volume_session_falls_through_cards_in_its_own_region():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(
            tmp, SPEC_YAML.replace('["RTX PRO 4500", "RTX 4090"]',
                                   '["RTX PRO 4500", "L4"]')))
        p = planmod.resolve(_client(), s)
    order = [(c["data_center_id"], c["gpu"]["display_name"])
             for c in p.deploy_candidates]
    assert order == [("EU-RO-1", "RTX PRO 4500"), ("EU-RO-1", "L4")], order


def test_candidates_within_excludes_the_dearer_ones():
    cands = [_cand("a", "cheap", 0.43), _cand("b", "dear", 2.09)]
    p = _Plan(cands)
    assert p.candidates_within(0.84) == [cands[0]]
    assert p.candidates_within(2.09) == cands
    assert p.candidates_within(None) == []


def test_the_session_lists_the_slower_cards_after_the_fast_ones():
    """Not synthetic: the shipped session, widened after the refusals."""
    import yaml as _y
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "..", "sessions",
                        "stackexchange-build.yaml")
    with open(path, encoding="utf-8") as f:
        spec = _y.safe_load(f)
    gpus = spec["gpu"]
    for name in ("L4", "RTX A5000", "RTX A4000", "RTX 3090", "A40"):
        assert name in gpus, name
    assert gpus.index("RTX 4090") < gpus.index("L4"), gpus
    assert gpus[-5:] == ["L4", "RTX A5000", "RTX A4000", "RTX 3090", "A40"]



def test_the_record_names_the_card_that_was_actually_deployed():
    """A fallback must not leave `status` and `watch` reporting a card the
    account never had."""
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        p = planmod.resolve(_client(), s)
        fallback = _cand("US-KS-2", "L4", 0.43)
        rec = statemod.record_for(p, "20260911-test", "pod-9", None, fallback)
    assert rec["gpu"] == "L4", rec["gpu"]
    assert rec["data_center_id"] == "US-KS-2"
    assert rec["usd_per_hr_confirmed"] == 0.43
    assert rec["planned_gpu"] == "RTX PRO 4500", rec["planned_gpu"]


def test_the_record_is_unchanged_when_the_plan_was_used_as_planned():
    with tempfile.TemporaryDirectory() as tmp:
        s = sessionmod.load(_spec_file(tmp))
        p = planmod.resolve(_client(), s)
        rec = statemod.record_for(p, "20260911-test", "pod-9")
    assert rec["gpu"] == "RTX PRO 4500"
    assert rec["data_center_id"] == "EU-RO-1"
    assert rec["planned_gpu"] is None, rec["planned_gpu"]

_SKIP_EXCEPTIONS = [_Skipped]
try:
    from _pytest.outcomes import Skipped as _PytestSkipped

    _SKIP_EXCEPTIONS.append(_PytestSkipped)
except ImportError:                                       # pragma: no cover
    pass
_SKIP_EXCEPTIONS = tuple(_SKIP_EXCEPTIONS)


def _main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    passed = failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print("ok    %s" % name)
        except _SKIP_EXCEPTIONS as e:
            skipped += 1
            print("skip  %s (%s)" % (name, e))
        except Exception as e:
            failed += 1
            print("FAIL  %s: %s: %s" % (name, type(e).__name__, e))
    print("\n%d passed, %d failed, %d skipped" % (passed, failed, skipped))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())


# ------------------------------------------------- session 20260911-001111
# A clone that "failed" and had not. The bundle was fine, every one of the 381
# files checked out, and the command that exited 1 was a `git checkout master`
# of a branch renamed to `main` in task 014 -- which the error message had
# already thrown away.

def test_tail_lines_collapses_carriage_return_progress_synthetic():
    """The reason the real error was lost.

    Git writes clone progress as ONE line with carriage returns, so the first
    800 characters of a failed clone are always progress and a head-truncation
    lands mid-word -- the captured output ended at `Upda`. The tail, with
    progress collapsed, is where the error actually is.
    """
    # A realistic stream. Git emits one progress update per file, all on ONE
    # logical line separated by carriage returns; 381 files is about 12 KB.
    progress = "".join("Updating files: %3d%% (%d/381)\r" % (i * 100 // 381, i)
                       for i in range(1, 382))
    raw = ("Cloning into '/workspace/oneground'...\n"
           + progress
           + "Updating files: 100% (381/381), done.\n"
           + "error: pathspec 'master' did not match any file(s) "
             "known to git\n")

    # Why the error was lost: the first 800 characters of a 12 KB stream are
    # entirely progress, and the cut lands inside a word.
    assert len(raw) > 8000
    assert "error:" not in raw[:800]
    assert "Updating files" in raw[:800]

    got = sshx.tail_lines(raw, 20)
    assert got.splitlines()[-1].startswith("error: pathspec 'master'")
    # 381 progress fragments collapse to one line, in their final state
    assert got.count("Updating files") == 1, got
    assert "\r" not in got
    assert len(got.splitlines()) == 3, got


def test_tail_lines_keeps_only_the_last_n_synthetic():
    text = "\n".join("line %d" % i for i in range(100))
    got = sshx.tail_lines(text, 5).splitlines()
    assert got == ["line 95", "line 96", "line 97", "line 98", "line 99"]


def test_clone_command_checks_out_no_branch_by_default_synthetic():
    """`git clone` from a bundle already checks out the bundle's HEAD.

    The old form appended `git checkout master` unconditionally. Even while
    that worked it was wrong: a task branch's session would clone at the
    task's HEAD and then move to the default branch, so the pod measured code
    the task had not written.
    """
    cmd = sshx.clone_command("/workspace/oneground.bundle",
                             "/workspace/oneground")
    assert "git clone /workspace/oneground.bundle /workspace/oneground" in cmd
    assert "git checkout" not in cmd
    assert "master" not in cmd


def test_clone_command_asserts_the_commit_it_was_given_synthetic():
    sha = "6fdebcb693c6066936b31212229d40f979059299"
    cmd = sshx.clone_command("/b", "/d", commit=sha)
    assert sha in cmd
    assert "git rev-parse HEAD" in cmd
    # It must FAIL, not warn, on the wrong commit: a pod running code nobody
    # chose produces measurements rather than errors.
    assert "exit 1" in cmd


def test_clone_command_still_takes_an_explicit_branch_synthetic():
    cmd = sshx.clone_command("/b", "/d", branch="some-branch")
    assert "git checkout some-branch" in cmd


def test_ssh_error_carries_both_streams_synthetic():
    e = sshx.SshError("boom", returncode=1, stdout="out", stderr="err",
                      command="ssh x")
    assert e.stdout == "out" and e.stderr == "err"
    assert e.returncode == 1 and e.command == "ssh x"


# ------------------------------------------------- session 20260911-174648
# /workspace is a NETWORK VOLUME: root can write there, nothing can chown
# there, and postgres cannot create a file there itself. Three of this task's
# six pod faults were that one surface, each fix trading one symptom for
# another. These pin the shape that finally worked, because the script is
# shell and nothing else type-checks it.

def _pod_script():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))
    with open(os.path.join(root, "corpora", "run_verify_pod.sh"),
              encoding="utf-8") as f:
        return [ln for ln in f.read().split("\n")]


def _live(lines):
    """Non-comment, non-blank lines. Comments quote the failures verbatim, so
    a naive grep matches its own history and never goes green."""
    out = []
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#"):
            out.append(ln)
    return out


def test_the_pod_script_never_chowns_the_network_volume():
    """Not synthetic: the shipped script.

    `chown: changing ownership of '/workspace/postgres.log': Operation not
    permitted` killed session 20260911-174648 under `set -e`, 23 seconds after
    the install finally succeeded.
    """
    offenders = [ln for ln in _live(_pod_script())
                 if "chown" in ln and "/workspace" in ln]
    assert not offenders, (
        "chown against the network volume: " + "; ".join(offenders))


def test_every_chown_in_the_pod_script_targets_a_directory_postgres_owns():
    for ln in _live(_pod_script()):
        if "chown" not in ln:
            continue
        assert ("$PGDATA" in ln or "$PG_LOG" in ln
                or "/var/lib/postgresql" in ln), \
            f"chown at an unvetted path: {ln.strip()}"


def test_postgres_writes_its_own_log_off_the_volume():
    """pg_ctl's -l file is created by the postgres process, not the calling
    shell, so it cannot live on /workspace at all."""
    live = _live(_pod_script())
    pg_ctl = [ln for ln in live if "pg_ctl" in ln and "-l " in ln]
    assert pg_ctl, "no pg_ctl start line found"
    for ln in pg_ctl:
        assert "$PG_LOG" in ln, f"pg_ctl -l is not $PG_LOG: {ln.strip()}"
        assert "-l /workspace" not in ln, ln.strip()
    assigns = [ln for ln in live if ln.strip().startswith("PG_LOG=")]
    assert assigns, "PG_LOG is never assigned"
    for ln in assigns:
        assert "/var/lib/postgresql" in ln, ln.strip()


def test_the_server_log_copy_is_best_effort():
    """A server log that cannot be copied must never fail a run whose
    measurements are already taken and already in the tarball."""
    text = "\n".join(_pod_script())
    i = text.index('if [ -n "${PG_LOG:-}" ]')
    block = text[i:i + 600]
    assert "cp " in block and "/workspace/postgres.log" in block
    assert "2>/dev/null" in block, "the copy must swallow its own error"
    assert "else" in block, "a failed copy must say so rather than be silent"
    # and it must not be the last word on the run
    assert "exit 1" not in block


# ---------- one quoting function, both sites (task 017b)
# Task 011 quoted the LAUNCH export and proved it with a round trip through a
# real shell. `_setup_script` had its own unquoted copy, untested, and session
# 20260912-165508 died on it at line 5:
#
#   bash: line 5: export: 'corpora/restart_engine.sh': not a valid identifier
#   bash: line 5: export: '{engine}': not a valid identifier
#
# The value was well-formed; the export was not.

TRICKY_ENV = {
    # The value that actually broke it: spaces and braces.
    "ONEGROUND_ENGINE_RESTART_COMMAND": "bash corpora/restart_engine.sh {engine}",
    "ONEGROUND_NOTE": "two words",
    "ONEGROUND_Q": "a'b",
    "ONEGROUND_BRACE": "{engine} ${NOPE} `false` $(false)",
}


def _setup_spec(env):
    class _S:
        pass
    s = _S()
    s.remote_repo = "/workspace/oneground"
    s.env = dict(env)
    return s


def test_the_setup_export_is_quoted_at_all_synthetic():
    """The regression, asserted on the text before any shell is involved."""
    script = cli._setup_script(_setup_spec(TRICKY_ENV))
    assert ("export ONEGROUND_ENGINE_RESTART_COMMAND="
            "'bash corpora/restart_engine.sh {engine}'") in script, script


def test_both_export_sites_use_the_one_function_synthetic():
    """A third unquoted copy is the way this comes back."""
    import inspect
    raw = "export " + "%s=%s"        # split, so this line is not itself a hit
    for fn in (cli._setup_script, sshx.build_start_command):
        src = inspect.getsource(fn)
        assert "export_lines" in src, fn.__name__
        assert raw not in src, (
            "%s builds its own export line instead of using export_lines"
            % fn.__name__)
    # And the shared function really does quote, rather than both sites
    # agreeing to call something that does not.
    assert sshx.export_lines({"A": "two words"}) == "export A='two words'"


def test_a_name_that_cannot_be_a_variable_is_refused_synthetic():
    """A value is quotable; a name is not. `export 'a b'=x` is a syntax
    error, so it has to be refused here rather than on a billing pod."""
    for bad in ("a b", "2LEGIT", "has-dash", "", "a;b", "{engine}"):
        with pytest.raises(ValueError):
            sshx.export_lines({bad: "x"})
    assert sshx.export_lines({"OK_1": "x"}) == "export OK_1=x"
    assert sshx.export_lines({}) == ""


def test_setup_env_values_survive_a_real_shell_synthetic():
    """The round trip, on the SETUP path this time.

    Task 011's round trip covered the launch only. This runs the setup
    script's own export block through a real shell and reads every value back,
    including the one that broke session 20260912-165508.
    """
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        bash = _bash_that_shares_this_filesystem(tmp)
        if bash is None:
            pytest.skip("no bash that can see this process's filesystem")
        # The export block exactly as _setup_script emits it.
        script = cli._setup_script(_setup_spec(TRICKY_ENV))
        exports = "\n".join(ln for ln in script.splitlines()
                            if ln.startswith("export "))
        probe = "\n".join(
            'printf "%s=[%s]\n" ' % (k, "%s") + '"$%s"' % k
            for k in sorted(TRICKY_ENV))
        r = subprocess.run([bash, "-c", "set -euo pipefail\n" + exports
                            + "\n" + probe],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=60)
        assert r.returncode == 0, (r.returncode, r.stderr)
        assert "not a valid identifier" not in r.stderr, r.stderr
        for k, v in sorted(TRICKY_ENV.items()):
            assert "%s=[%s]" % (k, v) in r.stdout, (k, v, r.stdout)


def test_launch_env_values_still_survive_after_the_refactor_synthetic():
    """The launch site kept its behaviour when the two were merged."""
    cmd = sshx.build_start_command(
        "/repo", "run.sh", "/tmp/x.log",
        env={"ONEGROUND_REQUIREMENTS": "requirements.smoke.yaml",
             "ONEGROUND_CONCURRENCY": "8"})
    assert "export ONEGROUND_REQUIREMENTS=requirements.smoke.yaml" in cmd
    assert "export ONEGROUND_CONCURRENCY=8" in cmd
    payload_start = cmd.index("nohup bash -c '") + len("nohup bash -c '")
    payload = cmd[payload_start:cmd.index("' >>", payload_start)]
    assert payload.index("cd /repo") < payload.index("export ")
    assert payload.rstrip().endswith("run.sh")


def test_the_setup_script_checks_the_marker_after_the_exports_synthetic():
    """Where the marker check sits relative to the exports is why session
    20260912-165508 never reached it: the script died in its own env block,
    so `running setup ...` in the local log said nothing about which venv
    path ran. Pinned so the ordering is deliberate rather than incidental."""
    script = cli._setup_script(_setup_spec(TRICKY_ENV))
    assert script.index("export ONEGROUND_") < script.index(
        "/opt/oneground-image/BAKED")
    # And the script, not the caller, is what reports which path it took.
    assert "baked image detected" in script


# ---------------- the setup-time split (task 017f)
# Three sessions reported it couldnt_check -- not because it is hard to
# measure, but because nothing wrote down when each phase began and ended, so
# the only honest answer was one total from `created_at` to the run's first
# log line. The baked image was meant to be judged on exactly this number.

def _session_rec(tmp, **extra):
    import json
    d = os.path.join(tmp, ".oneground", "sessions")
    os.makedirs(d, exist_ok=True)
    rec = {"id": "20260913-000000", "state": "running", "pod_id": "p1",
           "started_at_epoch": 1000.0}
    rec.update(extra)
    with open(os.path.join(d, rec["id"] + ".json"), "w",
              encoding="utf-8") as f:
        json.dump(rec, f)
    return rec["id"]


def test_phase_marks_from_two_writers_do_not_erase_each_other():
    """`up` stamps RUNNING and `_sync_and_start` stamps the rest.

    A plain mark(phase_times={...}) replaces the whole dict, so each writer
    would drop the other's marks and the record would keep whichever ran last
    -- a field added to answer a question, answering none of it.
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        sid = _session_rec(tmp)
        statemod.mark_phase(sid, "running_at", tmp, when=1010.0)
        statemod.mark_phase(sid, "sync_start", tmp, when=1020.0)
        statemod.mark_phase(sid, "sync_end", tmp, when=1050.0)
        rec = statemod.load(sid, tmp)
        assert set(rec["phase_times"]) == {"running_at", "sync_start",
                                           "sync_end"}, rec["phase_times"]
        assert rec["phase_times"]["running_at"] == 1010.0


def test_the_setup_split_reports_each_phase_against_the_previous():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        sid = _session_rec(tmp)
        for name, when in (("running_at", 1030.0), ("sync_start", 1035.0),
                           ("sync_end", 1065.0), ("upload_end", 1075.0),
                           ("setup_end", 1080.0), ("launch_start", 1081.0)):
            statemod.mark_phase(sid, name, tmp, when=when)
        split = statemod.setup_split(statemod.load(sid, tmp))
        secs = dict((lbl, s) for lbl, s in split)
        assert len(split) == 6, split
        # create(1000) -> RUNNING(1030) is provisioning, not ours
        assert secs["RunPod provisioning: create to RUNNING"] == 30.0
        assert secs["waiting for sshd"] == 5.0
        assert secs["repo sync: bundle, scp, clone on the pod"] == 30.0
        assert secs["uploading the session's declared inputs"] == 10.0
        assert sum(s for _, s in split) == 81.0


def test_a_session_without_marks_has_no_split_rather_than_zeros():
    """Sessions recorded before 017f. None, not a fabricated breakdown --
    deriving one from created_at is the quoted boundary three reports
    declined to give."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        sid = _session_rec(tmp)
        assert statemod.setup_split(statemod.load(sid, tmp)) is None
    assert statemod.setup_split({}) is None
    assert statemod.setup_split(None) is None


def test_a_partial_split_reports_only_the_phases_it_has():
    """A run that died mid-setup still says how far it got."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        sid = _session_rec(tmp)
        statemod.mark_phase(sid, "running_at", tmp, when=1030.0)
        statemod.mark_phase(sid, "sync_start", tmp, when=1035.0)
        split = statemod.setup_split(statemod.load(sid, tmp))
        assert len(split) == 2, split
        assert split[0][1] == 30.0 and split[1][1] == 5.0


def test_run_session_stamps_running_and_sync_stamps_the_rest():
    """The marks the code actually writes, not just the helper's arithmetic.

    Asserted on the source: both call sites must go through mark_phase, or
    the merge guarantee above is irrelevant.
    """
    import inspect
    up_src = inspect.getsource(cli._run_session)
    assert 'mark_phase(session_id, "running_at"' in up_src, up_src[:200]
    sync_src = inspect.getsource(cli._sync_and_start)
    for name in ("sync_start", "sync_end", "upload_end", "setup_end",
                 "launch_start"):
        assert 'phase("%s")' % name in sync_src, name
    assert "state.mark_phase" in sync_src


# -- task 030b: an unexpected stop fetches like every other exit path --------

class _FakeSshWithFiles(_FakeSsh):
    """_FakeSsh plus the two calls `_fetch_outputs` makes on each output.

    Kept separate from `_FakeSsh` so the watchdog tests that predate task 030b
    keep exercising exactly what they did before.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fetched = []

    def exists(self, remote):
        return True

    def get(self, remote, local, timeout=None):
        self.fetched.append(remote)
        pathlib.Path(local).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(local).write_bytes(b"x")


def _watch_with_status(tmp, status, sid="stopped1", ssh_raises=False,
                       outputs=None):
    """Drive `watch` against a pod whose desiredStatus is not RUNNING."""
    _seed_session(tmp, pod_id="pod-1", sid=sid, hours_ago=0.01)
    if outputs is not None:
        statemod.mark(sid, "running", tmp, outputs=outputs)
    pod = {"id": "pod-1", "desiredStatus": status, "costPerHr": 0.72}
    t = _transport({"/pods/pod-1": pod, "/pods": [pod]})
    fake = _FakeSshWithFiles([10, 20, 30])

    def from_pod(pod, **kw):
        if ssh_raises:
            raise sshx.SshError("pod pod-1 has no SSH endpoint yet")
        return fake

    orig_from_pod, orig_sleep = sshx.PodSsh.from_pod, cli.time.sleep
    sshx.PodSsh.from_pod = staticmethod(from_pod)
    cli.time.sleep = lambda s: None
    try:
        code, out, _ = _run_cli(["watch", sid, "--interval", "0"], t, tmp)
    finally:
        sshx.PodSsh.from_pod = orig_from_pod
        cli.time.sleep = orig_sleep
    return code, out, [c for c in t.calls if c[0] == "DELETE"]


def test_watch_fetches_when_the_pod_stops_unexpectedly():
    """The case where the evidence matters most must not be the case with no
    fetch. Before task 030b this path returned without fetching anything."""
    with tempfile.TemporaryDirectory() as tmp:
        code, out, deleted = _watch_with_status(tmp, "EXITED")
        assert "POD IS NO LONGER RUNNING" in out, out
        assert "fetching" in out.lower(), out
        assert deleted, "an unexpectedly stopped pod was not terminated"


def test_watch_still_terminates_when_the_stopped_pod_cannot_be_reached():
    """A stopped pod usually has no SSH endpoint. The fetch fails, is said to
    have failed, and the pod is terminated anyway -- a pod kept alive to retry
    a download is a pod billing while nobody is watching."""
    with tempfile.TemporaryDirectory() as tmp:
        code, out, deleted = _watch_with_status(tmp, "EXITED", sid="stopped2",
                                                ssh_raises=True)
        assert "POD IS NO LONGER RUNNING" in out, out
        assert "fetch failed" in out, out
        assert deleted, "the pod was left alive after a failed fetch"


def test_watch_records_why_an_unexpectedly_stopped_session_ended():
    """`finished_because` separates a stop nobody chose from a cap or a DONE."""
    with tempfile.TemporaryDirectory() as tmp:
        _watch_with_status(tmp, "EXITED", sid="stopped3")
        rec = statemod.load("stopped3", tmp)
        assert rec["state"] == "terminated"
        assert rec.get("finished_because") == "pod_stopped", rec


def test_watch_fetch_order_puts_the_log_first():
    """The run log is declared first so a run that never reached its MANIFEST
    still comes home with its phase timings. _fetch_outputs walks the list in
    order, so order is the guarantee."""
    with tempfile.TemporaryDirectory() as tmp:
        outs = [{"remote": "/workspace/oneground-session.log",
                 "local": "logs/", "extract": False},
                {"remote": "/workspace/big.tgz", "local": "./",
                 "extract": False}]
        code, out, _ = _watch_with_status(tmp, "EXITED", sid="stopped4",
                                          outputs=outs)
        i_log = out.find("oneground-session.log")
        i_tgz = out.find("big.tgz")
        assert i_log != -1 and i_tgz != -1, out
        assert i_log < i_tgz, "the log was not fetched first"


# -- task 030c: one output's failure must not cost the others ---------------

class _FakeSshFlakyProbe(_FakeSshWithFiles):
    """Fails the probe on the first output only, the way a transient ssh
    failure does. Everything after it must still arrive."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.probes = []

    def exists(self, remote):
        self.probes.append(remote)
        if len(self.probes) == 1:
            raise sshx.SshError("ssh -p 22 -> exit 255")
        return True


def _fetch_with(tmp, ssh, outputs, sid="f1"):
    _seed_session(tmp, pod_id="pod-1", sid=sid, hours_ago=0.01)
    statemod.mark(sid, "running", tmp, outputs=outputs)
    rec = statemod.load(sid, tmp)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli._fetch_outputs(ssh, rec, tmp)
    return code, buf.getvalue()


THREE_OUTPUTS = [
    {"remote": "/workspace/oneground-session.log", "local": "logs/",
     "extract": False},
    {"remote": "/workspace/small.tgz", "local": "bundle/", "extract": False},
    {"remote": "/workspace/large.tgz", "local": "asset/", "extract": False},
]


def test_a_failed_probe_on_the_first_output_does_not_skip_the_rest():
    """The 030c failure, and it is 030b's fix one layer down: the run log is
    declared FIRST so a capped run still comes home with its timings, so a
    flaky probe on the log used to cost both tarballs."""
    with tempfile.TemporaryDirectory() as tmp:
        ssh = _FakeSshFlakyProbe([10])
        code, out = _fetch_with(tmp, ssh, THREE_OUTPUTS)
        assert "FAILED" in out, out
        assert "continuing with the remaining outputs" in out, out
        assert ssh.fetched == ["/workspace/small.tgz",
                               "/workspace/large.tgz"], ssh.fetched
        assert code == 1, "a failed output must still be reported in the code"


def test_every_output_is_probed_even_when_an_earlier_one_fails():
    with tempfile.TemporaryDirectory() as tmp:
        ssh = _FakeSshFlakyProbe([10])
        _fetch_with(tmp, ssh, THREE_OUTPUTS, sid="f2")
        assert len(ssh.probes) == 3, ssh.probes


def test_a_missing_output_is_couldnt_check_not_a_transport_failure():
    """The two are kept apart: absent says the run did not get that far,
    failed says we could not look."""
    class _Absent(_FakeSshWithFiles):
        def exists(self, remote):
            return False
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _fetch_with(tmp, _Absent([10]), THREE_OUTPUTS, sid="f3")
        assert "couldn't-check: not present on the pod" in out, out
        assert "FAILED" not in out, out
        assert code == 1


def test_all_outputs_arriving_is_a_clean_exit():
    with tempfile.TemporaryDirectory() as tmp:
        ssh = _FakeSshWithFiles([10])
        code, out = _fetch_with(tmp, ssh, THREE_OUTPUTS, sid="f4")
        assert code == 0, out
        assert "did not arrive" not in out, out
        assert len(ssh.fetched) == 3, ssh.fetched


def test_a_transfer_failure_on_one_output_does_not_cost_the_others():
    """ssh.get used to be guarded, but only against SshError -- an OSError
    from the local disk escaped the loop exactly as the probe did."""
    class _BadGet(_FakeSshWithFiles):
        def get(self, remote, local, timeout=None):
            if remote.endswith("small.tgz"):
                raise OSError(28, "No space left on device")
            return super().get(remote, local, timeout)
    with tempfile.TemporaryDirectory() as tmp:
        ssh = _BadGet([10])
        code, out = _fetch_with(tmp, ssh, THREE_OUTPUTS, sid="f5")
        assert "No space left on device" in out, out
        assert ssh.fetched == ["/workspace/oneground-session.log",
                               "/workspace/large.tgz"], ssh.fetched
        assert code == 1
