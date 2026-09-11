"""`push-calibration.sh` against a stubbed remote.

**Not synthetic where it counts**: the remote is a real bare git repository and
the script is the one that ships. Only the contents are invented.

Calibration run #3 failed with

    ! [rejected]  calibration -> calibration (non-fast-forward)

because the action started the branch from the wrong commit when
`origin/calibration` was not a configured remote-tracking ref -- which is the
normal state on a tag push. The first two tests are the branch-absent and
branch-exists paths the brief asks for; the third is the case the retry exists
for.

    .venv/Scripts/python.exe -m pytest .github/scripts/test_push_calibration.py
"""

import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "push-calibration.sh")


def _bash():
    for c in (os.path.join("C:" + os.sep, "Program Files", "Git", "bin",
                           "bash.exe"), "/bin/bash", "/usr/bin/bash"):
        if os.path.exists(c):
            return c
    return shutil.which("bash")


def _git(cwd, *args, check=True):
    p = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {p.stderr or p.stdout}")
    return p.stdout.strip()


def _line(n, scope="advisory"):
    return json.dumps({"check": "glove_curve", "outcome": "contradicted",
                       "outcome_scope": scope, "date": "2026-09-11",
                       "n": n}, sort_keys=True)


@pytest.fixture
def world(tmp_path):
    """A bare remote with `main`, and a work clone. No calibration branch."""
    bash = _bash()
    if not bash:
        pytest.skip("no POSIX shell available")

    remote = str(tmp_path / "remote.git")
    work = str(tmp_path / "work")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote],
                   check=True, capture_output=True)

    seed = str(tmp_path / "seed")
    os.makedirs(os.path.join(seed, "calibration"))
    subprocess.run(["git", "init", "-q", "-b", "main", seed], check=True,
                   capture_output=True)
    _git(seed, "config", "user.email", "t@example.invalid")
    _git(seed, "config", "user.name", "t")
    with open(os.path.join(seed, "calibration", "history.jsonl"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(_line(0, scope="blocking") + "\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "seed")
    _git(seed, "remote", "add", "origin", remote)
    _git(seed, "push", "-q", "origin", "main")

    subprocess.run(["git", "clone", "-q", remote, work], check=True,
                   capture_output=True)
    _git(work, "config", "user.email", "t@example.invalid")
    _git(work, "config", "user.name", "t")
    return bash, remote, work


def _append(work, lines):
    """Simulate a calibration run appending to the working copy, and capture
    those lines the way the action's `what changed` step does."""
    hp = os.path.join(work, "calibration", "history.jsonl")
    with open(hp, "a", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line + "\n")
    np_ = os.path.join(work, "new.jsonl")
    with open(np_, "w", encoding="utf-8", newline="\n") as f:
        for line in lines:
            f.write(line + "\n")
    return "calibration/history.jsonl", "new.jsonl"


def _run(bash, work, hist, new, msg="calibration: test", **env):
    e = dict(os.environ)
    e.update({"REMOTE": "origin", "BASE_BRANCH": "main"})
    e.update({k: str(v) for k, v in env.items()})
    return subprocess.run(
        [bash, SCRIPT, "calibration", hist, new, msg],
        cwd=work, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=e, timeout=300)


def _remote_history(remote, tmp_path, branch="calibration"):
    out = str(tmp_path / f"peek-{branch}")
    subprocess.run(["git", "clone", "-q", "-b", branch, remote, out],
                   check=True, capture_output=True)
    with open(os.path.join(out, "calibration", "history.jsonl"),
              encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


# ------------------------------------------------------- branch absent
def test_the_branch_is_created_from_main_when_it_does_not_exist(world, tmp_path):
    bash, remote, work = world
    hist, new = _append(work, [_line(1), _line(2)])
    p = _run(bash, work, hist, new)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "branch created" in p.stdout, p.stdout

    lines = _remote_history(remote, tmp_path)
    assert len(lines) == 3, lines           # main's seed line plus two
    assert _line(1) in lines and _line(2) in lines


# ------------------------------------------------------- branch exists
def test_an_existing_branch_is_extended_not_replaced(world, tmp_path):
    bash, remote, work = world
    hist, new = _append(work, [_line(1)])
    assert _run(bash, work, hist, new).returncode == 0

    # A second run, from a fresh clone, as a later CI job would be.
    work2 = str(tmp_path / "work2")
    subprocess.run(["git", "clone", "-q", remote, work2], check=True,
                   capture_output=True)
    _git(work2, "config", "user.email", "t@example.invalid")
    _git(work2, "config", "user.name", "t")
    hist2, new2 = _append(work2, [_line(2)])
    p = _run(bash, work2, hist2, new2)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "branch existing" in p.stdout, p.stdout

    lines = _remote_history(remote, tmp_path)
    assert _line(1) in lines, "the earlier run's line was lost"
    assert _line(2) in lines


def test_a_tag_checkout_with_no_tracking_ref_still_finds_the_branch(world, tmp_path):
    """The exact condition that broke run #3.

    On a tag push the checkout action configures no `refs/remotes/origin/*`
    refspec, so `origin/calibration` does not exist locally even though the
    branch is on the remote. The old code's fallback then started the branch
    from the tag commit and the push could only be rejected.
    """
    bash, remote, work = world
    hist, new = _append(work, [_line(1)])
    assert _run(bash, work, hist, new).returncode == 0

    work2 = str(tmp_path / "work3")
    subprocess.run(["git", "clone", "-q", remote, work2], check=True,
                   capture_output=True)
    _git(work2, "config", "user.email", "t@example.invalid")
    _git(work2, "config", "user.name", "t")
    # Strip every remote-tracking ref and the fetch refspec, which is what a
    # tag checkout leaves behind.
    for ref in _git(work2, "for-each-ref", "--format=%(refname)",
                    "refs/remotes").splitlines():
        _git(work2, "update-ref", "-d", ref.strip())
    _git(work2, "config", "--unset-all", "remote.origin.fetch", check=False)
    assert "origin/calibration" not in _git(work2, "branch", "-r")

    hist2, new2 = _append(work2, [_line(2)])
    p = _run(bash, work2, hist2, new2)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "branch existing" in p.stdout, p.stdout
    lines = _remote_history(remote, tmp_path)
    assert _line(1) in lines and _line(2) in lines


# ------------------------------------------------------------- concurrency
def test_a_tip_that_moves_underneath_is_retried_not_forced(world, tmp_path):
    """Two runs append at once. Neither may lose the other's lines."""
    bash, remote, work = world
    hist, new = _append(work, [_line(1)])
    assert _run(bash, work, hist, new).returncode == 0

    # Run A prepares its lines from the current tip ...
    workA = str(tmp_path / "A")
    subprocess.run(["git", "clone", "-q", remote, workA], check=True,
                   capture_output=True)
    _git(workA, "config", "user.email", "a@example.invalid")
    _git(workA, "config", "user.name", "a")
    histA, newA = _append(workA, [_line("A")])

    # ... and run B pushes first, moving the tip underneath A.
    workB = str(tmp_path / "B")
    subprocess.run(["git", "clone", "-q", remote, workB], check=True,
                   capture_output=True)
    _git(workB, "config", "user.email", "b@example.invalid")
    _git(workB, "config", "user.name", "b")
    histB, newB = _append(workB, [_line("B")])
    assert _run(bash, workB, histB, newB, "calibration: B").returncode == 0

    p = _run(bash, workA, histA, newA, "calibration: A")
    assert p.returncode == 0, p.stdout + p.stderr

    lines = _remote_history(remote, tmp_path)
    assert _line("A") in lines, "A's line was lost"
    assert _line("B") in lines, "B's line was overwritten -- a force push?"
    assert _line(1) in lines


def test_the_script_never_force_pushes():
    """A force here would delete exactly the concurrent lines the retry
    exists to preserve."""
    src = open(SCRIPT, encoding="utf-8").read()
    code = [l for l in src.splitlines() if not l.lstrip().startswith("#")]
    joined = "\n".join(code)
    for forbidden in ("--force", "-f ", "+refs/heads/calibration:refs/heads/"):
        assert forbidden not in joined, forbidden


def test_a_remote_that_always_rejects_fails_after_the_bound(world, tmp_path):
    """A wedged remote must fail, not spin.

    The remote rejects every push via a `pre-receive` hook, so the retry can
    never succeed. The script must give up after PUSH_ATTEMPTS and exit
    non-zero -- an unbounded loop would hold a CI runner until its timeout,
    and an exit 0 would report a calibration line as recorded when it is not.
    """
    bash, remote, work = world
    hook = os.path.join(remote, "hooks", "pre-receive")
    with open(hook, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\necho 'wedged' >&2\nexit 1\n")
    os.chmod(hook, 0o755)

    hist, new = _append(work, [_line(1)])
    p = _run(bash, work, hist, new, PUSH_ATTEMPTS=2)
    assert p.returncode == 1, p.stdout + p.stderr
    assert p.stdout.count("attempt 1/2") == 1, p.stdout
    assert p.stdout.count("attempt 2/2") == 1, p.stdout
    assert "attempt 3/2" not in p.stdout
    assert "could not push calibration after 2 attempt(s)" in p.stdout


def test_a_failed_push_leaves_no_commit_behind(world, tmp_path):
    """Between attempts the script drops its own commit.

    If it did not, attempt 2 would stack a second commit of the same lines on
    top of attempt 1's, and attempt 3 a third -- so a run that eventually
    succeeded would push the same measurement three times. The reset runs
    after the last attempt too, so a wedged run leaves the checkout as it
    found it rather than a local branch carrying a commit that was never
    recorded anywhere.
    """
    bash, remote, work = world
    hook = os.path.join(remote, "hooks", "pre-receive")
    with open(hook, "w", encoding="utf-8", newline="\n") as f:
        f.write("#!/bin/sh\nexit 1\n")
    os.chmod(hook, 0o755)

    hist, new = _append(work, [_line(1)])
    _run(bash, work, hist, new, PUSH_ATTEMPTS=3)
    log = _git(work, "log", "--format=%s", "-n", "5")
    # One commit per attempt would leave three.
    assert log.count("calibration: test") == 0, log
    assert log.splitlines()[0] == "seed", log


def test_nothing_to_push_is_not_a_failure(world, tmp_path):
    bash, remote, work = world
    empty = os.path.join(work, "empty.jsonl")
    open(empty, "w").close()
    p = _run(bash, work, "calibration/history.jsonl", "empty.jsonl")
    assert p.returncode == 0, p.stdout + p.stderr
    assert "nothing to push" in p.stdout


def test_a_line_already_on_the_branch_is_not_duplicated(world, tmp_path):
    bash, remote, work = world
    hist, new = _append(work, [_line(1)])
    assert _run(bash, work, hist, new).returncode == 0

    work2 = str(tmp_path / "again")
    subprocess.run(["git", "clone", "-q", remote, work2], check=True,
                   capture_output=True)
    _git(work2, "config", "user.email", "t@example.invalid")
    _git(work2, "config", "user.name", "t")
    hist2, new2 = _append(work2, [_line(1)])       # the same line again
    p = _run(bash, work2, hist2, new2)
    assert p.returncode == 0, p.stdout + p.stderr
    lines = _remote_history(remote, tmp_path)
    assert lines.count(_line(1)) == 1, lines


# --------------------------------------------------------------- shallow
def _shallow_clone(remote, dest):
    subprocess.run(["git", "clone", "-q", "--depth", "1",
                    "file://" + remote.replace(os.sep, "/"), dest],
                   check=True, capture_output=True)
    _git(dest, "config", "user.email", "t@example.invalid")
    _git(dest, "config", "user.name", "t")
    assert _git(dest, "rev-parse", "--is-shallow-repository") == "true"
    return dest


def test_a_shallow_checkout_can_create_the_branch(world, tmp_path):
    """`actions/checkout@v4` defaults to `fetch-depth: 1`.

    A push from a shallow clone can be refused when the pushed history is
    incomplete relative to the remote. Here it is not: our commit's parent is
    a tip the remote already has, so only the new commit goes over.
    """
    bash, remote, work = world
    sh = _shallow_clone(remote, str(tmp_path / "shallow1"))
    hist, new = _append(sh, [_line(1)])
    p = _run(bash, sh, hist, new)
    assert p.returncode == 0, p.stdout + p.stderr
    assert _line(1) in _remote_history(remote, tmp_path)


def test_a_shallow_tag_checkout_extends_an_existing_branch(world, tmp_path):
    """The full run #3 condition: shallow, and no remote-tracking refs."""
    bash, remote, work = world
    hist, new = _append(work, [_line(1)])
    assert _run(bash, work, hist, new).returncode == 0

    sh = _shallow_clone(remote, str(tmp_path / "shallow2"))
    for ref in _git(sh, "for-each-ref", "--format=%(refname)",
                    "refs/remotes").splitlines():
        _git(sh, "update-ref", "-d", ref.strip())
    _git(sh, "config", "--unset-all", "remote.origin.fetch", check=False)

    hist2, new2 = _append(sh, [_line(2)])
    p = _run(bash, sh, hist2, new2)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "branch existing" in p.stdout, p.stdout
    lines = _remote_history(remote, tmp_path)
    assert _line(1) in lines and _line(2) in lines


# ---------------------------------------------------- the action wires it up
ACTION = os.path.join(HERE, "..", "actions", "record-calibration", "action.yml")
WORKFLOW = os.path.join(HERE, "..", "workflows", "calibration.yml")


def _action():
    return open(ACTION, encoding="utf-8").read()


def test_the_action_calls_the_script_rather_than_inlining_git():
    a = _action()
    assert "push-calibration.sh" in a
    # The inline version is what failed run #3, and it could not be tested
    # while it lived in a YAML block.
    assert 'git fetch origin "$BRANCH" || true' not in a
    assert 'git checkout -B "$BRANCH" "origin/$BRANCH"' not in a


def test_the_action_judges_the_lines_it_captured():
    a = _action()
    assert "--lines" in a
    # Comments are allowed to name the flag they explain the absence of.
    code = "\n".join(l for l in a.splitlines()
                     if not l.lstrip().startswith("#"))
    assert "--appended" not in code, \
        "a tail slice of the merged history can judge a concurrent run's line"


def test_the_action_refuses_a_history_that_lost_lines():
    assert "append-only" in _action()


def test_the_script_is_executable_in_the_index():
    """The action invokes it directly, so mode 100644 is a runner failure."""
    p = subprocess.run(["git", "ls-files", "-s",
                        ".github/scripts/push-calibration.sh"],
                       cwd=os.path.join(HERE, "..", ".."),
                       capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        pytest.skip("not a git checkout")
    assert p.stdout.split()[0] == "100755", p.stdout


def test_a_green_run_can_be_produced_on_demand():
    """`workflow_dispatch`, so the fix can be proven before the schedule."""
    assert "workflow_dispatch:" in open(WORKFLOW, encoding="utf-8").read()


# ------------------------------------------------- run #5: the branch's tree
def test_the_scripts_survive_a_push_to_a_branch_whose_tree_lacks_them(tmp_path):
    """Calibration run #5, reproduced and then prevented.

        .github/scripts/merge_history.py: No such file or directory

    `merge_history.py` was in the commit the job checked out. The push step
    then checked out `calibration` -- rooted at 0.1.0-preview, three commits
    before the scripts existed -- into the same working tree, which *deleted*
    them, and invoked one of them by path on the next line. The action's
    `find contradictions` step, one step later, would have died the same way
    on `count_contradictions.py`.

    Everything the existing tests do runs the script from the real repo, whose
    path no checkout inside `tmp_path` can disturb, so none of them could see
    this. Here the script runs from *inside* the clone it is operating on,
    which is what CI does.
    """
    bash = _bash()
    if not bash:
        pytest.skip("no POSIX shell available")

    remote = str(tmp_path / "remote.git")
    seed = str(tmp_path / "seed")
    work = str(tmp_path / "work")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote],
                   check=True, capture_output=True)

    # Commit A: the era the calibration branch was cut in. No scripts.
    os.makedirs(os.path.join(seed, "calibration"))
    subprocess.run(["git", "init", "-q", "-b", "main", seed], check=True,
                   capture_output=True)
    _git(seed, "config", "user.email", "t@example.invalid")
    _git(seed, "config", "user.name", "t")
    with open(os.path.join(seed, "calibration", "history.jsonl"), "w",
              encoding="utf-8", newline="\n") as f:
        f.write(_line(0, scope="blocking") + "\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "0.1.0-preview")
    _git(seed, "remote", "add", "origin", remote)
    _git(seed, "push", "-q", "origin", "main")
    _git(seed, "push", "-q", "origin", "main:calibration")   # run #1 cut it here

    # Commit B: the scripts land on main, and only on main.
    scripts = os.path.join(seed, ".github", "scripts")
    os.makedirs(scripts, exist_ok=True)
    for name in ("push-calibration.sh", "merge_history.py",
                 "count_contradictions.py"):
        shutil.copy(os.path.join(HERE, name), os.path.join(scripts, name))
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "task 014c")
    _git(seed, "push", "-q", "origin", "main")

    subprocess.run(["git", "clone", "-q", remote, work], check=True,
                   capture_output=True)
    _git(work, "config", "user.email", "t@example.invalid")
    _git(work, "config", "user.name", "t")

    assert _git(work, "ls-tree", "-r", "--name-only",
                "origin/calibration") == "calibration/history.jsonl", \
        "the fixture must reproduce a calibration branch with no scripts"

    hist, new = _append(work, [_line(1)])
    e = dict(os.environ, REMOTE="origin", BASE_BRANCH="main")
    p = subprocess.run(
        [bash, ".github/scripts/push-calibration.sh", "calibration", hist,
         new, "calibration(pins): 1 line(s)"],
        cwd=work, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=e, timeout=300)

    assert p.returncode == 0, p.stdout + p.stderr
    assert "No such file or directory" not in (p.stdout + p.stderr)

    # The scripts the next steps run must still be on disk.
    for name in ("merge_history.py", "count_contradictions.py",
                 "push-calibration.sh"):
        assert os.path.exists(os.path.join(work, ".github", "scripts", name)), \
            f"{name} was removed from the working tree by the push step"

    assert _line(1) in _remote_history(remote, tmp_path)


def test_the_push_leaves_the_checkout_exactly_as_it_found_it(world, tmp_path):
    """The job has steps after this one, and they read the tree they started
    with. A push that succeeds must not move HEAD, the branch, or the index."""
    bash, remote, work = world
    before_head = _git(work, "rev-parse", "HEAD")
    before_branch = _git(work, "rev-parse", "--abbrev-ref", "HEAD")

    hist, new = _append(work, [_line(1)])
    p = _run(bash, work, hist, new)
    assert p.returncode == 0, p.stdout + p.stderr

    assert _git(work, "rev-parse", "HEAD") == before_head
    assert _git(work, "rev-parse", "--abbrev-ref", "HEAD") == before_branch
    assert _git(work, "branch", "--list", "calibration") == "", \
        "a local calibration branch was created in the job's checkout"
    # The run's own appended lines are still in the working copy, untouched.
    with open(os.path.join(work, "calibration", "history.jsonl"),
              encoding="utf-8") as f:
        assert _line(1) in [l.strip() for l in f]
