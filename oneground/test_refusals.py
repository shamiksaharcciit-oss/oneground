"""A refusal is produced where it is raised, once (task 046).

`tasks/finding-refusals-arrive-as-tracebacks.md` measured the defect: the
project's own refusal type escaped `cli.main` as a traceback, so the
commonest refusal in the product was met as a crash by every command-line
user. These tests are the fix, and the fence around the classification the
supervisor reads.
"""

import json
import os
import subprocess
import sys

import pytest

from oneground import jobs, refusals

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(*args):
    """A real process, because the defect was in what a process returns."""
    code = (f"import sys; sys.path.insert(0, {REPO!r});"
            " from oneground.cli import main; sys.exit(main())")
    r = subprocess.run([sys.executable, "-c", code, *args],
                       capture_output=True, text=True, timeout=300, cwd=REPO)
    return r.returncode, (r.stdout + r.stderr)


# --------------------------------------------- the defect, and the fix
def test_a_missing_requirements_file_is_a_refusal_not_a_traceback():
    """The measured case. It exited 1 with a stack trace and the carefully
    written sentence on the last line; it now exits 2 with the sentence and
    nothing else."""
    code, out = _run("characterize", "nope.yaml")
    assert code == refusals.REFUSED_EXIT == 2, out
    assert "Traceback (most recent call last)" not in out
    assert "requirements file not found: nope.yaml" in out
    assert "oneground characterize: refused." in out


def test_the_refusal_is_one_line():
    """Verbatim and unadorned. `docs/INTERFACE.md` §4.4 has the UI show this
    string, so anything wrapped around it is something the UI would show."""
    _code, out = _run("characterize", "nope.yaml")
    lines = [ln for ln in out.splitlines() if "refused." in ln]
    assert len(lines) == 1, out
    assert lines[0].endswith("requirements file not found: nope.yaml")


def test_a_genuine_failure_keeps_its_traceback():
    """The half that makes the fix safe. A crash presented as a refusal
    would tell the user the tool meant it, which is worse than a traceback.
    """
    code = (f"import sys; sys.path.insert(0, {REPO!r});"
            " from oneground import cli;"
            " cli._dispatch = lambda argv: (_ for _ in ()).throw("
            "RuntimeError('a real bug')); sys.exit(cli.main(['simulate']))")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, timeout=300, cwd=REPO)
    assert r.returncode == 1
    assert "Traceback (most recent call last)" in r.stderr
    assert "RuntimeError: a real bug" in r.stderr
    assert "refused" not in r.stderr


# ---------------------------------------------------- the declaration
def test_every_declared_refusal_carries_a_reason():
    for name, why in refusals.REFUSALS.items():
        assert name.startswith("oneground."), name
        assert why and len(why) > 25, name


def test_the_exclusions_are_named_with_their_reason():
    """An exception wrongly called a refusal would hide a defect. The ones
    left out say why, so the next reader does not have to re-decide."""
    assert "oneground.embed.EmbedError" in refusals.NOT_REFUSALS
    assert "OR the model failed" in \
        refusals.NOT_REFUSALS["oneground.embed.EmbedError"]
    for name, why in refusals.NOT_REFUSALS.items():
        assert why and len(why) > 25, name
    assert not set(refusals.REFUSALS) & set(refusals.NOT_REFUSALS)


def test_a_declared_type_actually_exists_and_is_an_exception():
    """A name in the table that no longer resolves would silently stop
    matching, and every refusal of that kind would go back to being a
    traceback with nothing to report it."""
    import importlib
    for name in list(refusals.REFUSALS) + list(refusals.NOT_REFUSALS):
        module, _, cls = name.rpartition(".")
        mod = importlib.import_module(module)
        obj = getattr(mod, cls, None)
        assert obj is not None, f"{name} does not resolve"
        assert isinstance(obj, type) and issubclass(obj, BaseException), name


def test_matching_is_exact_on_the_type():
    from oneground.intake import RequirementsError

    class Subclass(RequirementsError):
        pass

    assert refusals.is_refusal(RequirementsError("x"))
    assert not refusals.is_refusal(Subclass("x")), (
        "a subclass inherits the class, not the reason in the table")
    assert not refusals.is_refusal(ValueError("x"))


# ------------------------------------- the exit-code mapping, as data
def test_the_mapping_declares_a_reason_for_every_code():
    for code, (state, why) in jobs.EXIT_MEANING.items():
        assert why and len(why) > 20, code
        assert state in (None, "done", "refused"), code


def test_exit_zero_is_done_and_exit_two_is_refused(tmp_path):
    assert jobs.classify("simulate", 0, str(tmp_path))[0] == "done"
    assert jobs.classify("simulate", 2, str(tmp_path))[0] == "refused"


# The row where one code means two things. Tested hardest, because the
# workdir is the only thing that separates them and a wrong answer here
# renders a crash as a finished run or a finished run as a crash.
@pytest.mark.parametrize("stage,receipt", [
    ("characterize", "characterization.json"),
    ("simulate", "simulate.json"),
    ("verify", "verify.json"),
    ("report", "report.json"),
    ("propose", "proposals"),
])
def test_exit_one_with_the_receipt_is_done(tmp_path, stage, receipt):
    """The run happened and dropped something; the drops are in the receipt.
    Calling this `failed` would throw away a run that produced results."""
    d = str(tmp_path)
    target = os.path.join(d, receipt)
    if "." in receipt:
        with open(target, "w", encoding="utf-8") as f:
            json.dump({}, f)
    else:
        os.makedirs(target)
    state, why = jobs.classify(stage, 1, d)
    assert state == "done", why
    assert receipt in why


@pytest.mark.parametrize("stage", ["characterize", "simulate", "verify",
                                   "report", "propose"])
def test_exit_one_without_the_receipt_is_failed(tmp_path, stage):
    """Nothing was produced, so the run did not happen. Calling this `done`
    would put a crash in the list as complete."""
    state, why = jobs.classify(stage, 1, str(tmp_path))
    assert state == "failed", why
    assert "no " in why


def test_exit_one_is_the_only_code_the_workdir_decides():
    """If a second code ever needs the workdir, this test says so before the
    classifier quietly grows a second branch."""
    undecided = [c for c, (s, _) in jobs.EXIT_MEANING.items() if s is None]
    assert undecided == [1]


def test_the_workdir_actually_decides_it(tmp_path):
    """The mutant for the row: the same stage and the same exit code, and
    only the receipt differs. Without this, `classify` could ignore the
    workdir entirely and every test above would still pass."""
    d = str(tmp_path)
    before, _ = jobs.classify("simulate", 1, d)
    with open(os.path.join(d, "simulate.json"), "w", encoding="utf-8") as f:
        f.write("{}")
    after, _ = jobs.classify("simulate", 1, d)
    assert (before, after) == ("failed", "done")


def test_a_stage_with_no_receipt_of_its_own_says_so_rather_than_guessing(
        tmp_path):
    state, why = jobs.classify("pod status", 1, str(tmp_path))
    assert state == "failed"
    assert "writes no receipt of its own" in why


def test_an_unexpected_code_is_failed_and_says_it_was_unexpected(tmp_path):
    state, why = jobs.classify("simulate", 137, str(tmp_path))
    assert state == "failed"
    assert "137" in why and "deliberately" in why


def test_every_stage_has_a_receipt_entry():
    """A stage added without one would fall to the no-receipt branch and be
    called failed on every drop, which is a wrong answer rather than a
    missing one."""
    assert set(jobs.STAGE_RECEIPT) == set(jobs.STAGES)
