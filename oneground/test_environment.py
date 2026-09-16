"""The pinned-environment guard.

**Synthetic throughout** — the running interpreter is never asserted about,
because these tests have to pass in a pinned venv and in a contributor's
unpinned checkout alike. Versions are injected.

The property under test: a command that writes a canonical artifact cannot
produce one outside the pins without the artifact saying so.

    .venv/Scripts/python.exe oneground/test_environment.py
    .venv/Scripts/python.exe -m pytest oneground/test_environment.py
"""

import ast
import io
import os
import sys
import tempfile

# Only the not-a-checkout branch uses it, which a git checkout never reaches:
# from a GitHub archive zip, or any tree without .git, both identifier-scan
# tests raised NameError here instead of skipping (task 022).
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


def _main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"ok    {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed} passed, {failed} failed "
          f"(of {len(tests)} collected)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())


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
    findings = env.identifier_findings()
    if findings is None:
        pytest.skip("not a git checkout; nothing to scan")
    assert findings == [], "\n".join(
        "%s:%s  %s\n    %s" % f for f in findings)


def test_the_scan_actually_reads_the_tree():
    """A scan that silently checked nothing would pass the test above.

    `identifier_findings` returning `[]` is only meaningful if it looked at
    something, so pin the floor rather than trusting the empty list.
    """
    paths = env.tracked_files()
    if paths is None:
        pytest.skip("not a git checkout; nothing to scan")
    assert len(paths) > 100, len(paths)
    assert "oneground/environment.py" in [p.replace("\\", "/") for p in paths]


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


def test_the_tracked_scan_opens_tracked_archives_synthetic():
    """`smoke-small.tgz` is tracked; the walk used to skip every .tgz."""
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        _tgz(os.path.join(tmp, "small.tgz"), {"x.json": b"{}"},
             uid=1000, uname="someuser")
        subprocess.run(["git", "init", "-q", tmp], check=True)
        subprocess.run(["git", "-C", tmp, "add", "small.tgz"], check=True)
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
