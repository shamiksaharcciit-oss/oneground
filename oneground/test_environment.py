"""The pinned-environment guard.

**Synthetic throughout** — the running interpreter is never asserted about,
because these tests have to pass in a pinned venv and in a contributor's
unpinned checkout alike. Versions are injected.

The property under test: a command that writes a canonical artifact cannot
produce one outside the pins without the artifact saying so.

    .venv/Scripts/python.exe oneground/test_environment.py
    .venv/Scripts/python.exe oneground/test_environment.py --list
    .venv/Scripts/python.exe -m pytest oneground/test_environment.py

Both runners collect the same tests, and `test_script_mode_collects_every_
test_pytest_does` is what says so.
"""

import ast
import io
import os
import sys
import tempfile

# The not-a-checkout branches use it -- from a GitHub archive zip, or any tree
# without .git, both identifier-scan tests raised NameError here instead of
# skipping (task 022) -- and so does the script runner below, which has to
# report a skip rather than stop on it (task 022e).
import pytest

sys.path.insert(0, os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))

from oneground import environment as env                 # noqa: E402

PINNED_TXT = "numpy==2.5.3\nfaiss-cpu==1.15.0\nscikit-learn==1.9.0\n"


def _reqs(tmp, text=PINNED_TXT):
    p = os.path.join(tmp, "requirements.txt")
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return p


# --------------------------------------------------------------- reading
def test_pins_are_read_and_markers_stripped_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        p = _reqs(tmp, '# comment\nnumpy==2.5.3\n'
                       'pywin32==312; sys_platform == "win32"\n'
                       'unpinned-thing\n\n')
        pins = env.read_requirements_pins(p)
        assert pins["numpy"] == "2.5.3"
        assert pins["pywin32"] == "312", "an environment marker broke the pin"
        assert "unpinned-thing" not in pins


def test_underscores_and_hyphens_are_the_same_project_synthetic():
    """pip freeze prints `pydantic_core`; requirements.txt pins
    `pydantic-core`. Comparing raw strings reports an installed package as
    absent, which is how task 013's first freeze comparison went wrong."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _reqs(tmp, "pydantic-core==2.46.5\n")
        assert env.read_requirements_pins(p)["pydantic-core"] == "2.46.5"
    assert env._normalise("pydantic_core") == env._normalise("pydantic-core")


def test_a_missing_requirements_file_pins_nothing_synthetic():
    assert env.read_requirements_pins(os.path.join("no", "such.txt")) == {}


# ------------------------------------------------------------ comparing
def test_a_matching_environment_has_no_mismatches_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        p = _reqs(tmp)
        assert env.running_pin_mismatches(p, versions={
            "numpy": "2.5.3", "faiss-cpu": "1.15.0",
            "scikit-learn": "1.9.0"}) == []


def test_each_differing_pin_is_reported_with_both_versions_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        p = _reqs(tmp)
        bad = env.running_pin_mismatches(p, versions={
            "numpy": "2.2.6", "faiss-cpu": "1.14.3",
            "scikit-learn": "1.9.0"})
        assert ("numpy", "2.2.6", "2.5.3") in bad, bad
        assert ("faiss-cpu", "1.14.3", "1.15.0") in bad, bad
        assert len(bad) == 2, bad


def test_only_packages_that_can_move_a_number_are_checked_synthetic():
    """A guard that fires on things which cannot matter gets routed around."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _reqs(tmp, PINNED_TXT + "pyyaml==6.0.3\n")
        assert env.running_pin_mismatches(p, versions={
            "numpy": "2.5.3", "faiss-cpu": "1.15.0",
            "scikit-learn": "1.9.0", "pyyaml": "5.0.0"}) == []
    assert "pyyaml" not in env.PINNED


def test_a_package_absent_from_either_side_is_not_a_mismatch_synthetic():
    """A contributor without faiss installed has not failed a pin check; they
    have a different problem, and the import error says so."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _reqs(tmp)
        assert env.running_pin_mismatches(p, versions={"numpy": "2.5.3"}) == []


# --------------------------------------------------------------- guarding
class _Log:
    def __init__(self):
        self.lines = []

    def __call__(self, msg=""):
        self.lines.append(str(msg))

    @property
    def text(self):
        return "\n".join(self.lines)


def test_the_interpreter_is_printed_whatever_the_outcome_synthetic():
    """The line that would have made task 013's mistake visible on sight."""
    with tempfile.TemporaryDirectory() as tmp:
        log = _Log()
        env.guard("cmd", _reqs(tmp, "pyyaml==6.0.3\n"), log=log)
        assert sys.executable in log.text, log.text


def test_an_unpinned_environment_refuses_rather_than_warns_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        p = _reqs(tmp, "numpy==0.0.1\n")     # nothing can be running this
        log = _Log()
        try:
            env.guard("oneground report", p, log=log)
        except env.UnpinnedEnvironment as e:
            assert "report" in str(e)
        else:
            raise AssertionError("an unpinned environment was allowed")
        assert "REFUSED" in log.text, log.text
        assert "--allow-unpinned" in log.text, log.text
        # The refusal has to say what to type next.
        assert ("python.exe" in log.text or "bin/python" in log.text
                or "pip install" in log.text), log.text


def test_guard_or_exit_returns_a_code_not_a_traceback_synthetic():
    """Being stopped by a guard is not a crash."""
    with tempfile.TemporaryDirectory() as tmp:
        stamp, code = env.guard_or_exit(
            "cmd", _reqs(tmp, "numpy==0.0.1\n"), log=_Log())
        assert stamp is None and code == 2


def test_allow_unpinned_proceeds_and_says_so_loudly_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        log = _Log()
        stamp, code = env.guard_or_exit(
            "cmd", _reqs(tmp, "numpy==0.0.1\n"), allow_unpinned=True, log=log)
        assert code == 0
        assert stamp is not None and stamp["pinned"] is False
        assert "WARNING" in log.text and "--allow-unpinned" in log.text
        assert env.UNPINNED_NOTE in log.text


# ---------------------------------------------------------------- stamping
def test_the_stamp_records_the_environment_and_the_verdict_synthetic():
    """What a reader of a published artifact needs, and nothing that
    identifies the machine that produced it."""
    with tempfile.TemporaryDirectory() as tmp:
        s = env.stamp(_reqs(tmp, "pyyaml==6.0.3\n"))
        assert s["environment_id"] == env.environment_id()
        assert s["python_version"].startswith("3.")
        assert s["in_venv"] == env.in_venv()
        assert s["pinned"] is True
        assert "mismatches" not in s, s


def test_an_unpinned_stamp_carries_the_note_and_every_mismatch_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        s = env.stamp(_reqs(tmp, "numpy==0.0.1\n"), allowed_unpinned=True)
        assert s["pinned"] is False
        assert s["note"] == env.UNPINNED_NOTE
        assert s["allowed_by"] == "--allow-unpinned"
        assert s["mismatches"][0]["pinned"] == "0.0.1"
        assert s["mismatches"][0]["package"] == "numpy"


def test_a_stamp_made_without_the_flag_does_not_claim_one_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        s = env.stamp(_reqs(tmp, "numpy==0.0.1\n"))
        assert s["pinned"] is False
        assert s["allowed_by"] is None


# -------------------------------------------------- every command is guarded
def _surface():
    """Every command the CLI can dispatch, derived from its own parsers."""
    from oneground import cli
    return cli.dispatchable_commands()


# The commands that guard inside their own handler rather than by decoration:
# they register on first use, so a test that has not run them cannot discover
# them. Named here with the exact strings their handlers use, which is what
# `test_every_declared_guard_string_is_real` checks.
GUARDS_ON_USE = {
    "oneground fixture verify", "oneground fixture build",
    # `project` writes a manifested artifact, so it is guarded exactly as
    # `build` is -- the same `guard_or_exit` call, which now takes the action
    # name. It exists because task 016g split the projection out of the
    # builder so the receipts can be packaged before UMAP runs.
    "oneground fixture project",
    "oneground calibrate fixture", "oneground calibrate layers",
    "oneground calibrate curve", "oneground calibrate engine",
    # `propose translate` has its own parser, dispatched before the shared
    # one ever sees it, the same reason `fixture verify`/`fixture build`
    # are here rather than decorated.
    "oneground propose translate",
    # `bridge export` writes real files (train/test/neighbors.parquet,
    # the card); guarded manually, the same reason `fixture build` is.
    "oneground bridge export",
}


def test_every_dispatchable_command_is_guarded_or_deliberately_not():
    """Not synthetic: walks the shipped command surface.

    Task 013b asserted coverage against a hand-written list of six names, so a
    seventh command added without a guard would have passed -- the same defect
    the guard exists to prevent, one level up. This walks the parsers instead,
    so a new subcommand appears here whether or not anyone remembers it.
    """
    from oneground import cli, environment as env
    guarded = set(env.GUARDED_COMMANDS) | GUARDS_ON_USE
    unaccounted = sorted(_surface() - guarded - set(cli.UNGUARDED))
    assert not unaccounted, (
        "these commands are neither guarded nor listed in cli.UNGUARDED with "
        "a reason: " + ", ".join(unaccounted))


def test_the_four_top_level_commands_are_guarded_by_decoration():
    from oneground import cli, environment as env
    for handler in (cli._cmd_characterize, cli._cmd_simulate,
                    cli._cmd_verify, cli._cmd_report):
        assert env.is_guarded(handler), handler.__name__


def test_every_declared_guard_string_is_real():
    """`GUARDS_ON_USE` names commands that exist and appear in the source.

    Without this the set could drift into naming commands nobody guards, and
    the coverage test would pass by asserting about fiction.
    """
    surface = _surface()
    for name in GUARDS_ON_USE:
        assert name in surface, f"{name} is not a dispatchable command"
    here = os.path.dirname(os.path.abspath(__file__))
    sources = "".join(
        open(os.path.join(here, *parts), encoding="utf-8").read()
        for parts in (("fixture", "verify.py"), ("cli.py",),
                      ("calibrate", "__init__.py")))
    for name in ("oneground fixture verify", "oneground fixture build"):
        assert name in sources, name
    # calibrate builds its guard string from the action, so the set it uses
    # is what proves the four.
    from oneground import calibrate
    assert set(calibrate.WRITES_ARTIFACTS) == {
        "fixture", "layers", "curve", "engine"}, calibrate.WRITES_ARTIFACTS


def test_every_unguarded_command_carries_a_reason():
    """Being on the list is a decision, and a decision has a reason."""
    from oneground import cli
    for name, reason in cli.UNGUARDED.items():
        assert name in _surface(), f"{name} is not a dispatchable command"
        assert len(reason) > 30, (name, reason)


def test_a_new_command_cannot_slip_through_synthetic():
    """The property that makes this self-extending: an unaccounted command
    fails the check without anyone editing a list."""
    from oneground import cli
    surface = _surface() | {"oneground brand-new-thing"}
    unaccounted = sorted(surface - set() - set(cli.UNGUARDED))
    assert "oneground brand-new-thing" in unaccounted


def test_the_guarded_commands_offer_the_escape_hatch():
    """A guard with no way past it is a guard people work around."""
    from oneground import cli

    def flags(parser):
        return {o for a in parser._actions
                for o in getattr(a, "option_strings", ())}

    top = cli.build_parser()._actions[-1].choices
    for name in ("characterize", "simulate", "verify", "report"):
        assert "--allow-unpinned" in flags(top[name]), name
    fx = cli._fixture_parser()._actions[-1].choices
    for name in ("verify", "build"):
        assert "--allow-unpinned" in flags(fx[name]), name


def test_the_fixture_verify_parser_is_defined_once():
    """`oneground fixture verify` and `python -m oneground.fixture.verify`
    used to parse different flags. Both now build from the same function."""
    from oneground import cli
    from oneground.fixture import verify as fv

    def flags(parser):
        return {o for a in parser._actions
                for o in getattr(a, "option_strings", ())}

    through_cli = flags(cli._fixture_parser()._actions[-1].choices["verify"])
    direct = flags(
        fv.build_parser()._actions[-1].choices["fixture"]
        ._actions[-1].choices["verify"])
    assert through_cli == direct, through_cli ^ direct
    for expected in ("--assets-dir", "--verbose", "--strict",
                     "--allow-unpinned", "--fixtures-dir", "--requirements"):
        assert expected in through_cli, expected


# --------------------------------------- the package guard (task 020b)
def _checkout(root, git_file=False):
    """A minimal oneground checkout: a `.git` and a `oneground/` package."""
    os.makedirs(os.path.join(root, "oneground"), exist_ok=True)
    open(os.path.join(root, "oneground", "__init__.py"), "w").close()
    if git_file:
        # what `git worktree add` leaves: a file pointing at the shared repo
        with open(os.path.join(root, ".git"), "w", encoding="utf-8") as f:
            f.write("gitdir: /elsewhere/.git/worktrees/x\n")
    else:
        os.makedirs(os.path.join(root, ".git"), exist_ok=True)
    return root


def test_a_checkout_running_its_own_package_passes_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        tree = _checkout(tmp)
        sub = os.path.join(tree, "runs", "deep")
        os.makedirs(sub)
        own = os.path.join(tree, "oneground")
        assert env.package_tree_mismatch(cwd=tree, package=own) is None
        # from a subdirectory the tree is still the tree
        assert env.package_tree_mismatch(cwd=sub, package=own) is None


def test_a_checkout_running_another_trees_package_is_found_synthetic():
    with tempfile.TemporaryDirectory() as a, \
            tempfile.TemporaryDirectory() as b:
        here, other = _checkout(a), _checkout(b)
        bad = env.package_tree_mismatch(
            cwd=here, package=os.path.join(other, "oneground"))
        assert bad is not None
        tree, own, imported = bad
        assert env._same_path(tree, here)
        assert env._same_path(own, os.path.join(here, "oneground"))
        assert env._same_path(imported, os.path.join(other, "oneground"))


def test_a_git_worktree_is_a_working_tree_synthetic():
    """`git worktree add` leaves `.git` as a file. Task 020 was in one."""
    with tempfile.TemporaryDirectory() as a, \
            tempfile.TemporaryDirectory() as b:
        here, other = _checkout(a, git_file=True), _checkout(b)
        assert env._same_path(env.working_tree_root(here), here)
        assert env.package_tree_mismatch(
            cwd=here, package=os.path.join(other, "oneground")) is not None


def test_a_copy_installed_inside_the_tree_is_still_foreign_synthetic():
    """Under the tree is not the tree's package: a venv in the checkout holds
    an installed, possibly stale copy, which is the thing being stopped."""
    with tempfile.TemporaryDirectory() as tmp:
        tree = _checkout(tmp)
        installed = os.path.join(tree, ".venv", "Lib", "site-packages",
                                 "oneground")
        os.makedirs(installed)
        assert env.package_tree_mismatch(cwd=tree,
                                         package=installed) is not None


def test_outside_a_oneground_checkout_nothing_is_judged_synthetic():
    """A user's own project, with oneground pip-installed, is not refused:
    there is no second copy of the package there to confuse it with."""
    with tempfile.TemporaryDirectory() as proj, \
            tempfile.TemporaryDirectory() as other:
        os.makedirs(os.path.join(proj, ".git"))          # their repository
        elsewhere = os.path.join(_checkout(other), "oneground")
        assert env.package_tree_mismatch(cwd=proj, package=elsewhere) is None


def test_a_foreign_package_is_refused_with_both_paths_synthetic():
    with tempfile.TemporaryDirectory() as a, \
            tempfile.TemporaryDirectory() as b:
        here, other = _checkout(a), _checkout(b)
        foreign = os.path.join(other, "oneground")
        log = _Log()
        stamp, code = env.guard_or_exit(
            "oneground simulate", _reqs(a, "pyyaml==6.0.3\n"), log=log,
            cwd=here, package=foreign)
        assert stamp is None and code == 2
        assert "REFUSED" in log.text, log.text
        assert os.path.join(here, "oneground") in log.text, log.text
        assert foreign in log.text, log.text
        assert "-m oneground.cli" in log.text, "the refusal must say what to do"


def test_allow_unpinned_does_not_wave_a_foreign_package_through_synthetic():
    """That flag is about library versions; it says nothing about which
    source tree is running."""
    with tempfile.TemporaryDirectory() as a, \
            tempfile.TemporaryDirectory() as b:
        here, other = _checkout(a), _checkout(b)
        log = _Log()
        stamp, code = env.guard_or_exit(
            "oneground simulate", _reqs(a, "numpy==0.0.1\n"),
            allow_unpinned=True, log=log, cwd=here,
            package=os.path.join(other, "oneground"))
        assert stamp is None and code == 2, (code, log.text)
        assert "REFUSED" in log.text and "WARNING" not in log.text, log.text


def test_the_package_is_printed_whatever_the_outcome_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        log = _Log()
        env.guard("cmd", _reqs(tmp, "pyyaml==6.0.3\n"), log=log, cwd=tmp)
        assert env.package_dir() in log.text, log.text


def test_a_guarded_command_run_from_another_checkout_refuses():
    """Not synthetic: a real process, a real guarded command.

    It imports THIS checkout's package while standing in a different
    oneground checkout -- the editable-install situation, inverted so it can
    be staged without touching any real second tree. `oneground simulate`
    must stop before reading its requirements file, exit 2, name both
    packages, and write nothing.
    """
    import subprocess

    repo = os.path.normpath(os.path.join(os.path.dirname(
        os.path.abspath(__file__)), ".."))
    with tempfile.TemporaryDirectory() as tmp:
        other = _checkout(tmp)
        code = ("import sys; sys.path.insert(0, %r); "
                "from oneground.cli import main; "
                "sys.exit(main(['simulate', 'requirements.yaml']))" % repo)
        r = subprocess.run([sys.executable, "-c", code], cwd=other,
                           capture_output=True, text=True, timeout=600)
        out = r.stdout + r.stderr
        assert r.returncode == 2, (r.returncode, out)
        assert "REFUSED" in out, out
        assert os.path.join(repo, "oneground") in out, out
        assert os.path.basename(tmp) in out, out
        assert sorted(os.listdir(other)) == [".git", "oneground"], \
            os.listdir(other)


def test_this_test_run_imports_the_package_of_the_checkout_it_tests():
    """Not synthetic: the guard's question, asked of the test run itself.

    Whichever module imports `oneground` first decides, for the whole
    process, which tree is under test. If that was another checkout's copy,
    every result in this run describes code nobody changed -- worse than a
    wrong number, because nothing looks wrong. This file is collected by path
    from the checkout being tested, so the package it sees must be that
    checkout's.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    bad = env.package_tree_mismatch(cwd=here)
    assert bad is None, (
        "this test run imported another tree's oneground package:\n"
        "  tests collected from  %s\n  package imported      %s"
        % (bad[1], bad[2]))


# ---------------------------------- no machine identifiers (task 014)
def test_a_local_environment_id_is_os_and_arch_never_a_hostname():
    """`local:<hostname>` reached calibration/history.jsonl, a file every
    report cites. A hostname identifies a person's machine; the OS and
    architecture identify whether two measurements are comparable, which is
    what the id is for."""
    import platform
    eid = env.local_environment_id()
    assert eid.startswith("local:"), eid
    assert eid == f"local:{platform.system().lower()}-{platform.machine().lower()}"
    node = platform.node()
    if node:
        assert node.lower() not in eid.lower(), eid


def test_a_pod_id_wins_over_the_local_id():
    """A pod id names a rented machine that no longer exists. It stays."""
    old = os.environ.get("ONEGROUND_ENVIRONMENT_ID")
    os.environ["ONEGROUND_ENVIRONMENT_ID"] = "tf8sd2usxbblsm"
    try:
        assert env.environment_id() == "tf8sd2usxbblsm"
    finally:
        if old is None:
            os.environ.pop("ONEGROUND_ENVIRONMENT_ID", None)
        else:
            os.environ["ONEGROUND_ENVIRONMENT_ID"] = old


def _machine_identifiers():
    """Every string that would identify this machine or its owner."""
    import platform
    out = set()
    for value in (platform.node(), os.environ.get("COMPUTERNAME"),
                  os.environ.get("HOSTNAME"), os.environ.get("USERNAME"),
                  os.environ.get("USER"),
                  os.path.basename(os.path.expanduser("~"))):
        if value and len(str(value)) > 2:
            out.add(str(value).lower())
    return out


def test_a_stamp_never_carries_a_machine_identifier():
    """The property, asserted against everything that could identify this box.

    Covers the hostname and, just as importantly, the absolute interpreter and
    prefix paths -- those run through a home directory, they are generated at
    run time so no redaction pass can reach them, and they answer no question
    a reader of a published artifact has.
    """
    import json
    blob = json.dumps(env.stamp()).lower()
    for ident in _machine_identifiers():
        assert ident not in blob, (ident, blob)
    assert "executable" not in env.stamp()
    assert "prefix" not in env.stamp()


def test_a_stamp_records_the_requirements_file_by_name_not_by_path():
    with tempfile.TemporaryDirectory() as tmp:
        s = env.stamp(_reqs(tmp))
        assert s["requirements"] == "requirements.txt", s["requirements"]
        assert os.sep not in str(s["requirements"])


def test_the_calibration_history_writes_no_hostname():
    """The file every report cites."""
    import json
    from oneground.calibrate import history as H
    blob = json.dumps({"environment": H.environment_id()}).lower()
    for ident in _machine_identifiers():
        assert ident not in blob, (ident, blob)


def test_no_module_reaches_for_platform_node_for_an_identifier():
    """A regression guard on the source itself.

    Three modules each grew their own `platform.node()` call; a fourth would
    be just as easy to add and just as invisible. `local_environment_id` is
    the one place allowed to look at the platform at all.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    offenders = []
    for root, _dirs, files in os.walk(here):
        if "test" in os.path.basename(root):
            continue
        for name in files:
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            path = os.path.join(root, name)
            if os.path.basename(path) == "environment.py":
                continue          # the one place that may
            # The AST, not the text. Two modules carry prose saying "not
            # platform.node(), and here is why" -- in a comment in one and a
            # docstring in the other -- and a guard that punishes the
            # explanation for a rule teaches people to delete the
            # explanation. Only an actual call counts.
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "node"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "platform"):
                    offenders.append(os.path.relpath(path, here))
                    break
    assert not offenders, (
        "these modules call platform.node(); use "
        "oneground.environment.environment_id() instead: " + ", ".join(offenders))


# ------------------------------- the tracked tree, scanned (task 017 item 4)
# 014's guards all assert on what is about to be written. This is the other
# side: what is already committed. 015 found the gap by grepping after a
# rebase; 016 then published two absolute developer paths in
# tasks/016-decision-log.txt without anything noticing.

def test_no_tracked_file_carries_a_machine_identifier():
    """The guard 015 found missing, against the tree as it stands."""
    if env.checkout_root() is None:
        pytest.skip("not a git checkout; nothing to scan")
    # A checkout with no runnable git raises `GitUnavailable` here rather than
    # skipping: the scan cannot say the tree is clean without reading it.
    findings = env.identifier_findings()
    assert findings is not None, "a checkout, and the scan read nothing"
    assert findings == [], "\n".join(
        "%s:%s  %s\n    %s" % f for f in findings)


def test_the_scan_actually_reads_the_tree():
    """A scan that silently checked nothing would pass the test above.

    `identifier_findings` returning `[]` is only meaningful if it looked at
    something, so pin the floor rather than trusting the empty list.
    """
    if env.checkout_root() is None:
        pytest.skip("not a git checkout; nothing to scan")
    paths = env.tracked_files()
    assert paths is not None, "a checkout, and git listed nothing"
    assert len(paths) > 100, len(paths)
    assert "oneground/environment.py" in [p.replace("\\", "/") for p in paths]


# ------------------------------- git present, git runnable: not the same thing
# Task 022e. Both tests above skipped on `tracked_files() is None`, which meant
# "no .git" and "git could not be run" alike -- so on a checkout whose git is
# missing or broken the identifier scan reported green having read nothing,
# which is the one outcome it exists to prevent. The empty PATH below is how a
# stripped container, a cron job, or a hook environment reaches that state.

class _empty_path:
    """Run a block with nothing on PATH, so launching `git` fails."""

    def __enter__(self):
        self._old = os.environ.get("PATH")
        os.environ["PATH"] = ""
        return self

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = self._old
        return False


def test_a_tree_with_no_git_is_not_a_checkout_synthetic():
    """The skip that stays a skip: nothing to scan, and nothing claimed."""
    with tempfile.TemporaryDirectory() as tmp:
        assert env.checkout_root(tmp) is None
        assert env.tracked_files(tmp) is None
        assert env.identifier_findings(root=tmp) is None


def test_a_checkout_whose_git_cannot_run_is_an_error_synthetic():
    """The distinction: `.git` is there, git is not. That is a failure."""
    with tempfile.TemporaryDirectory() as tmp:
        os.mkdir(os.path.join(tmp, ".git"))
        assert env.checkout_root(tmp) == os.path.abspath(tmp)
        with _empty_path():
            for call in (lambda: env.tracked_files(tmp),
                         lambda: env.identifier_findings(root=tmp)):
                try:
                    got = call()
                except env.GitUnavailable as e:
                    # It names the command tried and the error.
                    assert "git ls-files" in str(e), e
                    assert ("FileNotFoundError" in str(e)
                            or "exit " in str(e)), e
                else:
                    raise AssertionError(
                        "no git, and the scan answered %r" % (got,))


def test_a_git_that_answers_from_a_subdirectory_is_still_a_checkout_synthetic():
    """`checkout_root` walks up, so a test run from `oneground/` does not
    mistake its own directory for a tree with no `.git`."""
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, ".git"))
        deep = os.path.join(tmp, "a", "b")
        os.makedirs(deep)
        assert env.checkout_root(deep) == os.path.abspath(tmp)


def test_the_tree_tests_fail_rather_than_skip_when_git_cannot_run():
    """Not synthetic: calls the two tree tests above with an empty PATH.

    Asserting on `tracked_files` alone would leave the tests free to go on
    skipping. This runs them.
    """
    if env.checkout_root() is None:
        pytest.skip("not a git checkout; nothing to scan")
    with _empty_path():
        for fn in (test_no_tracked_file_carries_a_machine_identifier,
                   test_the_scan_actually_reads_the_tree):
            try:
                fn()
            except env.GitUnavailable as e:
                assert "git ls-files" in str(e), e
            except BaseException as e:         # a skip is BaseException
                raise AssertionError(
                    "%s neither passed nor failed on a checkout with no git: "
                    "%s: %s" % (fn.__name__, type(e).__name__, e))
            else:
                raise AssertionError(
                    "%s passed with nothing scanned" % fn.__name__)


def test_the_scan_catches_an_injected_path_and_hostname():
    """The acceptance criterion: it fails on an injected path.

    Asserted against a string rather than by writing into the checkout, so the
    test cannot leave a developer path behind if it fails half way.
    """
    idents = {"someuser"}
    for probe, why in (
            (r"TARBALL=C:\Users\someuser\projects\x", "windows path"),
            ("path: C:/Users/someuser/projects/x", "windows path, posix slashes"),
            ("cd /home/someuser/work", "linux home"),
            ("cd /Users/someuser/work", "macos home"),
            ("environment: local:DESKTOP-7QX2L4N", "hostname"),
            ("ran as someuser on the box", "bare identifier"),
    ):
        hits = env.scan_text(probe, identifiers=idents)
        assert len(hits) == 1, (why, probe, hits)


def test_the_scan_leaves_the_redacted_forms_alone():
    r"""A guard that flagged `C:\Users\<developer>` would teach people to
    stop redacting, which is the opposite of what 014 established."""
    idents = {"someuser"}
    for probe in (r"C:\Users\<developer>\projects\x",
                  "C:/Users/<name>/oneground-assets",
                  "C:/Users/.../runs",
                  "%USERNAME%",
                  "$HOME/work",
                  "~/oneground-assets",
                  "/home/runner/work/oneground",      # every CI job
                  "/root/pgdata",
                  "local:windows-amd64"):
        assert env.scan_text(probe, identifiers=idents) == [], probe


def test_a_generic_account_name_is_not_an_identifier():
    """`runner` is every GitHub Actions job and an English word besides."""
    assert "runner" not in env.machine_identifiers()
    assert "root" not in env.machine_identifiers()


# --------------------------------------------------- inside archives (022b)
# The stackexchange-150k release tarball carried the packing machine's user
# name and uid/gid in every header. The tree scan skipped archives by suffix
# and the asset is not tracked, so nothing saw it. Synthetic identifiers only.

def _tgz(path, members, gzip_name="", **owner):
    """A .tgz of `members` ({name: bytes}), every header given `owner`.

    The gzip member is written by hand (RFC 1952) so FNAME holds `gzip_name`
    verbatim: `gzip.GzipFile` keeps only a basename, which would make a stored
    path impossible to test.
    """
    import struct
    import tarfile
    import zlib
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            for k, v in owner.items():
                setattr(info, k, v)
            t.addfile(info, io.BytesIO(data))
    tar = buf.getvalue()
    flags = 8 if gzip_name else 0
    head = struct.pack("<BBBBIBB", 0x1F, 0x8B, 8, flags, 0, 0, 255)
    if gzip_name:
        head += gzip_name.encode("latin-1") + b"\0"
    deflate = zlib.compressobj(9, zlib.DEFLATED, -15)
    body = deflate.compress(tar) + deflate.flush()
    tail = struct.pack("<II", zlib.crc32(tar) & 0xFFFFFFFF,
                       len(tar) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(head + body + tail)
    return path


def test_an_archive_with_a_named_owner_is_caught_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        p = _tgz(os.path.join(tmp, "a.tgz"), {"fixtures/x/vectors.npy": b"\0" * 64},
                 uid=197609, gid=197609, uname="someuser", gname="")
        kinds = {kind for _m, kind, _d in
                 env.archive_findings(p, identifiers={"someuser"})}
        assert kinds == {"owner id", "owner name"}, kinds


def test_a_numeric_owner_archive_is_clean_synthetic():
    """What `--owner=0 --group=0 --numeric-owner` writes: 0/0, no names."""
    with tempfile.TemporaryDirectory() as tmp:
        p = _tgz(os.path.join(tmp, "a.tgz"), {"fixtures/x/vectors.npy": b"\0" * 64,
                                              "fixtures/x/notes.txt": b"hello\n"},
                 uid=0, gid=0, uname="", gname="")
        assert env.archive_findings(p, identifiers={"someuser"}) == []
        # `root` names nobody, and is what many archivers write for uid 0.
        p = _tgz(os.path.join(tmp, "b.tgz"), {"fixtures/x/q.npy": b"\0"},
                 uid=0, gid=0, uname="root", gname="root")
        assert env.archive_findings(p, identifiers={"someuser"}) == []


def test_a_path_in_the_gzip_header_or_a_text_member_is_caught_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        p = _tgz(os.path.join(tmp, "a.tgz"), {"fixtures/x/q.npy": b"\0"},
                 gzip_name=r"C:\Users\someuser\build\x.tar")
        hits = env.archive_findings(p, identifiers={"someuser"})
        assert [d for _m, _k, d in hits if d.startswith("gzip FNAME")], hits
        p = _tgz(os.path.join(tmp, "b.tgz"),
                 {"logs/build.log": b"ok\nwrote /home/someuser/out\n"})
        hits = env.archive_findings(p, identifiers={"someuser"})
        assert [m for m, _k, _d in hits] == ["logs/build.log:2"], hits


def test_an_unreadable_archive_is_reported_not_passed_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "broken.tgz")
        with open(p, "wb") as f:
            f.write(b"\x1f\x8bnot really gzip")
        hits = env.archive_findings(p, identifiers={"someuser"})
        assert hits and hits[0][1] == "unreadable archive, not checked", hits


def test_the_asset_scan_says_none_when_there_is_nothing_to_scan_synthetic():
    with tempfile.TemporaryDirectory() as tmp:
        assert env.asset_archive_findings(
            [os.path.join(tmp, "absent")], identifiers={"someuser"}) is None
        _tgz(os.path.join(tmp, "a.tgz"), {"x": b"\0"}, uid=1000, uname="someuser")
        found = env.asset_archive_findings([tmp], identifiers={"someuser"})
        assert {k for _p, _m, k, _d in found} == {"owner id", "owner name"}


def _git_or_skip(*args):
    """Run a git command for a synthetic checkout, or skip saying why.

    Task 022e: these calls were `check=True` with nothing around them, so on a
    machine with no git the test ended in a bare FileNotFoundError traceback.
    Git that cannot be launched at all means this test's fixture cannot be
    built -- a skip, named. Git that runs and fails is a real failure.
    """
    import subprocess
    cmd = ["git"] + list(args)
    # The temporary directory is under a home directory on this platform, so
    # the command is named with it redacted: a skip reason gets pasted into
    # reports, and task 016 published two developer paths that way.
    tmproot = os.path.abspath(tempfile.gettempdir())
    shown = " ".join("<tmp>" if os.path.abspath(a).startswith(tmproot) else a
                     for a in cmd)
    try:
        r = subprocess.run(cmd, capture_output=True)
    except OSError as e:
        pytest.skip("git could not be run (%s): %s: %s"
                    % (shown, type(e).__name__, e))
    assert r.returncode == 0, "%s: exit %s: %s" % (
        shown, r.returncode, r.stderr.decode("utf-8", "replace").strip())


def test_the_tracked_scan_opens_tracked_archives_synthetic():
    """`smoke-small.tgz` is tracked; the walk used to skip every .tgz."""
    with tempfile.TemporaryDirectory() as tmp:
        _tgz(os.path.join(tmp, "small.tgz"), {"x.json": b"{}"},
             uid=1000, uname="someuser")
        _git_or_skip("init", "-q", tmp)
        _git_or_skip("-C", tmp, "add", "small.tgz")
        found = env.identifier_findings(root=tmp, allowlist={})
        assert {(p, k) for p, _n, k, _d in found} == {
            ("small.tgz!x.json", "owner id"),
            ("small.tgz!x.json", "owner name")}, found


def test_no_release_asset_archive_carries_owner_metadata():
    """Not synthetic: every archive in the asset directory on this machine.

    The release tarballs are uploaded from here. An archive whose headers name
    the account that packed it publishes that name with the release.
    """
    found = env.asset_archive_findings()
    if found is None:
        pytest.skip("no asset directory on this machine (looked for "
                    + ", ".join(env.DEFAULT_ASSET_DIRS) + ")")
    assert found == [], "\n".join("%s!%s  %s  %s" % f for f in found)


# ------------------------------------------- the script runner (task 022f)
# `_main` and its `__main__` block sat between the parser tests and the
# task-014 section, so running this file as a script collected the 21 tests
# defined above it, never reached the identifier scan, and printed "21 passed"
# with nothing saying 22 were missing. The same defect 022e fixed, one level
# up: a green that covered what it had not looked at. The block is last in the
# file now, and the test below is what keeps it there.

def test_script_mode_collects_every_test_pytest_does():
    """Not synthetic: collects this file both ways and compares the lists."""
    import subprocess
    here = os.path.abspath(__file__)
    root = os.path.dirname(os.path.dirname(here))

    def run(*cmd):
        r = subprocess.run([sys.executable] + list(cmd), cwd=root,
                           capture_output=True, timeout=300)
        out = r.stdout.decode("utf-8", "replace")
        assert r.returncode == 0, "%s: exit %s\n%s%s" % (
            " ".join(cmd), r.returncode, out,
            r.stderr.decode("utf-8", "replace"))
        return out

    # `--list` collects and prints; it runs no test, so this cannot recurse
    # into itself. The collection is the same code a full script run uses.
    script = set(run(here, "--list").split())
    lines = run("-m", "pytest", "--collect-only", "-q",
                "-p", "no:cacheprovider", here).splitlines()
    under_pytest = {ln.split("::", 1)[1].strip() for ln in lines if "::" in ln}
    assert script == under_pytest, (
        "script mode and pytest disagree about what this file contains; "
        "only one of them saw: " + ", ".join(sorted(script ^ under_pytest)))
    assert len(script) > 40, len(script)


def _collect():
    """Every test in this module, in name order, as the runner sees it.

    Reads `globals()`, so it sees only what has been defined by the time it is
    called -- which is why the `__main__` block below has to stay last.
    """
    return [(n, o) for n, o in sorted(globals().items())
            if n.startswith("test_") and callable(o)]


def _main(argv=()):
    tests = _collect()
    if "--list" in argv:
        for name, _fn in tests:
            print(name)
        return 0
    failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        # A skip is not an Exception, so without this branch the script mode
        # stopped on the first one with a traceback (task 022e).
        except pytest.skip.Exception as e:
            skipped += 1
            print(f"skip  {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed - skipped} passed, {failed} failed, "
          f"{skipped} skipped (of {len(tests)} collected)")
    return 1 if failed else 0


# Nothing may be defined below this line: `_collect` would not see it, and the
# script runner would report a green over a file it had only half read.
if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
