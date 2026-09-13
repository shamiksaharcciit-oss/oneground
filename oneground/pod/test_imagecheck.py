"""The two checks that replaced rebuild-and-compare. Task 017d.

Run #4 failed because CI rebuilt the image and compared digests, which cannot
pass when the build is not byte-reproducible -- and it is not. These tests pin
what replaced it: the locked digest must be pullable, and a change to the
image's build inputs must come with a change to the lock.

The trigger set is derived from the Dockerfile rather than declared, so the
test that matters most here is the one asserting the workflow's `paths:` still
agrees with it. A new COPY source that nobody adds to the workflow would
otherwise escape the check silently.

    python oneground/pod/test_imagecheck.py
    pytest oneground/pod/test_imagecheck.py
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))

from oneground.pod import imagecheck as ic  # noqa: E402

ROOT = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
IMAGE = "ghcr.io/owner/oneground-pod"


# --------------------------------------------------- deriving the input set
def test_the_input_set_is_the_dockerfile_and_what_it_copies():
    df = "FROM base\nRUN true\nCOPY requirements.txt /tmp/requirements.txt\n"
    assert ic.copy_sources(df) == ["requirements.txt"]


def test_a_multi_source_copy_takes_every_source_and_not_the_destination():
    df = "COPY a.txt b.txt /dest/\n"
    assert ic.copy_sources(df) == ["a.txt", "b.txt"]


def test_copy_flags_are_not_mistaken_for_sources():
    df = "COPY --chown=1000:1000 requirements.txt /tmp/r.txt\n"
    assert ic.copy_sources(df) == ["requirements.txt"]


def test_a_copy_from_an_earlier_stage_is_not_a_repo_input():
    """`--from=builder` reads from a build stage, not from the context, so no
    file in the repository can change it."""
    df = "COPY --from=builder /opt/out /opt/out\nCOPY real.txt /r\n"
    assert ic.copy_sources(df) == ["real.txt"]


def test_a_remote_add_is_not_a_repo_input():
    df = "ADD https://example.com/x.tgz /tmp/x.tgz\nADD local.tgz /tmp/\n"
    assert ic.copy_sources(df) == ["local.tgz"]


def test_line_continuations_are_joined_before_parsing():
    df = "COPY \\\n    requirements.txt \\\n    /tmp/requirements.txt\n"
    assert ic.copy_sources(df) == ["requirements.txt"]


def test_commented_out_copies_are_not_inputs():
    df = "# COPY secrets.txt /secrets\nCOPY requirements.txt /tmp/r\n"
    assert ic.copy_sources(df) == ["requirements.txt"]


def test_the_shipped_dockerfile_derives_the_expected_set_real_file():
    """Not synthetic: the Dockerfile this repository actually builds."""
    assert ic.build_inputs(ROOT) == ["docker/pod/Dockerfile",
                                     "requirements.txt"]


def test_a_missing_dockerfile_raises_rather_than_returning_a_short_list():
    """Returning just the Dockerfile path would make co-change pass for the
    wrong reason -- silently, on the check that guards the pin."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            ic.build_inputs(tmp)
        except ic.ImageCheckError as e:
            assert "Dockerfile" in str(e)
            return
    raise AssertionError("a missing Dockerfile produced an input set")


def test_the_lock_is_not_one_of_its_own_build_inputs():
    """It is the build's output. Requiring it to change when it changes would
    be circular."""
    assert "docker/pod/IMAGE.lock" not in ic.build_inputs(ROOT)


def test_the_workflow_paths_match_the_derived_set_real_files():
    """The `paths:` filter is static YAML and cannot derive itself, so this is
    what keeps it honest. A COPY source added to the Dockerfile without being
    added here would never fire the workflow that checks it."""
    import yaml
    with open(os.path.join(ROOT, ic.WORKFLOW), encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    # `on` is parsed as the boolean True by YAML 1.1; accept either spelling.
    triggers = wf.get("on") or wf.get(True)
    derived = set(ic.build_inputs(ROOT))
    # The workflow file itself is a deliberate extra: editing the check should
    # run the check. It is NOT a build input -- it cannot change image bytes --
    # so it is excluded from the co-change trigger set, only from `paths:`.
    allowed = derived | {ic.WORKFLOW.replace(os.sep, "/")}
    for event in ("push", "pull_request"):
        got = set(triggers[event]["paths"])
        assert got == allowed, (event, sorted(got), sorted(allowed))


def test_session_scripts_do_not_fire_the_workflow():
    """Commit 696dd03 touched only run-time session scripts and triggered an
    18-minute build. They are not in the image and cannot change its bytes."""
    import yaml
    with open(os.path.join(ROOT, ic.WORKFLOW), encoding="utf-8") as f:
        wf = yaml.safe_load(f)
    triggers = wf.get("on") or wf.get(True)
    paths = triggers["push"]["paths"]
    assert "docker/pod/**" not in paths, paths
    for p in paths:
        assert not p.startswith("corpora/"), p


# ---------------------------------------------------------- 1. pullability
OCI_UNSUPPORTED = ("unsupported manifest media type and no default available: "
                   "application/vnd.oci.image.manifest.v1+json")


def test_pullable_is_true_when_the_registry_answers():
    calls = []

    def runner(cmd):
        calls.append(cmd)
        return 0, '{"schemaVersion":2}', ""

    ok, detail = ic.pullable(ref=f"{IMAGE}@{DIGEST}", runner=runner)
    assert ok, detail
    assert len(calls) == 1, "a working first inspector should not be retried"
    assert calls[0][:3] == ["docker", "buildx", "imagetools"], calls[0]


def test_an_oci_manifest_an_old_client_cannot_read_falls_through():
    """Measured on Docker 20.10.17: `docker manifest inspect` refuses an OCI
    manifest even for a public image that plainly exists. Our image is built
    by buildx and pushed to GHCR, so it is OCI. Depending on the client's
    manifest-format support would be a false red of exactly the kind this task
    removes -- so the OCI-aware inspector is tried first."""
    seen = []

    def runner(cmd):
        seen.append(cmd)
        if "manifest" in cmd and "buildx" not in cmd:
            return 1, "", OCI_UNSUPPORTED
        return 0, "{}", ""

    ok, detail = ic.pullable(ref=f"{IMAGE}@{DIGEST}", runner=runner)
    assert ok, detail
    assert seen[0][:3] == ["docker", "buildx", "imagetools"], seen[0]


def test_the_older_inspector_is_still_tried_if_buildx_is_absent():
    seen = []

    def runner(cmd):
        seen.append(cmd)
        if "buildx" in cmd:
            return 1, "", "docker: 'buildx' is not a docker command"
        return 0, "{}", ""

    ok, detail = ic.pullable(ref=f"{IMAGE}@{DIGEST}", runner=runner)
    assert ok, detail
    assert len(seen) == 2, seen
    assert seen[1][:3] == ["docker", "manifest", "inspect"], seen[1]


def test_pullable_prints_the_digest_and_every_registry_error():
    def runner(cmd):
        if "buildx" in cmd:
            return 1, "", "unexpected status: 404 Not Found"
        return 1, "", "manifest unknown: manifest unknown"

    ok, detail = ic.pullable(ref=f"{IMAGE}@{DIGEST}", runner=runner)
    assert not ok
    assert DIGEST in detail, detail
    assert "404 Not Found" in detail, detail
    assert "manifest unknown" in detail, detail
    assert "rebuild.sh" in detail, detail


def test_pullable_reads_the_manifest_rather_than_pulling_layers():
    """A pull of this image is gigabytes; reading a manifest is one request.
    The check has to be cheap enough to run on every push."""
    seen = []
    ic.pullable(ref="x@y",
                runner=lambda cmd: (seen.append(cmd), (1, "", "no"))[1])
    for cmd in seen:
        assert "inspect" in cmd, cmd
        assert "pull" not in cmd, cmd


# ------------------------------------------------------------ 2. co-change
INPUTS = ["docker/pod/Dockerfile", "requirements.txt"]


def test_touching_a_build_input_without_the_lock_fails():
    ok, detail = ic.co_change(["docker/pod/Dockerfile"], INPUTS)
    assert not ok
    assert "docker/pod/Dockerfile" in detail
    assert "IMAGE.lock" in detail.replace(os.sep, "/")
    assert "rebuild.sh" in detail


def test_touching_a_build_input_with_the_lock_passes():
    ok, detail = ic.co_change(
        ["docker/pod/Dockerfile", "docker/pod/IMAGE.lock"], INPUTS)
    assert ok, detail


def test_requirements_is_a_build_input_too():
    ok, _ = ic.co_change(["requirements.txt"], INPUTS)
    assert not ok
    ok, _ = ic.co_change(["requirements.txt", "docker/pod/IMAGE.lock"], INPUTS)
    assert ok


def test_a_session_script_change_needs_no_lock_change():
    """The 696dd03 shape: it should not even have fired the workflow, and if
    it does it must not demand a re-lock."""
    ok, detail = ic.co_change(
        ["corpora/run_verify_pod.sh", "corpora/restart_engine.sh"], INPUTS)
    assert ok, detail
    assert "does not need to move" in detail


def test_relocking_without_touching_the_recipe_is_allowed():
    """A rebuild against an unchanged Dockerfile produces a new, equally valid
    digest -- which is exactly what run #4 demonstrated. The rule is
    one-directional on purpose."""
    ok, detail = ic.co_change(["docker/pod/IMAGE.lock"], INPUTS)
    assert ok, detail


def test_the_failure_names_every_touched_input():
    ok, detail = ic.co_change(
        ["docker/pod/Dockerfile", "requirements.txt", "README.md"], INPUTS)
    assert not ok
    assert "docker/pod/Dockerfile" in detail and "requirements.txt" in detail
    assert "README.md" not in detail


def test_windows_separators_do_not_defeat_the_comparison():
    ok, _ = ic.co_change(["docker\\pod\\Dockerfile"], INPUTS)
    assert not ok, "a backslash path slipped past the input match"


# --------------------------------------- the range, over a real git repo
def _git(repo, *args):
    subprocess.run(["git", "-C", repo] + list(args), check=True,
                   capture_output=True, text=True)


def _fake_repo(tmp):
    """A real repository with a real history, so the range logic is exercised
    against git rather than against a mock of it."""
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@example.com")
    _git(tmp, "config", "user.name", "t")
    os.makedirs(os.path.join(tmp, "docker", "pod"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "corpora"), exist_ok=True)
    for path, body in (("docker/pod/Dockerfile",
                        "FROM base\nCOPY requirements.txt /tmp/r\n"),
                       ("requirements.txt", "numpy==2.5.3\n"),
                       ("docker/pod/IMAGE.lock", f"digest={DIGEST}\n"),
                       ("corpora/run_verify_pod.sh", "echo hi\n")):
        with open(os.path.join(tmp, path), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write(body)
    _git(tmp, "add", "-A")
    _git(tmp, "commit", "-qm", "base")
    return subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def _commit(tmp, path, body, msg):
    full = os.path.join(tmp, path)
    with open(full, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    _git(tmp, "add", "-A")
    _git(tmp, "commit", "-qm", msg)
    return subprocess.run(["git", "-C", tmp, "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def test_a_real_range_touching_the_dockerfile_alone_fails():
    with tempfile.TemporaryDirectory() as tmp:
        base = _fake_repo(tmp)
        head = _commit(tmp, "docker/pod/Dockerfile",
                       "FROM base\nRUN apt-get update\nCOPY requirements.txt /tmp/r\n",
                       "change the recipe")
        changed = ic.changed_files(base, head, root=tmp)
        assert changed == ["docker/pod/Dockerfile"], changed
        ok, detail = ic.co_change(changed, ic.build_inputs(tmp))
        assert not ok, detail


def test_a_real_range_with_the_lock_alongside_passes():
    with tempfile.TemporaryDirectory() as tmp:
        base = _fake_repo(tmp)
        _commit(tmp, "docker/pod/Dockerfile",
                "FROM base\nRUN apt-get update\nCOPY requirements.txt /tmp/r\n",
                "change the recipe")
        head = _commit(tmp, "docker/pod/IMAGE.lock", f"digest={OTHER}\n",
                       "re-lock")
        changed = ic.changed_files(base, head, root=tmp)
        ok, detail = ic.co_change(changed, ic.build_inputs(tmp))
        assert ok, detail


def test_a_real_range_touching_only_a_session_script_passes():
    with tempfile.TemporaryDirectory() as tmp:
        base = _fake_repo(tmp)
        head = _commit(tmp, "corpora/run_verify_pod.sh", "echo bye\n",
                       "696dd03 shape")
        changed = ic.changed_files(base, head, root=tmp)
        assert changed == ["corpora/run_verify_pod.sh"], changed
        ok, detail = ic.co_change(changed, ic.build_inputs(tmp))
        assert ok, detail


def test_an_unknown_base_raises_rather_than_reporting_no_changes():
    """A shallow clone or a force-push can hide the base. Reporting an empty
    diff would pass the check for the worst possible reason."""
    with tempfile.TemporaryDirectory() as tmp:
        head = _fake_repo(tmp)
        try:
            ic.changed_files("0" * 40, head, root=tmp)
        except ic.ImageCheckError as e:
            assert "could not diff" in str(e)
            return
    raise AssertionError("an unknown base was treated as an empty range")


# ------------------------------------------------------------- re-locking
def test_relock_rewrites_the_values_and_keeps_every_comment():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "IMAGE.lock")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("# why a digest and not a tag\n"
                    "# a long explanation nobody wants regenerated\n"
                    f"image={IMAGE}\n"
                    f"digest={DIGEST}\n"
                    "tag=6641737\n"
                    f"reference={IMAGE}@{DIGEST}\n"
                    "fallback_image=runpod/pytorch:1.1.0\n")
        changed = ic.write_lock_digest(IMAGE, OTHER, tag="abc1234", path=path)
        with open(path, encoding="utf-8") as f:
            after = f.read()

        assert "# why a digest and not a tag" in after
        assert "# a long explanation nobody wants regenerated" in after
        assert f"digest={OTHER}" in after
        assert f"reference={IMAGE}@{OTHER}" in after
        assert "tag=abc1234" in after
        # Untouched keys survive.
        assert "fallback_image=runpod/pytorch:1.1.0" in after
        assert {c[0] for c in changed} == {"digest", "reference", "tag"}


def test_relock_is_a_no_op_when_the_digest_already_matches():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "IMAGE.lock")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"image={IMAGE}\ndigest={DIGEST}\n"
                    f"reference={IMAGE}@{DIGEST}\n")
        assert ic.write_lock_digest(IMAGE, DIGEST, path=path) == []


def test_relock_refuses_something_that_is_not_a_sha256():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "IMAGE.lock")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(f"image={IMAGE}\ndigest={DIGEST}\n"
                    f"reference={IMAGE}@{DIGEST}\n")
        try:
            ic.write_lock_digest(IMAGE, "latest", path=path)
        except ic.ImageCheckError as e:
            assert "sha256" in str(e)
            return
    raise AssertionError("a tag was accepted as a digest")


def test_relock_refuses_a_lock_that_has_no_keys_to_update():
    """It edits in place to preserve the prose, so the keys have to exist."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "IMAGE.lock")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("# nothing but comments\n")
        try:
            ic.write_lock_digest(IMAGE, OTHER, path=path)
        except ic.ImageCheckError as e:
            assert "no image" in str(e) or "digest" in str(e)
            return
    raise AssertionError("an empty lock was silently rewritten")


# ----------------------------------------------- the committed lock, for real
def test_the_committed_lock_is_pullable_in_shape_real_file():
    """Not a network call: that the committed lock still resolves to a
    reference the check can ask about."""
    from oneground.pod import image as podimage
    assert podimage.is_baked(ROOT)
    ref = podimage.reference(ROOT)
    assert ref.startswith("ghcr.io/")
    assert "@sha256:" in ref


def _main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print("ok    %s" % name)
        except Exception as e:
            failed += 1
            print("FAIL  %s: %s: %s" % (name, type(e).__name__, e))
    print("\n%d passed, %d failed" % (len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
