"""Every receipt names the command that wrote it (task 046, step 3).

`docs/INTERFACE.md` §2: every UI action is exactly a CLI invocation, and the
receipt records which, so a test can replay the command from a terminal and
compare the outputs. That section also records that nothing captured it, and
this is where that stopped being true.
"""

import json
import os
import subprocess
import sys

import pytest

from oneground import provenance

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _forget():
    """Each test decides what was invoked. A module-level recording that
    leaked between tests would make every one of them pass for whatever the
    previous one set."""
    before = provenance._INVOCATION
    provenance._INVOCATION = None
    yield
    provenance._INVOCATION = before


def test_a_library_caller_has_no_invocation_and_says_why():
    """Null with a reason, not a guess. Reading `sys.argv` here would put
    pytest's command line in the receipt -- plausible, present, and
    reproducing nothing, which is the shape `docs/PRACTICE.md` section 4 is
    about."""
    got = provenance.invocation()
    assert got["command"] is None
    assert "not run from the command line" in got["note"]
    assert "pytest" not in json.dumps(got)


def test_a_recorded_invocation_is_what_follows_the_program_name():
    provenance.record_invocation(["characterize", "requirements.yaml"])
    assert provenance.invocation() == {
        "command": ["characterize", "requirements.yaml"], "note": ""}


def test_the_recorded_command_is_a_copy():
    """A caller mutating its own list afterwards must not rewrite history."""
    args = ["simulate", "runs/x"]
    provenance.record_invocation(args)
    args.append("--oops")
    assert provenance.invocation()["command"] == ["simulate", "runs/x"]


def test_the_cli_records_before_it_dispatches():
    """Not asserted on the source: a real process runs a real command and the
    receipt-shaped answer is read out of it.

    `--help` exits before any work, which is the point -- the recording has
    to happen before dispatch, so a command that refuses still names itself.
    """
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {REPO!r})\n"
        "from oneground import cli, provenance\n"
        "try:\n"
        "    cli.main(['characterize', '--help'])\n"
        "except SystemExit:\n"
        "    pass\n"
        "print(json.dumps(provenance.invocation()))\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=300, cwd=REPO)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["command"] == ["characterize", "--help"], got


def test_argv_zero_is_not_recorded():
    """It is an interpreter path on one machine and a console script on
    another, it names an install rather than the code, and it is not what a
    replay runs. `cli.main` is handed `sys.argv[1:]`, and this pins that the
    recording keeps that shape rather than quietly re-adding a program name.
    """
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {REPO!r})\n"
        "from oneground import cli, provenance\n"
        "sys.argv = ['/some/path/to/oneground.exe', 'simulate', '--help']\n"
        "try:\n"
        "    cli.main()\n"
        "except SystemExit:\n"
        "    pass\n"
        "print(json.dumps(provenance.invocation()))\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=300, cwd=REPO)
    assert r.returncode == 0, r.stderr
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["command"] == ["simulate", "--help"], got
    assert "oneground.exe" not in json.dumps(got)


def test_every_receipt_writer_records_it_beside_the_version():
    """The field goes *beside* `oneground`, not inside it.

    Inside would change a block four writers share and three tests assert the
    shape of, to carry a fact that is not about the version -- and
    `docs/INTERFACE.md` says beside. This asserts the pairing at every site
    rather than at one, because a writer that was forgotten is exactly the
    failure the replay rule cannot tolerate.
    """
    import ast
    sites = 0
    for root, _dirs, files in os.walk(os.path.join(REPO, "oneground")):
        for name in files:
            if not name.endswith(".py") or name.startswith("test_"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            if '"oneground": producing_version()' not in src:
                continue
            tree = ast.parse(src, path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                keys = [k.value for k in node.keys
                        if isinstance(k, ast.Constant)]
                if "oneground" not in keys:
                    continue
                sites += 1
                assert "invocation" in keys, (
                    f"{os.path.relpath(path, REPO)}:{node.lineno} writes the "
                    "oneground block and no invocation beside it")
    assert sites == 14, f"expected 14 writer sites, found {sites}"
